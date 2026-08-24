{
  "variables": {
    "conditions": [
      ["OS=='win'", { "dito_module%": "dito_win32" }],
      ["OS!='win'", { "dito_module%": "dito_linux" }]
    ]
  },
  "targets": [
    {
      "target_name": "<(dito_module)",
      "include_dirs": ["<!@(node -p \"require('node-addon-api').include\")", "src"],
      "defines": ["NAPI_DISABLE_CPP_EXCEPTIONS"],
      "conditions": [
        ["OS=='win'", {
          "sources": ["src/addon.cc", "src/input.cc", "src/key_hook.cpp", "src/key_table.cpp"],
          "defines": ["UNICODE", "_UNICODE"],
          "libraries": ["user32.lib"],
          "msvs_settings": {
            "VCCLCompilerTool": { "ExceptionHandling": 1, "AdditionalOptions": ["/std:c++17"] }
          }
        }],
        ["OS=='linux'", {
          "sources": ["src/addon_x11.cc", "src/input_x11.cc", "src/key_hook_x11.cpp"],
          "libraries": ["-lX11", "-lXtst", "-lXi"],
          "cflags_cc": ["-std=c++17", "-fexceptions"]
        }]
      ]
    }
  ]
}
