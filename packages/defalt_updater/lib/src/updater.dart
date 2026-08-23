// Auto-update fora das lojas: I/O puro, sem estado e sem tela — quem decide o que
// mostrar e o app. O desenho e o porque de cada plataforma: doc/PLATAFORMAS.md.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'linux_apt.dart';
import 'models.dart';
import 'version.dart';
import 'windows_installer.dart';

/// Onde o pacote grava o download. Injetavel pra o teste nao mexer no disco real.
typedef WorkDirResolver = Future<Directory> Function();

/// Como o Android entrega a URL ao navegador. Injetavel porque `url_launcher`
/// precisa do binding de plataforma, que nao existe em teste puro.
typedef UrlOpener = Future<bool> Function(Uri url);

class DefaltUpdater {
  DefaltUpdater({
    required this.config,
    http.Client? client,
    Future<String> Function()? currentVersionReader,
    WorkDirResolver? workDir,
    UrlOpener? openUrl,
  })  : _http = client ?? http.Client(),
        _readVersion = currentVersionReader ?? _packageInfoVersion,
        _workDirOf = workDir ?? _defaultWorkDir,
        _openUrl = openUrl ?? _defaultOpenUrl,
        _apt = LinuxApt(config),
        _windows = WindowsInstaller(config);

  final UpdaterConfig config;
  final http.Client _http;
  final Future<String> Function() _readVersion;
  final WorkDirResolver _workDirOf;
  final UrlOpener _openUrl;
  final LinuxApt _apt;
  final WindowsInstaller _windows;

  static Future<String> _packageInfoVersion() async =>
      (await PackageInfo.fromPlatform()).version;

  static Future<bool> _defaultOpenUrl(Uri url) =>
      launchUrl(url, mode: LaunchMode.externalApplication);

  /// Como a atualizacao chega nesta plataforma. A UI usa isto pra escolher o rotulo do
  /// botao — "Baixar" no Windows nao e a mesma acao que "Baixar no navegador" no Android.
  UpdateDelivery get delivery {
    if (!config.selfUpdatesHere) return UpdateDelivery.none;
    if (Platform.isWindows) return UpdateDelivery.inAppDownload;
    if (Platform.isAndroid) return UpdateDelivery.browserHandoff;
    if (Platform.isLinux && _apt.installedViaApt) return UpdateDelivery.packageManager;
    return UpdateDelivery.none;
  }

  bool get supported => delivery != UpdateDelivery.none;

  Future<String> currentVersion() => _readVersion();

  /// Consulta a origem certa da plataforma. Devolve null quando ja esta atualizado — e
  /// tambem em QUALQUER falha (rede, servidor fora, json torto): update quebrado nunca
  /// pode virar erro na cara de quem so quer usar o app.
  Future<UpdateInfo?> check() async {
    if (!supported) return null;
    try {
      final current = await currentVersion();
      final found = delivery == UpdateDelivery.packageManager
          ? await _checkApt(current)
          : await _checkManifest(current);
      if (found == null) return null;
      return compareVersions(found.version, current) > 0 ? found : null;
    } catch (e) {
      debugPrint('[${config.appId}] update check falhou (ignorado): $e');
      return null;
    }
  }

  Future<UpdateInfo?> _checkManifest(String current) async {
    final res = await _http.get(config.manifestUri).timeout(config.checkTimeout);
    if (res.statusCode != 200) return null;
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    if (body is! Map<String, dynamic>) return null;
    return UpdateInfo.fromManifest(body, UpdaterConfig.platformKey, current);
  }

  /// Linux: a versao vem do repositorio APT, nao do worker — sao fontes diferentes de
  /// proposito, o apt so enxerga a versao depois que o repositorio e reconstruido.
  Future<UpdateInfo?> _checkApt(String current) async {
    final latest = await _apt.latestVersion(_http);
    if (latest == null) return null;
    return UpdateInfo(version: latest, current: current);
  }

  // ── download ───────────────────────────────────────────────────────────────

  Future<Directory> _dir() => _workDirOf();

  static Future<Directory> _defaultWorkDir() async {
    // No Android e o diretorio privado do app em armazenamento externo — nao exige
    // NENHUMA permissao de storage.
    final base = Platform.isAndroid
        ? (await getExternalStorageDirectory() ?? await getApplicationSupportDirectory())
        : await getApplicationSupportDirectory();
    final dir = Directory('${base.path}${Platform.pathSeparator}updates');
    if (!dir.existsSync()) await dir.create(recursive: true);
    return dir;
  }

  String fileNameFor(String version) =>
      Platform.isWindows ? '${config.appId}-$version.zip' : '${config.appId}-$version.apk';

  Future<File> _destFor(String version) async =>
      File('${(await _dir()).path}${Platform.pathSeparator}${fileNameFor(version)}');

  /// Arquivo desta versao ja baixado E integro, se existir (sobrevive a reabrir o app).
  Future<File?> downloaded(UpdateInfo info) async {
    final f = await _destFor(info.version);
    if (!f.existsSync()) return null;
    return await _integrityProblem(f, info) == null ? f : null;
  }

  /// Baixa o asset reportando progresso 0..1. Escreve num `.part` e so renomeia depois de
  /// conferir a integridade — download interrompido nunca vira arquivo "pronto".
  Future<File> download(
    UpdateInfo info, {
    void Function(double)? onProgress,
    CancelToken? cancel,
  }) async {
    if (delivery != UpdateDelivery.inAppDownload) {
      throw UpdateException('esta plataforma nao baixa dentro do app (${delivery.name})');
    }
    final dest = await _destFor(info.version);
    final part = File('${dest.path}.part');
    if (part.existsSync()) await part.delete();

    final req = http.Request('GET', config.downloadUri);
    final res = await _http.send(req).timeout(config.downloadTimeout);
    if (res.statusCode != 200) {
      throw UpdateException('download falhou: HTTP ${res.statusCode}');
    }

    final total = res.contentLength ?? info.size;
    var received = 0;
    final sink = part.openWrite();
    try {
      await for (final chunk in res.stream) {
        if (cancel?.isCancelled ?? false) throw const UpdateCancelled();
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress?.call(received / total);
      }
      await sink.flush();
    } finally {
      await sink.close();
    }
    if (cancel?.isCancelled ?? false) {
      if (part.existsSync()) await part.delete();
      throw const UpdateCancelled();
    }

    final problem = await _integrityProblem(part, info);
    if (problem != null) {
      await part.delete();
      throw IntegrityException(problem);
    }

    if (dest.existsSync()) await dest.delete();
    await part.rename(dest.path);
    onProgress?.call(1);
    return dest;
  }

  /// Devolve a descricao do problema, ou null quando o arquivo confere.
  /// sha256 quando o manifesto traz um; senao o tamanho, que ao menos pega truncamento.
  Future<String?> _integrityProblem(File f, UpdateInfo info) async {
    final len = await f.length();
    if (info.size > 0 && len != info.size) {
      return 'download incompleto ($len de ${info.size} bytes)';
    }
    final expected = info.sha256;
    if (expected == null) return null;
    final got = await sha256OfFile(f);
    if (got != expected) return 'conteudo corrompido (sha256 $got != $expected)';
    return null;
  }

  /// Hash em streaming: um APK de ~100 MB nao cabe confortavelmente na memoria do celular.
  static Future<String> sha256OfFile(File f) async {
    final digest = await f.openRead().transform(sha256).first;
    return digest.toString();
  }

  // ── aplicacao ──────────────────────────────────────────────────────────────

  /// Aplica a atualizacao pelo caminho da plataforma. Lanca [UpdateException] em falha.
  ///
  /// Windows: NAO RETORNA — o processo encerra pro updater trocar os arquivos.
  /// Android: abre o navegador e retorna; quem instala e o instalador do sistema.
  /// Linux: roda o apt via polkit e retorna; o binario novo so vale na proxima abertura.
  Future<void> apply({File? file}) async {
    switch (delivery) {
      case UpdateDelivery.inAppDownload:
        if (file == null) throw const UpdateException('nada baixado pra instalar');
        await _windows.applyAndRestart(file);
      case UpdateDelivery.browserHandoff:
        await openInBrowser();
      case UpdateDelivery.packageManager:
        await _apt.upgrade();
      case UpdateDelivery.none:
        throw const UpdateException('esta plataforma nao se atualiza sozinha');
    }
  }

  /// Android: entrega o download ao NAVEGADOR em vez de baixar aqui dentro.
  ///
  /// O Android autoriza instalacao por ORIGEM, e o Chrome quase sempre ja tem essa
  /// permissao — instalando por ele a pessoa nao topa com o aviso de "fonte desconhecida".
  /// De quebra, o app deixa de precisar de REQUEST_INSTALL_PACKAGES e de escrita em disco.
  Future<void> openInBrowser() async {
    if (!await _openUrl(config.downloadUri)) {
      throw const UpdateException('nao foi possivel abrir o navegador');
    }
  }

  /// Apaga downloads de outras versoes — ~100 MB por release esquecida e muito.
  ///
  /// PRESERVA o `.part` da versao mantida: rodar isto junto da checagem enquanto o
  /// download escreve no parcial quebraria o download com erro de filesystem.
  Future<void> cleanup({String? keepVersion}) async {
    try {
      final dir = await _dir();
      if (!dir.existsSync()) return;
      final keep = keepVersion == null ? null : fileNameFor(keepVersion);
      for (final e in dir.listSync()) {
        if (e is! File) continue;
        final name = e.uri.pathSegments.last;
        if (keep != null && (name == keep || name == '$keep.part')) continue;
        await e.delete();
      }
    } catch (e) {
      debugPrint('[${config.appId}] cleanup de update falhou (ignorado): $e');
    }
  }
}
