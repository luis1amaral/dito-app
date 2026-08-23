// Ciclo real contra um HttpServer local: versao antiga -> acha a nova -> baixa ->
// confere. Sem mock de socket — se o streaming ou o rename quebrar, quebra aqui.
//
// O download so existe onde `delivery == inAppDownload` (Windows), entao o grupo
// inteiro e pulado nas outras plataformas em vez de fingir que passou.
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late HttpServer server;
  late Directory tmp;
  late List<int> payload;
  late String payloadHash;
  Map<String, dynamic> manifest = {};
  int truncateTo = 0;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('defalt_upd_test');
    payload = List<int>.generate(64 * 1024, (i) => i % 251);
    payloadHash = sha256.convert(payload).toString();
    truncateTo = 0;
    manifest = {
      'version': '1.13.0',
      'notes': 'nova',
      UpdaterConfig.platformKey: {'size': payload.length, 'sha256': payloadHash},
    };

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    unawaitedServe(server, () => manifest, () => payload, () => truncateTo);
  });

  tearDown(() async {
    await server.close(force: true);
    if (tmp.existsSync()) tmp.deleteSync(recursive: true);
  });

  UpdaterConfig cfg() => UpdaterConfig(
        appId: 'testapp',
        manifestUrl: 'http://${server.address.host}:${server.port}/api/app/latest',
        downloadUrl: 'http://${server.address.host}:${server.port}/api/app/download',
      );

  DefaltUpdater make({String current = '1.12.0'}) => DefaltUpdater(
        config: cfg(),
        currentVersionReader: () async => current,
        workDir: () async => tmp,
      );

  group('check', () {
    test('versao antiga encontra a nova no manifesto', () async {
      final info = await make().check();
      expect(info, isNotNull);
      expect(info!.version, '1.13.0');
      expect(info.current, '1.12.0');
      expect(info.sha256, payloadHash);
      expect(info.integrity, IntegrityCheck.sha256);
    });

    test('versao igual a publicada nao oferece update', () async {
      expect(await make(current: '1.13.0').check(), isNull);
    });

    test('versao mais nova que a publicada nunca vira downgrade', () async {
      expect(await make(current: '2.0.0').check(), isNull);
    });

    test('servidor fora do ar devolve null, nao excecao', () async {
      final u = make(); // monta a config ANTES de derrubar: `server.address` some depois
      await server.close(force: true);
      expect(await u.check(), isNull);
    });
  }, skip: _skipUnlessInApp);

  group('download', () {
    test('baixa, confere o sha256 e reporta progresso ate 1', () async {
      final u = make();
      final info = (await u.check())!;
      final visto = <double>[];
      final f = await u.download(info, onProgress: visto.add);

      expect(f.existsSync(), isTrue);
      expect(f.lengthSync(), payload.length);
      expect(await DefaltUpdater.sha256OfFile(f), payloadHash);
      expect(visto.last, 1.0);
      expect(File('${f.path}.part').existsSync(), isFalse, reason: 'o .part tem que sumir');
    });

    test('conteudo trocado com o tamanho certo e recusado pelo sha256', () async {
      final u = make();
      final info = (await u.check())!;
      // mesmo tamanho, bytes diferentes: so o hash pega isso
      payload = List<int>.filled(payload.length, 7);

      await expectLater(
        u.download(info),
        throwsA(isA<IntegrityException>()),
      );
      expect(
        Directory(tmp.path).listSync().whereType<File>().length,
        0,
        reason: 'arquivo corrompido nao pode sobrar no disco',
      );
    });

    test('download truncado e recusado pelo tamanho', () async {
      final u = make();
      final info = (await u.check())!;
      truncateTo = 1024;

      await expectLater(u.download(info), throwsA(isA<IntegrityException>()));
      expect(Directory(tmp.path).listSync().whereType<File>().length, 0);
    });

    test('cancelar no meio nao deixa arquivo pronto nem vira erro de rede', () async {
      final u = make();
      final info = (await u.check())!;
      final token = CancelToken();

      await expectLater(
        u.download(info, cancel: token, onProgress: (_) => token.cancel()),
        throwsA(isA<UpdateCancelled>()),
      );
      expect(await u.downloaded(info), isNull);
    });

    test('downloaded() so devolve o arquivo quando ele confere', () async {
      final u = make();
      final info = (await u.check())!;
      expect(await u.downloaded(info), isNull, reason: 'nada baixado ainda');

      final f = await u.download(info);
      expect(await u.downloaded(info), isNotNull);

      f.writeAsBytesSync([1, 2, 3]); // corrompe o que estava pronto
      expect(await u.downloaded(info), isNull);
    });
  }, skip: _skipUnlessInApp);

  group('cleanup', () {
    test('apaga as outras versoes e preserva o .part da versao mantida', () async {
      final u = make();
      File p(String n) => File('${tmp.path}${Platform.pathSeparator}$n')
        ..writeAsStringSync('x');

      final velha = p(u.fileNameFor('1.11.0'));
      final atual = p(u.fileNameFor('1.13.0'));
      final parcial = p('${u.fileNameFor('1.13.0')}.part');

      await u.cleanup(keepVersion: '1.13.0');

      expect(velha.existsSync(), isFalse);
      expect(atual.existsSync(), isTrue);
      expect(parcial.existsSync(), isTrue, reason: 'apagar o .part quebraria o download em curso');
    });
  });
}

final String? _skipUnlessInApp = Platform.isWindows
    ? null
    : 'download dentro do app so existe no Windows (delivery=inAppDownload)';

/// Serve o manifesto e o binario. `truncate>0` corta a resposta pra simular queda.
void unawaitedServe(
  HttpServer server,
  Map<String, dynamic> Function() manifest,
  List<int> Function() body,
  int Function() truncate,
) {
  server.listen((req) async {
    if (req.uri.path.endsWith('/latest')) {
      req.response
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(manifest()));
    } else {
      final bytes = body();
      final cut = truncate();
      req.response.add(cut > 0 ? bytes.sublist(0, cut) : bytes);
    }
    await req.response.close();
  });
}
