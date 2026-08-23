//
//  Generated file. Do not edit.
//

// clang-format off

#include "generated_plugin_registrant.h"

#include <dito_whisper/dito_whisper_plugin.h>
#include <dito_win32/dito_win32_plugin.h>
#include <screen_retriever_linux/screen_retriever_linux_plugin.h>
#include <url_launcher_linux/url_launcher_plugin.h>
#include <window_manager/window_manager_plugin.h>

void fl_register_plugins(FlPluginRegistry* registry) {
  g_autoptr(FlPluginRegistrar) dito_whisper_registrar =
      fl_plugin_registry_get_registrar_for_plugin(registry, "DitoWhisperPlugin");
  dito_whisper_plugin_register_with_registrar(dito_whisper_registrar);
  g_autoptr(FlPluginRegistrar) dito_win32_registrar =
      fl_plugin_registry_get_registrar_for_plugin(registry, "DitoWin32Plugin");
  dito_win32_plugin_register_with_registrar(dito_win32_registrar);
  g_autoptr(FlPluginRegistrar) screen_retriever_linux_registrar =
      fl_plugin_registry_get_registrar_for_plugin(registry, "ScreenRetrieverLinuxPlugin");
  screen_retriever_linux_plugin_register_with_registrar(screen_retriever_linux_registrar);
  g_autoptr(FlPluginRegistrar) url_launcher_linux_registrar =
      fl_plugin_registry_get_registrar_for_plugin(registry, "UrlLauncherPlugin");
  url_launcher_plugin_register_with_registrar(url_launcher_linux_registrar);
  g_autoptr(FlPluginRegistrar) window_manager_registrar =
      fl_plugin_registry_get_registrar_for_plugin(registry, "WindowManagerPlugin");
  window_manager_plugin_register_with_registrar(window_manager_registrar);
}
