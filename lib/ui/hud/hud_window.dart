import 'dart:async';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';

import '../../core/logbook.dart';
import '../../platform/window_bus.dart';
import '../../state/hud_commands.dart';
import '../../l10n/app_strings.dart';
import '../theme.dart';
import '../window_shot.dart';
import '../tokens.dart';
import '../review/review_card.dart';
import 'hud_pill.dart';
import 'hud_state.dart';

/// Entry point of the HUD window; it renders signals and reports intents, nothing more.
Future<void> runHudWindow(WindowController controller, String ownerId) async {
  final state = HudState();
  final bus = MultiWindowBus(controller);

  runApp(_HudApp(state: state, bus: bus, controller: controller, ownerId: ownerId));

  // The styles were set at creation; this only makes sure we stay out of the taskbar.
  await DitoWin32.adoptAsHud();
}

class _HudApp extends StatefulWidget {
  const _HudApp({
    required this.state,
    required this.bus,
    required this.controller,
    required this.ownerId,
  });

  final HudState state;
  final MultiWindowBus bus;
  final WindowController controller;
  final String ownerId;

  @override
  State<_HudApp> createState() => _HudAppState();
}

/// Uma fala esperando revisao, agora na MESMA sub-janela da pilula.
class _Pendente {
  _Pendente({required this.id, required this.text, required this.meeting});
  final String id;
  final String text;
  final bool meeting;
}

/// Tres posicoes que ciclam: embaixo, meio, cima, e o proximo volta para baixo.
const int _slots = 3;

class _HudAppState extends State<_HudApp> {
  final _log = Logbook('hud_window');
  final List<_Pendente> _itens = <_Pendente>[];
  String _theme = 'auto';
  String _locale = 'auto';
  bool _placed = false;
  bool _visible = false;
  bool _busy = false;
  bool _again = false;
  Timer? _retry;
  final GlobalKey _pill = GlobalKey();
  final GlobalKey _canvas = GlobalKey();
  Rect? _hit;

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onStateChanged);
    widget.bus.onMessage(_onMessage);
    unawaited(_askAppearance());
    unawaited(_askHudState());
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_apply()));
  }

  Future<Object?> _onMessage(String method, Map<String, Object?> data) async {
    if (method == 'hudRect') {
      final rect = await DitoWin32.windowRect();
      return '${rect.left},${rect.top},${rect.right},${rect.bottom}';
    }
    if (method == 'hudProbe') {
      final view = View.of(context);
      final box = _pill.currentContext?.findRenderObject() as RenderBox?;
      return 'visual=${widget.state.visual.name} mostrado=$_visible '
          'acao=${widget.state.action.name} dpr=${view.devicePixelRatio} '
          'view=${view.physicalSize} pilula=${box?.size} '
          'pos=${box?.localToGlobal(Offset.zero)}';
    }
    if (method == 'hudShot') return shootBoundary(_canvas, data['path'] as String);
    if (method == 'appearance') {
      _applyAppearance(data);
      return null;
    }
    if (method == 'review') {
      final id = data['id'] as String? ??
          DateTime.now().microsecondsSinceEpoch.toString();
      setState(() {
        _itens.removeWhere((e) => e.id == id);
        _itens.add(_Pendente(
          id: id,
          text: data['text'] as String? ?? '',
          meeting: data['meeting'] == true,
        ));
      });
      _log('cartao recebido: id=$id texto=${(data['text'] as String? ?? '').length} chars');
      await _mostrarCartao();
      return null;
    }
    if (method == 'reviewHide') {
      setState(_itens.clear);
      await _apply();
      await DitoWin32.giveBackFocus();
      return null;
    }
    if (method == 'reviewProbe') {
      return 'cartoes=${_itens.length} mostrado=$_visible';
    }
    if (method != 'hud') return null;
    widget.state.apply(HudMessage.fromMap(data));
    return null;
  }

  /// Asks the owner instead of waiting: the broadcast may have gone out before we existed.
  /// Retried because giving up leaves the window on the system locale, not the configured one.
  Future<void> _askAppearance() async {
    for (var attempt = 0; attempt < 10; attempt++) {
      if (!mounted) return;
      final raw = await widget.bus.request(widget.ownerId, 'appearance', <String, Object?>{});
      if (raw is Map) {
        _applyAppearance(Map<String, Object?>.from(raw));
        return;
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    _log('sem resposta de appearance: janela fica no idioma e tema do sistema');
  }

  /// The pill only ever hears transitions; on boot it has to ask what is happening right now.
  Future<void> _askHudState() async {
    for (var attempt = 0; attempt < 10; attempt++) {
      if (!mounted) return;
      final raw = await widget.bus.request(widget.ownerId, 'hudState', <String, Object?>{});
      if (raw is Map) {
        widget.state.apply(HudMessage.fromMap(Map<String, Object?>.from(raw)));
        return;
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    _log('sem resposta de hudState: a pilula so reage a transicoes');
  }

  void _applyAppearance(Map<String, Object?> data) {
    if (!mounted) return;
    setState(() {
      _theme = data['theme'] as String? ?? 'auto';
      _locale = data['locale'] as String? ?? 'auto';
    });
  }

  void _onStateChanged() {
    setState(() {});
    unawaited(_apply());
  }

  /// Runs one native window call best-effort; false means the window did NOT change.
  Future<bool> _tryNative(String what, Future<void> Function() call) async {
    try {
      await call();
      return true;
    } catch (e) {
      _log('$what falhou: $e');
      return false;
    }
  }

  Future<void> _nextFrame() {
    final done = Completer<void>();
    WidgetsBinding.instance.addPostFrameCallback((_) => done.complete());
    return done.future;
  }

  /// Serialised: two overlapping runs could leave `_visible` disagreeing with the real window.
  Future<void> _apply() async {
    if (_busy) {
      _again = true;
      return;
    }
    _busy = true;
    try {
      do {
        _again = false;
        await _applyOnce();
      } while (_again && mounted);
    } finally {
      _busy = false;
    }
  }

  /// Places the fixed canvas once, then only shows and hides it.
  Future<void> _applyOnce() async {
    if (!mounted) return;
    final ratio = View.of(context).devicePixelRatio;

    if (!_placed) {
      _placed = true;
      await DitoWin32.setBottomCenter(
        width: AppSize.hudCanvasWidth,
        height: AppSize.hudCanvasHeight,
        devicePixelRatio: ratio,
        margin: AppSize.screenMargin,
      );
    }

    final shouldShow = widget.state.isOnScreen || _itens.isNotEmpty;
    // O show nativo e idempotente e o GTK aceita "mostrar" sem mapear a janela: confiar na flag
    // deixava a pilula invisivel em gravacoes alternadas. Ver docs/armadilhas.md 4.3.
    if (shouldShow) {
      await _nextFrame();
      if (!mounted) return;
      await _clipToPill();
      final shown = await _tryNative('show', widget.controller.show) &&
          await _tryNative('showNoActivate', DitoWin32.showNoActivate);
      // The flag follows the window, never the intention: lying here mutes every later attempt.
      _visible = shown;
      if (shown) {
        _hit = null;
        await _clipToPill();
      } else {
        _scheduleRetry();
      }
    } else if (_visible) {
      // Nao desmapeia: so recorta para nada. Ver docs/armadilhas.md 4.3.
      _visible = false;
      _hit = null;
      await _tryNative('esconder', () => DitoWin32.setHitRect(
            rect: Rect.zero,
            devicePixelRatio: View.of(context).devicePixelRatio,
          ));
    }
  }

  /// Cartao na tela precisa de teclado: a pilula sozinha nunca pede foco, o cartao sempre pede.
  Future<void> _mostrarCartao() async {
    await _tryNative('takeFocus', DitoWin32.takeFocus);
    // Sem isto o gerenciador de janelas RECUSA o foco: adoptAsHud marcou a janela como incapaz de
    // receber foco (WM_HINTS.input=False), e nem XSetInputFocus contorna. Ver armadilhas 4.6.
    await _tryNative('setFocusable', () async {
      await DitoWin32.setFocusable(true);
    });
    await _apply();
    if (!mounted) return;
    var focado = false;
    try {
      focado = await DitoWin32.focusWindow();
    } catch (e) {
      _log('focusWindow falhou: $e');
    }
    _log('cartao no ar: focado=$focado itens=${_itens.length}');
  }

  /// Fecha um cartao; a janela so devolve o foco quando o ultimo for resolvido.
  Future<void> _fecharCartao(String id) async {
    setState(() => _itens.removeWhere((e) => e.id == id));
    await _apply();
    // Devolver o foco com cartao ainda na tela deixava os proximos sem teclado; quem envia texto
    // devolve o foco no proprio fluxo de colagem. Ver docs/armadilhas.md 4.5.
    if (_itens.isEmpty) {
      await _tryNative('setFocusable', () async {
        await DitoWin32.setFocusable(false);
      });
      await DitoWin32.giveBackFocus();
    }
  }

  Future<void> _enviarCartao(String id, String text, {required bool toVault}) async {
    _log('cartao enviado: id=$id ${text.length} chars, restam ${_itens.length - 1}');
    // O texto vai para onde o cursor estava: o foco tem de voltar ANTES do dono colar.
    setState(() => _itens.removeWhere((e) => e.id == id));
    if (_itens.isEmpty) {
      await _tryNative('setFocusable', () async {
        await DitoWin32.setFocusable(false);
      });
    }
    await _apply();
    await DitoWin32.giveBackFocus();
    await widget.bus.send(widget.ownerId, 'reviewSend', <String, Object?>{
      'id': id,
      'text': text,
      'toVault': toVault,
    });
  }

  Future<void> _descartarCartao(String id) async {
    _log('cartao descartado: id=$id, restam ${_itens.length - 1}');
    await _fecharCartao(id);
    await widget.bus.send(widget.ownerId, 'reviewDiscard', <String, Object?>{'id': id});
  }

  /// A native call that failed once must be tried again; the pill is the only "we are recording".
  void _scheduleRetry() {
    _retry?.cancel();
    _retry = Timer(AppMotion.retry, () {
      if (mounted) unawaited(_apply());
    });
  }

  /// The region is the pill's visible shape: it clips the canvas and bounds the clicks.
  Future<void> _clipToPill() async {
    if (!mounted) return;
    final box = _pill.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) {
      // Sem medida ainda: liberar a janela inteira. Sair daqui deixaria a regiao do "escondido"
      // (vazia) valendo, e a janela desenharia sem aceitar clique nenhum.
      // Ver docs/armadilhas.md 4.5.
      _hit = null;
      await DitoWin32.setHitRect(
        rect: const Rect.fromLTWH(0, 0, AppSize.hudCanvasWidth, AppSize.hudCanvasHeight),
        devicePixelRatio: View.of(context).devicePixelRatio,
      );
      return;
    }
    // Region matches the pill surface exactly to avoid black edge cuts.
    final rect = (box.localToGlobal(Offset.zero) & box.size)
        .deflate(AppShadow.margin);
    if (rect.isEmpty || rect == _hit) return;
    _hit = rect;
    await DitoWin32.setHitRect(
      rect: rect,
      devicePixelRatio: View.of(context).devicePixelRatio,
      radius: AppRadius.overlay,
    );
  }

  void _onAction() {
    final intent = widget.state.visual == HudVisual.dead
        ? HudIntent.fixRequested
        : HudIntent.stopRequested;
    widget.bus.send(widget.ownerId, 'hudIntent', <String, Object?>{'intent': intent.name});
  }

  @override
  void dispose() {
    _retry?.cancel();
    widget.state.removeListener(_onStateChanged);
    unawaited(_log.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: appTheme(Brightness.light),
        darkTheme: appTheme(Brightness.dark),
        themeMode: themeModeFrom(_theme),
        localizationsDelegates: AppStrings.localizationsDelegates,
        supportedLocales: AppStrings.supportedLocales,
        locale: localeFromCode(_locale),
        home: Scaffold(
          backgroundColor: Colors.transparent,
          // Fixed transparent canvas; the pill sizes itself and sits at the bottom.
          // No IntrinsicWidth here: it inflated the pill to the whole canvas width.
          body: RepaintBoundary(
            key: _canvas,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: Column(
                key: _pill,
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.end,
                children: <Widget>[
                  if (_itens.isNotEmpty)
                    Stack(
                      alignment: Alignment.bottomCenter,
                      children: <Widget>[
                        // Baralho em leque: embaixo, meio, cima, e o proximo volta para baixo.
                        for (var i = 0; i < _itens.length; i++)
                          Padding(
                            padding: EdgeInsets.only(
                              bottom: AppSize.reviewStackStep * (i % _slots),
                            ),
                            child: ReviewCard(
                              key: ValueKey<String>(_itens[i].id),
                              text: _itens[i].text,
                              meeting: _itens[i].meeting,
                              onSend: (t, {required toVault}) => unawaited(
                                  _enviarCartao(_itens[i].id, t, toVault: toVault)),
                              onDiscard: () =>
                                  unawaited(_descartarCartao(_itens[i].id)),
                              onContentChanged: () => WidgetsBinding.instance
                                  .addPostFrameCallback((_) => unawaited(_clipToPill())),
                            ),
                          ),
                      ],
                    ),
                  HudPill(state: widget.state, onAction: _onAction),
                ],
              ),
            ),
          ),
        ),
      );
}
