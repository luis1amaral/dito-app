# Dito

## Language rule (hard)

- **All code is English**: identifiers, file names, directory names, function names, comments.
- **Only user-visible strings are pt-BR** — window text, labels, log messages shown to the user.
- Docs (`CHANGELOG.md`, `README.md` and everything in `_docs/`) stay in pt-BR.
- Comments: English, one line max, and only when they carry a *why* the code cannot.

## What this app is

Voice dictation, nothing else. Press a key, speak, the text is typed where the cursor was.
No agent, no chat, no browser.

## Quality gate

`npm run verify` is the single entry point. Exit 0 PASS, 1 FAIL, 2 INCOMPLETE.
INCOMPLETE is never green. See `_docs/PARIDADE.md`.

Every new gate must be proven **both ways**: put the defect back and require it to fail.
A gate that has never failed is not a gate.

## Windows on screen

The pill re-asserts `alwaysOnTop('screen-saver')` every time it shows. Inside the topmost band
the last window to set it wins, so an app that goes always-on-top after us (a Meet call, a game
overlay) would cover it otherwise.
