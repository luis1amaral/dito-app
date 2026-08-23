#include "dito_win32_plugin.h"

#include <flutter/event_stream_handler_functions.h>
#include <flutter/standard_method_codec.h>
#include <windows.h>
#include <dwmapi.h>
#include <mmsystem.h>
#include <shellapi.h>

#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "key_table.h"
#include "tray.h"

namespace dito_win32 {

HWND DitoWin32Plugin::previous_foreground_ = nullptr;
HWND DitoWin32Plugin::last_paste_target_ = nullptr;

namespace {

using flutter::EncodableList;
using flutter::EncodableMap;
using flutter::EncodableValue;

// Events cross from the hook thread; only the platform thread may touch the sink.
std::mutex g_sink_mutex;

template <typename T>
const T* Find(const EncodableMap& map, const char* key) {
  const auto it = map.find(EncodableValue(key));
  if (it == map.end()) return nullptr;
  return std::get_if<T>(&it->second);
}

std::string GetString(const EncodableMap& map, const char* key, const std::string& fallback = "") {
  const auto* value = Find<std::string>(map, key);
  return value == nullptr ? fallback : *value;
}

bool GetBool(const EncodableMap& map, const char* key, bool fallback) {
  const auto* value = Find<bool>(map, key);
  return value == nullptr ? fallback : *value;
}

double GetDouble(const EncodableMap& map, const char* key, double fallback) {
  if (const auto* d = Find<double>(map, key)) return *d;
  if (const auto* i = Find<int32_t>(map, key)) return static_cast<double>(*i);
  return fallback;
}

const EncodableMap* ArgsOf(const flutter::MethodCall<EncodableValue>& call) {
  return std::get_if<EncodableMap>(call.arguments());
}

}  // namespace


namespace {

// OpenClipboard fails while another process holds it; the Python side learned this the hard way.
bool OpenClipboardWithRetry(HWND owner) {
  for (int attempt = 0; attempt < 5; attempt++) {
    if (OpenClipboard(owner) != 0) return true;
    Sleep(20);
  }
  return false;
}

std::wstring Widen(const std::string& utf8) {
  if (utf8.empty()) return std::wstring();
  const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.data(),
                                       static_cast<int>(utf8.size()), nullptr, 0);
  std::wstring out;
  out.resize(static_cast<size_t>(size));
  MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()),
                      out.data(), size);
  return out;
}

std::string Narrow(const std::wstring& wide) {
  if (wide.empty()) return std::string();
  const int size = WideCharToMultiByte(CP_UTF8, 0, wide.data(),
                                       static_cast<int>(wide.size()), nullptr, 0,
                                       nullptr, nullptr);
  std::string out;
  out.resize(static_cast<size_t>(size));
  WideCharToMultiByte(CP_UTF8, 0, wide.data(), static_cast<int>(wide.size()),
                      out.data(), size, nullptr, nullptr);
  return out;
}

// Windows only grants the foreground to whoever already has it; attaching input borrows that.
bool ForceForeground(HWND target) {
  if (target == nullptr || IsWindow(target) == 0) return false;
  if (SetForegroundWindow(target) != 0) return true;

  const DWORD owner = GetWindowThreadProcessId(GetForegroundWindow(), nullptr);
  const DWORD mine = GetCurrentThreadId();
  if (owner == 0 || owner == mine) return false;

  AttachThreadInput(mine, owner, TRUE);
  const bool ok = SetForegroundWindow(target) != 0;
  AttachThreadInput(mine, owner, FALSE);
  return ok;
}

// Windows twin of IsTerminalWindow in the Linux plugin: says how the target accepts text (measured, see docs/medicoes/colagem-windows.md).
const char* ClassifyTarget(HWND target) {
  if (target == nullptr || IsWindow(target) == 0) return "gui";
  wchar_t cls[256] = {};
  if (GetClassNameW(target, cls, 256) == 0) return "gui";
  const std::wstring name(cls);
  // Only conhost is broken: with PROCESSED_INPUT off it hands Ctrl+V to the app as 0x16.
  if (name == L"ConsoleWindowClass") return "console";
  // These already paste with Ctrl+V today, so they stay on the path that works.
  if (name == L"CASCADIA_HOSTING_WINDOW_CLASS" || name == L"mintty") return "terminal";
  return "gui";
}

// Types the text as UTF-16 units: works where paste has no usable shortcut, and keeps pt-BR accents exact because the scan code IS the character.
bool SendUnicodeText(const std::wstring& text) {
  if (text.empty()) return false;
  std::vector<INPUT> inputs;
  inputs.reserve(text.size() * 2);
  for (const wchar_t ch : text) {
    INPUT down{};
    down.type = INPUT_KEYBOARD;
    down.ki.wScan = ch;
    down.ki.dwFlags = KEYEVENTF_UNICODE;
    INPUT up = down;
    up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
    inputs.push_back(down);
    inputs.push_back(up);
  }
  const UINT sent = SendInput(static_cast<UINT>(inputs.size()), inputs.data(), sizeof(INPUT));
  return sent == inputs.size();
}

bool SendKeyStroke(WORD vk, bool ctrl) {
  INPUT inputs[4]{};
  int count = 0;
  if (ctrl) {
    inputs[count].type = INPUT_KEYBOARD;
    inputs[count++].ki.wVk = VK_CONTROL;
  }
  inputs[count].type = INPUT_KEYBOARD;
  inputs[count++].ki.wVk = vk;
  inputs[count].type = INPUT_KEYBOARD;
  inputs[count].ki.wVk = vk;
  inputs[count++].ki.dwFlags = KEYEVENTF_KEYUP;
  if (ctrl) {
    inputs[count].type = INPUT_KEYBOARD;
    inputs[count].ki.wVk = VK_CONTROL;
    inputs[count++].ki.dwFlags = KEYEVENTF_KEYUP;
  }
  return SendInput(count, inputs, sizeof(INPUT)) == static_cast<UINT>(count);
}

}  // namespace

void DitoWin32Plugin::RegisterWithRegistrar(flutter::PluginRegistrarWindows* registrar) {
  auto plugin = std::make_unique<DitoWin32Plugin>(registrar);

  auto method_channel = std::make_shared<flutter::MethodChannel<EncodableValue>>(
      registrar->messenger(), "dito/win32",
      &flutter::StandardMethodCodec::GetInstance());

  auto* raw = plugin.get();
  method_channel->SetMethodCallHandler(
      [raw](const auto& call, auto result) { raw->HandleMethod(call, std::move(result)); });

  registrar->AddPlugin(std::move(plugin));
}

DitoWin32Plugin::DitoWin32Plugin(flutter::PluginRegistrarWindows* registrar)
    : registrar_(registrar) {
  auto key_channel = std::make_unique<flutter::EventChannel<EncodableValue>>(
      registrar->messenger(), "dito/keys", &flutter::StandardMethodCodec::GetInstance());

  hook_ = &dito::KeyHook::Shared();

  dito::KeyHook::Listener listener;
  listener.on_edge = [this](const dito::KeyEdge& edge) {
    std::lock_guard<std::mutex> lock(g_sink_mutex);
    if (key_sink_ == nullptr) return;
    key_sink_->Success(EncodableValue(EncodableMap{
        {EncodableValue("type"), EncodableValue(edge.down ? "down" : "up")},
        {EncodableValue("name"), EncodableValue(edge.action)},
        {EncodableValue("key"), EncodableValue(edge.key)},
        {EncodableValue("t"), EncodableValue(edge.micros)},
    }));
  };

  listener.on_tick = [this](const dito::KeyTick& tick) {
    std::lock_guard<std::mutex> lock(g_sink_mutex);
    if (key_sink_ == nullptr) return;
    EncodableList down;
    for (const auto& action : tick.down) down.push_back(EncodableValue(action));
    key_sink_->Success(EncodableValue(EncodableMap{
        {EncodableValue("type"), EncodableValue("tick")},
        {EncodableValue("down"), EncodableValue(down)},
        {EncodableValue("t"), EncodableValue(tick.micros)},
    }));
  };

  listener_token_ = hook_->AddListener(std::move(listener));

  key_channel->SetStreamHandler(
      std::make_unique<flutter::StreamHandlerFunctions<EncodableValue>>(
          [this](const EncodableValue*, std::unique_ptr<flutter::EventSink<EncodableValue>>&& sink)
              -> std::unique_ptr<flutter::StreamHandlerError<EncodableValue>> {
            std::lock_guard<std::mutex> lock(g_sink_mutex);
            key_sink_ = std::move(sink);
            return nullptr;
          },
          [this](const EncodableValue*)
              -> std::unique_ptr<flutter::StreamHandlerError<EncodableValue>> {
            std::lock_guard<std::mutex> lock(g_sink_mutex);
            key_sink_ = nullptr;
            return nullptr;
          }));

  auto tray_channel = std::make_unique<flutter::EventChannel<EncodableValue>>(
      registrar->messenger(), "dito/tray", &flutter::StandardMethodCodec::GetInstance());
  tray_channel->SetStreamHandler(
      std::make_unique<flutter::StreamHandlerFunctions<EncodableValue>>(
          [this](const EncodableValue*, std::unique_ptr<flutter::EventSink<EncodableValue>>&& sink)
              -> std::unique_ptr<flutter::StreamHandlerError<EncodableValue>> {
            std::lock_guard<std::mutex> lock(g_sink_mutex);
            tray_sink_ = std::move(sink);
            return nullptr;
          },
          [this](const EncodableValue*)
              -> std::unique_ptr<flutter::StreamHandlerError<EncodableValue>> {
            std::lock_guard<std::mutex> lock(g_sink_mutex);
            tray_sink_ = nullptr;
            return nullptr;
          }));

  key_channel_ = std::move(key_channel);
  tray_channel_ = std::move(tray_channel);

  const UINT wm_show = ::RegisterWindowMessageW(L"WM_DITO_SHOW_MAIN_WINDOW");
  proc_delegate_id_ = registrar_->RegisterTopLevelWindowProcDelegate(
      [this, wm_show](HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) -> std::optional<LRESULT> {
        if (message == wm_show) {
          std::lock_guard<std::mutex> lock(g_sink_mutex);
          if (tray_sink_ != nullptr) {
            tray_sink_->Success(EncodableValue(EncodableMap{
                {EncodableValue("event"), EncodableValue("menu")},
                {EncodableValue("id"), EncodableValue("open")},
            }));
          }
          return 0;
        }
        return std::nullopt;
      });

  hook_->Start();
}

DitoWin32Plugin::~DitoWin32Plugin() {
  if (proc_delegate_id_ != -1) {
    registrar_->UnregisterTopLevelWindowProcDelegate(proc_delegate_id_);
    proc_delegate_id_ = -1;
  }
  // The hook is shared and outlives every window; only drop our own listener and sink.
  if (hook_ != nullptr && listener_token_ != 0) hook_->RemoveListener(listener_token_);
  std::lock_guard<std::mutex> lock(g_sink_mutex);
  key_sink_ = nullptr;
}

HWND DitoWin32Plugin::RootWindow() {
  return GetAncestor(registrar_->GetView()->GetNativeWindow(), GA_ROOT);
}

void DitoWin32Plugin::HandleMethod(
    const flutter::MethodCall<EncodableValue>& call,
    std::unique_ptr<flutter::MethodResult<EncodableValue>> result) {
  const std::string& method = call.method_name();
  const EncodableMap* args = ArgsOf(call);
  const EncodableMap empty;
  if (args == nullptr) args = &empty;

  if (method == "keys.bind") {
    const std::string name = GetString(*args, "name");
    const std::string key = GetString(*args, "key");
    const bool suppress = GetBool(*args, "suppress", true);
    if (!hook_->Bind(name, key, suppress)) {
      result->Error("KEY_UNKNOWN", "tecla desconhecida: " + key);
      return;
    }
    result->Success();
    return;
  }

  if (method == "keys.unbindAll") {
    hook_->UnbindAll();
    result->Success();
    return;
  }

  if (method == "keys.pause") {
    hook_->Pause();
    result->Success();
    return;
  }

  if (method == "keys.resume") {
    hook_->Resume();
    result->Success();
    return;
  }

  if (method == "keys.snapshot") {
    EncodableMap out;
    for (const auto& [action, down] : hook_->Snapshot()) {
      out[EncodableValue(action)] = EncodableValue(down);
    }
    out[EncodableValue("_installed")] = EncodableValue(hook_->installed());
    out[EncodableValue("_seen")] =
        EncodableValue(static_cast<int64_t>(hook_->seen_count()));
    out[EncodableValue("_pump")] =
        EncodableValue(static_cast<int64_t>(hook_->pump_count()));
    out[EncodableValue("_err")] =
        EncodableValue(static_cast<int64_t>(hook_->install_error()));

    // Which window is in front, and whether we are elevated: a low-integrity process gets no hook events while an elevated window holds the foreground.
    wchar_t cls[128] = {0};
    GetClassName(GetForegroundWindow(), cls, 128);
    out[EncodableValue("_fg")] = EncodableValue(Narrow(std::wstring(cls)));

    bool elevated = false;
    HANDLE token = nullptr;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
      TOKEN_ELEVATION elevation{};
      DWORD size = sizeof(elevation);
      if (GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &size)) {
        elevated = elevation.TokenIsElevated != 0;
      }
      CloseHandle(token);
    }
    out[EncodableValue("_elevated")] = EncodableValue(elevated);
    result->Success(EncodableValue(out));
    return;
  }

  if (method == "keys.injectForTest") {
    const std::string key = GetString(*args, "key");
    const UINT vk = dito::VkFromName(key);
    if (vk == 0) {
      result->Error("KEY_UNKNOWN", "tecla desconhecida: " + key);
      return;
    }
    const UINT sent = hook_->InjectForTest(vk, GetBool(*args, "down", true));
    result->Success(EncodableValue(static_cast<int32_t>(sent)));
    return;
  }

  if (method == "window.adoptAsHud") {
    const HWND hwnd = RootWindow();
    if (hwnd == nullptr) {
      result->Error("NO_WINDOW", "sem janela nativa");
      return;
    }
    LONG_PTR ex = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
    ex |= WS_EX_TOOLWINDOW;
    ex &= ~WS_EX_APPWINDOW;
    ex |= WS_EX_NOACTIVATE;
    SetWindowLongPtr(hwnd, GWL_EXSTYLE, ex);

    LONG_PTR st = GetWindowLongPtr(hwnd, GWL_STYLE);
    st &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);
    st |= WS_POPUP;
    SetWindowLongPtr(hwnd, GWL_STYLE, st);

    // No DWM alpha trick here: Flutter's release swapchain composes opaque, so blur-behind rendered these windows fully invisible; shape comes from SetWindowRgn instead.
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    result->Success(EncodableValue(static_cast<int64_t>(reinterpret_cast<intptr_t>(hwnd))));
    return;
  }

  if (method == "window.showNoActivate") {
    const HWND hwnd = RootWindow();
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
    // 1px size jiggle: the Flutter swapchain only presents after a real resize while visible, or a window sized when hidden stays black forever.
    RECT rect{};
    if (GetWindowRect(hwnd, &rect)) {
      const int width = rect.right - rect.left;
      const int height = rect.bottom - rect.top;
      SetWindowPos(hwnd, nullptr, rect.left, rect.top, width + 1, height,
                   SWP_NOACTIVATE | SWP_NOZORDER);
      SetWindowPos(hwnd, nullptr, rect.left, rect.top, width, height,
                   SWP_NOACTIVATE | SWP_NOZORDER);
    }
    result->Success();
    return;
  }

  if (method == "window.forceRepaint") {
    // Same jiggle as showNoActivate: a window resized while hidden keeps a dead black band
    // until a real resize happens while it is visible.
    const HWND hwnd = RootWindow();
    RECT rect{};
    if (hwnd != nullptr && GetWindowRect(hwnd, &rect)) {
      const int width = rect.right - rect.left;
      const int height = rect.bottom - rect.top;
      SetWindowPos(hwnd, nullptr, rect.left, rect.top, width + 1, height,
                   SWP_NOACTIVATE | SWP_NOZORDER);
      SetWindowPos(hwnd, nullptr, rect.left, rect.top, width, height,
                   SWP_NOACTIVATE | SWP_NOZORDER);
    }
    result->Success();
    return;
  }

  if (method == "clipboard.get") {
    if (!OpenClipboardWithRetry(RootWindow())) {
      result->Success();
      return;
    }
    std::string text;
    if (HANDLE handle = GetClipboardData(CF_UNICODETEXT)) {
      if (auto* locked = static_cast<wchar_t*>(GlobalLock(handle))) {
        text = Narrow(std::wstring(locked));
        GlobalUnlock(handle);
      }
    }
    CloseClipboard();
    if (text.empty()) {
      result->Success();
    } else {
      result->Success(EncodableValue(text));
    }
    return;
  }

  if (method == "clipboard.set") {
    const std::wstring wide = Widen(GetString(*args, "text"));
    if (!OpenClipboardWithRetry(RootWindow())) {
      result->Success(EncodableValue(false));
      return;
    }
    EmptyClipboard();
    const size_t bytes = (wide.size() + 1) * sizeof(wchar_t);
    HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE, bytes);
    bool ok = false;
    if (memory != nullptr) {
      if (auto* locked = static_cast<wchar_t*>(GlobalLock(memory))) {
        memcpy(locked, wide.c_str(), bytes);
        GlobalUnlock(memory);
        ok = SetClipboardData(CF_UNICODETEXT, memory) != nullptr;
      }
      if (!ok) GlobalFree(memory);
    }
    CloseClipboard();
    result->Success(EncodableValue(ok));
    return;
  }

  if (method == "input.targetKind") {
    result->Success(EncodableValue(std::string(ClassifyTarget(last_paste_target_))));
    return;
  }

  if (method == "input.sendCtrlV") {
    // The remembered target, never GetForegroundWindow(): on the card path Dito IS the foreground.
    const std::string kind = ClassifyTarget(last_paste_target_);
    if (kind == "console") {
      // conhost with PROCESSED_INPUT off never pastes on Ctrl+V; typing is what lands.
      const std::wstring text = Widen(GetString(*args, "text"));
      result->Success(EncodableValue(text.empty() ? SendKeyStroke('V', true)
                                                  : SendUnicodeText(text)));
      return;
    }
    result->Success(EncodableValue(SendKeyStroke('V', true)));
    return;
  }

  if (method == "input.sendEnter") {
    result->Success(EncodableValue(SendKeyStroke(VK_RETURN, false)));
    return;
  }

  if (method == "window.setFocusable") {
    // WS_EX_NOACTIVATE is weak on Windows, but the card still needs it OFF to be activated reliably (docs/armadilhas.md 4.6).
    const HWND hwnd = RootWindow();
    if (hwnd == nullptr) {
      result->Success(EncodableValue(false));
      return;
    }
    const auto* raw = std::get_if<bool>(call.arguments());
    const bool focusable = raw != nullptr && *raw;
    LONG_PTR ex = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
    if (focusable) {
      ex &= ~WS_EX_NOACTIVATE;
    } else {
      ex |= WS_EX_NOACTIVATE;
    }
    SetWindowLongPtr(hwnd, GWL_EXSTYLE, ex);
    result->Success(EncodableValue(true));
    return;
  }

  if (method == "input.sendChord") {
    const std::string key = GetString(*args, "key", "v");
    const bool ctrl = GetBool(*args, "ctrl", true);
    WORD vk = 0;
    if (key == "a") vk = 'A';
    else if (key == "c") vk = 'C';
    else if (key == "v") vk = 'V';
    else if (key == "enter") vk = VK_RETURN;
    if (vk == 0) {
      result->Error("KEY_UNKNOWN", "tecla desconhecida: " + key);
      return;
    }
    result->Success(EncodableValue(SendKeyStroke(vk, ctrl)));
    return;
  }

  // Test-only target: a real EDIT control owned by this process, so the paste path is never proven by sending a keystroke at the user's own window.
  if (method == "test.createEditTarget") {
    if (test_edit_ != nullptr) DestroyWindow(test_edit_);
    test_edit_ = CreateWindowEx(
        WS_EX_CLIENTEDGE, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL,
        10, 10, 600, 200, RootWindow(), nullptr, GetModuleHandle(nullptr), nullptr);
    if (test_edit_ == nullptr) {
      result->Error("NO_TARGET", "nao consegui criar o alvo de teste");
      return;
    }
    ForceForeground(RootWindow());
    SetFocus(test_edit_);
    result->Success(EncodableValue(
        static_cast<int64_t>(reinterpret_cast<intptr_t>(test_edit_))));
    return;
  }

  if (method == "test.readEditTarget") {
    if (test_edit_ == nullptr) {
      result->Success();
      return;
    }
    const int length = GetWindowTextLength(test_edit_);
    if (length <= 0) {
      result->Success(EncodableValue(std::string()));
      return;
    }
    std::wstring buffer;
    buffer.resize(static_cast<size_t>(length) + 1);
    GetWindowText(test_edit_, buffer.data(), length + 1);
    buffer.resize(static_cast<size_t>(length));
    result->Success(EncodableValue(Narrow(buffer)));
    return;
  }

  if (method == "test.destroyEditTarget") {
    if (test_edit_ != nullptr) DestroyWindow(test_edit_);
    test_edit_ = nullptr;
    result->Success();
    return;
  }

  // Guard for tests: refuse to send keys unless our own window holds the foreground.
  if (method == "test.ownsForeground") {
    result->Success(EncodableValue(GetForegroundWindow() == RootWindow()));
    return;
  }

  if (method == "tray.create") {
    auto& tray = dito::Tray::Shared();
    tray.on_menu = [this](const std::string& id) {
      std::lock_guard<std::mutex> lock(g_sink_mutex);
      if (tray_sink_ == nullptr) return;
      tray_sink_->Success(EncodableValue(EncodableMap{
          {EncodableValue("event"), EncodableValue("menu")},
          {EncodableValue("id"), EncodableValue(id)},
      }));
    };
    tray.on_click = [this]() {
      std::lock_guard<std::mutex> lock(g_sink_mutex);
      if (tray_sink_ == nullptr) return;
      tray_sink_->Success(EncodableValue(EncodableMap{
          {EncodableValue("event"), EncodableValue("click")},
      }));
    };
    result->Success(EncodableValue(tray.Create(Widen(GetString(*args, "tooltip")))));
    return;
  }

  if (method == "tray.setIcon") {
    result->Success(
        EncodableValue(dito::Tray::Shared().SetIcon(Widen(GetString(*args, "path")))));
    return;
  }

  if (method == "tray.setTooltip") {
    result->Success(
        EncodableValue(dito::Tray::Shared().SetTooltip(Widen(GetString(*args, "tooltip")))));
    return;
  }

  if (method == "tray.setMenu") {
    std::vector<dito::TrayMenuItem> items;
    const auto it = args->find(EncodableValue("items"));
    if (it != args->end()) {
      if (const auto* list = std::get_if<EncodableList>(&it->second)) {
        for (const auto& entry : *list) {
          const auto* map = std::get_if<EncodableMap>(&entry);
          if (map == nullptr) continue;
          dito::TrayMenuItem item;
          item.id = GetString(*map, "id");
          item.label = GetString(*map, "label");
          item.enabled = GetBool(*map, "enabled", true);
          item.checked = GetBool(*map, "checked", false);
          item.separator = GetBool(*map, "separator", false);
          item.checkbox = GetBool(*map, "checkbox", false);
          items.push_back(item);
        }
      }
    }
    dito::Tray::Shared().SetMenu(std::move(items));
    result->Success();
    return;
  }

  if (method == "tray.destroy") {
    dito::Tray::Shared().Destroy();
    result->Success();
    return;
  }

  if (method == "notify.balloon") {
    result->Success(EncodableValue(dito::Tray::Shared().ShowBalloon(
        Widen(GetString(*args, "title")), Widen(GetString(*args, "body")))));
    return;
  }

  if (method == "notify.alarmSound") {
    PlaySound(TEXT("SystemExclamation"), nullptr, SND_ALIAS | SND_ASYNC);
    result->Success(EncodableValue(true));
    return;
  }

  if (method == "window.rect") {
    RECT rect{};
    GetWindowRect(RootWindow(), &rect);
    result->Success(EncodableValue(EncodableMap{
        {EncodableValue("left"), EncodableValue(static_cast<int64_t>(rect.left))},
        {EncodableValue("top"), EncodableValue(static_cast<int64_t>(rect.top))},
        {EncodableValue("right"), EncodableValue(static_cast<int64_t>(rect.right))},
        {EncodableValue("bottom"), EncodableValue(static_cast<int64_t>(rect.bottom))},
    }));
    return;
  }

  if (method == "window.handle") {
    result->Success(EncodableValue(EncodableMap{
        {EncodableValue("self"),
         EncodableValue(static_cast<int64_t>(reinterpret_cast<intptr_t>(RootWindow())))},
        {EncodableValue("foreground"),
         EncodableValue(
             static_cast<int64_t>(reinterpret_cast<intptr_t>(GetForegroundWindow())))},
    }));
    return;
  }

  if (method == "window.focus") {
    result->Success(EncodableValue(ForceForeground(RootWindow())));
    return;
  }

  if (method == "window.hide") {
    ShowWindow(RootWindow(), SW_HIDE);
    result->Success();
    return;
  }

  if (method == "window.setBottomCenter") {
    const HWND hwnd = RootWindow();
    if (hwnd == nullptr) {
      result->Error("NO_WINDOW", "sem janela nativa");
      return;
    }
    // Physical pixels, already scaled by Dart: scaling here as well is what shrank the card.
    const double physical_width = GetDouble(*args, "width", 340);
    const double physical_height = GetDouble(*args, "height", 52);
    const double margin = GetDouble(*args, "margin", 32);

    // Place against the work area of the monitor holding the foreground window.
    HWND reference = GetForegroundWindow();
    HMONITOR monitor = MonitorFromWindow(reference != nullptr ? reference : hwnd,
                                         MONITOR_DEFAULTTOPRIMARY);
    MONITORINFO info{};
    info.cbSize = sizeof(MONITORINFO);
    GetMonitorInfo(monitor, &info);

    const int width = static_cast<int>(physical_width);
    const int height = static_cast<int>(physical_height);
    const int margin_px = static_cast<int>(margin + 0.5);

    const int x = (info.rcWork.left + info.rcWork.right) / 2 - width / 2;
    const int y = info.rcWork.bottom - height - margin_px;

    SetWindowPos(hwnd, HWND_TOPMOST, x, y, width, height,
                 SWP_NOACTIVATE | SWP_NOZORDER);
    result->Success(EncodableValue(EncodableMap{
        {EncodableValue("x"), EncodableValue(x)},
        {EncodableValue("y"), EncodableValue(y)},
        {EncodableValue("w"), EncodableValue(width)},
        {EncodableValue("h"), EncodableValue(height)},
    }));
    return;
  }

  if (method == "window.setHitRect") {
    const HWND hwnd = RootWindow();
    if (hwnd == nullptr) {
      result->Error("NO_WINDOW", "sem janela nativa");
      return;
    }
    // The canvas is fixed and mostly transparent; without a region the empty part swallows every click aimed at whatever is behind it.
    const int left = static_cast<int>(GetDouble(*args, "left", 0));
    const int top = static_cast<int>(GetDouble(*args, "top", 0));
    const int width = static_cast<int>(GetDouble(*args, "width", 0));
    const int height = static_cast<int>(GetDouble(*args, "height", 0));
    const int radius = static_cast<int>(GetDouble(*args, "radius", 0));
    if (width <= 0 || height <= 0) {
      SetWindowRgn(hwnd, nullptr, TRUE);
      result->Success(EncodableValue(false));
      return;
    }
    // The region IS the visible shape now, so it carries the content's corner radius.
    HRGN region = radius > 0
        ? CreateRoundRectRgn(left, top, left + width + 1, top + height + 1,
                             radius * 2, radius * 2)
        : CreateRectRgn(left, top, left + width, top + height);
    // Ownership passes to the window, so this must not be deleted here.
    const bool ok = SetWindowRgn(hwnd, region, TRUE) != 0;
    if (!ok) DeleteObject(region);
    result->Success(EncodableValue(ok));
    return;
  }

  if (method == "focus.take") {
    const HWND current = GetForegroundWindow();
    const HWND mine = RootWindow();
    // Never remember ourselves, or two takes in a row give focus back to Dito.
    if (current != nullptr && current != mine) {
      previous_foreground_ = current;
      last_paste_target_ = current;
    }
    result->Success();
    return;
  }

  if (method == "focus.giveBack") {
    const HWND target = previous_foreground_;
    previous_foreground_ = nullptr;
    if (target == nullptr || IsWindow(target) == 0) {
      result->Success(EncodableValue(false));
      return;
    }
    last_paste_target_ = target;
    result->Success(EncodableValue(ForceForeground(target)));
    return;
  }

  result->NotImplemented();
}

}  // namespace dito_win32
