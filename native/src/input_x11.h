#ifndef DITO_INPUT_X11_H_
#define DITO_INPUT_X11_H_

#include <X11/Xlib.h>

#include <string>

namespace dito {

// Must be called on key DOWN: by the time the pill shows, the active window may have changed.
void RememberTarget();
// Called from the hook thread, which owns a different connection.
void RememberTargetWith(Display* dpy);
Window RememberedTarget();

// "gui" pastes with Ctrl+V, "terminal" with Ctrl+Shift+V, "console" is typed key by key.
const char* ClassifyTarget(Window target);

bool TargetIsForeground();
std::string TargetClass(Window target);
std::string TargetTitle(Window target);

// Types the text through XTest, remapping a spare keycode so pt-BR accents survive.
bool SendUnicodeText(const std::string& utf8);
bool SendKeyStroke(const char* keysym_name, bool ctrl, bool shift);

// Pastes into the remembered target, picking the method from its window class.
// The clipboard is filled by Electron before this runs; see src/main/native.ts.
bool PasteIntoTarget(const std::string& utf8);

void CloseInputDisplay();

}  // namespace dito

#endif  // DITO_INPUT_X11_H_
