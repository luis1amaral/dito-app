import 'package:toml/toml.dart';

import 'config_model.dart';

/// TOML <-> model; unknown keys land in `_extras` so a save never drops what it cannot parse.
class ConfigCodec {
  const ConfigCodec();

  static const int currentSchema = 1;

  DecodedConfig decode(String toml) {
    Map<String, dynamic> raw;
    try {
      raw = Map<String, dynamic>.from(TomlDocument.parse(toml).toMap());
    } catch (e) {
      return DecodedConfig(
        config: const AppConfig(),
        extras: const <String, dynamic>{},
        error: 'TOML invalido: $e',
      );
    }
    return DecodedConfig(config: _fill(raw), extras: raw);
  }

  AppConfig _fill(Map<String, dynamic> raw) {
    final hotkeys = _table(raw, 'hotkeys');
    final audio = _table(raw, 'audio');
    final alerts = _table(audio, 'alerts');
    final stt = _table(raw, 'stt');
    final output = _table(raw, 'output');
    final meeting = _table(raw, 'meeting');
    final obsidian = _table(meeting, 'obsidian');
    final library = _table(raw, 'library');
    final ui = _table(raw, 'ui');

    const d = AppConfig();
    return AppConfig(
      schema: _int(raw['schema'], d.schema),
      hotkeys: HotkeyConfig(
        pushToTalk: _string(hotkeys['push_to_talk'], d.hotkeys.pushToTalk),
        meetingToggle: _string(hotkeys['meeting_toggle'], d.hotkeys.meetingToggle),
        grab: _bool(hotkeys['grab'], d.hotkeys.grab),
      ),
      audio: AudioConfig(
        device: _string(audio['device'], d.audio.device),
        alerts: AlertConfig(
          deadMs: _int(alerts['dead_ms'], d.audio.alerts.deadMs),
          quietMs: _int(alerts['quiet_ms'], d.audio.alerts.quietMs),
          sound: _bool(alerts['sound'], d.audio.alerts.sound),
          notify: _bool(alerts['notify'], d.audio.alerts.notify),
        ),
      ),
      stt: SttConfig(
        model: _string(stt['model'], d.stt.model),
        language: _string(stt['language'], d.stt.language),
        device: _string(stt['device'], d.stt.device),
        beamDictation: _int(stt['beam_dictation'], d.stt.beamDictation),
        beamMeeting: _int(stt['beam_meeting'], d.stt.beamMeeting),
        idleUnloadMin: _double(stt['idle_unload_min'], d.stt.idleUnloadMin),
      ),
      output: OutputConfig(
        paste: _bool(output['paste'], d.output.paste),
        enter: _bool(output['enter'], d.output.enter),
        confirm: _bool(output['confirm'], d.output.confirm),
        restoreClipboard: _bool(output['restore_clipboard'], d.output.restoreClipboard),
      ),
      obsidian: ObsidianConfig(
        vault: _string(obsidian['vault'], d.obsidian.vault),
        folder: _string(obsidian['folder'], d.obsidian.folder),
      ),
      library: LibraryConfig(
        folder: _string(library['folder'], d.library.folder),
        keepDays: _int(library['keep_days'], d.library.keepDays),
      ),
      ui: UiConfig(
        theme: _string(ui['theme'], d.ui.theme),
        language: _string(ui['language'], d.ui.language),
        tray: _bool(ui['tray'], d.ui.tray),
      ),
    );
  }

  /// Rebuilds the document from `extras`, overwriting only the keys the model owns.
  String encode(AppConfig config, Map<String, dynamic> extras) {
    final out = _deepCopy(extras);
    out['schema'] = config.schema;

    _into(out, 'hotkeys', {
      'push_to_talk': config.hotkeys.pushToTalk,
      'meeting_toggle': config.hotkeys.meetingToggle,
      'grab': config.hotkeys.grab,
    });

    final audio = _into(out, 'audio', {'device': config.audio.device});
    _into(audio, 'alerts', {
      'dead_ms': config.audio.alerts.deadMs,
      'quiet_ms': config.audio.alerts.quietMs,
      'sound': config.audio.alerts.sound,
      'notify': config.audio.alerts.notify,
    });

    _into(out, 'stt', {
      'model': config.stt.model,
      'language': config.stt.language,
      'device': config.stt.device,
      'beam_dictation': config.stt.beamDictation,
      'beam_meeting': config.stt.beamMeeting,
      'idle_unload_min': config.stt.idleUnloadMin,
    });

    _into(out, 'output', {
      'paste': config.output.paste,
      'enter': config.output.enter,
      'confirm': config.output.confirm,
      'restore_clipboard': config.output.restoreClipboard,
    });

    final meeting = _into(out, 'meeting', <String, dynamic>{});
    _into(meeting, 'obsidian', {
      'vault': config.obsidian.vault,
      'folder': config.obsidian.folder,
    });

    _into(out, 'library', {
      'folder': config.library.folder,
      'keep_days': config.library.keepDays,
    });

    _into(out, 'ui', {
      'theme': config.ui.theme,
      'language': config.ui.language,
      'tray': config.ui.tray,
    });

    return TomlDocument.fromMap(out).toString();
  }

  static Map<String, dynamic> _table(Map<String, dynamic> parent, String key) {
    final value = parent[key];
    return value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
  }

  static Map<String, dynamic> _into(
      Map<String, dynamic> parent, String key, Map<String, dynamic> values) {
    final existing = parent[key];
    final table = existing is Map ? Map<String, dynamic>.from(existing) : <String, dynamic>{};
    table.addAll(values);
    parent[key] = table;
    return table;
  }

  static Map<String, dynamic> _deepCopy(Map<String, dynamic> source) {
    final out = <String, dynamic>{};
    source.forEach((key, value) {
      out[key] = value is Map ? _deepCopy(Map<String, dynamic>.from(value)) : value;
    });
    return out;
  }

  // Wrong type keeps the default AND the original value survives in extras.
  static String _string(Object? value, String fallback) =>
      value is String ? value : fallback;

  // Checked before int, or `dead_ms = true` would silently become 1.
  static bool _bool(Object? value, bool fallback) => value is bool ? value : fallback;

  static int _int(Object? value, int fallback) =>
      value is bool ? fallback : (value is int ? value : fallback);

  static double _double(Object? value, double fallback) =>
      value is bool ? fallback : (value is num ? value.toDouble() : fallback);
}

class DecodedConfig {
  const DecodedConfig({required this.config, required this.extras, this.error});

  final AppConfig config;

  /// The raw document, so unknown keys survive a save.
  final Map<String, dynamic> extras;
  final String? error;
}
