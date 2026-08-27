#ifndef DITO_KEY_HOOK_X11_H_
#define DITO_KEY_HOOK_X11_H_

#include <X11/Xlib.h>

#include <atomic>
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

// XGrabKey on the root window delivers press/release without root or the input group.
class KeyHookX11 {
 public:
  static KeyHookX11& Shared();

  KeyHookX11();
  ~KeyHookX11();

  bool Bind(const std::string& action, const std::string& key);
  void UnbindAll();

  void Start();
  void Stop();

  bool installed() const { return installed_.load(); }
  int install_error() const { return install_error_.load(); }
  int64_t seen_count() const { return seen_count_.load(); }
  int64_t pump_count() const { return pump_count_.load(); }

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
    KeyCode code = 0;
    // Detectable auto-repeat still fires KeyPress while held; only a real change is an edge.
    bool last_down = false;
  };

  void ThreadMain();
  void EmitEdge(const KeyEdge& edge);
  void EmitTick(const KeyTick& tick);
  void EmitStatus(const std::string& status);

  std::thread thread_;
  std::atomic<bool> running_{false};
  std::atomic<bool> installed_{false};
  std::atomic<int> install_error_{0};
  std::atomic<int64_t> seen_count_{0};
  std::atomic<int64_t> pump_count_{0};
  int wake_pipe_[2] = {-1, -1};

  std::mutex bindings_mutex_;
  std::vector<Binding> bindings_;

  std::mutex listeners_mutex_;
  std::map<int, Listener> listeners_;
  int next_token_ = 1;
};

}  // namespace dito

#endif  // DITO_KEY_HOOK_X11_H_
