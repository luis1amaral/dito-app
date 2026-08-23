import 'package:dito_win32/dito_win32.dart';

import 'paste_service.dart';

/// PasteBackend on the Win32 plugin.
class NativePasteBackend implements PasteBackend {
  const NativePasteBackend();

  @override
  Future<String?> readClipboard() => DitoWin32.clipboardGet();

  @override
  Future<bool> writeClipboard(String text) => DitoWin32.clipboardSet(text);

  @override
  Future<bool> pressCtrlV({String? text}) => DitoWin32.sendCtrlV(text: text);

  @override
  Future<bool> pressEnter() => DitoWin32.sendEnter();

  @override
  Future<bool> restoreFocus() => DitoWin32.giveBackFocus();

  @override
  Future<PasteTarget> describeTarget() async => switch (await DitoWin32.targetKind()) {
        'console' => PasteTarget.console,
        'terminal' => PasteTarget.terminal,
        _ => PasteTarget.gui,
      };
}
