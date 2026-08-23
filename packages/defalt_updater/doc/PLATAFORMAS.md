# Por que cada plataforma atualiza de um jeito diferente

Este arquivo existe porque as decisões abaixo não cabem em comentário de uma linha. O
código aponta para cá.

## Windows — `UpdateDelivery.inAppDownload`

O app baixa um `.zip` e troca a própria instalação por cima.

Um processo não consegue sobrescrever o próprio `.exe` enquanto roda. Por isso a troca é
delegada a um script PowerShell: o app lança o updater **destacado**, morre, e o script
espera o PID sumir para copiar.

Detalhes que custaram bug para descobrir:

- **`cmd /c start` em vez de `Process.start` detached direto.** Um `powershell.exe` criado
  sem console morre na hora nesse estado — foi o bug da v1.12.3 do Slime Animes (o app
  fechava e nada acontecia). O `start` cria o console para ele e o `cmd` sai.
- **O app só fecha depois que o updater PROVA que subiu.** O script grava a primeira linha
  do log antes de qualquer outra coisa; `launchUpdater` espera essa linha por até 15s. Sem
  essa prova ele lança exceção e o app **continua aberto** — fechar sozinho e não atualizar
  nada é o pior resultado possível, porque a pessoa reabre e acha que o app quebrou.
- **`robocopy /E`, nunca `/MIR`.** `/MIR` apagaria o que o usuário tiver a mais na pasta.
  Códigos de saída `< 8` são sucesso no robocopy.
- **Pasta protegida pede UAC uma vez.** `_canWrite` faz uma escrita de sondagem; se falhar
  (`C:\Program Files`), o script é relançado via `Start-Process -Verb RunAs`.
- **Falha em qualquer etapa relança a versão ANTIGA.** Ficar sem app aberto seria pior do
  que ficar sem a atualização.
- **O zip da release tem os arquivos na RAIZ** (`Compress-Archive -Path ...\Release\*`),
  então extrair e copiar por cima é suficiente.

Provado por `test/windows_apply_test.dart`, que roda o `.ps1` de verdade contra uma
instalação de mentira.

## Android — `UpdateDelivery.browserHandoff`

O app **não** baixa o APK: ele abre a URL de download no navegador.

Não é desvio de trabalho, é a opção melhor. O Android autoriza instalação por **origem**, e
o Chrome quase sempre já tem essa permissão — instalando por ele, a pessoa não topa com o
aviso de "fonte desconhecida" que apareceria vindo do app. De quebra, o app deixa de
precisar de `REQUEST_INSTALL_PACKAGES` e de qualquer escrita em disco.

Só faz sentido para app **fora da Play Store**. App que publica na Play não deve expor este
caminho — a loja atualiza, e um APK lateral colide com o que ela instalou.

## Linux — `UpdateDelivery.packageManager`

Quem atualiza é o `apt`, não o app.

O pacote instala em `/usr/lib/<pkg>`, dono root, rastreado pelo `dpkg`. Se o app baixasse um
binário e se sobrescrevesse, o `dpkg` passaria a mentir sobre o que está instalado e o
próximo `apt upgrade` desfaria a troca por cima. Por isso aqui **não existe download**:

- a checagem lê a versão publicada no próprio repositório APT (`.../binary-amd64/Packages`),
  **não** o manifesto do worker. São fontes diferentes de propósito: o worker responde assim
  que a release é publicada, mas o `.deb` só passa a existir para o `apt` depois que o
  repositório é reconstruído e subido. Anunciar pelo worker deixaria o botão "atualizar"
  rodando um `apt` que ainda não tem nada novo para instalar;
- a instalação delega ao `apt` por um helper autorizado no polkit
  (`/usr/lib/<pkg>/update-helper`, gerado pelo `tools/make-deb.sh` de cada app). O diálogo de
  senha é do sistema: o app nunca vê a senha, e a ação autorizada é **só** aquele helper —
  não `pkexec` genérico, que autorizaria rodar qualquer programa.

`installedViaApt` checa a existência do helper: quem roda o bundle solto do `.tar.gz` não o
tem, e oferecer "atualizar" nesse caso levaria a um erro garantido — melhor nem mostrar o
botão. Por isso `delivery` devolve `none` nesse caso.

O binário novo só vale na **próxima abertura**: o processo atual continua com os arquivos
antigos já mapeados em memória.

## Integridade

`sha256` quando o manifesto traz um; senão, o tamanho exato; senão, nada — e
`UpdateInfo.integrity` diz qual dos três está valendo, para a UI poder ser honesta.

O tamanho sozinho pega truncamento (a falha comum: rede caiu no meio), mas não pega troca de
conteúdo. O hash é conferido em **streaming** — um APK de ~100 MB não cabe confortavelmente
na memória de um celular.

O download escreve num `.part` e só é renomeado **depois** de conferir. Um download
interrompido nunca é confundido com arquivo pronto.
