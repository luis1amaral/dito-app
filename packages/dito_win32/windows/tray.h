#ifndef DITO_WIN32_TRAY_H_
#define DITO_WIN32_TRAY_H_

#include <windows.h>

#include <functional>
#include <string>
#include <vector>

namespace dito {

struct TrayMenuItem {
  std::string id;
  std::string label;
  bool enabled = true;
  bool checked = false;
  bool separator = false;
  bool checkbox = false;
};

// Owns the tray icon outright: icon, tooltip, menu and balloon in one place.
//
// Two owners for one icon is why the balloon used to fail silently — Shell_NotifyIcon
// modifies by (hwnd, uID), and a second library's icon is not ours to modify.
class Tray {
 public:
  static Tray& Shared();

  bool Create(const std::wstring& tooltip);
  bool SetIcon(const std::wstring& path);
  bool SetTooltip(const std::wstring& tooltip);
  void SetMenu(std::vector<TrayMenuItem> items);
  bool ShowBalloon(const std::wstring& title, const std::wstring& body);
  void Destroy();

  std::function<void(const std::string&)> on_menu;
  std::function<void()> on_click;

 private:
  static LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM w, LPARAM l);
  void ShowMenu();

  HWND window_ = nullptr;
  HICON icon_ = nullptr;
  bool created_ = false;
  std::vector<TrayMenuItem> items_;
};

}  // namespace dito

#endif  // DITO_WIN32_TRAY_H_
