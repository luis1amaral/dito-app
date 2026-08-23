import '../../l10n/app_strings.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../keys/key_names.dart';
import '../palette.dart';
import '../tokens.dart';

/// Click, then press the key you want (no dropdown); capturing PAUSES the global hook so the key reaches this field.
class KeyCaptureField extends StatefulWidget {
  const KeyCaptureField({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    required this.onCaptureStart,
    required this.onCaptureEnd,
    this.conflictFor,
  });

  final String label;
  final String value;
  final void Function(String key) onChanged;

  /// Called before listening, so the global hook stops swallowing keys.
  final Future<void> Function() onCaptureStart;
  final Future<void> Function() onCaptureEnd;

  /// Names the action this key already answers to, if any.
  final String? Function(String key)? conflictFor;

  @override
  State<KeyCaptureField> createState() => _KeyCaptureFieldState();
}

class _KeyCaptureFieldState extends State<KeyCaptureField> {
  final FocusNode _focus = FocusNode();
  bool _capturing = false;
  String? _error;

  static final Map<LogicalKeyboardKey, String> _named = <LogicalKeyboardKey, String>{
    LogicalKeyboardKey.f1: 'f1',
    LogicalKeyboardKey.f2: 'f2',
    LogicalKeyboardKey.f3: 'f3',
    LogicalKeyboardKey.f4: 'f4',
    LogicalKeyboardKey.f5: 'f5',
    LogicalKeyboardKey.f9: 'f9',
    LogicalKeyboardKey.f10: 'f10',
    LogicalKeyboardKey.f11: 'f11',
    LogicalKeyboardKey.f12: 'f12',
    LogicalKeyboardKey.space: 'space',
    LogicalKeyboardKey.printScreen: 'print_screen',
    LogicalKeyboardKey.pageUp: 'page_up',
    LogicalKeyboardKey.pageDown: 'page_down',
    LogicalKeyboardKey.scrollLock: 'scroll_lock',
    LogicalKeyboardKey.pause: 'pause',
    LogicalKeyboardKey.insert: 'insert',
    LogicalKeyboardKey.contextMenu: 'menu',
    LogicalKeyboardKey.home: 'home',
    LogicalKeyboardKey.end: 'end',
    LogicalKeyboardKey.capsLock: 'caps_lock',
  };

  @override
  void dispose() {
    if (_capturing) widget.onCaptureEnd();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _startCapture() async {
    await widget.onCaptureStart();
    setState(() {
      _capturing = true;
      _error = null;
    });
    _focus.requestFocus();
  }

  Future<void> _stopCapture() async {
    if (!_capturing) return;
    setState(() => _capturing = false);
    await widget.onCaptureEnd();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (!_capturing || event is! KeyDownEvent) return KeyEventResult.ignored;

    if (event.logicalKey == LogicalKeyboardKey.escape) {
      unawaitedStop();
      return KeyEventResult.handled;
    }

    // A modifier waits instead of being refused: Ctrl+F9 starts with Ctrl.
    if (HardwareKeyboard.instance.isControlPressed ||
        HardwareKeyboard.instance.isAltPressed ||
        HardwareKeyboard.instance.isShiftPressed ||
        HardwareKeyboard.instance.isMetaPressed) {
      return KeyEventResult.handled;
    }

    final name = _named[event.logicalKey];
    if (name == null || !bindableKeys.contains(name)) {
      setState(() => _error = context.strings.keyErrorTypes);
      return KeyEventResult.handled;
    }

    final conflict = widget.conflictFor?.call(name);
    if (conflict != null) {
      setState(() => _error = context.strings.keyErrorTaken(conflict));
      return KeyEventResult.handled;
    }

    widget.onChanged(name);
    unawaitedStop();
    return KeyEventResult.handled;
  }

  void unawaitedStop() => _stopCapture();

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    return Focus(
      focusNode: _focus,
      onKeyEvent: _onKey,
      // Losing focus ends the capture, or the field keeps eating keys forever.
      onFocusChange: (has) => has ? null : _stopCapture(),
      child: ListTile(
        title: Text(widget.label),
        subtitle: _error == null
            ? (_capturing
                ? Text(context.strings.keyCaptureHint,
                    style: TextStyle(color: c.primary, fontSize: AppType.caption))
                : null)
            : Text(_error!,
                style: TextStyle(color: c.danger, fontSize: AppType.caption)),
        trailing: OutlinedButton(
          onPressed: _capturing ? _stopCapture : _startCapture,
          style: OutlinedButton.styleFrom(
            foregroundColor: _capturing ? c.primary : c.textPrimary,
            side: BorderSide(color: _capturing ? c.primary : c.border),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadius.control)),
          ),
          child: Text(_capturing ? 'Ouvindo...' : labelForKey(widget.value)),
        ),
      ),
    );
  }
}
