#ifndef DITO_WIN32_KEY_HOOK_H_
#define DITO_WIN32_KEY_HOOK_H_

#include <windows.h>

#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace dito {

struct KeyEdge {
  std::string action;
  std::string key;
  bool down;
  int64_t micros;
};

struct KeyTick {
  std::vector<std::string> down;
  int64_t micros;
};

// Low-level keyboard hook on a thread of its own, with its own message loop.
//
// It must never run on the main thread: that thread serves the message loop of every Flutter
// engine, and a hook there gets throttled by LowLevelHooksTimeout and silently uninstalled.
class KeyHook {
 public:
  // One hook per PROCESS, not per window. Every Flutter window instantiates the plugin
  // again, and a per-instance hook meant the last window created won the static pointer
  // while the bindings lived on the first one: installed, pumping, and blind.
  static KeyHook& Shared();

  KeyHook();
  ~KeyHook();

  void Start();
  void Stop();

  // Bind an action name to a key; hold and toggle differ only in Dart.
  bool Bind(const std::string& action, const std::string& key, bool suppress);
  void UnbindAll();

  void Pause();
  void Resume();
  bool paused() const { return paused_; }

  // Physical state of every bound key, hook table first.
  std::map<std::string, bool> Snapshot();

  // Diagnostics: how many key events the hook saw at all, and whether it is installed.
  int64_t seen_count() const { return seen_count_; }
  int64_t pump_count() const { return pump_count_; }
  DWORD install_error() const { return install_error_; }
  bool installed() const { return hook_ != nullptr; }

  // Test-only: drives SendInput so the suite can prove hook plus suppression together.
  UINT InjectForTest(UINT vk, bool down);

  // A list, not a single callback: every window instantiates the plugin, and a lone
  // callback means the last window created silently steals the events from the first.
  struct Listener {
    std::function<void(const KeyEdge&)> on_edge;
    std::function<void(const KeyTick&)> on_tick;
    std::function<void(const std::string&)> on_hook_status;
  };

  int AddListener(Listener listener);
  void RemoveListener(int token);

  static int64_t NowMicros();

 private:
  struct Binding {
    std::string action;
    std::string key;
    UINT vk;
    bool suppress;
  };

  void ThreadMain();
  LRESULT HandleKey(int code, WPARAM wparam, LPARAM lparam);
  static LRESULT CALLBACK HookProc(int code, WPARAM wparam, LPARAM lparam);
  bool AnyEngaged();

  // Drains what the hook queued; runs on the message loop, never inside the hook.
  void DrainEdges();

  // The hook is the authority: a swallowed key reads as up in GetAsyncKeyState forever.
  bool IsDown(const Binding& binding);

  std::thread thread_;
  DWORD thread_id_ = 0;
  HHOOK hook_ = nullptr;
  UINT_PTR timer_ = 0;
  bool running_ = false;
  bool paused_ = false;
  int64_t last_engaged_micros_ = 0;
  int64_t seen_count_ = 0;
  int64_t pump_count_ = 0;
  DWORD install_error_ = 0;

  std::mutex mutex_;
  std::vector<Binding> bindings_;
  std::map<UINT, bool> seen_;

  std::mutex queue_mutex_;
  std::deque<KeyEdge> queue_;

  std::mutex listeners_mutex_;
  std::map<int, Listener> listeners_;
  int next_token_ = 1;

  static KeyHook* instance_;
};

}  // namespace dito

#endif  // DITO_WIN32_KEY_HOOK_H_
