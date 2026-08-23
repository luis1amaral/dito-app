# dito-desktop

## Language rule (hard)

- **All code is English**: identifiers, file names, directory names, function names, comments.
- **Only user-visible strings are pt-BR** — window text, labels, log messages shown to the user.
- Docs (`CHANGELOG.md`, `PARIDADE.md`, `PENDENCIAS.md`, `README.md`) stay in pt-BR.
- Comments: English, one line max, and only when they carry a *why* the code cannot.

## What this app is

Voice dictation, nothing else. Press a key, speak, the text is typed where the cursor was.
No agent, no chat, no browser.

## Quality gate

`npm run verify` is the single entry point. Exit 0 PASS, 1 FAIL, 2 INCOMPLETE.
INCOMPLETE is never green. See `quality/PARIDADE.md`.
