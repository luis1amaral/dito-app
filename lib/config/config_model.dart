import 'paths.dart';

/// Config model mirroring src/dito/config.py; defaults MUST match it field by field.
class AppConfig {
  const AppConfig({
    this.schema = 1,
    this.hotkeys = const HotkeyConfig(),
    this.audio = const AudioConfig(),
    this.stt = const SttConfig(),
    this.output = const OutputConfig(),
    this.obsidian = const ObsidianConfig(),
    this.library = const LibraryConfig(),
    this.ui = const UiConfig(),
  });

  final int schema;
  final HotkeyConfig hotkeys;
  final AudioConfig audio;
  final SttConfig stt;
  final OutputConfig output;
  final ObsidianConfig obsidian;
  final LibraryConfig library;
  final UiConfig ui;

  AppConfig copyWith({
    HotkeyConfig? hotkeys,
    AudioConfig? audio,
    SttConfig? stt,
    OutputConfig? output,
    ObsidianConfig? obsidian,
    LibraryConfig? library,
    UiConfig? ui,
  }) =>
      AppConfig(
        schema: schema,
        hotkeys: hotkeys ?? this.hotkeys,
        audio: audio ?? this.audio,
        stt: stt ?? this.stt,
        output: output ?? this.output,
        obsidian: obsidian ?? this.obsidian,
        library: library ?? this.library,
        ui: ui ?? this.ui,
      );

  @override
  bool operator ==(Object other) =>
      other is AppConfig &&
      other.schema == schema &&
      other.hotkeys == hotkeys &&
      other.audio == audio &&
      other.stt == stt &&
      other.output == output &&
      other.obsidian == obsidian &&
      other.library == library &&
      other.ui == ui;

  @override
  int get hashCode =>
      Object.hash(schema, hotkeys, audio, stt, output, obsidian, library, ui);
}

class HotkeyConfig {
  const HotkeyConfig({
    this.pushToTalk = 'f9',
    this.meetingToggle = 'f10',
    this.grab = true,
  });

  final String pushToTalk;
  final String meetingToggle;

  /// Swallow the key so it never reaches the app underneath.
  final bool grab;

  HotkeyConfig copyWith({String? pushToTalk, String? meetingToggle, bool? grab}) =>
      HotkeyConfig(
        pushToTalk: pushToTalk ?? this.pushToTalk,
        meetingToggle: meetingToggle ?? this.meetingToggle,
        grab: grab ?? this.grab,
      );

  @override
  bool operator ==(Object other) =>
      other is HotkeyConfig &&
      other.pushToTalk == pushToTalk &&
      other.meetingToggle == meetingToggle &&
      other.grab == grab;

  @override
  int get hashCode => Object.hash(pushToTalk, meetingToggle, grab);
}

class AudioConfig {
  const AudioConfig({this.device = '', this.alerts = const AlertConfig()});

  /// '' means the system default; otherwise an index or part of the device name.
  final String device;
  final AlertConfig alerts;

  AudioConfig copyWith({String? device, AlertConfig? alerts}) =>
      AudioConfig(device: device ?? this.device, alerts: alerts ?? this.alerts);

  @override
  bool operator ==(Object other) =>
      other is AudioConfig && other.device == device && other.alerts == alerts;

  @override
  int get hashCode => Object.hash(device, alerts);
}

class AlertConfig {
  // Off by default: the red pill already says it, and a popup per drop trains people to ignore it.
  const AlertConfig({
    this.deadMs = 700,
    this.quietMs = 2500,
    this.sound = false,
    this.notify = false,
  });

  final int deadMs;
  final int quietMs;
  final bool sound;
  final bool notify;

  AlertConfig copyWith({int? deadMs, int? quietMs, bool? sound, bool? notify}) =>
      AlertConfig(
        deadMs: deadMs ?? this.deadMs,
        quietMs: quietMs ?? this.quietMs,
        sound: sound ?? this.sound,
        notify: notify ?? this.notify,
      );

  @override
  bool operator ==(Object other) =>
      other is AlertConfig &&
      other.deadMs == deadMs &&
      other.quietMs == quietMs &&
      other.sound == sound &&
      other.notify == notify;

  @override
  int get hashCode => Object.hash(deadMs, quietMs, sound, notify);
}

class SttConfig {
  const SttConfig({
    this.model = 'small',
    this.language = 'pt',
    this.device = 'auto',
    this.beamDictation = 5,
    this.beamMeeting = 1,
    this.idleUnloadMin = 10.0,
  });

  /// tiny|base|small|medium|large-v3 - the installer pre-downloads small.
  final String model;
  final String language;

  /// auto|cpu|cuda
  final String device;
  final int beamDictation;
  final int beamMeeting;
  final double idleUnloadMin;

  SttConfig copyWith({
    String? model,
    String? language,
    String? device,
    int? beamDictation,
    int? beamMeeting,
    double? idleUnloadMin,
  }) =>
      SttConfig(
        model: model ?? this.model,
        language: language ?? this.language,
        device: device ?? this.device,
        beamDictation: beamDictation ?? this.beamDictation,
        beamMeeting: beamMeeting ?? this.beamMeeting,
        idleUnloadMin: idleUnloadMin ?? this.idleUnloadMin,
      );

  @override
  bool operator ==(Object other) =>
      other is SttConfig &&
      other.model == model &&
      other.language == language &&
      other.device == device &&
      other.beamDictation == beamDictation &&
      other.beamMeeting == beamMeeting &&
      other.idleUnloadMin == idleUnloadMin;

  @override
  int get hashCode => Object.hash(
      model, language, device, beamDictation, beamMeeting, idleUnloadMin);
}

class OutputConfig {
  const OutputConfig({
    this.paste = true,
    this.enter = true,
    this.confirm = true,
    this.restoreClipboard = true,
  });

  final bool paste;
  final bool enter;

  /// Opens the review card before anything is pasted.
  final bool confirm;
  final bool restoreClipboard;

  OutputConfig copyWith({
    bool? paste,
    bool? enter,
    bool? confirm,
    bool? restoreClipboard,
  }) =>
      OutputConfig(
        paste: paste ?? this.paste,
        enter: enter ?? this.enter,
        confirm: confirm ?? this.confirm,
        restoreClipboard: restoreClipboard ?? this.restoreClipboard,
      );

  @override
  bool operator ==(Object other) =>
      other is OutputConfig &&
      other.paste == paste &&
      other.enter == enter &&
      other.confirm == confirm &&
      other.restoreClipboard == restoreClipboard;

  @override
  int get hashCode => Object.hash(paste, enter, confirm, restoreClipboard);
}

class ObsidianConfig {
  const ObsidianConfig({this.vault = '~/notas', this.folder = 'trabalho'});

  final String vault;
  final String folder;

  ObsidianConfig copyWith({String? vault, String? folder}) =>
      ObsidianConfig(vault: vault ?? this.vault, folder: folder ?? this.folder);

  @override
  bool operator ==(Object other) =>
      other is ObsidianConfig && other.vault == vault && other.folder == folder;

  @override
  int get hashCode => Object.hash(vault, folder);
}

class LibraryConfig {
  const LibraryConfig({this.folder = '', this.keepDays = 30});

  /// Empty means "ask paths"; it must never reach the engine empty, or it writes to the CWD.
  final String folder;
  final int keepDays;

  String resolved() => folder.trim().isEmpty ? DitoPaths.defaultLibrary : folder;

  LibraryConfig copyWith({String? folder, int? keepDays}) =>
      LibraryConfig(folder: folder ?? this.folder, keepDays: keepDays ?? this.keepDays);

  @override
  bool operator ==(Object other) =>
      other is LibraryConfig && other.folder == folder && other.keepDays == keepDays;

  @override
  int get hashCode => Object.hash(folder, keepDays);
}

class UiConfig {
  const UiConfig({this.theme = 'auto', this.language = 'auto', this.tray = true});

  /// auto|light|dark
  final String theme;

  /// auto|en|pt_BR, independent from stt.language.
  final String language;
  final bool tray;

  UiConfig copyWith({String? theme, String? language, bool? tray}) => UiConfig(
        theme: theme ?? this.theme,
        language: language ?? this.language,
        tray: tray ?? this.tray,
      );

  @override
  bool operator ==(Object other) =>
      other is UiConfig &&
      other.theme == theme &&
      other.language == language &&
      other.tray == tray;

  @override
  int get hashCode => Object.hash(theme, language, tray);
}
