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

`src/input_x11.cc`, `src/key_hook_x11.cpp` e `src/addon_x11.cc` cumprem o **mesmo contrato de 9
funções** sobre X11: `XGrabKey` na janela raiz, `XTest` para digitar, EWMH para achar e ativar a
janela alvo. Escritos na 2.0.10 e compilados pelo bloco `OS=='linux'` do `binding.gyp`.

A tradução API por API do Win32 para o X11, as armadilhas de cada peça e os portões que provam cada
uma estão em `_docs/port-linux/`.

## Regra do Linux

Não editar sem rodar, antes e depois:

```
npm run addon && npm run build && node quality/native.mjs && node quality/hotkey-linux.mjs
```
