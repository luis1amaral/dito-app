// N-API shell over the X11 code. Same exports as addon.cc; only the primitives differ.
#include <napi.h>
#include <unistd.h>

#include <algorithm>
#include <memory>
#include <mutex>
#include <string>

#include "input_x11.h"
#include "key_hook_x11.h"

namespace {

// One name, one owner: a second copy of this string is what broke 2.0.0.
constexpr const char* kAction = "dictation";

Napi::ThreadSafeFunction g_tsfn;
// The hook thread emits while the main thread may be releasing: guard the handle.
std::mutex g_tsfn_mutex;
int g_token = 0;
bool g_running = false;

struct Edge {
  std::string kind;
  std::string action;
  std::string key;
  bool down = false;
};

void Emit(const Edge& e) {
  std::lock_guard<std::mutex> lock(g_tsfn_mutex);
  if (!g_tsfn) return;
  auto* copy = new Edge(e);
  g_tsfn.NonBlockingCall(copy, [](Napi::Env env, Napi::Function cb, Edge* data) {
    std::unique_ptr<Edge> guard(data);
    Napi::Object obj = Napi::Object::New(env);
    obj.Set("kind", data->kind);
    obj.Set("action", data->action);
    obj.Set("key", data->key);
    obj.Set("down", data->down);
    cb.Call({obj});
  });
}

Napi::Value StartHook(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  if (g_running) return Napi::Boolean::New(env, true);
  if (info.Length() < 2 || !info[0].IsString() || !info[1].IsFunction()) {
    Napi::TypeError::New(env, "startHook(key, callback)").ThrowAsJavaScriptException();
    return env.Undefined();
  }
  const std::string key = info[0].As<Napi::String>().Utf8Value();

  g_tsfn = Napi::ThreadSafeFunction::New(env, info[1].As<Napi::Function>(), "ditoHook", 0, 1);

  dito::KeyHookX11& hook = dito::KeyHookX11::Shared();
  hook.UnbindAll();
  if (!hook.Bind(kAction, key)) {
    g_tsfn.Release();
    g_tsfn = Napi::ThreadSafeFunction();
    return Napi::Boolean::New(env, false);
  }

  dito::KeyHookX11::Listener listener;
  listener.on_edge = [](const dito::KeyEdge& edge) {
    Emit({"edge", edge.action, edge.key, edge.down});
  };
  // The physical state, every tick: a swallowed key-up would otherwise leave hold mode stuck on.
  listener.on_tick = [](const dito::KeyTick& tick) {
    const bool down = std::find(tick.down.begin(), tick.down.end(), kAction) != tick.down.end();
    Emit({"tick", kAction, "", down});
  };
  listener.on_hook_status = [](const std::string& status) { Emit({"status", status, "", false}); };
  g_token = hook.AddListener(listener);
  hook.Start();
  g_running = true;
  // The grab happens on the hook thread; reading installed() right after Start() is a race.
  for (int i = 0; i < 100 && !hook.installed(); ++i) usleep(10000);
  return Napi::Boolean::New(env, hook.installed());
}

Napi::Value StopHook(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  if (!g_running) return env.Undefined();
  dito::KeyHookX11& hook = dito::KeyHookX11::Shared();
  hook.RemoveListener(g_token);
  hook.Stop();
  {
    std::lock_guard<std::mutex> lock(g_tsfn_mutex);
    if (g_tsfn) {
      g_tsfn.Release();
      g_tsfn = Napi::ThreadSafeFunction();
    }
  }
  g_running = false;
  return env.Undefined();
}

Napi::Value HookStatus(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  Napi::Object obj = Napi::Object::New(env);
  dito::KeyHookX11& hook = dito::KeyHookX11::Shared();
  obj.Set("installed", hook.installed());
  obj.Set("error", static_cast<double>(hook.install_error()));
  obj.Set("seen", static_cast<double>(hook.seen_count()));
  obj.Set("pumps", static_cast<double>(hook.pump_count()));
  return obj;
}

Napi::Value RememberTargetJs(const Napi::CallbackInfo& info) {
  dito::RememberTarget();
  return info.Env().Undefined();
}

Napi::Value CurrentTarget(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  const Window target = dito::RememberedTarget();
  Napi::Object obj = Napi::Object::New(env);
  obj.Set("hwnd", static_cast<double>(target));
  obj.Set("className", dito::TargetClass(target));
  obj.Set("title", dito::TargetTitle(target));
  obj.Set("kind", std::string(dito::ClassifyTarget(target)));
  return obj;
}

// Incremental typing must never land in a window the person moved to mid-sentence.
Napi::Value TargetIsForeground(const Napi::CallbackInfo& info) {
  return Napi::Boolean::New(info.Env(), dito::TargetIsForeground());
}

// The clipboard is filled by Electron first; see paste() in src/main/native.ts.
Napi::Value Paste(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  if (info.Length() < 1 || !info[0].IsString()) {
    Napi::TypeError::New(env, "paste(text)").ThrowAsJavaScriptException();
    return env.Undefined();
  }
  return Napi::Boolean::New(env, dito::PasteIntoTarget(info[0].As<Napi::String>().Utf8Value()));
}

Napi::Value TypeText(const Napi::CallbackInfo& info) {
  Napi::Env env = info.Env();
  if (info.Length() < 1 || !info[0].IsString()) {
    Napi::TypeError::New(env, "typeText(text)").ThrowAsJavaScriptException();
    return env.Undefined();
  }
  return Napi::Boolean::New(env, dito::SendUnicodeText(info[0].As<Napi::String>().Utf8Value()));
}

Napi::Object Init(Napi::Env env, Napi::Object exports) {
  exports.Set("ACTION", Napi::String::New(env, kAction));
  exports.Set("startHook", Napi::Function::New(env, StartHook));
  exports.Set("stopHook", Napi::Function::New(env, StopHook));
  exports.Set("hookStatus", Napi::Function::New(env, HookStatus));
  exports.Set("rememberTarget", Napi::Function::New(env, RememberTargetJs));
  exports.Set("currentTarget", Napi::Function::New(env, CurrentTarget));
  exports.Set("targetIsForeground", Napi::Function::New(env, TargetIsForeground));
  exports.Set("paste", Napi::Function::New(env, Paste));
  exports.Set("typeText", Napi::Function::New(env, TypeText));
  return exports;
}

}  // namespace

NODE_API_MODULE(dito_linux, Init)
