// On Linux apt updates the app, not the app itself — see doc/PLATAFORMAS.md.
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'models.dart';

class LinuxApt {
  const LinuxApt(this.config);
  final UpdaterConfig config;

  String get helperPath => '/usr/lib/${config.debPackage}/update-helper';

  /// True when this install came from the APT repository; a loose .tar.gz bundle has no helper, so offering "update" there would guarantee an error.
  bool get installedViaApt => File(helperPath).existsSync();

  /// Version the APT repository publishes — the source of truth for what apt would install (asking the release worker would answer too early: the .deb only exists for apt after the repo rebuilds).
  Future<String?> latestVersion(http.Client client) async {
    final res = await client.get(Uri.parse(config.aptPackagesUrl)).timeout(config.checkTimeout);
    if (res.statusCode != 200) return null;
    return versionOf(utf8.decode(res.bodyBytes), config.debPackage);
  }

  /// Extracts `Version:` from the block whose `Package:` matches, in the Packages file format.
  static String? versionOf(String packages, String pkg) {
    // `\r?` on both sides: apt-ftparchive emits LF, but a Packages file touched by Windows tooling arrives as CRLF.
    for (final bloco in packages.split(RegExp(r'\r?\n[ \t]*\r?\n'))) {
      String? nome;
      String? versao;
      for (final linha in const LineSplitter().convert(bloco)) {
        if (linha.startsWith('Package:')) nome = linha.substring(8).trim();
        if (linha.startsWith('Version:')) versao = linha.substring(8).trim();
      }
      if (nome == pkg && versao != null && versao.isNotEmpty) return versao;
    }
    return null;
  }

  /// Runs apt as root via polkit; the password dialog is the system's, the app never sees it. Throws [UpdateException] on failure.
  Future<void> upgrade() async {
    if (!installedViaApt) {
      throw const UpdateException('esta instalacao nao veio do repositorio APT');
    }
    try {
      final r = await Process.run('pkexec', [helperPath]);
      if (r.exitCode == 0) return;
      // 126 = polkit denied or the user closed the dialog; 127 = helper missing.
      if (r.exitCode == 126) throw const UpdateException('autenticacao cancelada');
      if (r.exitCode == 127) throw const UpdateException('helper de atualizacao nao encontrado');
      final err = '${r.stderr}'.trim();
      throw UpdateException(err.isEmpty ? 'apt saiu com codigo ${r.exitCode}' : err);
    } on ProcessException catch (e) {
      throw UpdateException(e.message);
    }
  }
}
