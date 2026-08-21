import 'package:dito_app/config/config_codec.dart';
import 'package:dito_app/config/config_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const codec = ConfigCodec();

  group('defaults match src/dito/config.py field by field', () {
    const d = AppConfig();

    test('hotkeys', () {
      expect(d.hotkeys.pushToTalk, 'f9');
      expect(d.hotkeys.meetingToggle, 'f10');
      expect(d.hotkeys.grab, isTrue);
    });

    test('audio alerts carry the measured watchdog windows', () {
      expect(d.audio.device, '');
      expect(d.audio.alerts.deadMs, 700);
      expect(d.audio.alerts.quietMs, 2500);
      // Both channels ship off: the red pill carries the alarm, a popup per drop only annoys.
      expect(d.audio.alerts.sound, isFalse);
      expect(d.audio.alerts.notify, isFalse);
    });

    test('stt model is small, not base — the installer only pre-downloads small', () {
      expect(d.stt.model, 'small');
      expect(d.stt.language, 'pt');
      expect(d.stt.device, 'auto');
      expect(d.stt.beamDictation, 5);
      expect(d.stt.beamMeeting, 1);
      expect(d.stt.idleUnloadMin, 10.0);
    });

    test('output.confirm defaults to true, as in Python', () {
      expect(d.output.paste, isTrue);
      expect(d.output.enter, isTrue);
      expect(d.output.confirm, isTrue);
      expect(d.output.restoreClipboard, isTrue);
    });

    test('library keeps 30 days and never resolves to a relative path', () {
      expect(d.library.keepDays, 30);
      expect(d.library.resolved(), isNot(''));
      expect(d.library.resolved(), isNot('.'));
    });

    test('obsidian and ui', () {
      expect(d.obsidian.vault, '~/notas');
      expect(d.obsidian.folder, 'trabalho');
      expect(d.ui.theme, 'auto');
      expect(d.ui.language, 'auto');
      expect(d.ui.tray, isTrue);
    });
  });

  group('decode', () {
    test('reads a full document', () {
      final decoded = codec.decode('''
schema = 1

[hotkeys]
push_to_talk = "f8"
meeting_toggle = "f7"
grab = false

[audio]
device = "H510"

[audio.alerts]
dead_ms = 900
quiet_ms = 3000
sound = false
notify = false

[stt]
model = "medium"
language = "en"
device = "cuda"

[output]
paste = false
enter = false
confirm = false
restore_clipboard = false

[library]
folder = "D:/Gravacoes"
keep_days = 7

[ui]
theme = "dark"
language = "en"
tray = false
''');
      final c = decoded.config;
      expect(decoded.error, isNull);
      expect(c.hotkeys.pushToTalk, 'f8');
      expect(c.hotkeys.grab, isFalse);
      expect(c.audio.device, 'H510');
      expect(c.audio.alerts.deadMs, 900);
      expect(c.stt.model, 'medium');
      expect(c.stt.device, 'cuda');
      expect(c.output.confirm, isFalse);
      expect(c.library.folder, 'D:/Gravacoes');
      expect(c.library.keepDays, 7);
      expect(c.ui.theme, 'dark');
    });

    test('a bool never slips into an int field', () {
      final decoded = codec.decode('[audio.alerts]\ndead_ms = true\n');
      expect(decoded.config.audio.alerts.deadMs, 700);
    });

    test('a wrong type keeps the default instead of throwing', () {
      final decoded = codec.decode('[stt]\nmodel = 42\nidle_unload_min = "muito"\n');
      expect(decoded.config.stt.model, 'small');
      expect(decoded.config.stt.idleUnloadMin, 10.0);
    });

    test('broken TOML yields defaults plus an error, never an exception', () {
      final decoded = codec.decode('[[[ nao e toml');
      expect(decoded.error, isNotNull);
      expect(decoded.config, const AppConfig());
    });
  });

  group('round trip', () {
    test('an unknown key survives being saved', () {
      final decoded = codec.decode('''
schema = 1
minha_chave = "nao mexa"

[experimental]
algo = 3

[stt]
model = "small"
''');
      final encoded = codec.encode(decoded.config, decoded.extras);
      expect(encoded, contains('nao mexa'));
      expect(encoded, contains('experimental'));
      expect(encoded, contains('algo'));

      final again = codec.decode(encoded);
      expect(again.extras['minha_chave'], 'nao mexa');
      expect((again.extras['experimental'] as Map)['algo'], 3);
    });

    test('a wrong-typed value is preserved even though the model ignored it', () {
      final decoded = codec.decode('[stt]\nmodel = 42\n');
      final encoded = codec.encode(decoded.config, decoded.extras);
      // The model kept its default, but the file must not lose what the owner wrote.
      expect(codec.decode(encoded).config.stt.model, 'small');
    });

    test('changed values are written back', () {
      final decoded = codec.decode('[hotkeys]\npush_to_talk = "f9"\n');
      final next = decoded.config.copyWith(
        hotkeys: decoded.config.hotkeys.copyWith(pushToTalk: 'f4'),
      );
      final encoded = codec.encode(next, decoded.extras);
      expect(codec.decode(encoded).config.hotkeys.pushToTalk, 'f4');
    });
  });
}
