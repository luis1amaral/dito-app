// No Linux quem atualiza e o apt, nao o app — ver doc/PLATAFORMAS.md.
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'models.dart';

class LinuxApt {
  const LinuxApt(this.config);
  final UpdaterConfig config;

  String get helperPath => '/usr/lib/${config.debPackage}/update-helper';

  /// true quando esta instalacao veio do repositorio APT.
  ///
  /// Quem roda o bundle solto do .tar.gz nao tem o helper, e oferecer "atualizar"
  /// nesse caso levaria a um erro garantido — melhor nem mostrar o botao.
  bool get installedViaApt => File(helperPath).existsSync();

  /// Versao que o repositorio APT publica — a fonte da verdade do que o apt instalaria.
  ///
  /// Perguntar ao worker aqui daria a resposta errada: a release existe assim que e
  /// publicada, mas o .deb so passa a existir para o apt depois que o repositorio e
  /// reconstruido e subido.
  Future<String?> latestVersion(http.Client client) async {
    final res = await client.get(Uri.parse(config.aptPackagesUrl)).timeout(config.checkTimeout);
    if (res.statusCode != 200) return null;
    return versionOf(utf8.decode(res.bodyBytes), config.debPackage);
  }

  /// Extrai `Version:` do bloco cujo `Package:` bate, no formato do arquivo Packages.
  static String? versionOf(String packages, String pkg) {
    // `\r?` nos dois lados: o apt-ftparchive gera LF, mas um Packages que passou por
    // ferramenta de Windows chega com CRLF e o separador de bloco deixaria de casar.
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

  /// Roda o apt como root pelo polkit. O dialogo de senha e do sistema: o app nunca ve
  /// a senha, e a acao autorizada e so este helper. Lanca [UpdateException] em falha.
  Future<void> upgrade() async {
    if (!installedViaApt) {
      throw const UpdateException('esta instalacao nao veio do repositorio APT');
    }
    try {
      final r = await Process.run('pkexec', [helperPath]);
      if (r.exitCode == 0) return;
      // 126 = polkit negou ou a pessoa fechou o dialogo; 127 = helper sumiu.
      if (r.exitCode == 126) throw const UpdateException('autenticacao cancelada');
      if (r.exitCode == 127) throw const UpdateException('helper de atualizacao nao encontrado');
      final err = '${r.stderr}'.trim();
      throw UpdateException(err.isEmpty ? 'apt saiu com codigo ${r.exitCode}' : err);
    } on ProcessException catch (e) {
      throw UpdateException(e.message);
    }
  }
}
