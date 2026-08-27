// The X11 half of the Win32 code in input.cc. Same jobs, different primitives.
#include "input_x11.h"

#include <X11/XKBlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <X11/extensions/XTest.h>

#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cstring>
#include <mutex>
#include <vector>

namespace dito {
namespace {

// Written by the hook thread (key down) and read by the main thread (paste).
std::atomic<unsigned long> g_target{0};

// Xlib is not thread safe on one connection: input ops get their own, guarded.
std::mutex g_display_mutex;
Display* g_display = nullptr;

// Slow enough that GTK and VTE keep up; measured against xdotool's own 12 ms default.
constexpr useconds_t kTypeDelayUs = 4000;

Display* InputDisplay() {
  if (g_display == nullptr) g_display = XOpenDisplay(nullptr);
  return g_display;
}

Window ActiveWindow(Display* dpy) {
  if (dpy == nullptr) return 0;
  const Atom property = XInternAtom(dpy, "_NET_ACTIVE_WINDOW", True);
  if (property == None) return 0;
  Atom type = None;
  int format = 0;
  unsigned long count = 0, bytes = 0;
  unsigned char* data = nullptr;
  if (XGetWindowProperty(dpy, DefaultRootWindow(dpy), property, 0, 1, False, AnyPropertyType, &type,
                         &format, &count, &bytes, &data) != Success) return 0;
  Window active = (data != nullptr && format == 32 && count >= 1) ? *reinterpret_cast<unsigned long*>(data) : 0;
  if (data != nullptr) XFree(data);
  return active;
}

std::string Lower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(::tolower(c)); });
  return value;
}

bool Contains(const std::string& haystack, const char* needle) { return haystack.find(needle) != std::string::npos; }

// Ctrl+Shift+V is not a terminal standard: these are the ones that do not have it.
bool IsDumbTerminal(const std::string& cls) {
  return Contains(cls, "xterm") || Contains(cls, "urxvt") || Contains(cls, "rxvt") || Contains(cls, "eterm");
}

bool IsTerminal(const std::string& cls) {
  return Contains(cls, "terminal") || Contains(cls, "konsole") || Contains(cls, "alacritty") ||
         Contains(cls, "kitty") || Contains(cls, "tilix") || Contains(cls, "termite") ||
         Contains(cls, "wezterm") || Contains(cls, "ghostty") || Contains(cls, "console") ||
         Contains(cls, "terminator") || Contains(cls, "guake") || Contains(cls, "tilda") || IsDumbTerminal(cls);
}

std::vector<unsigned int> DecodeUtf8(const std::string& utf8) {
  std::vector<unsigned int> out;
  for (size_t i = 0; i < utf8.size();) {
    const unsigned char c = static_cast<unsigned char>(utf8[i]);
    unsigned int cp = c;
    size_t extra = 0;
    if (c >= 0xF0) { cp = c & 0x07u; extra = 3; }
    else if (c >= 0xE0) { cp = c & 0x0Fu; extra = 2; }
    else if (c >= 0xC0) { cp = c & 0x1Fu; extra = 1; }
    if (i + extra >= utf8.size()) extra = 0;
    for (size_t k = 1; k <= extra; ++k) cp = (cp << 6) | (static_cast<unsigned char>(utf8[i + k]) & 0x3Fu);
    out.push_back(cp);
    i += extra + 1;
  }
  return out;
}

KeySym KeysymFor(unsigned int codepoint) {
  if (codepoint == '\n' || codepoint == '\r') return XK_Return;
  if (codepoint == '\t') return XK_Tab;
  // Latin-1 maps one to one; everything above needs Unicode keysym range.
  return codepoint < 0x100 ? static_cast<KeySym>(codepoint) : static_cast<KeySym>(codepoint | 0x01000000u);
}

// A keycode with no keysym at all: remapping a used one would break the real keyboard.
int SpareKeycode(Display* dpy) {
  int min_code = 0, max_code = 0, per_code = 0;
  XDisplayKeycodes(dpy, &min_code, &max_code);
  KeySym* map = XGetKeyboardMapping(dpy, static_cast<KeyCode>(min_code), max_code - min_code + 1, &per_code);
  if (map == nullptr) return 0;
  int spare = 0;
  for (int code = max_code; code >= min_code && spare == 0; --code) {
    bool empty = true;
    for (int slot = 0; slot < per_code; ++slot) {
      if (map[(code - min_code) * per_code + slot] != NoSymbol) empty = false;
    }
    if (empty) spare = code;
  }
  XFree(map);
  return spare;
}

void TapKeycode(Display* dpy, KeyCode code) {
  XTestFakeKeyEvent(dpy, code, True, 0);
  XTestFakeKeyEvent(dpy, code, False, 0);
  XFlush(dpy);
}

}  // namespace

void RememberTargetWith(Display* dpy) {
  const Window active = ActiveWindow(dpy);
  if (active != 0) g_target.store(active, std::memory_order_relaxed);
}

void RememberTarget() {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  RememberTargetWith(InputDisplay());
}

Window RememberedTarget() { return g_target.load(std::memory_order_relaxed); }

std::string TargetClass(Window target) {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  Display* dpy = InputDisplay();
  if (dpy == nullptr || target == 0) return std::string();
  XClassHint hint{};
  if (XGetClassHint(dpy, target, &hint) == 0) return std::string();
  std::string out = hint.res_class ? hint.res_class : (hint.res_name ? hint.res_name : "");
  if (hint.res_name != nullptr) XFree(hint.res_name);
  if (hint.res_class != nullptr) XFree(hint.res_class);
  return out;
}

std::string TargetTitle(Window target) {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  Display* dpy = InputDisplay();
  if (dpy == nullptr || target == 0) return std::string();
  // _NET_WM_NAME is UTF-8; WM_NAME is latin-1 and only fallback.
  const Atom net_name = XInternAtom(dpy, "_NET_WM_NAME", True);
  if (net_name != None) {
    Atom type = None;
    int format = 0;
    unsigned long count = 0, bytes = 0;
    unsigned char* data = nullptr;
    if (XGetWindowProperty(dpy, target, net_name, 0, 512, False, AnyPropertyType, &type, &format,
                           &count, &bytes, &data) == Success && data != nullptr) {
      std::string out(reinterpret_cast<char*>(data), count);
      XFree(data);
      if (!out.empty()) return out;
    }
  }
  char* legacy = nullptr;
  if (XFetchName(dpy, target, &legacy) != 0 && legacy != nullptr) {
    std::string out(legacy);
    XFree(legacy);
    return out;
  }
  return std::string();
}

const char* ClassifyTarget(Window target) {
  if (target == 0) return "gui";
  const std::string cls = Lower(TargetClass(target));
  if (cls.empty()) return "gui";
  if (IsDumbTerminal(cls)) return "console";
  if (IsTerminal(cls)) return "terminal";
  return "gui";
}

bool TargetIsForeground() {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  Display* dpy = InputDisplay();
  const Window target = RememberedTarget();
  return dpy != nullptr && target != 0 && ActiveWindow(dpy) == target;
}

bool SendKeyStroke(const char* keysym_name, bool ctrl, bool shift) {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  Display* dpy = InputDisplay();
  if (dpy == nullptr) return false;
  const KeyCode code = XKeysymToKeycode(dpy, XStringToKeysym(keysym_name));
  if (code == 0) return false;
  const KeyCode ctrl_code = XKeysymToKeycode(dpy, XK_Control_L);
  const KeyCode shift_code = XKeysymToKeycode(dpy, XK_Shift_L);
  if (ctrl) XTestFakeKeyEvent(dpy, ctrl_code, True, 0);
  if (shift) XTestFakeKeyEvent(dpy, shift_code, True, 0);
  XFlush(dpy);
  XTestFakeKeyEvent(dpy, code, True, 0);
  XFlush(dpy);
  usleep(kTypeDelayUs * 3);
  XTestFakeKeyEvent(dpy, code, False, 0);
  if (shift) XTestFakeKeyEvent(dpy, shift_code, False, 0);
  if (ctrl) XTestFakeKeyEvent(dpy, ctrl_code, False, 0);
  XFlush(dpy);
  return true;
}

bool SendUnicodeText(const std::string& utf8) {
  if (utf8.empty()) return false;
  std::lock_guard<std::mutex> lock(g_display_mutex);
  Display* dpy = InputDisplay();
  if (dpy == nullptr) return false;

  const std::vector<unsigned int> points = DecodeUtf8(utf8);
  const int spare = SpareKeycode(dpy);
  if (spare == 0) return false;

  for (const unsigned int cp : points) {
    const KeySym symbol = KeysymFor(cp);
    // A key already on the keyboard is typed as itself: no remap, no MappingNotify storm.
    const KeyCode existing = XKeysymToKeycode(dpy, symbol);
    if (existing != 0 && XkbKeycodeToKeysym(dpy, existing, 0, 0) == symbol) {
      TapKeycode(dpy, existing);
      usleep(kTypeDelayUs);
      continue;
    }
    KeySym mapping[2] = {symbol, symbol};
    XChangeKeyboardMapping(dpy, spare, 2, mapping, 1);
    XSync(dpy, False);
    TapKeycode(dpy, static_cast<KeyCode>(spare));
    usleep(kTypeDelayUs);
  }
  KeySym cleared[2] = {NoSymbol, NoSymbol};
  XChangeKeyboardMapping(dpy, spare, 2, cleared, 1);
  XSync(dpy, False);
  return true;
}

bool PasteIntoTarget(const std::string& utf8) {
  if (utf8.empty()) return false;
  const Window target = RememberedTarget();
  if (target == 0) return SendUnicodeText(utf8);
  // Windows steals the foreground back; X11 has no such need, so a moved focus is simply refused.
  if (!TargetIsForeground()) return false;

  const std::string kind = ClassifyTarget(target);
  if (kind == "console") return SendUnicodeText(utf8);
  return SendKeyStroke("v", true, kind == "terminal");
}

bool SendEnter() { return SendKeyStroke("Return", false, false); }

void CloseInputDisplay() {
  std::lock_guard<std::mutex> lock(g_display_mutex);
  if (g_display != nullptr) { XCloseDisplay(g_display); g_display = nullptr; }
}

}  // namespace dito
