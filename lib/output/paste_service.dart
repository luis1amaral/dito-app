import 'dart:async';

import '../core/result.dart';

/// The clipboard and keyboard, behind an interface so the sequence can be tested without either.
abstract class PasteBackend {
  Future<String?> readClipboard();
  Future<bool> writeClipboard(String text);
  Future<bool> pressCtrlV();
  Future<bool> pressEnter();

  /// Restores the window that had focus; completes only after the attempt.
  Future<bool> restoreFocus();
}

/// Pastes the way src/dito/output/paste.py does, timings included.
///
/// Types nothing: synthetic keystrokes get pt-BR accents wrong, so the text goes via clipboard.
class PasteService {
  PasteService({
    required this.backend,
    this.settle = const Duration(milliseconds: 50),
    this.beforeEnter = const Duration(milliseconds: 250),
    this.restoreAfter = const Duration(seconds: 1),
  });

  final PasteBackend backend;

  /// Between copying and Ctrl+V.
  final Duration settle;

  /// Between Ctrl+V and Enter: without it the Enter lands before the text and sends an empty field.
  final Duration beforeEnter;

  /// Before handing the old clipboard back, so the target app has finished reading ours.
  final Duration restoreAfter;

  /// Never throws; the result says where the text ended up.
  Future<PasteResult> paste(
    String text, {
    bool sendEnter = false,
    bool restoreClipboard = true,
    bool giveBackFocus = true,
  }) async {
    if (text.isEmpty) {
      return const PasteResult(pasted: false, copied: false, error: 'texto vazio');
    }

    String? previous;
    if (restoreClipboard) {
      try {
        previous = await backend.readClipboard();
      } catch (_) {
        previous = null;
      }
    }

    bool copied;
    try {
      copied = await backend.writeClipboard(text);
    } catch (e) {
      copied = false;
    }
    if (!copied) {
      return const PasteResult(
          pasted: false, copied: false, error: 'area de transferencia indisponivel');
    }

    try {
      // Focus goes back BEFORE the paste, or the Ctrl+V lands in our own window.
      if (giveBackFocus) await backend.restoreFocus();

      await Future<void>.delayed(settle);
      final pasted = await backend.pressCtrlV();
      if (!pasted) {
        _scheduleRestore(previous);
        return PasteResult(pasted: false, copied: true, error: 'Ctrl+V recusado');
      }

      if (sendEnter) {
        await Future<void>.delayed(beforeEnter);
        await backend.pressEnter();
      }
    } catch (e) {
      _scheduleRestore(previous);
      return PasteResult(pasted: false, copied: true, error: '$e');
    }

    _scheduleRestore(previous);
    return const PasteResult.ok();
  }

  /// Copies without pasting, for the tray item that says "copy".
  Future<PasteResult> copy(String text) async {
    if (text.isEmpty) {
      return const PasteResult(pasted: false, copied: false, error: 'texto vazio');
    }
    try {
      final copied = await backend.writeClipboard(text);
      return PasteResult(
          pasted: false, copied: copied, error: copied ? null : 'area de transferencia indisponivel');
    } catch (e) {
      return PasteResult(pasted: false, copied: false, error: '$e');
    }
  }

  void _scheduleRestore(String? previous) {
    if (previous == null) return;
    Timer(restoreAfter, () async {
      try {
        await backend.writeClipboard(previous);
      } catch (_) {
        // Losing one restore beats losing the paste path for the rest of the session.
      }
    });
  }
}
