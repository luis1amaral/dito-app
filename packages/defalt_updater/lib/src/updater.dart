// Auto-update outside the app stores: pure I/O, no state, no screen — see doc/PLATAFORMAS.md for the design and the why of each platform.
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

/// Where the package writes the download; injectable so tests never touch the real disk.
typedef WorkDirResolver = Future<Directory> Function();

/// How Android hands the URL to the browser; injectable because `url_launcher` needs the platform binding, absent in pure tests.
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

  /// How the update reaches this platform; the UI uses this to pick the button label ("Download" on Windows isn't "Download in browser" on Android).
  UpdateDelivery get delivery {
    if (!config.selfUpdatesHere) return UpdateDelivery.none;
    if (Platform.isWindows) return UpdateDelivery.inAppDownload;
    if (Platform.isAndroid) return UpdateDelivery.browserHandoff;
    if (Platform.isLinux && _apt.installedViaApt) return UpdateDelivery.packageManager;
    return UpdateDelivery.none;
  }

  bool get supported => delivery != UpdateDelivery.none;

  Future<String> currentVersion() => _readVersion();

  /// Queries the platform's own source; returns null when already up to date, and on ANY failure too — a broken update check must never surface as an error to someone who just wants to use the app.
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

  /// Linux: the version comes from the APT repository, not the worker — deliberately different sources, since apt only sees the version after the repo rebuilds.
  Future<UpdateInfo?> _checkApt(String current) async {
    final latest = await _apt.latestVersion(_http);
    if (latest == null) return null;
    return UpdateInfo(version: latest, current: current);
  }

  // ── download ───────────────────────────────────────────────────────────────

  Future<Directory> _dir() => _workDirOf();

  static Future<Directory> _defaultWorkDir() async {
    // On Android this is the app's private directory in external storage — needs NO storage permission.
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

  /// This version's file if already downloaded AND intact (survives reopening the app).
  Future<File?> downloaded(UpdateInfo info) async {
    final f = await _destFor(info.version);
    if (!f.existsSync()) return null;
    return await _integrityProblem(f, info) == null ? f : null;
  }

  /// Downloads the asset reporting progress 0..1; writes to a `.part` and only renames after checking integrity, so an interrupted download never becomes a "ready" file.
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

  /// Returns the problem's description, or null when the file checks out (sha256 if the manifest has one, else size, which at least catches truncation).
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

  /// Hashes in streaming: a ~100 MB APK does not comfortably fit in phone memory.
  static Future<String> sha256OfFile(File f) async {
    final digest = await f.openRead().transform(sha256).first;
    return digest.toString();
  }

  // ── apply ──────────────────────────────────────────────────────────────

  /// Applies the update via the platform's path; throws [UpdateException] on failure. Windows: NEVER RETURNS. Android: opens the browser and returns. Linux: runs apt via polkit and returns.
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

  /// Android: hands the download to the BROWSER instead of downloading in-app; Chrome usually already holds install-by-origin permission, sidestepping the "unknown source" warning and REQUEST_INSTALL_PACKAGES.
  Future<void> openInBrowser() async {
    if (!await _openUrl(config.downloadUri)) {
      throw const UpdateException('nao foi possivel abrir o navegador');
    }
  }

  /// Deletes downloads of other versions (~100 MB per forgotten release adds up); PRESERVES the kept version's `.part`, or running this during a download would break it with a filesystem error.
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
