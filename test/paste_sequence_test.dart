import 'package:dito_app/core/result.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:flutter_test/flutter_test.dart';

/// Records what happened and in which order, so the sequence itself can be asserted.
class SpyBackend implements PasteBackend {
  SpyBackend({
    this.clipboard,
    this.writeSucceeds = true,
    this.ctrlVSucceeds = true,
  });

  String? clipboard;
  bool writeSucceeds;
  bool ctrlVSucceeds;

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
    if (!writeSucceeds) return false;
    clipboard = text;
    return true;
  }

  @override
  Future<bool> pressCtrlV() async {
    _mark('ctrl+v');
    return ctrlVSucceeds;
  }

  @override
  Future<bool> pressEnter() async {
    _mark('enter');
    return true;
  }

  @override
  Future<bool> restoreFocus() async {
    _mark('focus');
    return true;
  }
}

void main() {
  PasteService serviceFor(SpyBackend spy) => PasteService(
        backend: spy,
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
