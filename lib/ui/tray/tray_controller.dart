import '../../l10n/app_strings.dart';
import 'dart:async';
import 'dart:io';

import 'package:dito_win32/dito_win32.dart';

import '../../core/logbook.dart';
import '../../engine/engine_health.dart';
import '../../engine/engine_protocol.dart';
import '../../state/app_snapshot.dart';

/// Tray icon and menu, owned end to end by the native plugin.
///
/// One owner for icon, tooltip, menu and balloon: two libraries sharing one icon is why
/// the balloon used to fail silently.
class TrayController {
  TrayController({Logbook? log}) : _log = log ?? Logbook('tray');

  final Logbook _log;
  StreamSubscription<TrayEvent>? _events;

  bool _ready = false;
  String _icon = '';
  String _menuSignature = '';
  String _tooltip = '';

  void Function()? onOpen;
  void Function()? onCopy;
  void Function()? onTogglePause;
  void Function()? onQuit;

  /// The icon carries the app logo; the state is a badge, so shape still tells them apart.
  static String _iconFor(AppSnapshot state) {
    if (state.alarm != AudioState.ok || state.engine.state == EngineState.dead) {
      return 'tray-alert.ico';
    }
    if (state.isRecording) return 'tray-recording.ico';
    return 'tray-idle.ico';
  }

  static String _statusFor(AppSnapshot state, AppStrings s, String hotkey,
      {required bool paused}) {
    if (paused) return s.trayTipPaused;
    return switch (state.phase) {
      AppPhase.recording => s.trayTipRecording,
      AppPhase.meeting => s.trayTipMeeting,
      AppPhase.transcribing => s.hudTranscribing,
      AppPhase.paused => s.trayTipPaused,
      AppPhase.idle => state.alarm == AudioState.ok
          ? s.trayTipReady(hotkey)
          : s.trayTipNoAudio,
    };
  }

  /// Assets sit beside the executable once packaged; a relative path alone does not survive.
  static String _resolve(String asset) {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final bundled = File('$exeDir\\data\\flutter_assets\\assets\\icons\\$asset');
    if (bundled.existsSync()) return bundled.path;
    return File('assets/icons/$asset').absolute.path;
  }

  Future<bool> init() async {
    try {
      _ready = await DitoWin32.trayCreate(tooltip: 'Dito');
      if (!_ready) {
        _log('bandeja nao pode ser criada');
        return false;
      }
      _events = DitoWin32.trayEvents.listen(_onEvent);
      await DitoWin32.traySetIcon(_resolve('tray-idle.ico'));
      return true;
    } catch (e) {
      _log('bandeja indisponivel: $e');
      return false;
    }
  }

  void _onEvent(TrayEvent event) {
    if (event.isClick) {
      onOpen?.call();
      return;
    }
    switch (event.menuId) {
      case 'open':
        onOpen?.call();
      case 'copy':
        onCopy?.call();
      case 'pause':
        onTogglePause?.call();
      case 'quit':
        onQuit?.call();
    }
  }

  Future<void> update(AppSnapshot state, AppStrings s, String hotkey,
      {required bool paused}) async {
    if (!_ready) return;
    try {
      final icon = _resolve(_iconFor(state));
      if (icon != _icon) {
        await DitoWin32.traySetIcon(icon);
        _icon = icon;
      }

      final status = _statusFor(state, s, hotkey, paused: paused);
      final tooltip = 'Dito - $status';
      if (tooltip != _tooltip) {
        await DitoWin32.traySetTooltip(tooltip);
        _tooltip = tooltip;
      }

      final hasText = (state.lastText ?? '').isNotEmpty;
      final signature = '$status|$hasText|$paused';
      // Rebuilding the menu on every level event is what made the old port thrash the tray.
      if (signature == _menuSignature) return;
      _menuSignature = signature;

      await DitoWin32.traySetMenu(<TrayItem>[
        TrayItem(id: 'status', label: status, enabled: false),
        const TrayItem.separator(),
        TrayItem(id: 'open', label: s.trayOpen),
        TrayItem(id: 'copy', label: s.trayCopyLast, enabled: hasText),
        TrayItem(id: 'pause', label: s.trayPause, checkbox: true, checked: paused),
        const TrayItem.separator(),
        TrayItem(id: 'quit', label: s.trayQuit),
      ]);
    } catch (e) {
      _log('falha ao atualizar a bandeja: $e');
    }
  }

  Future<void> dispose() async {
    await _events?.cancel();
    try {
      await DitoWin32.trayDestroy();
    } catch (_) {
      // Nothing to do if the shell already took the icon away.
    }
    await _log.close();
  }
}
