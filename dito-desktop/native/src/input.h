#ifndef DITO_INPUT_H_
#define DITO_INPUT_H_

#include <windows.h>

#include <string>

namespace dito {

// Must be called on key DOWN: by the time the card shows, Dito itself is the foreground window.
void RememberTarget();
HWND RememberedTarget();

// How the target accepts text; measured in docs/medicoes/colagem-windows.md.
const char* ClassifyTarget(HWND target);

bool ForceForeground(HWND target);
bool SendUnicodeText(const std::wstring& text);
bool SendKeyStroke(WORD vk, bool ctrl);
bool SetClipboardText(const std::wstring& text);

// Pastes into the remembered target, picking the method from the window class.
bool PasteIntoTarget(const std::wstring& text);

std::wstring Widen(const std::string& utf8);

}  // namespace dito

#endif  // DITO_INPUT_H_
