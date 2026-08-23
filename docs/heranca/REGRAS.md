# Regras de trabalho — o que impede repetir o que já deu errado

Este arquivo existe por um motivo concreto: a versão **1.7.0** foi publicada com
`flutter analyze` limpo, **220 testes** e **16 goldens** passando — e o app **morria no start**,
antes de imprimir a primeira linha de log. O dono descobriu instalando.

Não foi azar. Foi um processo que media o que era fácil medir.

---

## 1. Nada é "pronto" sem o binário ter subido

`analyze` e teste unitário provam que o código compila e que funções puras funcionam. **Não provam
que o aplicativo abre.** Todo passo termina com o executável rodando de verdade.

O que já existe e continua valendo no projeto atual:

- `tool/fumaca.ps1` — sobe o executável nos dois modos (bandeja e janela), exige `boot completo` no
  log, e **fotografa a área cliente**, reprovando se mais de 3% for preto puro.
- `tool/fumaca_instalador.ps1` — instala o setup de verdade e sobe o **app instalado**.
- `packaging/windows/construir.ps1` **não empacota** se qualquer um dos dois reprovar.

**No projeto novo em Electron, o equivalente tem de existir desde o primeiro dia**, não depois do
primeiro defeito. Sem portão que suba o app, não se publica.

## 2. Um portão que nunca reprovou não é portão

Todo teste novo tem de ser provado **nos dois sentidos**: passa com o conserto, **falha sem ele**.

Foi assim que os dois consertos de hoje ficaram travados:

- Conserto do foco: removida a chamada, **3 testes ficam vermelhos**; reposta, 5 verdes.
- Conserto da faixa preta: recolocado o bug de propósito, `FUMACA: FALHA`, **exit 1**.

Se você escreveu um teste e nunca o viu reprovar, você não sabe se ele testa alguma coisa.

## 3. Olhar a tela, não só o exit code

Três dos defeitos de hoje eram **visuais** e nenhum teste os via: faixa preta no topo da janela,
faixa preta acima da pílula, janela inteira piscando.

O que funcionou foi **medir pixel**: capturar a janela e contar. O tema nunca pinta preto puro (o
fundo é `#0E0E13`), então preto puro é área que não foi apresentada. Foi assim que "28px de preto e
pílula cortada em 25 de 56" virou número em vez de impressão.

Antes de dizer que uma tela está pronta: **abrir, capturar, olhar**.

## 4. Medir antes de afirmar a causa

Nesta sessão eu errei o diagnóstico **três vezes** por afirmar antes de medir:

- Disse que o culpado era `setPreventClose` — estava lendo **uma linha de log velha** que não mudava
  entre execuções. O `Logbook` escreve por `IOSink` assíncrono e a linha se perde no segfault. Só
  com escrita **síncrona** o trace apontou o verdadeiro culpado, `setSkipTaskbar`.
- Disse que era DLL desatualizada — recompilei tudo limpo e continuou quebrando.
- Disse que a `AlarmPolicy` tinha a histerese e mandei um agente restaurá-la. **Não tinha**: a
  histerese está em `silence_alarm.dart`; a `AlarmPolicy` era só um throttle de 10s de som.

Regra: sem evidência, a resposta é *"ainda não sei — vou verificar"*, nunca um palpite com cara de
conclusão.

## 5. Trocar arquitetura sem provar cada passo é o que quebrou tudo

A migração single-engine foi commitada com **teste verde** e **nunca tinha bootado no Windows uma
vez sequer** — os últimos boots com sucesso no log ainda registravam a arquitetura multi-janela
antiga. Ela apagou `hud_window.dart` e levou junto o **único** `takeFocus` do app, matando em
silêncio o conserto de colagem no conhost da versão anterior.

**Ao apagar um arquivo, procurar o que ele chamava no nativo antes de apagar.** O código compila
igual sem a chamada; o defeito só aparece na mão do dono.

No plano novo, os passos 1 e 2 (transcrever em português; colar num `cmd.exe` cru) existem
exatamente para derrubar a ideia cedo, se for para derrubar.

## 6. Cuidado ao usar agentes em paralelo

O que deu errado hoje, para não repetir:

- `git add -A` **varreu trabalho em andamento de outros agentes** para dentro do meu commit. Duas
  vezes. Commitar só os arquivos que são seus, nomeados.
- Um agente **apagou `lib/state/alarm_policy.dart`** contrariando instrução explícita. Revisar o que
  o agente fez, não aceitar o relatório dele como prova.
- Um agente deixou um `.git/index.lock` órfão que travou o repositório.

Agente em paralelo só com **conjunto de arquivos disjunto**, e o relatório dele **não substitui**
conferir o resultado.

## 7. Não publicar release sem o dono testar

O fluxo é: build → instalar na máquina dele → **ele testa** → só então publicar. A 1.7.0 foi
publicada antes disso e teve de ser despublicada (virou rascunho) para o auto-update não empurrar um
app que não abre.
