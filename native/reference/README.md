# Referência de porte

`dito_win32_plugin.cc` é o plugin **X11 do Dito 1.x**, que funcionava: `XGrabKey` com thread
própria, `XTest` para digitar, EWMH para achar e ativar a janela alvo.

Ele está aqui porque foi a base do addon de Linux, escrito na 2.0.10 em `src/input_x11.cc` e
`src/key_hook_x11.cpp`: o trabalho foi **trocar a casca** — o method channel do Flutter virou
N-API — e não reescrever a lógica.

Não é compilado; fica como fonte de consulta. O que cada peça faz, a armadilha de cada uma e como
provar estão em `_docs/port-linux/`.
