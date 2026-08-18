#ifndef FLUTTER_PLUGIN_DITO_WIN32_PLUGIN_H_
#define FLUTTER_PLUGIN_DITO_WIN32_PLUGIN_H_

#include <flutter/event_channel.h>
#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>

#include <memory>

#include "key_hook.h"

namespace dito_win32 {

class DitoWin32Plugin : public flutter::Plugin {
 public:
  static void RegisterWithRegistrar(flutter::PluginRegistrarWindows* registrar);

  explicit DitoWin32Plugin(flutter::PluginRegistrarWindows* registrar);
  ~DitoWin32Plugin() override;

  DitoWin32Plugin(const DitoWin32Plugin&) = delete;
  DitoWin32Plugin& operator=(const DitoWin32Plugin&) = delete;

 private:
  void HandleMethod(const flutter::MethodCall<flutter::EncodableValue>& call,
                    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);

  HWND RootWindow();

  flutter::PluginRegistrarWindows* registrar_;
  std::unique_ptr<flutter::EventChannel<flutter::EncodableValue>> key_channel_;
  std::unique_ptr<flutter::EventSink<flutter::EncodableValue>> key_sink_;
  std::unique_ptr<flutter::EventChannel<flutter::EncodableValue>> tray_channel_;
  std::unique_ptr<flutter::EventSink<flutter::EncodableValue>> tray_sink_;
  dito::KeyHook* hook_ = nullptr;
  int listener_token_ = 0;

  // The window that had the foreground before we took it; never ourselves.
  HWND previous_foreground_ = nullptr;

  // Test-only EDIT control; never used by the product.
  HWND test_edit_ = nullptr;
  int proc_delegate_id_ = -1;
};

}  // namespace dito_win32

#endif  // FLUTTER_PLUGIN_DITO_WIN32_PLUGIN_H_
