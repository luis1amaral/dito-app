# Herança do Dito 1.x

Estes arquivos vieram do Dito em Flutter, que foi substituído pelo Dito 2.x em Electron. Eles não
descrevem o código atual — descrevem **defeitos que já aconteceram de verdade**, com sintoma, causa
provada e a regra que impede a reincidência. É a parte do projeto antigo que não podia se perder.

| Arquivo | O que é |
|---|---|
| `armadilhas.md` | O arquivo mais valioso do projeto antigo. Cada entrada é um defeito real, medido |
| `colagem-windows-medido.md` | A medição que prova por que só `SendInput` UNICODE cola no conhost |
| `REGRAS.md` | Como se trabalha aqui: nada é pronto sem o binário subir, portão que nunca reprovou não é portão |

Muitas armadilhas continuam valendo porque são do Windows, não do Flutter: o hook de teclado precisa
de thread própria, tecla suprimida some do `GetAsyncKeyState`, e o conhost em modo cru não entende
`Ctrl+V`. As que eram de renderização do Flutter foram substituídas pelas do Chromium, registradas
em `../decisoes.md` e no `CHANGELOG.md`.
