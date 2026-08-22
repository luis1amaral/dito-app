#include "include/dito_win32/dito_win32_plugin_c_api.h"

#include <flutter/plugin_registrar_windows.h>

#include "dito_win32_plugin.h"

void DitoWin32PluginCApiRegisterWithRegistrar(
    FlutterDesktopPluginRegistrarRef registrar) {
  dito_win32::DitoWin32Plugin::RegisterWithRegistrar(
      flutter::PluginRegistrarManager::GetInstance()
          ->GetRegistrar<flutter::PluginRegistrarWindows>(registrar));
}
