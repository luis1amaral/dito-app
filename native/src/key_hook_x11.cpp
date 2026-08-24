#include "key_hook_x11.h"

#include <X11/XKBlib.h>
#include <X11/keysym.h>
#include <sys/select.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cstring>

#include "input_x11.h"

namespace dito {
namespace {

// The lock keys are part of the grabbed combination, so every state has to be grabbed too.
const unsigned int kLockMasks[] = {0,
                                   LockMask,
                                   Mod2Mask,
                                   Mod2Mask | LockMask,
                                   Mod3Mask,
                                   Mod3Mask | LockMask,
                                   Mod3Mask | Mod2Mask,
                                   Mod3Mask | Mod2Mask | LockMask};

constexpr int kTickIntervalUs = 100000;

std::atomic<int> g_grab_error{0};

int GrabErrorHandler(Display*, XErrorEvent* event) {
  g_grab_error.store(event->error_code);
  return 0;
}

// The names the settings screen offers are not the names Xlib knows.
KeySym KeysymForName(const std::string& name) {
  std::string key = name;
  std::transform(key.begin(), key.end(), key.begin(),
                 [](unsigned char c) { return static_cast<char>(::tolower(c)); });
  if (key == "scrolllock" || key == "scroll_lock") return XK_Scroll_Lock;
  if (key == "pause") return XK_Pause;
  if (key == "capslock" || key == "caps_lock") return XK_Caps_Lock;
  if (key == "printscreen" || key == "print_screen") return XK_Print;
  if (key == "space") return XK_space;
  if (key == "insert") return XK_Insert;
  if (key == "home") return XK_Home;
  if (key == "end") return XK_End;
  if (key == "pageup" || key == "page_up") return XK_Prior;
  if (key == "pagedown" || key == "page_down") return XK_Next;
  if (key.size() >= 2 && key[0] == 'f') {
    const int number = ::atoi(key.c_str() + 1);
    if (number >= 1 && number <= 24) return XK_F1 + (number - 1);
  }
  return XStringToKeysym(name.c_str());
}

bool KeycodeIsDown(const char* keymap, KeyCode code) {
  return (keymap[code / 8] & (1 << (code % 8))) != 0;
}

}  // namespace

KeyHookX11& KeyHookX11::Shared() {
  static KeyHookX11 shared;
  return shared;
}

KeyHookX11::KeyHookX11() = default;

KeyHookX11::~KeyHookX11() { Stop(); }

int64_t KeyHookX11::NowMicros() {
  return std::chrono::duration_cast<std::chrono::microseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

bool KeyHookX11::Bind(const std::string& action, const std::string& key) {
  if (KeysymForName(key) == NoSymbol) return false;
  std::lock_guard<std::mutex> lock(bindings_mutex_);
  bindings_.push_back(Binding{action, key, 0});
  return true;
}

void KeyHookX11::UnbindAll() {
  std::lock_guard<std::mutex> lock(bindings_mutex_);
  bindings_.clear();
}

int KeyHookX11::AddListener(Listener listener) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  const int token = next_token_++;
  listeners_[token] = std::move(listener);
  return token;
}

void KeyHookX11::RemoveListener(int token) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  listeners_.erase(token);
}

void KeyHookX11::EmitEdge(const KeyEdge& edge) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  for (const auto& entry : listeners_) {
    if (entry.second.on_edge) entry.second.on_edge(edge);
  }
}

void KeyHookX11::EmitTick(const KeyTick& tick) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  for (const auto& entry : listeners_) {
    if (entry.second.on_tick) entry.second.on_tick(tick);
  }
}

void KeyHookX11::EmitStatus(const std::string& status) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  for (const auto& entry : listeners_) {
    if (entry.second.on_hook_status) entry.second.on_hook_status(status);
  }
}

void KeyHookX11::Start() {
  if (running_.exchange(true)) return;
  if (pipe(wake_pipe_) != 0) {
    running_.store(false);
    install_error_.store(-1);
    return;
  }
  thread_ = std::thread([this] { ThreadMain(); });
}

void KeyHookX11::Stop() {
  if (!running_.exchange(false)) return;
  if (wake_pipe_[1] != -1) {
    const char byte = 1;
    ssize_t ignored = write(wake_pipe_[1], &byte, 1);
    (void)ignored;
  }
  if (thread_.joinable()) thread_.join();
  for (int& fd : wake_pipe_) {
    if (fd != -1) close(fd);
    fd = -1;
  }
  installed_.store(false);
}

void KeyHookX11::ThreadMain() {
  Display* dpy = XOpenDisplay(nullptr);
  if (dpy == nullptr) {
    install_error_.store(-2);
    EmitStatus("no-display");
    return;
  }

  // Without this X11 fakes a release before every auto-repeat press, and hold mode never holds.
  Bool detectable = False;
  XkbSetDetectableAutoRepeat(dpy, True, &detectable);

  const Window root = DefaultRootWindow(dpy);
  {
    std::lock_guard<std::mutex> lock(bindings_mutex_);
    for (Binding& binding : bindings_) {
      binding.code = XKeysymToKeycode(dpy, KeysymForName(binding.key));
    }
  }

  g_grab_error.store(0);
  XErrorHandler previous = XSetErrorHandler(GrabErrorHandler);
  bool grabbed = false;
  {
    std::lock_guard<std::mutex> lock(bindings_mutex_);
    for (const Binding& binding : bindings_) {
      if (binding.code == 0) continue;
      for (const unsigned int mask : kLockMasks) {
        XGrabKey(dpy, binding.code, mask, root, False, GrabModeAsync, GrabModeAsync);
      }
      grabbed = true;
    }
  }
  XSync(dpy, False);
  XSetErrorHandler(previous);

  install_error_.store(g_grab_error.load());
  const bool ok = grabbed && g_grab_error.load() == 0;
  installed_.store(ok);
  EmitStatus(ok ? "installed" : "grab-failed");

  XSelectInput(dpy, root, KeyPressMask | KeyReleaseMask);
  const int x_fd = ConnectionNumber(dpy);

  while (running_.load()) {
    pump_count_.fetch_add(1);

    while (XPending(dpy) > 0) {
      XEvent event;
      XNextEvent(dpy, &event);
      if (event.type != KeyPress && event.type != KeyRelease) continue;
      seen_count_.fetch_add(1);
      const bool down = event.type == KeyPress;
      std::lock_guard<std::mutex> lock(bindings_mutex_);
      for (Binding& binding : bindings_) {
        if (binding.code == 0 || event.xkey.keycode != binding.code) continue;
        if (binding.last_down == down) continue;
        binding.last_down = down;
        // The paste target is captured on key DOWN, before the pill shows up.
        if (down) RememberTargetWith(dpy);
        EmitEdge(KeyEdge{binding.action, binding.key, down, NowMicros()});
      }
    }

    char keymap[32] = {};
    XQueryKeymap(dpy, keymap);
    KeyTick tick;
    tick.micros = NowMicros();
    {
      std::lock_guard<std::mutex> lock(bindings_mutex_);
      for (Binding& binding : bindings_) {
        if (binding.code == 0) continue;
        const bool physical = KeycodeIsDown(keymap, binding.code);
        // The keymap is the authority: a lost event would otherwise wedge the edge state forever.
        binding.last_down = physical;
        if (physical) tick.down.push_back(binding.action);
      }
    }
    EmitTick(tick);

    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(x_fd, &fds);
    FD_SET(wake_pipe_[0], &fds);
    struct timeval timeout {};
    timeout.tv_usec = kTickIntervalUs;
    const int highest = std::max(x_fd, wake_pipe_[0]);
    select(highest + 1, &fds, nullptr, nullptr, &timeout);
    if (FD_ISSET(wake_pipe_[0], &fds)) {
      char drain[8];
      ssize_t ignored = read(wake_pipe_[0], drain, sizeof(drain));
      (void)ignored;
    }
  }

  {
    std::lock_guard<std::mutex> lock(bindings_mutex_);
    for (const Binding& binding : bindings_) {
      if (binding.code == 0) continue;
      for (const unsigned int mask : kLockMasks) XUngrabKey(dpy, binding.code, mask, root);
    }
  }
  XSync(dpy, False);
  XCloseDisplay(dpy);
}

}  // namespace dito
