{
  "targets": [
    {
      "target_name": "dito_win32",
      "sources": ["src/addon.cc", "src/input.cc", "src/key_hook.cpp", "src/key_table.cpp"],
      "include_dirs": ["<!@(node -p \"require('node-addon-api').include\")", "src"],
      "defines": ["NAPI_DISABLE_CPP_EXCEPTIONS", "UNICODE", "_UNICODE"],
      "libraries": ["user32.lib"],
      "msvs_settings": {
        "VCCLCompilerTool": { "ExceptionHandling": 1, "AdditionalOptions": ["/std:c++17"] }
      }
    }
  ]
}
