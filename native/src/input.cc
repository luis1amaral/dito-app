// Ported from packages/dito_win32/windows/dito_win32_plugin.cpp: same logic, no Flutter.
#include "input.h"

#include <atomic>
#include <vector>

namespace dito {
namespace {

// Written on the hook thread (key down) and read on the main thread (paste).
std::atomic<HWND> g_target{nullptr};

}  // namespace

std::wstring Widen(const std::string& utf8) {
  if (utf8.empty()) return std::wstring();
  const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()), nullptr, 0);
  std::wstring out;
  out.resize(static_cast<size_t>(size));
  MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()), out.data(), size);
  return out;
}

void RememberTarget() {
  const HWND atual = GetForegroundWindow();
  if (atual != nullptr && IsWindow(atual) != 0) g_target.store(atual, std::memory_order_relaxed);
}

HWND RememberedTarget() { return g_target.load(std::memory_order_relaxed); }

// Windows only grants the foreground to whoever already has it; attaching input borrows that.
bool ForceForeground(HWND target) {
  if (target == nullptr || IsWindow(target) == 0) return false;
  if (SetForegroundWindow(target) != 0) return true;

  const DWORD owner = GetWindowThreadProcessId(GetForegroundWindow(), nullptr);
  const DWORD mine = GetCurrentThreadId();
  if (owner == 0 || owner == mine) return false;

  AttachThreadInput(mine, owner, TRUE);
  const bool ok = SetForegroundWindow(target) != 0;
  AttachThreadInput(mine, owner, FALSE);
  return ok;
}

const char* ClassifyTarget(HWND target) {
  if (target == nullptr || IsWindow(target) == 0) return "gui";
  wchar_t cls[256] = {};
  if (GetClassNameW(target, cls, 256) == 0) return "gui";
  const std::wstring name(cls);
  // Only conhost is broken: with PROCESSED_INPUT off it hands Ctrl+V to the app as 0x16.
  if (name == L"ConsoleWindowClass") return "console";
  if (name == L"CASCADIA_HOSTING_WINDOW_CLASS" || name == L"mintty") return "terminal";
  return "gui";
}

// Types UTF-16 units: the scan code IS the character, so pt-BR accents survive exactly.
bool SendUnicodeText(const std::wstring& text) {
  if (text.empty()) return false;
  std::vector<INPUT> inputs;
  inputs.reserve(text.size() * 2);
  for (const wchar_t ch : text) {
    INPUT down{};
    down.type = INPUT_KEYBOARD;
    down.ki.wScan = ch;
    down.ki.dwFlags = KEYEVENTF_UNICODE;
    INPUT up = down;
    up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
    inputs.push_back(down);
    inputs.push_back(up);
  }
  return SendInput(static_cast<UINT>(inputs.size()), inputs.data(), sizeof(INPUT)) == inputs.size();
}

bool SendKeyStroke(WORD vk, bool ctrl) {
  INPUT inputs[4]{};
  int n = 0;
  if (ctrl) {
    inputs[n].type = INPUT_KEYBOARD;
    inputs[n++].ki.wVk = VK_CONTROL;
  }
  inputs[n].type = INPUT_KEYBOARD;
  inputs[n++].ki.wVk = vk;
  inputs[n].type = INPUT_KEYBOARD;
  inputs[n].ki.wVk = vk;
  inputs[n++].ki.dwFlags = KEYEVENTF_KEYUP;
  if (ctrl) {
    inputs[n].type = INPUT_KEYBOARD;
    inputs[n].ki.wVk = VK_CONTROL;
    inputs[n++].ki.dwFlags = KEYEVENTF_KEYUP;
  }
  return SendInput(n, inputs, sizeof(INPUT)) == static_cast<UINT>(n);
}

// OpenClipboard fails while another process holds it; retrying is what fixes it.
bool SetClipboardText(const std::wstring& text) {
  for (int i = 0; i < 10; ++i) {
    if (OpenClipboard(nullptr) != 0) {
      bool ok = false;
      EmptyClipboard();
      const size_t bytes = (text.size() + 1) * sizeof(wchar_t);
      if (HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE, bytes)) {
        if (void* dest = GlobalLock(memory)) {
          memcpy(dest, text.c_str(), bytes);
          GlobalUnlock(memory);
          ok = SetClipboardData(CF_UNICODETEXT, memory) != nullptr;
        }
        if (!ok) GlobalFree(memory);
      }
      CloseClipboard();
      return ok;
    }
    Sleep(20);
  }
  return false;
}

// SetForegroundWindow returns before the switch; typing early sent text to the wrong window.
bool WaitForForeground(HWND target, int timeout_ms) {
  for (int waited = 0; waited < timeout_ms; waited += 20) {
    if (GetForegroundWindow() == target) return true;
    Sleep(20);
  }
  return GetForegroundWindow() == target;
}

bool PasteIntoTarget(const std::wstring& text) {
  if (text.empty()) return false;
  const HWND target = RememberedTarget();
  if (!ForceForeground(target)) return false;
  if (!WaitForForeground(target, 600)) return false;

  const std::string tipo = ClassifyTarget(target);
  if (tipo == "console") {
    // conhost with PROCESSED_INPUT off never pastes on Ctrl+V; typing is what lands.
    return SendUnicodeText(text);
  }
  if (!SetClipboardText(text)) return SendUnicodeText(text);
  return SendKeyStroke('V', true);
}

}  // namespace dito
