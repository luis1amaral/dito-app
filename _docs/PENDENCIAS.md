# Pendências

O que **ainda não foi feito** e por que importa. Atualizado em 2026-08-28, na 2.0.16.

Só fica aqui o que está em aberto. O porte para Linux foi concluído e saiu desta lista: o que ele
custou está no `CHANGELOG.md` (2.0.10 a 2.0.16) e o mapa comportamento a comportamento — inclusive
as duas linhas do Linux que seguem sem portão, `H6` (pílula transparente sem compositor) e `H7`
(equivalente do `smoke.ps1`) — está no `PARIDADE.md`.

---

## 1. Windows — aberto

| # | Pendência | Por quê importa |
|---|---|---|
| W3 | **Modelos que não são transducer sem portão automático.** O Whisper foi provado à mão na 2.0.5 (carrega em 608 ms e transcreve); `nemo-ctc`, `senseVoice` e `paraformer` continuam sem nenhuma execução | O portão `engine.mjs` monta o transducer na mão em vez de chamar o `build()` real, então não cobriria a regressão que a 2.0.5 corrigiu |
| W4 | **Modelo streaming nunca rodou.** Nomes da API conferidos contra o pacote, mas nenhum foi baixado | Nome certo não é execução certa |
| W8 | **Instalador cai na mesma pasta da 1.7.x** (`%LOCALAPPDATA%\Programs\Dito`) | Quem atualizar sem desinstalar fica com duas árvores misturadas |

## 2. Captura de som do computador — aberto (os dois sistemas)

**O áudio que está tocando entra misturado com a voz, e o texto sai embaralhado.** A opção
`captureSystemAudio` nasceu ligada na 2.0.15, então quem dita com um vídeo, uma reunião ou uma música
tocando recebe as duas fontes somadas no mesmo ditado. O motor transcreve a mistura, e a frase final
intercala o que a pessoa falou com o que o computador estava dizendo.

Medido em 2026-08-28, com um vídeo do YouTube aberto: dois ditados seguidos de 14 s vieram com
narração de terceiro grudada na fala do dono ("é uma prop do componente React e vaza pro bundle,
variável `VITE_`…"), sem nenhuma marca de onde uma acaba e a outra começa. O ciclo da tecla estava
íntegro nos dois casos (`started` e `stopped` no log, zero captura órfã) — o defeito é de produto,
não de mecanismo.

Caminhos possíveis, nenhum decidido:

- **Nascer desligada** e ligar sob demanda para transcrever reunião ou áudio de WhatsApp.
- **Separar as duas fontes** em vez de somar, transcrevendo cada uma e rotulando quem falou.
- **Avisar na pílula** quando houver som do sistema entrando junto, para a pessoa pausar antes.
