import 'dart:io';

import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/core/result.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:flutter_test/flutter_test.dart';

/// Records what happened and in which order, so the sequence itself can be asserted.
class SpyBackend extends PasteBackend {
  SpyBackend({
    this.clipboard,
    this.writeSucceeds = true,
    this.ctrlVSucceeds = true,
    this.restoreFocusSucceeds = true,
    this.pressEnterSucceeds = true,
    this.target = PasteTarget.gui,
  });

  String? clipboard;
  bool writeSucceeds;
  bool ctrlVSucceeds;
  bool restoreFocusSucceeds;
  bool pressEnterSucceeds;
  PasteTarget target;

  /// O que realmente foi para a area de transferencia e para o teclado.
  String? escrito;
  String? digitado;

  final List<String> log = <String>[];
  final Stopwatch clock = Stopwatch()..start();
  final Map<String, int> at = <String, int>{};

  void _mark(String step) {
    log.add(step);
    at.putIfAbsent(step, () => clock.elapsedMilliseconds);
  }

  @override
  Future<String?> readClipboard() async {
    _mark('read');
    return clipboard;
  }

  @override
  Future<bool> writeClipboard(String text) async {
    _mark('write:$text');
    escrito = text;
    if (!writeSucceeds) return false;
    clipboard = text;
    return true;
  }

  @override
  Future<bool> pressCtrlV({String? text}) async {
    _mark('ctrl+v');
    digitado = text;
    return ctrlVSucceeds;
  }

  @override
  Future<bool> pressEnter() async {
    _mark('enter');
    return pressEnterSucceeds;
  }

  @override
  Future<bool> restoreFocus() async {
    _mark('focus');
    return restoreFocusSucceeds;
  }

  @override
  Future<PasteTarget> describeTarget() async => target;
}

/// describeTarget que explode: a colagem tem de seguir mesmo assim.
class _AlvoQuebrado extends SpyBackend {
  @override
  Future<PasteTarget> describeTarget() async => throw StateError('sem alvo');
}

void main() {
  PasteService serviceFor(SpyBackend spy, {Logbook? log}) => PasteService(
        backend: spy,
        log: log,
        settle: const Duration(milliseconds: 20),
        beforeEnter: const Duration(milliseconds: 60),
        restoreAfter: const Duration(milliseconds: 120),
      );

  group('order', () {
    test('focus goes back BEFORE the paste, or Ctrl+V lands in our own window', () async {
      final spy = SpyBackend(clipboard: 'antigo');
      await serviceFor(spy).paste('ola');

      expect(spy.log.indexOf('focus'), lessThan(spy.log.indexOf('ctrl+v')));
      expect(spy.log, containsAllInOrder(<String>['read', 'write:ola', 'focus', 'ctrl+v']));
    });

    test('Enter waits for the paste to land', () async {
      final spy = SpyBackend();
      await serviceFor(spy).paste('ola', sendEnter: true);

      expect(spy.log, containsAllInOrder(<String>['ctrl+v', 'enter']));
      final gap = spy.at['enter']! - spy.at['ctrl+v']!;
      expect(gap, greaterThanOrEqualTo(50),
          reason: 'sem a espera o Enter envia o campo vazio');
    });

    test('no Enter unless asked', () async {
      final spy = SpyBackend();
      await serviceFor(spy).paste('ola');
      expect(spy.log, isNot(contains('enter')));
    });
  });

  group('clipboard', () {
    test('the old clipboard comes back, and only after the app has read ours', () async {
      final spy = SpyBackend(clipboard: 'antigo');
      await serviceFor(spy).paste('ola');

      expect(spy.clipboard, 'ola', reason: 'restaurar na hora corre com quem esta lendo');
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(spy.clipboard, 'antigo');
    });

    test('restoreClipboard false never reads and never restores', () async {
      final spy = SpyBackend(clipboard: 'antigo');
      await serviceFor(spy).paste('ola', restoreClipboard: false);
      await Future<void>.delayed(const Duration(milliseconds: 200));

      expect(spy.log, isNot(contains('read')));
      expect(spy.clipboard, 'ola');
    });
  });

  group('failure never throws, and says where the text is', () {
    test('a refused Ctrl+V leaves the text on the clipboard', () async {
      final spy = SpyBackend(ctrlVSucceeds: false);
      final result = await serviceFor(spy).paste('ola');

      expect(result.pasted, isFalse);
      expect(result.copied, isTrue);
      expect(result.fallback, PasteFallback.clipboard);
    });

    test('a dead clipboard points at the session folder', () async {
      final spy = SpyBackend(writeSucceeds: false);
      final result = await serviceFor(spy).paste('ola');

      expect(result.pasted, isFalse);
      expect(result.copied, isFalse);
      expect(result.fallback, PasteFallback.sessionFolder);
      expect(spy.log, isNot(contains('ctrl+v')));
    });

    test('empty text is refused before anything is touched', () async {
      final spy = SpyBackend();
      final result = await serviceFor(spy).paste('');

      expect(result.pasted, isFalse);
      expect(spy.log, isEmpty);
    });

    test('success reports no fallback at all', () async {
      final spy = SpyBackend();
      final result = await serviceFor(spy).paste('ola');
      expect(result.pasted, isTrue);
      expect(result.fallback, isNull);
    });

    test('a refused restoreFocus does not stop Ctrl+V, still reports success, and gets logged',
        () async {
      final tempDir = Directory.systemTemp.createTempSync('dito_paste_test_');
      addTearDown(() => tempDir.deleteSync(recursive: true));
      final log = Logbook('paste-test', directory: tempDir.path);
      addTearDown(log.close);

      final spy = SpyBackend(restoreFocusSucceeds: false);
      final result = await serviceFor(spy, log: log).paste('ola');

      expect(spy.log, contains('ctrl+v'), reason: 'foco recusado é aviso, nunca aborta a colagem');
      expect(result.pasted, isTrue);
      expect(result.fallback, isNull);
      // Pins the log line paste_service.dart writes for this known false negative.
      expect(
        log.recent,
        anyElement(contains('paste: falha ao restaurar foco (prosseguindo mesmo assim)')),
      );
    });

    test('a refused Enter still reports the paste as done, but qualifies the result', () async {
      final spy = SpyBackend(pressEnterSucceeds: false);
      final result = await serviceFor(spy).paste('ola', sendEnter: true);

      expect(result.pasted, isTrue, reason: 'o texto ja foi colado quando o Enter falha');
      expect(result.copied, isTrue);
      expect(result.error, isNotNull);
      expect(result.fallback, isNull);
    });
  });

  group('alvo de terminal recebe UMA linha', () {
    const tresLinhas = 'primeira\nsegunda\nterceira';

    test('em console as quebras viram um espaco: sem bracketed paste, cada uma seria um envio',
        () async {
      final spy = SpyBackend(target: PasteTarget.console);
      await serviceFor(spy).paste(tresLinhas);
      expect(spy.escrito, 'primeira segunda terceira');
      expect(spy.digitado, 'primeira segunda terceira');
    });

    test('em terminal vale a mesma regra', () async {
      final spy = SpyBackend(target: PasteTarget.terminal);
      await serviceFor(spy).paste(tresLinhas);
      expect(spy.escrito, 'primeira segunda terceira');
    });

    test('em janela normal o texto vai inteiro, com as quebras', () async {
      final spy = SpyBackend(target: PasteTarget.gui);
      await serviceFor(spy).paste(tresLinhas);
      expect(spy.escrito, tresLinhas);
    });

    test('linhas em branco seguidas colapsam num espaco so, e as pontas sao aparadas', () {
      expect(joinLines('  um\n\n\n  dois  \r\n'), 'um dois');
    });

    test('o clipboard de volta guarda o texto ORIGINAL, com as quebras', () async {
      final spy = SpyBackend(clipboard: 'antigo', target: PasteTarget.console);
      await serviceFor(spy).paste(tresLinhas);
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(spy.clipboard, 'antigo');
    });

    test('um alvo que nao sabe se classificar nao derruba a colagem', () async {
      final spy = _AlvoQuebrado();
      final r = await serviceFor(spy).paste('ola');
      expect(r.pasted, isTrue);
    });
  });

  group('copy', () {
    test('copy copies and never presses a key', () async {
      final spy = SpyBackend();
      final result = await PasteService(backend: spy).copy('ola');

      expect(result.copied, isTrue);
      expect(result.pasted, isFalse);
      expect(spy.log, isNot(contains('ctrl+v')));
      expect(spy.clipboard, 'ola');
    });
  });
}
