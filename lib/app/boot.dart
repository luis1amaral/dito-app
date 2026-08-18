import 'dart:async';
import 'dart:io';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:dito_win32/dito_win32.dart';
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
import '../platform/window_bus.dart';
import '../state/dito_controller.dart';
import '../state/hud_commands.dart';
import '../ui/tray/tray_controller.dart';

/// Window roles, carried as the sub-window argument.
class WindowRole {
  static const String main = 'main';
  static const String hud = 'hud';
  static const String review = 'review';
}

/// Everything the main window owns. Sub-windows are views and own nothing.
class DitoApp {
  DitoApp() : log = Logbook('app');

  final Logbook log;

  // Built eagerly, never late: the window renders before start() finishes, and a late
  // field there is a LateInitializationError on the very first frame.
  final ConfigService config = ConfigService();
  final LibraryReader library = LibraryReader();
  final EngineClient client = EngineClient();
  late final EngineSupervisor supervisor = EngineSupervisor(client: client);
  final HotkeyService hotkeys = createHotkeyService();
  final TrayController tray = TrayController();
  final AlertService alerts = createAlertService();
  late final DefaltUpdater updater = buildDitoUpdater();
  late final UpdateController updateController = UpdateController(updater: updater);
  late final DitoController controller = DitoController(
    client: client,
    supervisor: supervisor,
    config: config,
    paste: PasteService(backend: const NativePasteBackend()),
    hud: _toHud,
    review: _toReview,
    notify: _notify,
    playSound: _playAlarm,
  );

  final ValueNotifier<bool> paused = ValueNotifier<bool>(false);

  /// False until every service is wired; the window shows a boot state meanwhile.
  final ValueNotifier<bool> isReady = ValueNotifier<bool>(false);

  String? _hudWindowId;
  String? _reviewWindowId;
  WindowBus? _bus;

  /// Sub-windows are created once and only ever hidden: spinning up an engine costs
  /// 150-300 ms and the pill has to appear on the key going down.
  Future<void> start() async {
    DitoPaths.ensureDirs();
    await config.load();

    unawaited(library.load(config.config.library.resolved()));
    unawaited(_sweepOldSessions());

    await _openSubWindows();

    controller.snapshot.addListener(_onSnapshot);
    config.addListener(_broadcastAppearance);
    _broadcastAppearance();

    hotkeys.onStart = controller.onHotkeyStart;
    hotkeys.onStop = controller.onHotkeyStop;
    hotkeys.onHoldCeiling = controller.onHoldCeiling;
    hotkeys.onRefused = controller.onHotkeyRefused;
    hotkeys.addListener(_onHotkeys);
    await hotkeys.start(config.config.hotkeys);

    tray.onOpen = () => onOpenWindow?.call();
    tray.onCopy = () => unawaited(controller.copyLastText());
    tray.onTogglePause = () => unawaited(togglePause());
    tray.onQuit = () => unawaited(shutdown());
    // Tray icon is Win32; Linux boots without it until a native tray lands (docs/LINUX.md).
    if (Platform.isWindows) {
      await tray.init();
      await tray.update(controller.state, strings, config.config.hotkeys.pushToTalk,
          paused: paused.value);
    }

    await supervisor.start();
    isReady.value = true;
    log('boot completo');

    if (Platform.environment['DITO_SELFTEST'] == '1') unawaited(_selfTest());
    if (Platform.environment['DITO_HUD_HOLD'] == '1') unawaited(_holdHud());
  }

  void Function()? onOpenWindow;

  /// Walks every HUD state and photographs each one: a screen grab cannot see a DWM-alpha window.
  Future<void> _holdHud() async {
    await Future<void>.delayed(const Duration(seconds: 2));
    final id = _hudWindowId;
    if (id == null) return;
    final dir = Platform.environment['DITO_HUD_SHOT'];

    final cenas = <String, HudMessage>{
      'gravando': HudMessage.recording(meeting: false),
      'baixo': HudMessage.quiet('fale mais perto do microfone'),
      'reuniao': HudMessage.recording(meeting: true),
      'sem-audio': HudMessage.dead('o microfone nao esta captando', canFix: true),
      'transcrevendo': HudMessage.working(HudWork.minutesDone, minutes: 2),
      'pronto': HudMessage.toast(HudToast.pasted, ms: 20000),
    };

    for (final cena in cenas.entries) {
      _toHud(cena.value);
      for (var i = 0; i < 12; i++) {
        _toHud(HudMessage.level(0.02 + (i % 5) * 0.08));
        await Future<void>.delayed(const Duration(milliseconds: 60));
      }
      log('hud_hold: ${cena.key} rect=${await _bus?.request(id, 'hudRect')}');
      log('hud_hold: ${cena.key} probe=${await _bus?.request(id, 'hudProbe')}');
      if (dir != null) {
        await _bus?.request(id, 'hudShot', <String, Object?>{'path': '$dir\\${cena.key}.png'});
      }
    }
    final revisao = _reviewWindowId;
    if (revisao != null) {
      await _bus?.send(revisao, 'review', <String, Object?>{
        // Texto LONGO e acentuado de proposito: prova no print que o cartao inteiro cabe (nao corta)
        // e que os acentos aparecem certos (sem o «replacement char» do encoding antigo).
        'text': 'Reuniao de segunda-feira sobre o planejamento do trimestre. '
            'Revisamos a acao de cada frente, a decisao sobre o orcamento e os prazos combinados. '
            'Ficou definido que o time de producao manda o resumo ate quinta-feira, '
            'enquanto o pessoal de suporte organiza as pendencias que sobraram da semana passada. '
            'Tambem falamos sobre a migracao do servidor, que precisa de atencao especial porque '
            'envolve varios sistemas antigos. A ideia e comecar pela parte menos arriscada e so '
            'depois mexer no coracao da aplicacao, medindo cada passo com calma. '
            'No fim, cada responsavel confirmou que consegue entregar a sua parte no prazo.',
        'meeting': true,
        'folder': '',
      });
      await Future<void>.delayed(const Duration(milliseconds: 900));
      log('hud_hold: cartao probe=${await _bus?.request(revisao, 'reviewProbe')}');
      if (dir != null) {
        await _bus?.request(
            revisao, 'reviewShot', <String, Object?>{'path': '$dir\\cartao.png'});
      }
      await _bus?.send(revisao, 'reviewHide', <String, Object?>{});
    }
    // Back to a known state so the harness can probe hit-testing against a steady pill.
    _toHud(HudMessage.recording(meeting: false));
    await Future<void>.delayed(const Duration(milliseconds: 600));
    log('hud_hold: fim rect=${await _bus?.request(id, 'hudRect')} '
        'probe=${await _bus?.request(id, 'hudProbe')}');
    await Future<void>.delayed(const Duration(seconds: 15));
    _toHud(HudMessage.dismiss);
  }

  /// Drives the whole key path from inside the app, with our own window in front.
  ///
  /// Guarded by an environment variable and by the foreground check: it must never send a
  /// keystroke at a window belonging to the user.
  Future<void> _selfTest() async {
    log('autoteste: comecando');
    await Future<void>.delayed(const Duration(seconds: 2));
    onOpenWindow?.call();
    await DitoWin32.focusWindow();
    await Future<void>.delayed(const Duration(milliseconds: 800));

    if (!await DitoWin32.ownsForeground()) {
      log('autoteste: ABORTADO, a janela do app nao esta em primeiro plano');
      return;
    }

    // Two cycles: the first press always worked, and the report was that the NEXT one dies.
    final key = config.config.hotkeys.pushToTalk;
    for (var volta = 1; volta <= 2; volta++) {
      if (!await DitoWin32.ownsForeground()) {
        log('autoteste: ABORTADO na volta $volta, a janela do app saiu da frente');
        return;
      }
      log('autoteste: volta $volta, injetando $key');
      await DitoWin32.injectKeyForTest(key, down: true);
      await Future<void>.delayed(const Duration(seconds: 2));
      log('autoteste: volta $volta hook = ${await DitoWin32.keySnapshot()}');
      await DitoWin32.injectKeyForTest(key, down: false);
      await Future<void>.delayed(const Duration(seconds: 6));
      log('autoteste: volta $volta fase = ${controller.state.phase.name}'
          ' revisao=${controller.pendingReview != null}');
    }

    // Ask the windows themselves: sending a message is not proof that it rendered.
    final hudId = _hudWindowId;
    if (hudId != null) {
      log('autoteste: HUD = ${await _bus?.request(hudId, 'hudProbe')}');
    }

    final reviewId = _reviewWindowId;
    if (reviewId != null) {
      await _bus?.send(reviewId, 'review', <String, Object?>{
        'text': 'Ação e coração: teste de tamanho do cartão em português, '
            'com uma frase longa o bastante para ocupar mais de uma linha.',
        'meeting': false,
        'folder': '',
      });
      await Future<void>.delayed(const Duration(seconds: 2));
      log('autoteste: cartao = ${await _bus?.request(reviewId, 'reviewProbe')}');
      await _bus?.send(reviewId, 'reviewHide', <String, Object?>{});
    }

    log('autoteste: notificacao = '
        '${await DitoWin32.notifyBalloon(title: "Dito", body: "Autoteste do balao")}');
    if (config.config.audio.alerts.sound) {
      log('autoteste: som = ${await DitoWin32.playAlarmSound()}');
    }
    log('autoteste: fim');
  }

  Future<void> _openSubWindows() async {
    try {
      final self = await WindowController.fromCurrentEngine();
      // The sub-window has to be told our id: window ids are UUIDs, never a fixed "0".
      final hud = await WindowController.create(WindowConfiguration(
        arguments: '${WindowRole.hud}:${self.windowId}',
        focusable: false,
      ));
      _hudWindowId = hud.windowId;

      final review = await WindowController.create(
        WindowConfiguration(arguments: '${WindowRole.review}:${self.windowId}'),
      );
      _reviewWindowId = review.windowId;

      _bus = MultiWindowBus(self)..onMessage(_onWindowMessage);
      log('janelas: principal=${self.windowId} hud=$_hudWindowId review=$_reviewWindowId');
    } catch (e) {
      log('nao consegui abrir as sub-janelas: $e');
    }
  }

  Future<Object?> _onWindowMessage(String method, Map<String, Object?> data) async {
    switch (method) {
      case 'hudIntent':
        if (data['intent'] == HudIntent.stopRequested.name) {
          controller.onHotkeyStop('meeting');
        }
      case 'reviewSend':
        await controller.onReviewSend(
          data['text'] as String? ?? '',
          toVault: data['toVault'] == true,
        );
      case 'reviewDiscard':
        controller.onReviewDiscard();
      case 'appearance':
        // Pulled, not only pushed: a sub-window boots after us and misses the broadcast.
        return _appearance();
    }
    return null;
  }

  Map<String, Object?> _appearance() => <String, Object?>{
        'theme': config.config.ui.theme,
        'locale': config.config.ui.language,
      };

  /// Sub-windows own no config: theme and language reach them over the bus or not at all.
  void _broadcastAppearance() {
    for (final id in <String?>[_hudWindowId, _reviewWindowId]) {
      if (id != null) unawaited(_bus?.send(id, 'appearance', _appearance()));
    }
  }

  void _toHud(HudMessage message) {
    final id = _hudWindowId;
    if (id == null) return;
    unawaited(_bus?.send(id, 'hud', message.toMap()));
  }

  void _toReview(FinishedEvent event) {
    final id = _reviewWindowId;
    if (id == null) return;
    unawaited(_bus?.send(id, 'review', <String, Object?>{
      'text': event.text,
      'meeting': event.isMeeting,
      'folder': event.folder,
    }));
  }

  void _notify({required String title, required String body}) {
    if (!config.config.audio.alerts.notify) return;
    alerts.notify(title: title, body: body);
  }

  void _playAlarm() => alerts.playAlarm();

  /// The catalogue for everything outside a widget: the tray and the balloons.
  AppStrings get strings => stringsFor(config.config.ui.language);

  void _onSnapshot() {
    if (!Platform.isWindows) return;
    unawaited(tray.update(controller.state, strings,
        config.config.hotkeys.pushToTalk,
        paused: paused.value));
  }

  void _onHotkeys() => controller.setHookInstalled(hotkeys.hookInstalled);

  Future<void> togglePause() async {
    paused.value = !paused.value;
    if (paused.value) {
      await hotkeys.pause();
    } else {
      await hotkeys.resume();
    }
    controller.setPaused(paused.value);
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
    if (Platform.isWindows) await tray.dispose();
    await supervisor.stop();
    await controller.dispose();
    await log.close();
  }
}
