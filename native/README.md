# native/ — código importado e congelado

`key_hook.cpp`, `key_table.cpp` e `input.cc` vieram inteiros de
`dito-app/packages/dito_win32/windows`. Eles funcionam e **não devem ser reescritos**.

## As duas armadilhas que este código carrega

1. **`WH_KEYBOARD_LL` precisa de thread própria com message pump próprio.** Na thread principal o
   Windows desinstala o hook em silêncio por `LowLevelHooksTimeout`.
2. **Tecla suprimida lê como solta no `GetAsyncKeyState` para sempre.** Por isso `IsDown` confia na
   tabela do hook, e por isso existe o timer de 50 ms — sem ele o modo segurar fica preso.

## Regra

Não editar sem rodar, antes e depois:

```
npm run addon && npm run build && npx electron-builder --win --dir && node quality/hold.mjs
```

`ACTION` é exportado pelo addon de propósito: a string existia em dois lugares e dessincronizou —
foi o defeito que quebrou a 2.0.0.

## Linux

`binding.gyp` já tem o bloco `OS=='linux'`, apontando para `src/input_x11.cc` e
`src/key_hook_x11.cpp` — **que ainda não existem**. O que precisa ser escrito, e a armadilha de
cada peça, está em `PENDENCIAS.md`. A referência de porte é
`dito-app/packages/dito_win32/linux/dito_win32_plugin.cc` (1.687 linhas, já funciona).
