#include "tray.h"

#include <shellapi.h>

namespace dito {

namespace {
constexpr UINT kTrayMessage = WM_APP + 1;
constexpr UINT kIconId = 1;
constexpr UINT kFirstCommand = 40000;
const wchar_t* kClassName = L"DitoTrayHost";
}  // namespace

Tray& Tray::Shared() {
  static Tray* shared = new Tray();
  return *shared;
}

LRESULT CALLBACK Tray::WndProc(HWND hwnd, UINT message, WPARAM w, LPARAM l) {
  auto* self = reinterpret_cast<Tray*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
  if (self == nullptr) return DefWindowProc(hwnd, message, w, l);

  if (message == kTrayMessage) {
    const UINT event = LOWORD(l);
    if (event == WM_LBUTTONUP || event == WM_LBUTTONDBLCLK) {
      if (self->on_click) self->on_click();
    } else if (event == WM_RBUTTONUP || event == WM_CONTEXTMENU) {
      self->ShowMenu();
    }
    return 0;
  }

  if (self->taskbar_created_ != 0 && message == self->taskbar_created_) {
    // Explorer came back and dropped every icon; ours only returns if we re-add it.
    self->AddIcon();
    return 0;
  }

  if (message == WM_COMMAND) {
    const UINT index = LOWORD(w) - kFirstCommand;
    if (index < self->items_.size() && self->on_menu) {
      self->on_menu(self->items_[index].id);
    }
    return 0;
  }

  return DefWindowProc(hwnd, message, w, l);
}

bool Tray::Create(const std::wstring& tooltip) {
  if (created_) return true;

  WNDCLASSEX wc{};
  wc.cbSize = sizeof(WNDCLASSEX);
  wc.lpfnWndProc = &Tray::WndProc;
  wc.hInstance = GetModuleHandle(nullptr);
  wc.lpszClassName = kClassName;
  RegisterClassEx(&wc);

  // Top level, never shown: HWND_MESSAGE would be tidier but message-only windows are cut out
  // of broadcasts, and TaskbarCreated is a broadcast. WS_EX_TOOLWINDOW keeps it out of Alt+Tab.
  window_ = CreateWindowEx(WS_EX_TOOLWINDOW, kClassName, L"", WS_POPUP, 0, 0, 0, 0, nullptr,
                           nullptr, GetModuleHandle(nullptr), nullptr);
  if (window_ == nullptr) return false;
  SetWindowLongPtr(window_, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(this));

  taskbar_created_ = RegisterWindowMessage(L"TaskbarCreated");
  tooltip_ = tooltip;

  created_ = AddIcon();
  return created_;
}

bool Tray::AddIcon() {
  NOTIFYICONDATA data{};
  data.cbSize = sizeof(NOTIFYICONDATA);
  data.hWnd = window_;
  data.uID = kIconId;
  data.uFlags = NIF_MESSAGE | NIF_TIP | NIF_ICON;
  data.uCallbackMessage = kTrayMessage;
  data.hIcon = icon_ != nullptr ? icon_ : LoadIcon(nullptr, IDI_APPLICATION);
  wcsncpy_s(data.szTip, tooltip_.c_str(), _TRUNCATE);
  return Shell_NotifyIcon(NIM_ADD, &data) != 0;
}

bool Tray::SetIcon(const std::wstring& path) {
  if (!created_) return false;

  HICON loaded = static_cast<HICON>(
      LoadImage(nullptr, path.c_str(), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE));
  if (loaded == nullptr) return false;

  NOTIFYICONDATA data{};
  data.cbSize = sizeof(NOTIFYICONDATA);
  data.hWnd = window_;
  data.uID = kIconId;
  data.uFlags = NIF_ICON;
  data.hIcon = loaded;

  const bool ok = Shell_NotifyIcon(NIM_MODIFY, &data) != 0;
  if (ok) {
    if (icon_ != nullptr) DestroyIcon(icon_);
    icon_ = loaded;
  } else {
    DestroyIcon(loaded);
  }
  return ok;
}

bool Tray::SetTooltip(const std::wstring& tooltip) {
  if (!created_) return false;
  NOTIFYICONDATA data{};
  data.cbSize = sizeof(NOTIFYICONDATA);
  data.hWnd = window_;
  data.uID = kIconId;
  data.uFlags = NIF_TIP;
  wcsncpy_s(data.szTip, tooltip.c_str(), _TRUNCATE);
  const bool ok = Shell_NotifyIcon(NIM_MODIFY, &data) != 0;
  if (ok) tooltip_ = tooltip;
  return ok;
}

void Tray::SetMenu(std::vector<TrayMenuItem> items) { items_ = std::move(items); }

void Tray::ShowMenu() {
  if (items_.empty()) return;

  HMENU menu = CreatePopupMenu();
  for (size_t i = 0; i < items_.size(); i++) {
    const TrayMenuItem& item = items_[i];
    if (item.separator) {
      AppendMenu(menu, MF_SEPARATOR, 0, nullptr);
      continue;
    }
    UINT flags = MF_STRING;
    if (!item.enabled) flags |= MF_GRAYED;
    if (item.checkbox && item.checked) flags |= MF_CHECKED;

    const int size = MultiByteToWideChar(CP_UTF8, 0, item.label.data(),
                                         static_cast<int>(item.label.size()), nullptr, 0);
    std::wstring label;
    label.resize(static_cast<size_t>(size));
    MultiByteToWideChar(CP_UTF8, 0, item.label.data(),
                        static_cast<int>(item.label.size()), label.data(), size);

    AppendMenu(menu, flags, kFirstCommand + i, label.c_str());
  }

  POINT cursor;
  GetCursorPos(&cursor);
  // Foreground first, or the menu never closes when the user clicks elsewhere.
  SetForegroundWindow(window_);
  TrackPopupMenu(menu, TPM_RIGHTBUTTON, cursor.x, cursor.y, 0, window_, nullptr);
  PostMessage(window_, WM_NULL, 0, 0);
  DestroyMenu(menu);
}

bool Tray::ShowBalloon(const std::wstring& title, const std::wstring& body) {
  if (!created_) return false;
  NOTIFYICONDATA data{};
  data.cbSize = sizeof(NOTIFYICONDATA);
  data.hWnd = window_;
  data.uID = kIconId;
  data.uFlags = NIF_INFO;

  // NIIF_USER shows OUR icon instead of the system warning triangle; NIIF_NOSOUND keeps it silent, since Dito has its own sound and switch.
  data.dwInfoFlags = NIIF_USER | NIIF_NOSOUND | NIIF_LARGE_ICON;
  data.hBalloonIcon = icon_;

  wcsncpy_s(data.szInfoTitle, title.c_str(), _TRUNCATE);
  wcsncpy_s(data.szInfo, body.c_str(), _TRUNCATE);
  return Shell_NotifyIcon(NIM_MODIFY, &data) != 0;
}

void Tray::Destroy() {
  if (!created_) return;
  NOTIFYICONDATA data{};
  data.cbSize = sizeof(NOTIFYICONDATA);
  data.hWnd = window_;
  data.uID = kIconId;
  Shell_NotifyIcon(NIM_DELETE, &data);
  if (icon_ != nullptr) DestroyIcon(icon_);
  if (window_ != nullptr) DestroyWindow(window_);
  icon_ = nullptr;
  window_ = nullptr;
  created_ = false;
}

}  // namespace dito
