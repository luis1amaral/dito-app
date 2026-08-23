# Gate 2: paste into a raw console. The injection logic came whole from the plugin that already
# worked (packages/dito_win32/windows); the readback uses quality/raw-target.mjs.
node "$PSScriptRoot/paste-wiring.mjs"
exit $LASTEXITCODE
