# Referência de porte

`dito_win32_plugin.cc` é o plugin **X11 do Dito 1.x**, que funcionava: `XGrabKey` com thread
própria, `XTest` para digitar, EWMH para achar e ativar a janela alvo.

Ele está aqui porque é a base do addon de Linux que falta escrever (`src/input_x11.cc` e
`src/key_hook_x11.cpp`, já declarados no `binding.gyp`). O trabalho é **trocar a casca** — o
method channel do Flutter vira N-API — e não reescrever a lógica.

Não é compilado. Ver `PENDENCIAS.md` para o que cada peça precisa e a armadilha de cada uma.
