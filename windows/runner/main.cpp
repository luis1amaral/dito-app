#include <desktop_multi_window/desktop_multi_window_plugin.h>
#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <shobjidl.h>
#include <windows.h>

#include "flutter/generated_plugin_registrant.h"
#include "flutter_window.h"
#include "utils.h"

// Sub-windows get their own engine; without this they have no plugin channels at all.
void RegisterPluginsInSubWindow(void *controller) {
  auto *view_controller =
      reinterpret_cast<flutter::FlutterViewController *>(controller);
  RegisterPlugins(view_controller->engine());
}

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // A zombie instance with grab=true swallows F9/F10 before the new one; never run two.
  ::CreateMutexW(nullptr, TRUE, L"Local\\DitoSingleInstance");
  if (::GetLastError() == ERROR_ALREADY_EXISTS) {
    HWND existing = ::FindWindowW(L"FLUTTER_RUNNER_WIN32_WINDOW", L"Dito");
    if (existing) {
      ::ShowWindow(existing, SW_RESTORE);
      ::SetForegroundWindow(existing);
    }
    return EXIT_SUCCESS;
  }

  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  // Without this the shell labels our notifications with the executable name.
  ::SetCurrentProcessExplicitAppUserModelID(L"com.defalt.dito");

  DesktopMultiWindowSetWindowCreatedCallback(RegisterPluginsInSubWindow);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Point origin(10, 10);
  Win32Window::Size size(1280, 720);
  if (!window.Create(L"Dito", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(false);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  return EXIT_SUCCESS;
}
