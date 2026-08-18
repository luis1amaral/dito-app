/// JSON-lines protocol with the Python engine: commands on stdin, events on stdout.
library;

// ---------------------------------------------------------------------------
// Commands (Flutter -> engine)
// ---------------------------------------------------------------------------

sealed class EngineCommand {
  const EngineCommand();

  Map<String, dynamic> toJson();

  /// Short name, for logging and for matching the reply.
  String get name;
}

class StartCommand extends EngineCommand {
  const StartCommand({
    required this.mode,
    required this.model,
    required this.language,
    required this.device,
    required this.devicePref,
  });

  /// 'dictation' or 'meeting'; the engine treats anything else as dictation.
  final String mode;
  final String model;
  final String language;
  final String device;
  final String devicePref;

  @override
  String get name => 'start';

  @override
  Map<String, dynamic> toJson() => {
        'cmd': 'start',
        'mode': mode,
        'model': model,
        'language': language,
        'device': device,
        'device_pref': devicePref,
      };
}

class StopCommand extends EngineCommand {
  const StopCommand();
  @override
  String get name => 'stop';
  @override
  Map<String, dynamic> toJson() => {'cmd': 'stop'};
}

class StatusCommand extends EngineCommand {
  const StatusCommand();
  @override
  String get name => 'status';
  @override
  Map<String, dynamic> toJson() => {'cmd': 'status'};
}

class ListDevicesCommand extends EngineCommand {
  const ListDevicesCommand();
  @override
  String get name => 'list_devices';
  @override
  Map<String, dynamic> toJson() => {'cmd': 'list_devices'};
}

class QuitCommand extends EngineCommand {
  const QuitCommand();
  @override
  String get name => 'quit';
  @override
  Map<String, dynamic> toJson() => {'cmd': 'quit'};
}

// ---------------------------------------------------------------------------
// Events (engine -> Flutter)
// ---------------------------------------------------------------------------

sealed class EngineEvent {
  const EngineEvent();

  /// The engine announces startup with this session_id: it is NOT a recording.
  static const String readySessionId = 'engine_ready';

  static EngineEvent parse(Map<String, dynamic> json) {
    final event = json['event'] as String? ?? '';
    return switch (event) {
      // Handshake reuses the recording event name; splitting it here is what stops the mix-up.
      'started' when json['session_id'] == readySessionId => const EngineReadyEvent(),
      'started' => StartedEvent.fromJson(json),
      'level' => LevelEvent.fromJson(json),
      'alarm' => AlarmEvent.fromJson(json),
      'phase' => PhaseEvent.fromJson(json),
      'partial' => PartialEvent.fromJson(json),
      'finished' => FinishedEvent.fromJson(json),
      'published' => PublishedEvent.fromJson(json),
      'failed' => FailedEvent.fromJson(json),
      'devices' => DevicesEvent.fromJson(json),
      'status' => StatusEvent.fromJson(json),
      _ => UnknownEvent(event, json),
    };
  }

  static double _double(Object? value) => switch (value) {
        final num n => n.toDouble(),
        final String s => double.tryParse(s) ?? 0,
        _ => 0,
      };

  static int _int(Object? value) => switch (value) {
        final num n => n.toInt(),
        final String s => int.tryParse(s) ?? 0,
        _ => 0,
      };

  static String _string(Object? value) => value is String ? value : '';

  static String? _stringOrNull(Object? value) =>
      value is String && value.isNotEmpty ? value : null;
}

/// The engine finished starting and can take commands.
class EngineReadyEvent extends EngineEvent {
  const EngineReadyEvent();
}

class StartedEvent extends EngineEvent {
  const StartedEvent({
    required this.sessionId,
    required this.mode,
    required this.deviceName,
  });

  final String sessionId;
  final String mode;
  final String deviceName;

  bool get isMeeting => mode == 'meeting';

  factory StartedEvent.fromJson(Map<String, dynamic> j) => StartedEvent(
        sessionId: EngineEvent._string(j['session_id']),
        mode: EngineEvent._string(j['mode']),
        deviceName: EngineEvent._string(j['device_name']),
      );
}

class LevelEvent extends EngineEvent {
  const LevelEvent({required this.peak, required this.rms, required this.seconds});

  final double peak;
  final double rms;
  final double seconds;

  factory LevelEvent.fromJson(Map<String, dynamic> j) => LevelEvent(
        peak: EngineEvent._double(j['peak']),
        rms: EngineEvent._double(j['rms']),
        seconds: EngineEvent._double(j['seconds']),
      );
}

enum AudioState { ok, quiet, dead, unknown }

class AlarmEvent extends EngineEvent {
  const AlarmEvent({required this.state, this.reason, this.fixHint});

  final AudioState state;
  final String? reason;

  /// When set, the diagnosis knows the fix: this is the repair button label.
  final String? fixHint;

  factory AlarmEvent.fromJson(Map<String, dynamic> j) => AlarmEvent(
        state: switch (EngineEvent._string(j['state'])) {
          'ok' => AudioState.ok,
          'quiet' => AudioState.quiet,
          'dead' => AudioState.dead,
          _ => AudioState.unknown,
        },
        reason: EngineEvent._stringOrNull(j['reason']),
        fixHint: EngineEvent._stringOrNull(j['fix_hint']),
      );
}

enum EnginePhase { idle, recording, transcribing, review, done, failed, unknown }

class PhaseEvent extends EngineEvent {
  const PhaseEvent({required this.phase, this.detail});

  final EnginePhase phase;
  final String? detail;

  factory PhaseEvent.fromJson(Map<String, dynamic> j) => PhaseEvent(
        phase: switch (EngineEvent._string(j['phase'])) {
          'idle' => EnginePhase.idle,
          'recording' => EnginePhase.recording,
          'transcribing' => EnginePhase.transcribing,
          'review' => EnginePhase.review,
          'done' => EnginePhase.done,
          'failed' => EnginePhase.failed,
          _ => EnginePhase.unknown,
        },
        detail: EngineEvent._stringOrNull(j['detail']),
      );
}

/// Partial transcript of one meeting chunk, emitted while the meeting is still running.
class PartialEvent extends EngineEvent {
  const PartialEvent({
    required this.index,
    required this.startS,
    required this.endS,
    required this.text,
  });

  final int index;
  final double startS;
  final double endS;
  final String text;

  factory PartialEvent.fromJson(Map<String, dynamic> j) => PartialEvent(
        index: EngineEvent._int(j['index']),
        startS: EngineEvent._double(j['start_s']),
        endS: EngineEvent._double(j['end_s']),
        text: EngineEvent._string(j['text']),
      );
}

class FinishedEvent extends EngineEvent {
  const FinishedEvent({
    required this.sessionId,
    required this.mode,
    required this.text,
    required this.seconds,
    required this.folder,
    required this.everHeardAudio,
  });

  final String sessionId;
  final String mode;
  final String text;
  final double seconds;
  final String folder;
  final bool everHeardAudio;

  bool get isMeeting => mode == 'meeting';

  factory FinishedEvent.fromJson(Map<String, dynamic> j) => FinishedEvent(
        sessionId: EngineEvent._string(j['session_id']),
        mode: EngineEvent._string(j['mode']),
        text: EngineEvent._string(j['text']),
        seconds: EngineEvent._double(j['seconds']),
        folder: EngineEvent._string(j['folder']),
        everHeardAudio: j['ever_heard_audio'] == true,
      );
}

class PublishedEvent extends EngineEvent {
  const PublishedEvent({
    required this.folder,
    required this.note,
    required this.noteInVault,
    required this.minutes,
    required this.words,
    this.warning,
  });

  final String folder;
  final String? note;
  final bool noteInVault;
  final int minutes;
  final int words;
  final String? warning;

  factory PublishedEvent.fromJson(Map<String, dynamic> j) => PublishedEvent(
        folder: EngineEvent._string(j['folder']),
        note: EngineEvent._stringOrNull(j['note']),
        noteInVault: j['note_in_vault'] == true,
        minutes: EngineEvent._int(j['minutes']),
        words: EngineEvent._int(j['words']),
        warning: EngineEvent._stringOrNull(j['warning']),
      );
}

class FailedEvent extends EngineEvent {
  const FailedEvent({required this.sessionId, required this.reason, this.folder});

  final String sessionId;
  final String reason;
  final String? folder;

  factory FailedEvent.fromJson(Map<String, dynamic> j) => FailedEvent(
        sessionId: EngineEvent._string(j['session_id']),
        reason: EngineEvent._string(j['reason']),
        folder: EngineEvent._stringOrNull(j['folder']),
      );
}

class DeviceItem {
  const DeviceItem({required this.index, required this.name, required this.isDefault});

  final int index;
  final String name;
  final bool isDefault;

  factory DeviceItem.fromJson(Map<String, dynamic> j) => DeviceItem(
        index: EngineEvent._int(j['index']),
        name: EngineEvent._string(j['name']),
        isDefault: j['default'] == true,
      );
}

class DevicesEvent extends EngineEvent {
  const DevicesEvent(this.devices);

  final List<DeviceItem> devices;

  factory DevicesEvent.fromJson(Map<String, dynamic> j) {
    final raw = j['devices'];
    if (raw is! List) return const DevicesEvent(<DeviceItem>[]);
    return DevicesEvent(raw
        .whereType<Map>()
        .map((e) => DeviceItem.fromJson(Map<String, dynamic>.from(e)))
        .toList(growable: false));
  }
}

class StatusEvent extends EngineEvent {
  const StatusEvent({
    required this.isRecording,
    required this.model,
    required this.backend,
  });

  /// The field the previous port dropped, and without which nothing can resynchronise.
  final bool isRecording;
  final String model;
  final String backend;

  factory StatusEvent.fromJson(Map<String, dynamic> j) => StatusEvent(
        isRecording: EngineEvent._string(j['state']) == 'recording',
        model: EngineEvent._string(j['model']),
        backend: EngineEvent._string(j['backend']),
      );
}

class UnknownEvent extends EngineEvent {
  const UnknownEvent(this.event, this.raw);

  final String event;
  final Map<String, dynamic> raw;
}
