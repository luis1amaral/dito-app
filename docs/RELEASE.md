# Como sai uma release do Dito

**O build é local e o upload é à mão. Não é o CI que publica.**

Está escrito aqui porque o repositório tem um workflow chamado `Release Dito` e alguém vai olhar
para ele e supor o contrário. Ele existe só como reserva, e **só dispara à mão**
(`workflow_dispatch`) — nunca por tag. Se ele rodasse na tag, correria junto com o upload manual e
sobrescreveria asset já publicado.

## Por que local

1. **O Windows tem que ser compilado nesta máquina.** O motor é C++ (`whisper.cpp` + `ggml` +
   `miniaudio`) com CUDA; o que sai daqui é o que foi testado aqui.
2. **O Linux tem que ser compilado numa máquina Linux** — a mesma de onde o `.deb` depois é
   publicado no repositório APT. Não dá para gerar `.deb` do Windows.
3. **O passo de teste do CI não pode passar sozinho.** Ele roda antes do build existir, e o
   `native_transcription_test` precisa da biblioteca nativa já compilada — por isso ele está atrás
   da tag `live`. Ver armadilha 6.9.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
```

Faz o portão (`analyze` + `test`), compila, gera o instalador Inno Setup, o `.zip` e o
`SHA256SUMS.txt` em `build\windows\installer\`.

Antes de publicar, escanear — o instalador já caiu em falso-positivo `Bearfoos.B!ml` uma vez, por
causa de PowerShell oculto na seção `[Run]`:

```powershell
& "C:\Program Files\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 `
  -File "build\windows\installer\dito-<versao>-setup.exe" -DisableRemediation
```

Publicar:

```powershell
gh release create v<versao> --title "..." --notes-file <arquivo> `
  build\windows\installer\dito-<versao>-setup.exe `
  build\windows\installer\dito-<versao>.zip `
  build\windows\installer\SHA256SUMS.txt
```

## Linux

Na máquina Linux, depois de `git pull`:

```bash
bash packaging/linux/construir.sh
gh release upload v<versao> build/linux/installer/*.deb build/linux/installer/*.tar.gz
```

## O passo que ninguém pode esquecer: o APT

**Subir o `.deb` para a release do GitHub NÃO atualiza o Linux de ninguém.**

O updater do Linux não pergunta ao `dito-api`: ele lê a versão publicada em
`https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages`
(`packages/defalt_updater/lib/src/linux_apt.dart`). E isso é de propósito — a release existe assim
que é publicada, mas o `.deb` só passa a existir *para o apt* depois que o repositório é
reconstruído e subido. Enquanto isso não acontece, o app Linux continua vendo a versão antiga.

Nada neste repositório publica no APT. Esse passo é manual, feito na máquina Linux, e a release
não está terminada sem ele.

## Windows: como a atualização chega no usuário

Diferente do Linux. O app pergunta ao `dito-api`
(`https://dito-api.defaltm.com/api/app/latest`), que é um Cloudflare Worker que lê as releases
deste repositório — privado — com um token próprio e as reexpõe. O app nunca fala com o GitHub
direto, porque um `.exe` distribuído não pode carregar token.

Duas consequências práticas:

- **Release em rascunho não conta.** O GitHub não devolve rascunho em `/releases/latest`, então o
  worker anuncia a versão publicada anterior. Se a atualização "não aparece", esse é o primeiro
  lugar para olhar.
- **A checagem é automática desde a 1.7.0**, no boot, com trava de 6 h
  (`UpdateController.checkQuiet()`). Antes dela existia o método, mas ninguém o chamava: só o botão
  "Verificar agora" nos Ajustes funcionava.

Conferir o que o mundo está vendo:

```bash
curl -s https://dito-api.defaltm.com/api/app/latest
curl -s https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages | head
```
