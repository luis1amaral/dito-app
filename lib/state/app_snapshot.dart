import '../engine/engine_health.dart';
import '../engine/engine_protocol.dart';

enum AppPhase { idle, recording, meeting, transcribing, paused }

/// The RARE state, roughly once a second. The audio level never lives here.
///
/// Immutable and compared by value, so a burst of events that changes nothing rebuilds nothing.
class AppSnapshot {
  const AppSnapshot({
    this.phase = AppPhase.idle,
    this.alarm = AudioState.ok,
    this.alarmReason,
    this.fixHint,
    this.engine = const EngineHealth(state: EngineState.starting),
    this.lastText,
    this.hookInstalled = true,
    this.deviceName,
  });

  final AppPhase phase;
  final AudioState alarm;
  final String? alarmReason;
  final String? fixHint;
  final EngineHealth engine;
  final String? lastText;

  /// False means the app cannot hear the keyboard, and has to say so.
  final bool hookInstalled;
  final String? deviceName;

  bool get isRecording => phase == AppPhase.recording || phase == AppPhase.meeting;
  bool get isBusy => isRecording || phase == AppPhase.transcribing;
  /// Transcribing counts: it runs on its own isolate, so only a live capture blocks a new one.
  bool get canStart => phase != AppPhase.recording && phase != AppPhase.meeting;

  AppSnapshot copyWith({
    AppPhase? phase,
    AudioState? alarm,
    String? alarmReason,
    String? fixHint,
    bool clearAlarm = false,
    EngineHealth? engine,
    String? lastText,
    bool? hookInstalled,
    String? deviceName,
  }) =>
      AppSnapshot(
        phase: phase ?? this.phase,
        alarm: clearAlarm ? AudioState.ok : (alarm ?? this.alarm),
        alarmReason: clearAlarm ? null : (alarmReason ?? this.alarmReason),
        fixHint: clearAlarm ? null : (fixHint ?? this.fixHint),
        engine: engine ?? this.engine,
        lastText: lastText ?? this.lastText,
        hookInstalled: hookInstalled ?? this.hookInstalled,
        deviceName: deviceName ?? this.deviceName,
      );

  @override
  bool operator ==(Object other) =>
      other is AppSnapshot &&
      other.phase == phase &&
      other.alarm == alarm &&
      other.alarmReason == alarmReason &&
      other.fixHint == fixHint &&
      other.engine == engine &&
      other.lastText == lastText &&
      other.hookInstalled == hookInstalled &&
      other.deviceName == deviceName;

  @override
  int get hashCode => Object.hash(
      phase, alarm, alarmReason, fixHint, engine, lastText, hookInstalled, deviceName);
}
