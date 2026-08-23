import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../app_updater.dart';
import '../config/config_service.dart';
import '../l10n/app_strings.dart';
import '../config/paths.dart';
import '../core/logbook.dart';
import '../engine/engine_client.dart';
import '../engine/engine_supervisor.dart';
import '../engine/engine_protocol.dart';
import '../keys/hotkey_service.dart';
import '../library/library_reader.dart';
import '../output/alert_service.dart';
import '../output/native_paste_backend.dart';
import '../output/paste_service.dart';
import '../state/dito_controller.dart';
import '../state/hud_commands.dart';
import '../ui/hud/hud_state.dart';
import '../ui/tray/tray_controller.dart';
import '../ui/window_orchestrator.dart';

/// Everything the Dito desktop application owns in Single-Engine architecture.
class DitoApp {
  DitoApp() : log = Logbook('app');

  final Logbook log;

  final ConfigService config = ConfigService();
  final LibraryReader library = LibraryReader();
  final HudState hudState = HudState();
  final WindowOrchestrator orchestrator = WindowOrchestrator();

  late final EngineClient client = EngineClient(localeCode: () => config.config.ui.language);
  late final EngineSupervisor supervisor =
      EngineSupervisor(client: client, localeCode: () => config.config.ui.language);
  final HotkeyService hotkeys = createHotkeyService();
  final TrayController tray = TrayController();
  final AlertService alerts = createAlertService();
  late final DefaltUpdater updater = buildDitoUpdater();
  late final UpdateController updateController = UpdateController(updater: updater);
  late final DitoController controller = DitoController(
    client: client,
    supervisor: supervisor,
    config: config,
    paste: PasteService(backend: const NativePasteBackend(), log: log),
    hud: _toHud,
    review: _toReview,
    notify: _notify,
    playSound: _playAlarm,
  );

  final ValueNotifier<bool> paused = ValueNotifier<bool>(false);
  final ValueNotifier<FinishedEvent?> reviewEvent = ValueNotifier<FinishedEvent?>(null);

  /// False until every service is wired; the window shows a boot state meanwhile.
  final ValueNotifier<bool> isReady = ValueNotifier<bool>(false);

  Future<void> start({bool startHidden = true}) async {
    DitoPaths.ensureDirs();
    await config.load();

    unawaited(library.load(config.config.library.resolved()));
    unawaited(_sweepOldSessions());

    await orchestrator.init(startHidden: startHidden);

    controller.snapshot.addListener(_onSnapshot);

    hotkeys.onStart = controller.onHotkeyStart;
    hotkeys.onStop = controller.onHotkeyStop;
    hotkeys.onHoldCeiling = controller.onHoldCeiling;
    hotkeys.onRefused = controller.onHotkeyRefused;
    hotkeys.onGrabChanged = _onGrabChanged;
    hotkeys.addListener(_onHotkeys);
    await hotkeys.start(config.config.hotkeys);

    tray.onOpen = () => unawaited(orchestrator.showMainWindow());
    tray.onCopy = () => unawaited(controller.copyLastText());
    tray.onTogglePause = () => unawaited(togglePause());
    tray.onQuit = () => unawaited(shutdown());
    await tray.init(strings);
    await tray.update(controller.state, strings, config.config.hotkeys.pushToTalk,
        paused: paused.value);

    await supervisor.start();
    isReady.value = true;
    log('boot completo (Single-Engine)');
  }

  void _toHud(HudMessage message) {
    hudState.apply(message);
  }

  void _toReview(FinishedEvent event) {
    reviewEvent.value = event;
  }

  void _notify({required String title, required String body}) {
    if (!config.config.audio.alerts.notify) return;
    alerts.notify(title: title, body: body);
  }

  void _playAlarm() => alerts.playAlarm();

  /// The catalogue for everything outside a widget: the tray and the balloons.
  AppStrings get strings => stringsFor(config.config.ui.language);

  void _onSnapshot() {
    unawaited(tray.update(controller.state, strings,
        config.config.hotkeys.pushToTalk,
        paused: paused.value));
  }

  void _onHotkeys() => controller.setHookInstalled(hotkeys.hookInstalled);

  void _onGrabChanged(String action, String key, bool ok) {
    final label = key.toUpperCase();
    final what = action == 'meeting' ? strings.meetingLabel : strings.dictationLabel;
    _toHud(HudMessage.toast(
      ok ? HudToast.pasted : HudToast.failed,
      detail: ok
          ? strings.errKeyBack(label, what)
          : strings.errKeyTaken(label, what),
      ms: ok ? 4000 : 8000,
    ));
    unawaited(tray.update(controller.state, strings,
        config.config.hotkeys.pushToTalk,
        paused: paused.value));
  }

  Future<void> togglePause() async {
    paused.value = !paused.value;
    if (paused.value) {
      await hotkeys.pause();
    } else {
      await hotkeys.resume();
    }
    controller.setPaused(paused.value);
    await tray.update(controller.state, strings,
        config.config.hotkeys.pushToTalk,
        paused: paused.value);
  }

  Future<void> _sweepOldSessions() async {
    try {
      final result = await LibraryReader()
          .sweep(config.config.library.resolved(), config.config.library.keepDays);
      if (result.sessions > 0) {
        log('varredura: ${result.sessions} sessoes, ${result.bytes ~/ 1048576} MB');
      }
    } catch (e) {
      log('varredura falhou: $e');
    }
  }

  /// Ends any recording in progress before anything is torn down.
  Future<void> shutdown() async {
    log('encerrando');
    hotkeys.shutdown();
    await hotkeys.dispose();
    await tray.dispose();
    await supervisor.stop();
    await controller.dispose();
    hudState.dispose();
    await log.close();
    exit(0);
  }
}
