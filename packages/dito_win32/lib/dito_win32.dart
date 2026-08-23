import 'dart:async';
import 'dart:ui' show Rect; // ignore: unnecessary_import

import 'package:flutter/services.dart';

/// Typed facade over the native Win32 plugin: keys, windows and focus.
class DitoWin32 {
  DitoWin32._();

  static const MethodChannel _methods = MethodChannel('dito/win32');
  static const EventChannel _keys = EventChannel('dito/keys');

  static Stream<KeySignal>? _keyStream;

  /// Physical keyboard signals from the low-level hook.
  static Stream<KeySignal> get keys => _keyStream ??= _keys
      .receiveBroadcastStream()
      .map((dynamic event) => KeySignal.fromMap(Map<Object?, Object?>.from(event as Map)))
      .where((signal) => signal is! UnknownSignal);

  static Future<void> bindKey({
    required String name,
    required String key,
    bool suppress = true,
  }) =>
      _methods.invokeMethod<void>('keys.bind', <String, Object?>{
        'name': name,
        'key': key,
        'suppress': suppress,
      });

  static Future<void> unbindAll() => _methods.invokeMethod<void>('keys.unbindAll');

  /// Pause stops acting but keeps the hook installed.
  static Future<void> pauseKeys() => _methods.invokeMethod<void>('keys.pause');

  static Future<void> resumeKeys() => _methods.invokeMethod<void>('keys.resume');

  static Future<Map<String, Object?>> keySnapshot() async {
    final raw = await _methods.invokeMethod<Map<Object?, Object?>>('keys.snapshot');
    return <String, Object?>{
      for (final entry in (raw ?? <Object?, Object?>{}).entries)
        entry.key.toString(): entry.value,
    };
  }

  /// Test-only: drives SendInput; returns how many events Windows accepted.
  static Future<int> injectKeyForTest(String key, {required bool down}) async =>
      await _methods.invokeMethod<int>('keys.injectForTest', <String, Object?>{
        'key': key,
        'down': down,
      }) ??
      0;

  static const EventChannel _trayEvents = EventChannel('dito/tray');

  /// Tray events: a click on the icon, or a menu item chosen.
  static Stream<TrayEvent> get trayEvents => _trayEvents
      .receiveBroadcastStream()
      .map((dynamic e) => TrayEvent.fromMap(Map<Object?, Object?>.from(e as Map)));

  /// Creates the tray icon; one owner for icon, tooltip, menu and balloon.
  static Future<bool> trayCreate({required String tooltip}) async =>
      await _methods.invokeMethod<bool>(
          'tray.create', <String, Object?>{'tooltip': tooltip}) ??
      false;

  static Future<bool> traySetIcon(String path) async =>
      await _methods.invokeMethod<bool>('tray.setIcon', <String, Object?>{'path': path}) ??
      false;

  static Future<bool> traySetTooltip(String tooltip) async =>
      await _methods.invokeMethod<bool>(
          'tray.setTooltip', <String, Object?>{'tooltip': tooltip}) ??
      false;

  static Future<void> traySetMenu(List<TrayItem> items) =>
      _methods.invokeMethod<void>('tray.setMenu', <String, Object?>{
        'items': <Map<String, Object?>>[for (final item in items) item.toMap()],
      });

  static Future<void> trayDestroy() => _methods.invokeMethod<void>('tray.destroy');

  /// Test-only: creates an EDIT control inside our own window as a safe paste target.
  static Future<int?> createEditTarget() =>
      _methods.invokeMethod<int>('test.createEditTarget');

  static Future<String?> readEditTarget() =>
      _methods.invokeMethod<String>('test.readEditTarget');

  static Future<void> destroyEditTarget() =>
      _methods.invokeMethod<void>('test.destroyEditTarget');

  /// True when OUR window holds the foreground; tests must never send keys otherwise.
  static Future<bool> ownsForeground() async =>
      await _methods.invokeMethod<bool>('test.ownsForeground') ?? false;

  /// This window's rectangle in screen coordinates.
  static Future<({int left, int top, int right, int bottom})> windowRect() async {
    final raw = await _methods.invokeMethod<Map<Object?, Object?>>('window.rect');
    final map = Map<Object?, Object?>.from(raw ?? <Object?, Object?>{});
    int at(String key) => (map[key] as num?)?.toInt() ?? 0;
    return (left: at('left'), top: at('top'), right: at('right'), bottom: at('bottom'));
  }

  /// Diagnostics: this window's handle and whoever currently holds the foreground.
  static Future<({int self, int foreground})> windowHandles() async {
    final raw = await _methods.invokeMethod<Map<Object?, Object?>>('window.handle');
    final map = Map<Object?, Object?>.from(raw ?? <Object?, Object?>{});
    return (
      self: (map['self'] as num?)?.toInt() ?? 0,
      foreground: (map['foreground'] as num?)?.toInt() ?? 0,
    );
  }

  /// Drops the overlay clip so the window is a plain rectangle again.
  static Future<void> clearHitRect() => _methods.invokeMethod<void>('window.clearHitRect');

  /// Forces the swapchain to present; a window resized while hidden stays partly black.
  static Future<void> forceRepaint() => _methods.invokeMethod<void>('window.forceRepaint');

  /// Brings this window to the foreground; SendInput is refused to a background process.
  static Future<bool> focusWindow() async =>
      await _methods.invokeMethod<bool>('window.focus') ?? false;

  /// Applies WS_EX_NOACTIVATE|TOOLWINDOW to this window; it can never take focus again.
  static Future<int?> adoptAsHud() => _methods.invokeMethod<int>('window.adoptAsHud');

  static Future<void> showNoActivate() =>
      _methods.invokeMethod<void>('window.showNoActivate');

  static Future<void> hideWindow() => _methods.invokeMethod<void>('window.hide');

  /// Places the window bottom-centre of the work area holding the foreground window; sizes are LOGICAL, scaled here once.
  static Future<Rect?> setBottomCenter({
    required double width,
    required double height,
    required double devicePixelRatio,
    double margin = 32,
  }) async {
    final raw = await _methods.invokeMethod<Map<Object?, Object?>>(
      'window.setBottomCenter',
      <String, Object?>{
        'width': width * devicePixelRatio,
        'height': height * devicePixelRatio,
        'margin': margin * devicePixelRatio,
      },
    );
    if (raw == null) return null;
    final map = Map<Object?, Object?>.from(raw);
    return Rect.fromLTWH(
      (map['x'] as num).toDouble(),
      (map['y'] as num).toDouble(),
      (map['w'] as num).toDouble(),
      (map['h'] as num).toDouble(),
    );
  }

  /// Limits the window to the rectangle its content occupies (LOGICAL pixels), or the transparent canvas still eats clicks meant for the app behind; an empty rect clears the region.
  static Future<bool> setHitRect({
    required Rect rect,
    required double devicePixelRatio,
    double radius = 0,
  }) async =>
      await _methods.invokeMethod<bool>('window.setHitRect', <String, Object?>{
        'left': rect.left * devicePixelRatio,
        'top': rect.top * devicePixelRatio,
        'width': rect.width * devicePixelRatio,
        'height': rect.height * devicePixelRatio,
        'radius': radius * devicePixelRatio,
      }) ??
      false;

  static Future<String?> clipboardGet() =>
      _methods.invokeMethod<String>('clipboard.get');

  static Future<bool> clipboardSet(String text) async =>
      await _methods.invokeMethod<bool>('clipboard.set', <String, Object?>{'text': text}) ??
      false;

  /// Returns whether the keystrokes were INJECTED -- not whether the target pasted them; `text` lets the native side type instead where Ctrl+V does not work.
  static Future<bool> sendCtrlV({String? text}) async =>
      await _methods.invokeMethod<bool>(
          'input.sendCtrlV', <String, Object?>{'text': text ?? ''}) ??
      false;

  /// How the remembered paste target accepts text: `gui`, `console` or `terminal`.
  static Future<String> targetKind() async =>
      await _methods.invokeMethod<String>('input.targetKind') ?? 'gui';

  static Future<bool> sendEnter() async =>
      await _methods.invokeMethod<bool>('input.sendEnter') ?? false;

  /// Test helper: drives a chord such as Ctrl+A or Ctrl+C at the focused window.
  static Future<bool> sendChord(String key, {bool ctrl = true}) async =>
      await _methods.invokeMethod<bool>(
          'input.sendChord', <String, Object?>{'key': key, 'ctrl': ctrl}) ??
      false;

  /// Toggles the ability to receive focus: on X11 this is a contract with the window manager, not a preference (docs/armadilhas.md 4.6).
  static Future<bool> setFocusable(bool focusable) async =>
      await _methods.invokeMethod<bool>('window.setFocusable', focusable) ?? false;

  /// Remembers the current foreground window so it can be restored before pasting.
  static Future<void> takeFocus() => _methods.invokeMethod<void>('focus.take');

  /// Completes only after the restore was attempted; await this before pasting.
  static Future<bool> giveBackFocus() async =>
      await _methods.invokeMethod<bool>('focus.giveBack') ?? false;

}

sealed class KeySignal {
  const KeySignal();

  static KeySignal fromMap(Map<Object?, Object?> map) {
    final micros = (map['t'] as num?)?.toInt() ?? 0;
    return switch (map['type']) {
      'down' => KeyDown(
          action: map['name'] as String? ?? '',
          key: map['key'] as String? ?? '',
          micros: micros,
        ),
      'up' => KeyUp(
          action: map['name'] as String? ?? '',
          key: map['key'] as String? ?? '',
          micros: micros,
        ),
      'tick' => KeyTick(
          down: <String>{
            for (final item in (map['down'] as List<Object?>? ?? <Object?>[]))
              item.toString(),
          },
          micros: micros,
        ),
      'hook' => HookStatus(map['status'] as String? ?? ''),
      'grab' => GrabStatus(
          action: map['name'] as String? ?? '',
          key: map['key'] as String? ?? '',
          ok: map['ok'] as bool? ?? false,
        ),
      _ => const UnknownSignal(),
    };
  }
}

/// Includes auto-repeat: the machine decides what to do with it.
class KeyDown extends KeySignal {
  const KeyDown({required this.action, required this.key, required this.micros});
  final String action;
  final String key;
  final int micros;
}

/// Informative only, NEVER the authority on whether a key is up.
class KeyUp extends KeySignal {
  const KeyUp({required this.action, required this.key, required this.micros});
  final String action;
  final String key;
  final int micros;
}

/// Physical truth, every 50 ms while any bound key is engaged.
class KeyTick extends KeySignal {
  const KeyTick({required this.down, required this.micros});
  final Set<String> down;
  final int micros;
}

class HookStatus extends KeySignal {
  const HookStatus(this.status);
  final String status;

  bool get installed => status == 'installed';
}

/// Linux only: says whether the OS actually handed this key over (X11 grab is exclusive).
class GrabStatus extends KeySignal {
  const GrabStatus({required this.action, required this.key, required this.ok});
  final String action;
  final String key;
  final bool ok;
}

class UnknownSignal extends KeySignal {
  const UnknownSignal();
}

class TrayItem {
  const TrayItem({
    required this.id,
    required this.label,
    this.enabled = true,
    this.checked = false,
    this.checkbox = false,
    this.separator = false,
  });

  const TrayItem.separator()
      : id = '',
        label = '',
        enabled = true,
        checked = false,
        checkbox = false,
        separator = true;

  final String id;
  final String label;
  final bool enabled;
  final bool checked;
  final bool checkbox;
  final bool separator;

  Map<String, Object?> toMap() => <String, Object?>{
        'id': id,
        'label': label,
        'enabled': enabled,
        'checked': checked,
        'checkbox': checkbox,
        'separator': separator,
      };
}

class TrayEvent {
  const TrayEvent({required this.isClick, this.menuId});

  final bool isClick;
  final String? menuId;

  static TrayEvent fromMap(Map<Object?, Object?> map) => TrayEvent(
        isClick: map['event'] == 'click',
        menuId: map['id'] as String?,
      );
}
