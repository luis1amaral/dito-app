import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../config/config_model.dart';
import '../config/config_service.dart';
import '../config/paths.dart';
import '../core/logbook.dart';
import '../core/result.dart';
import '../l10n/app_strings.dart';
import '../engine/engine_client.dart';
import '../engine/engine_protocol.dart';
import '../engine/engine_supervisor.dart';
import '../output/paste_service.dart';
import 'alarm_policy.dart';
import 'app_snapshot.dart';
import 'hud_commands.dart';

/// Where the app's policy lives; the only class that decides anything.
class DitoController {
  DitoController({
    required this.client,
    required this.supervisor,
    required this.config,
    required this.paste,
    required this.hud,
    required this.review,
    this.notify,
    this.playSound,
    this.now = _defaultNow,
    Logbook? log,
  })  : _log = log ?? Logbook('controller'),
        alarms = AlarmPolicy(now: now) {
    _events = client.events.listen(_onEvent);
    supervisor.addListener(_onHealth);
    supervisor.onDiedRecording = _onEngineDiedRecording;
  }

  static int _defaultNow() => DateTime.now().microsecondsSinceEpoch;

  final EngineClient client;
  final EngineSupervisor supervisor;
  final ConfigService config;
  final PasteService paste;
  final AlarmPolicy alarms;
  final int Function() now;
  final Logbook _log;

  /// Sends one signal to the HUD window.
  final void Function(HudMessage message) hud;

  /// Asks the review window to show the text; null when the card is not used.
  final void Function(FinishedEvent event) review;

  /// Shows a desktop notification; only the FIRST alarm of each episode gets one.
  final void Function({required String title, required String body})? notify;

  /// Plays the alarm sound; throttled to once every ten seconds.
  final void Function()? playSound;

  final ValueNotifier<AppSnapshot> snapshot =
      ValueNotifier<AppSnapshot>(const AppSnapshot());

  /// The 20 Hz signal, deliberately outside the snapshot.
  final ValueNotifier<double> level = ValueNotifier<double>(0);

  StreamSubscription<EngineEvent>? _events;
  Timer? _commandTimeout;
  Timer? _transcribeTimeout;

  /// The finished session the review card is holding, if any.
  FinishedEvent? pendingReview;

  AppConfig get _cfg => config.config;

  /// The controller owns no BuildContext, so it looks the catalogue up by preference.
  AppStrings get _s => stringsFor(_cfg.ui.language);
  AppSnapshot get state => snapshot.value;

  void _set(AppSnapshot next) {
    if (next == snapshot.value) return;
    snapshot.value = next;
  }

  void _onHealth() => _set(state.copyWith(engine: supervisor.health));

  void _onEngineDiedRecording(String reason) {
    _set(state.copyWith(phase: AppPhase.idle));
    hud(HudMessage.dead(reason, canFix: false));
    // The WAV survived: guarantee 1 holds even when the engine does not.
    notify?.call(
      title: _s.notifyEngineDied,
      body: _s.notifyEngineDiedWhy,
    );
    if (_cfg.audio.alerts.sound) playSound?.call();
  }

  // ---- key actions ----

  bool onHotkeyStart(String action) {
    if (!state.canStart) {
      _log('start ignorado: fase ${state.phase.name}'
          ' (revisao pendente=${pendingReview != null})');
      // Auto-cura contra o "ainda terminando o anterior" preso: uma transcricao que travou ou
      // morreu sem emitir finished/failed deixava a fase em transcribing para sempre. So agimos
      // nesse estado - nunca numa gravacao ativa (essa recusa e legitima). Perguntamos o estado
      // real ao motor e o handler de StatusEvent resincroniza para idle quando nao ha sessao.
      if (state.phase == AppPhase.transcribing) _resyncFromEngine();
      // A refusal the user cannot see reads exactly like a dead shortcut.
      hud(HudMessage.toast(HudToast.stillBusy, ms: 1600));
      return false;
    }
    if (!supervisor.health.canAcceptCommands) {
      // Silent here is what made a dead shortcut impossible to diagnose from the log.
      _log('start recusado: motor ${supervisor.health.state.name}'
          ' (${supervisor.health.reason ?? "sem motivo"})');
      hud(HudMessage.toast(HudToast.engineStarting));
      return false;
    }

    final meeting = action == 'meeting';
    supervisor.wasRecording = true;
    final sent = client.send(StartCommand(
      mode: meeting ? 'meeting' : 'dictation',
      model: _cfg.stt.model,
      language: _cfg.stt.language,
      device: _cfg.audio.device,
      devicePref: _cfg.stt.device,
    ));

    if (!sent) {
      supervisor.wasRecording = false;
      _log('start recusado: nao consegui escrever no motor');
      hud(HudMessage.toast(HudToast.engineUnreachable));
      return false;
    }
    _log('start aceito: ${meeting ? "meeting" : "dictation"}');
    _armTimeout();
    return true;
  }

  /// A key press the machine swallowed still has to say why on screen.
  void onHotkeyRefused(String action, String blockedBy) {
    _log('tecla recusada: $action (ativo=$blockedBy)');
    hud(HudMessage.toast(HudToast.stillBusy, ms: 1600));
  }

  void onHotkeyStop(String action) {
    if (!state.isRecording) return;
    supervisor.wasRecording = false;
    if (!client.send(const StopCommand())) {
      hud(HudMessage.toast(HudToast.engineUnreachable));
    }
  }

  /// A hold that hit its ceiling ends the recording and says why.
  void onHoldCeiling(String action) {
    hud(HudMessage.toast(HudToast.recordingEnded, ms: 4000));
  }

  /// Asks the engine for the truth and unsticks a phase that never came home. We TRUST the engine:
  /// the StatusEvent handler only drops to idle when the engine reports it is not recording, so a
  /// genuine recording in progress is never killed. If the engine is unreachable, send() returns
  /// false and the phase is a lie anyway - then it is safe to go straight back to idle.
  void _resyncFromEngine() {
    final asked = client.send(const StatusCommand());
    if (!asked) {
      supervisor.wasRecording = false;
      _set(state.copyWith(phase: AppPhase.idle));
      hud(HudMessage.dismiss);
    }
  }

  /// A start that never answers must not leave the app stuck: the engine reports a bad
  /// preflight with an alarm and no failure, so this is the only way back to idle.
  void _armTimeout() {
    _commandTimeout?.cancel();
    _commandTimeout = Timer(const Duration(seconds: 5), () {
      if (state.isRecording) return;
      supervisor.markDegraded('o motor nao respondeu ao start');
      supervisor.wasRecording = false;
      _set(state.copyWith(phase: AppPhase.idle));
      hud(HudMessage.dead('o motor não respondeu', canFix: false));
    });
  }

  /// ModelNotReady dies on stderr with no failed event; without this the app is stuck forever.
  void _armTranscribeTimeout() {
    _transcribeTimeout?.cancel();
    _transcribeTimeout = Timer(const Duration(seconds: 120), () {
      if (state.phase != AppPhase.transcribing) return;
      _log('transcricao sem resposta ha 120s: liberando o app');
      supervisor.markDegraded('a transcricao nao respondeu');
      supervisor.wasRecording = false;
      _set(state.copyWith(phase: AppPhase.idle));
      hud(HudMessage.toast(HudToast.failed,
          detail: 'a transcrição não respondeu', ms: 6000));
    });
  }

  // ---- engine events ----

  void _onEvent(EngineEvent event) {
    switch (event) {
      case EngineReadyEvent():
        _log('motor pronto');

      case StatusEvent(:final isRecording):
        // Resynchronise: if we disagree with the engine, the engine wins.
        if (!isRecording && state.isBusy) {
          _transcribeTimeout?.cancel();
          _set(state.copyWith(phase: AppPhase.idle));
          hud(HudMessage.dismiss);
        }

      case StartedEvent(:final isMeeting, :final deviceName):
        _commandTimeout?.cancel();
        supervisor.markHealthy();
        alarms.reset();
        _set(state.copyWith(
          phase: isMeeting ? AppPhase.meeting : AppPhase.recording,
          deviceName: deviceName,
          clearAlarm: true,
        ));
        hud(HudMessage.recording(meeting: isMeeting));

      case LevelEvent(:final rms):
        level.value = rms;
        hud(HudMessage.level(rms));

      case AlarmEvent(state: final audio, :final reason, :final fixHint):
        _onAlarm(audio, reason, fixHint);

      case PhaseEvent(:final phase):
        if (phase == EnginePhase.transcribing) {
          _set(state.copyWith(phase: AppPhase.transcribing));
          hud(HudMessage.working(HudWork.transcribing));
          _armTranscribeTimeout();
        }

      case PartialEvent(:final endS):
        // Live meeting progress; the Python HUD shows the same thing.
        _armTranscribeTimeout();
        hud(HudMessage.working(HudWork.minutesDone, minutes: (endS / 60).floor()));

      case FinishedEvent():
        _onFinished(event);

      case FailedEvent(:final reason):
        _commandTimeout?.cancel();
        _transcribeTimeout?.cancel();
        supervisor.wasRecording = false;
        _set(state.copyWith(phase: AppPhase.idle));
        hud(HudMessage.toast(HudToast.failed, detail: reason, ms: 4000));

      case PublishedEvent():
      case DevicesEvent():
      case UnknownEvent():
        break;
    }
  }

  void _onAlarm(AudioState audio, String? reason, String? fixHint) {
    switch (audio) {
      case AudioState.dead:
        _set(state.copyWith(alarm: audio, alarmReason: reason, fixHint: fixHint));
        hud(HudMessage.dead(reason, canFix: fixHint != null));
        final action = alarms.evaluate(
          AlarmEvent(state: audio, reason: reason, fixHint: fixHint),
          _cfg.audio.alerts,
        );
        if (action.sound) playSound?.call();
        if (action.notify) {
          notify?.call(
            title: '${_s.appTitle} - ${_s.hudNoAudio}',
            body: reason ?? _s.notifyNoAudio,
          );
        }
      case AudioState.quiet:
        _set(state.copyWith(alarm: audio, alarmReason: reason));
        hud(HudMessage.quiet(reason));
      case AudioState.ok:
        alarms.reset();
        _set(state.copyWith(clearAlarm: true));
        if (state.isRecording) {
          hud(HudMessage.recording(meeting: state.phase == AppPhase.meeting));
        }
      case AudioState.unknown:
        break;
    }
  }

  void _onFinished(FinishedEvent event) {
    _commandTimeout?.cancel();
    _transcribeTimeout?.cancel();
    supervisor.wasRecording = false;
    level.value = 0;
    _set(state.copyWith(
      phase: AppPhase.idle,
      lastText: event.text.isEmpty ? state.lastText : event.text,
    ));

    if (event.text.trim().isEmpty) {
      // A mis-tap leaves nothing behind and says nothing: the watchdog's grace makes a
      // recording this short always look silent, so alarming here is a guaranteed lie.
      hud(HudMessage.dismiss);
      return;
    }

    if (_cfg.output.confirm) {
      pendingReview = event;
      hud(HudMessage.dismiss);
      review(event);
      return;
    }

    hud(HudMessage.dismiss);

    // A meeting is never pasted without review.
    if (event.isMeeting) return;
    if (!_cfg.output.paste) return;
    unawaited(_paste(event.text));
  }

  Future<void> _paste(String text) async {
    final result = await paste.paste(
      text,
      sendEnter: _cfg.output.enter,
      restoreClipboard: _cfg.output.restoreClipboard,
    );
    final onde = result.fallback;
    if (onde != null) {
      hud(HudMessage.toast(
          onde == PasteFallback.clipboard
              ? HudToast.pasteToClipboard
              : HudToast.pasteToFolder,
          ms: 6000));
    }
  }

  // ---- review card ----

  Future<void> _saveToVault(String text) async {
    try {
      final targetDir = DitoPaths.resolveObsidianPath(
        _cfg.obsidian.vault,
        _cfg.obsidian.folder,
      );
      final dir = Directory(targetDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      final n = DateTime.fromMillisecondsSinceEpoch(now());
      final stamp = '${n.year.toString().padLeft(4, '0')}-'
          '${n.month.toString().padLeft(2, '0')}-'
          '${n.day.toString().padLeft(2, '0')}-'
          '${n.hour.toString().padLeft(2, '0')}'
          '${n.minute.toString().padLeft(2, '0')}'
          '${n.second.toString().padLeft(2, '0')}';
      final file = File('$targetDir\\$stamp.md');
      final content = '# Nota Dito - ${n.day.toString().padLeft(2, '0')}/${n.month.toString().padLeft(2, '0')}/${n.year} ${n.hour.toString().padLeft(2, '0')}:${n.minute.toString().padLeft(2, '0')}\n\n$text\n';
      await file.writeAsString(content);
      _log('salvo no obsidian em ${file.path}');
    } catch (e) {
      _log('falha ao salvar no obsidian: $e');
    }
  }

  Future<void> onReviewSend(String text, {required bool toVault}) async {
    pendingReview = null;
    _set(state.copyWith(lastText: text));
    if (text.trim().isEmpty) return;

    if (toVault) {
      hud(HudMessage.working(HudWork.saving));
      await _saveToVault(text);
    }

    // 150 ms for the focus to settle after the card hands it back.
    await Future<void>.delayed(const Duration(milliseconds: 150));
    if (_cfg.output.paste) await _paste(text);

    if (toVault) {
      hud(HudMessage.toast(HudToast.pasted, ms: 1200));
    } else if (!_cfg.output.paste) {
      hud(HudMessage.dismiss);
    }
  }

  void onReviewDiscard() {
    pendingReview = null;
    hud(HudMessage.toast(HudToast.discarded, ms: 1200));
  }

  Future<void> copyLastText() async {
    final text = state.lastText;
    if (text == null || text.isEmpty) return;
    // Copy means copy: the old port pasted here, injecting text into whatever was in front.
    await paste.copy(text);
    hud(HudMessage.toast(HudToast.copied, ms: 1200));
  }

  void setPaused(bool paused) {
    _set(state.copyWith(phase: paused ? AppPhase.paused : AppPhase.idle));
  }

  void setHookInstalled(bool installed) =>
      _set(state.copyWith(hookInstalled: installed));

  Future<void> dispose() async {
    _commandTimeout?.cancel();
    _transcribeTimeout?.cancel();
    await _events?.cancel();
    supervisor.removeListener(_onHealth);
    snapshot.dispose();
    level.dispose();
    await _log.close();
  }
}
