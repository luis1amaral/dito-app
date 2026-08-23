{
  "targets": [
    {
      "target_name": "dito_win32",
      "sources": ["src/addon.cc"],
      "include_dirs": ["<!@(node -p \"require('node-addon-api').include\")", "src"],
      "defines": ["NAPI_DISABLE_CPP_EXCEPTIONS"],
      "conditions": [
        ["OS=='win'", {
          "sources": ["src/input.cc", "src/key_hook.cpp", "src/key_table.cpp"],
          "defines": ["UNICODE", "_UNICODE"],
          "libraries": ["user32.lib"],
          "msvs_settings": {
            "VCCLCompilerTool": { "ExceptionHandling": 1, "AdditionalOptions": ["/std:c++17"] }
          }
        }],
        ["OS=='linux'", {
          "sources": ["src/input_x11.cc", "src/key_hook_x11.cpp"],
          "libraries": ["-lX11", "-lXtst"],
          "cflags_cc": ["-std=c++17", "-fexceptions"]
        }]
      ]
    }
  ]
}
