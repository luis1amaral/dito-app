#include "key_hook.h"

#include "key_table.h"

namespace dito {

namespace {
// One poll interval, matching POLL_S in src/dito/platform/hotkeys_core.py.
constexpr UINT kTickMs = 50;
constexpr UINT_PTR kTimerId = 1;
// Tick past the release long enough for Dart's 300 ms grace to see the key up.
constexpr int64_t kTailMicros = 500000;
}  // namespace

KeyHook* KeyHook::instance_ = nullptr;

KeyHook& KeyHook::Shared() {
  static KeyHook* shared = new KeyHook();
  return *shared;
}

KeyHook::KeyHook() { instance_ = this; }

KeyHook::~KeyHook() {
  Stop();
  instance_ = nullptr;
}

int64_t KeyHook::NowMicros() {
  static LARGE_INTEGER frequency = [] {
    LARGE_INTEGER f;
    QueryPerformanceFrequency(&f);
    return f;
  }();
  LARGE_INTEGER counter;
  QueryPerformanceCounter(&counter);
  return static_cast<int64_t>(counter.QuadPart * 1000000LL / frequency.QuadPart);
}

void KeyHook::Start() {
  if (running_) return;
  running_ = true;
  thread_ = std::thread(&KeyHook::ThreadMain, this);
}

void KeyHook::Stop() {
  if (!running_) return;
  running_ = false;
  if (thread_id_ != 0) {
    PostThreadMessage(thread_id_, WM_QUIT, 0, 0);
  }
  if (thread_.joinable()) thread_.join();
  thread_id_ = 0;
}

void KeyHook::ThreadMain() {
  thread_id_ = GetCurrentThreadId();

  // The proc lives in this DLL, so the module must be THIS DLL: passing the exe's handle
  // installs a hook that is never called.
  HMODULE module = nullptr;
  GetModuleHandleExW(
      GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
          GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
      reinterpret_cast<LPCWSTR>(&KeyHook::HookProc), &module);

  hook_ = SetWindowsHookEx(WH_KEYBOARD_LL, &KeyHook::HookProc, module, 0);
  install_error_ = hook_ == nullptr ? GetLastError() : 0;

  timer_ = SetTimer(nullptr, kTimerId, kTickMs, nullptr);

  MSG msg;
  while (running_ && GetMessage(&msg, nullptr, 0, 0) > 0) {
    pump_count_++;
    DrainEdges();

    if (msg.message == WM_TIMER) {
      const int64_t now = NowMicros();
      const bool engaged = AnyEngaged();
      if (engaged) last_engaged_micros_ = now;

      // Keep ticking past the release, or Dart never sees the key come up.
      if (engaged || now - last_engaged_micros_ < kTailMicros) {
        KeyTick tick;
        tick.micros = now;
        for (const auto& [action, down] : Snapshot()) {
          if (down) tick.down.push_back(action);
        }
          std::vector<Listener> targets;
        {
          std::lock_guard<std::mutex> lock(listeners_mutex_);
          for (const auto& [token, listener] : listeners_) targets.push_back(listener);
        }
        for (const auto& listener : targets) {
          if (listener.on_tick) listener.on_tick(tick);
        }
      }
    }
    TranslateMessage(&msg);
    DispatchMessage(&msg);
  }

  if (timer_ != 0) KillTimer(nullptr, timer_);
  if (hook_ != nullptr) UnhookWindowsHookEx(hook_);
  hook_ = nullptr;
  timer_ = 0;
}

LRESULT CALLBACK KeyHook::HookProc(int code, WPARAM wparam, LPARAM lparam) {
  if (instance_ == nullptr) return CallNextHookEx(nullptr, code, wparam, lparam);
  return instance_->HandleKey(code, wparam, lparam);
}

LRESULT KeyHook::HandleKey(int code, WPARAM wparam, LPARAM lparam) {
  if (code != HC_ACTION) return CallNextHookEx(nullptr, code, wparam, lparam);

  seen_count_++;

  const auto* info = reinterpret_cast<KBDLLHOOKSTRUCT*>(lparam);
  const bool down = wparam == WM_KEYDOWN || wparam == WM_SYSKEYDOWN;
  const bool up = wparam == WM_KEYUP || wparam == WM_SYSKEYUP;
  if (!down && !up) return CallNextHookEx(nullptr, code, wparam, lparam);

  Binding match;
  bool found = false;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto& binding : bindings_) {
      if (binding.vk == info->vkCode) {
        match = binding;
        found = true;
        break;
      }
    }
    if (found) seen_[info->vkCode] = down;
  }
  if (!found) return CallNextHookEx(nullptr, code, wparam, lparam);

  if (paused_) return CallNextHookEx(nullptr, code, wparam, lparam);

  // Only queue and return. Calling into Flutter from here can exceed LowLevelHooksTimeout,
  // and Windows then uninstalls the hook silently: installed, pumping, and blind.
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    queue_.push_back(KeyEdge{match.action, match.key, down, NowMicros()});
    if (queue_.size() > 256) queue_.pop_front();
  }

  if (match.suppress) return 1;
  return CallNextHookEx(nullptr, code, wparam, lparam);
}

bool KeyHook::Bind(const std::string& action, const std::string& key, bool suppress) {
  const UINT vk = VkFromName(key);
  if (vk == 0) return false;
  std::lock_guard<std::mutex> lock(mutex_);
  bindings_.push_back(Binding{action, key, vk, suppress});
  // Always up. GetAsyncKeyState reports F10 as held when nothing is touching it, and seeding
  // from it booted the app believing a meeting was already running: F9 got refused and F10
  // never produced a rising edge. The hook's own edges are the only authority.
  seen_[vk] = false;
  return true;
}

void KeyHook::UnbindAll() {
  std::lock_guard<std::mutex> lock(mutex_);
  bindings_.clear();
  seen_.clear();
}

// Pause keeps the hook alive and only stops acting: tearing it down with a key held
// loses the release and leaves the action stuck forever.
void KeyHook::Pause() { paused_ = true; }

void KeyHook::Resume() { paused_ = false; }

bool KeyHook::IsDown(const Binding& binding) {
  // A suppressed key reads as up in GetAsyncKeyState forever, so the hook table wins.
  const auto it = seen_.find(binding.vk);
  if (it != seen_.end()) return it->second;
  return (GetAsyncKeyState(static_cast<int>(binding.vk)) & 0x8000) != 0;
}

std::map<std::string, bool> KeyHook::Snapshot() {
  std::lock_guard<std::mutex> lock(mutex_);
  std::map<std::string, bool> out;
  for (const auto& binding : bindings_) {
    out[binding.action] = IsDown(binding);
  }
  return out;
}

int KeyHook::AddListener(Listener listener) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  const int token = next_token_++;
  listeners_[token] = std::move(listener);
  return token;
}

void KeyHook::RemoveListener(int token) {
  std::lock_guard<std::mutex> lock(listeners_mutex_);
  listeners_.erase(token);
}

void KeyHook::DrainEdges() {
  std::deque<KeyEdge> batch;
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    batch.swap(queue_);
  }
  if (batch.empty()) return;

  std::vector<Listener> targets;
  {
    std::lock_guard<std::mutex> lock(listeners_mutex_);
    for (const auto& [token, listener] : listeners_) targets.push_back(listener);
  }
  for (const auto& edge : batch) {
    for (const auto& listener : targets) {
      if (listener.on_edge) listener.on_edge(edge);
    }
  }
}

bool KeyHook::AnyEngaged() {
  std::lock_guard<std::mutex> lock(mutex_);
  for (const auto& binding : bindings_) {
    if (IsDown(binding)) return true;
  }
  return false;
}

UINT KeyHook::InjectForTest(UINT vk, bool down) {
  INPUT input{};
  input.type = INPUT_KEYBOARD;
  input.ki.wVk = static_cast<WORD>(vk);
  input.ki.dwFlags = down ? 0 : KEYEVENTF_KEYUP;
  return SendInput(1, &input, sizeof(INPUT));
}

}  // namespace dito
