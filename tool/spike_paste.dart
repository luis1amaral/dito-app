// Proves the paste path end to end: clipboard, Ctrl+V, pt-BR accents and clipboard restore.
//
// The target is an EDIT control this process creates inside its OWN window, and every
// keystroke is gated on us holding the foreground. Nothing is ever sent at a user window,
// and no window content is ever written to the log.
import 'dart:io';

import 'package:dito_app/output/native_paste_backend.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';

const String kSample = 'Ação e coração: hoje às 5, não é? Ótimo — vamos à reunião.';
const String kPrevious = 'conteudo antigo';

final File _result = File('${Directory.current.path}/spike_paste_result.txt');

void _say(String line) =>
    _result.writeAsStringSync('$line\n', mode: FileMode.append, flush: true);

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  if (_result.existsSync()) _result.deleteSync();
  _say('== espinho de colagem ==');
  runApp(const _Spike());
}

class _Spike extends StatefulWidget {
  const _Spike();
  @override
  State<_Spike> createState() => _SpikeState();
}

class _SpikeState extends State<_Spike> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _fail(String why) async {
    _say('ABORTADO .................... $why');
    _say('VEREDITO .................... FALHA');
    _say('== fim ==');
    await DitoWin32.destroyEditTarget();
    exit(1);
  }

  Future<void> _run() async {
    await Future<void>.delayed(const Duration(milliseconds: 900));

    final target = await DitoWin32.createEditTarget();
    if (target == null || target == 0) {
      await _fail('nao consegui criar o alvo de teste');
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 600));

    // Hard gate: never send a keystroke unless our own window holds the foreground.
    if (!await DitoWin32.ownsForeground()) {
      await _fail('o app nao esta em primeiro plano — nada foi enviado');
      return;
    }
    _say('alvo proprio em foco ........ OK');

    await DitoWin32.clipboardSet(kPrevious);
    await Future<void>.delayed(const Duration(milliseconds: 200));

    final service = PasteService(backend: const NativePasteBackend());
    if (!await DitoWin32.ownsForeground()) {
      await _fail('o foco saiu do app antes de colar');
      return;
    }
    final result = await service.paste(kSample, giveBackFocus: false);
    await Future<void>.delayed(const Duration(milliseconds: 500));

    _say('resultado ................... pasted=${result.pasted} copied=${result.copied}');
    _say('sobra ....................... ${result.fallback?.name ?? "(nenhuma)"}');

    final landed = (await DitoWin32.readEditTarget() ?? '').trim();
    final identical = landed == kSample;
    _say('comprimento colado .......... ${landed.length} de ${kSample.length}');
    _say('texto identico .............. ${identical ? "OK" : "FALHOU"}');

    // The whole reason for going through the clipboard instead of typing the characters.
    final accentsOk = landed.contains('Ação') &&
        landed.contains('coração') &&
        landed.contains('às') &&
        landed.contains('Ótimo') &&
        landed.contains('—');
    _say('acentos preservados ......... ${accentsOk ? "OK" : "FALHOU"}');

    await Future<void>.delayed(const Duration(milliseconds: 1400));
    final restored = await DitoWin32.clipboardGet();
    final restoredOk = restored == kPrevious;
    _say('clipboard restaurado ........ ${restoredOk ? "OK" : "FALHOU"}');

    final pass = result.pasted && identical && accentsOk && restoredOk;
    _say('VEREDITO .................... ${pass ? "PASSA" : "FALHA"}');
    _say('== fim ==');

    await DitoWin32.destroyEditTarget();
    exit(pass ? 0 : 1);
  }

  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(body: SizedBox.shrink()),
      );
}
