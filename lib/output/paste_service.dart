import 'dart:async';

import '../core/logbook.dart';
import '../core/result.dart';

/// How the target window accepts text; decided natively, measured in docs/medicoes/colagem-windows.md.
enum PasteTarget { gui, console, terminal }

/// The clipboard and keyboard, behind an interface so the sequence can be tested without either.
abstract class PasteBackend {
  Future<String?> readClipboard();
  Future<bool> writeClipboard(String text);

  /// `text` is only used where the native side has to type instead of pasting.
  Future<bool> pressCtrlV({String? text});
  Future<bool> pressEnter();

  /// Restores the window that had focus; completes only after the attempt.
  Future<bool> restoreFocus();

  /// Defaults to gui so the test doubles do not all have to answer this.
  Future<PasteTarget> describeTarget() async => PasteTarget.gui;
}

/// A CLI without bracketed paste (conhost, mintty) turns every newline into a separate submit, so a dictated paragraph must reach it as one line.
String joinLines(String text) =>
    text.replaceAll(RegExp(r'[\r\n]+'), ' ')
        .replaceAll(RegExp(r' {2,}'), ' ')
        .trim();

/// Pastes without typing: synthetic keystrokes get pt-BR accents wrong, so the text goes via clipboard.
class PasteService {
  PasteService({
    required this.backend,
    Logbook? log,
    this.settle = const Duration(milliseconds: 50),
    this.beforeEnter = const Duration(milliseconds: 250),
    this.restoreAfter = const Duration(seconds: 1),
  }) : _log = log ?? Logbook('paste');

  final PasteBackend backend;
  final Logbook _log;

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

    // The target decides BEFORE the clipboard is written, and the leftover keeps the original.
    var target = PasteTarget.gui;
    try {
      target = await backend.describeTarget();
    } catch (e) {
      _log.call('paste: falha ao classificar o alvo: $e');
    }
    final toSend = target == PasteTarget.gui ? text : joinLines(text);

    String? previous;
    if (restoreClipboard) {
      try {
        previous = await backend.readClipboard();
      } catch (e) {
        _log.call('paste: falha ao ler clipboard: $e');
        previous = null;
      }
    }

    bool copied;
    try {
      copied = await backend.writeClipboard(toSend);
    } catch (e) {
      _log.call('paste: falha ao escrever clipboard: $e');
      copied = false;
    }
    if (!copied) {
      return const PasteResult(
          pasted: false, copied: false, error: 'area de transferencia indisponivel');
    }

    var enterFailed = false;
    try {
      // Focus goes back BEFORE the paste, or the Ctrl+V lands in our own window.
      if (giveBackFocus) {
        final focusRestored = await backend.restoreFocus();
        // Known false negative: the WM refuses yet focus lands anyway, so log and go on.
        if (!focusRestored) _log.call('paste: falha ao restaurar foco (prosseguindo mesmo assim)');
      }

      await Future<void>.delayed(settle);
      final pasted = await backend.pressCtrlV(text: toSend);
      if (!pasted) {
        _scheduleRestore(previous);
        return PasteResult(pasted: false, copied: true, error: 'Ctrl+V recusado');
      }

      if (sendEnter) {
        await Future<void>.delayed(beforeEnter);
        final entered = await backend.pressEnter();
        if (!entered) {
          _log.call('paste: falha ao pressionar Enter');
          enterFailed = true;
        }
      }
    } catch (e) {
      _scheduleRestore(previous);
      return PasteResult(pasted: false, copied: true, error: '$e');
    }

    _scheduleRestore(previous);
    // Text is already pasted by this point, so a refused Enter qualifies the result instead of failing it.
    if (enterFailed) {
      return const PasteResult(pasted: true, copied: true, error: 'Enter recusado');
    }
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
