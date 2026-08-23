# defalt_updater

Auto-update fora das lojas para os apps Flutter do Defalt. **Sem UI** — o pacote checa,
baixa, confere e aplica; quem decide como mostrar é o app.

Extraído do `slime-animes`, que já rodava isto em produção. O *porquê* de cada plataforma
está em [`doc/PLATAFORMAS.md`](doc/PLATAFORMAS.md).

| Plataforma | `UpdateDelivery`  | Como aplica                                        |
| ---------- | ----------------- | -------------------------------------------------- |
| Windows    | `inAppDownload`   | baixa `.zip`, troca a instalação por cima, relança |
| Android    | `browserHandoff`  | abre o download no navegador (instalador do sistema) |
| Linux/APT  | `packageManager`  | `apt` via helper autorizado no polkit               |
| resto      | `none`            | não se atualiza sozinho                             |

## Uso

```dart
final updater = DefaltUpdater(
  config: const UpdaterConfig(
    appId: 'slime-animes',
    displayName: 'Slime Animes',
    manifestUrl: 'https://.../api/app/latest',
    downloadUrl: 'https://.../api/app/download',
    platforms: {'windows', 'linux', 'android'}, // Android é opt-in — veja abaixo
  ),
);

final info = await updater.check();          // null = atualizado, ou qualquer falha
if (info == null) return;

switch (updater.delivery) {
  case UpdateDelivery.inAppDownload:
    final file = await updater.download(info, onProgress: (p) => setState(...));
    await updater.apply(file: file);          // NÃO RETORNA: o app fecha e reabre
  case UpdateDelivery.browserHandoff:
  case UpdateDelivery.packageManager:
    await updater.apply();                    // sem passo de download
  case UpdateDelivery.none:
    break;
}
```

### `UpdateController` (opcional)

`ChangeNotifier` com o estado inteiro pronto: throttle de 6h, "pular versão", modo
(`notify` / `auto` / `off`), progresso e estágio. Serve ao `provider` e ao `riverpod`
(`ChangeNotifierProvider`) sem adaptador.

```dart
final c = UpdateController(updater: updater);
unawaited(c.checkQuiet());   // no boot, sem await e sem bloquear a UI
// c.showBanner, c.stage, c.progress, c.info, c.error
// c.startDownload(), c.install(), c.skipCurrent(), c.dismissBanner()
```

## Contrato do manifesto

`GET <manifestUrl>` deve responder:

```json
{
  "version": "1.13.0",
  "notes": "markdown do corpo da release",
  "windows": { "size": 22337073, "sha256": "abc..." },
  "linux":   { "size": 20091465 },
  "android": { "size": 89466382 }
}
```

- `version` sem o `v` — comparada com `PackageInfo.version` por `compareVersions`.
- A chave da plataforma ausente = **não há update para ela**. É assim que um app que publica
  na Play Store some do caminho do Android.
- `sha256` é opcional; sem ele a conferência cai para o tamanho exato.
  `UpdateInfo.integrity` diz qual das duas valeu.

### Android é opt-in, e falha fechado

`platforms` vem sem `android` por padrão. App que publica na **Play Store** não pode se
auto-instalar: a loja atualiza, e um APK lateral colide com o que ela instalou. Só quem está
fora da loja (hoje, só o `slime-animes`) declara `'android'` — esquecer o campo desliga o
Android, e não o contrário.

`GET <downloadUrl>?platform=windows|android|linux` responde o binário (ou 302 para ele).

## API

| Símbolo | O que faz |
| --- | --- |
| `UpdaterConfig` | tudo que muda de um app para outro (`appId`, URLs, pacote APT) |
| `UpdaterConfig.platforms` | onde este app se atualiza sozinho — **Android é opt-in** |
| `DefaltUpdater.delivery` | como a atualização chega nesta plataforma |
| `DefaltUpdater.check()` | `UpdateInfo?` — `null` quando atualizado **ou** em qualquer falha |
| `DefaltUpdater.download()` | baixa em `.part`, confere, renomeia; progresso e `CancelToken` |
| `DefaltUpdater.downloaded()` | arquivo já baixado **e íntegro** desta versão, se existir |
| `DefaltUpdater.apply()` | aplica pelo caminho da plataforma |
| `DefaltUpdater.cleanup()` | apaga downloads de outras versões |
| `compareVersions(a, b)` | semver numérico (`1.11` > `1.9`), ignora `+build` |

Falhas viram `UpdateException` (mensagem em pt-BR, pronta para a tela), com
`IntegrityException` e `UpdateCancelled` como subtipos.

## Checks

```
flutter analyze && flutter test
```

`test/full_cycle_test.dart` exercita o ciclo inteiro sem mock nenhum: versão 1.12.0 →
descobre a 1.13.0 num `HttpServer` real → baixa → confere o `sha256` → roda o updater → a
instalação passa a ser a 1.13.0, com os arquivos do usuário intactos.

`test/windows_apply_test.dart` roda o `.ps1` **de verdade** contra uma instalação de
mentira: prova que os arquivos são trocados, que o que é do usuário sobrevive e que a versão
nova é relançada. Ele é pulado fora do Windows, não mascarado.
