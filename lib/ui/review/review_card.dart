import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_strings.dart';
import '../palette.dart';
import '../tokens.dart';
import '../widgets/floating_surface.dart';

/// The card that shows the transcript: editable, grows UPWARD to fit, never scrolls.
class ReviewCard extends StatefulWidget {
  const ReviewCard({
    super.key,
    required this.text,
    required this.meeting,
    required this.onSend,
    required this.onDiscard,
    this.onContentChanged,
  });

  final String text;
  final bool meeting;
  final void Function(String text, {required bool toVault}) onSend;
  final void Function() onDiscard;

  /// Fires whenever the text changes size so the window can re-clip and the card can grow upward
  /// instead of being cut by a stale region.
  final VoidCallback? onContentChanged;

  @override
  State<ReviewCard> createState() => _ReviewCardState();
}

class _ReviewCardState extends State<ReviewCard> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.text);
  final FocusNode _focus = FocusNode();

  /// Text before the current edit, so a newly typed newline can be told apart from a dictated one.
  late String _previous = widget.text;

  /// One card resolves once: both key and text paths can carry the same Enter.
  bool _resolved = false;

  /// Off on every recording, deliberately: it never remembers being on.
  bool _toVault = false;

  @override
  void initState() {
    super.initState();
    _controller.selection =
        TextSelection.collapsed(offset: _controller.text.length);
    _grabFocusSoon();
  }

  @override
  void didUpdateWidget(ReviewCard old) {
    super.didUpdateWidget(old);
    if (old.text == widget.text) return;
    // A new recording starts a new card, even when Flutter reuses this State object.
    _controller.text = widget.text;
    _controller.selection = TextSelection.collapsed(offset: widget.text.length);
    _previous = widget.text;
    _resolved = false;
    _toVault = false;
    // Re-pega o teclado quando o cartao reaparece com um texto novo: sem isto so o primeiro
    // cartao ficava ativo e os seguintes exigiam um clique.
    _grabFocusSoon();
  }

  /// Pede o foco no proximo frame. Junto com autofocus: true no TextField e a ativacao da janela
  /// nativa (hud_window: focusWindow/ForceForeground), o teclado cai no editor SEM clique.
  /// Sem timers de proposito: um Future.delayed pendente derrubaria os testes de widget.
  void _grabFocusSoon() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focus.requestFocus();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send() {
    if (_resolved) return;
    _resolved = true;
    final text = _controller.text.trim();
    // An emptied box discards instead of sending nothing.
    if (text.isEmpty) {
      widget.onDiscard();
      return;
    }
    widget.onSend(text, toVault: _toVault);
  }

  /// On Linux the Enter arrives as a text INSERTION, not only as a key; without this the first one
  /// just broke the line and only the second sent. Ver CHANGELOG 1.6.7.
  void _onChanged(String value) {
    final quebrouLinha =
        '\n'.allMatches(value).length > '\n'.allMatches(_previous).length;
    if (quebrouLinha && !HardwareKeyboard.instance.isShiftPressed) {
      _controller.value = TextEditingValue(
        text: _previous,
        selection: TextSelection.collapsed(offset: _previous.length),
      );
      _send();
      return;
    }
    _previous = value;
    setState(() {});
    widget.onContentChanged?.call();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;

    final isEnter = event.logicalKey == LogicalKeyboardKey.enter ||
        event.logicalKey == LogicalKeyboardKey.numpadEnter;
    if (isEnter) {
      // Shift+Enter keeps adding lines; plain Enter is the send.
      if (HardwareKeyboard.instance.isShiftPressed) return KeyEventResult.ignored;
      _send();
      return KeyEventResult.handled;
    }

    if (event.logicalKey == LogicalKeyboardKey.tab ||
        event.logicalKey == LogicalKeyboardKey.escape) {
      widget.onDiscard();
      return KeyEventResult.handled;
    }

    return KeyEventResult.ignored;
  }

  void _setVault(bool v) {
    setState(() => _toVault = v);
    widget.onContentChanged?.call();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final style = TextStyle(
      fontSize: 16,
      color: c.hudText,
      fontWeight: FontWeight.w500,
      height: 1.5,
    );

    // O cartao esta ancorado no rodape (Align.bottomCenter em hud_window) e cresce COM o texto
    // (maxLines: null, SEM scroll): ele SOBE para mostrar tudo, o rodape nunca sai da tela. UMA cor
    // so: o editor vive direto sobre a superficie do cartao, sem uma "caixa preta" em volta. Fundo
    // escuro + texto branco, reusando os componentes e tokens do app (FloatingSurface, AppColors).
    return SizedBox(
      width: AppSize.reviewWidth + AppShadow.margin * 2,
      // Com varios cartoes empilhados, clicar tem de escolher qual recebe Enter/Tab.
      child: Listener(
        onPointerDown: (_) => _focus.requestFocus(),
        child: FloatingSurface(
        fill: c.hudSurface,
        border: null,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl, AppSpacing.xl, AppSpacing.xl, AppSpacing.xxxl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: AppSize.reviewCanvasHeight - AppSize.screenMargin * 2 - 120,
                ),
                child: SingleChildScrollView(
                  physics: const ClampingScrollPhysics(),
                  child: Focus(
                    onKeyEvent: _onKey,
                    child: Theme(
                      data: Theme.of(context).copyWith(
                        textSelectionTheme: TextSelectionThemeData(
                          cursorColor: c.hudText,
                          selectionColor: c.hudText.withValues(alpha: 0.28),
                          selectionHandleColor: c.hudText,
                        ),
                        colorScheme:
                            Theme.of(context).colorScheme.copyWith(onSurface: c.hudText),
                      ),
                      child: TextField(
                        controller: _controller,
                        focusNode: _focus,
                        autofocus: true,
                        style: style,
                        maxLines: null,
                        cursorColor: c.hudText,
                        scrollPhysics: const NeverScrollableScrollPhysics(),
                        decoration: const InputDecoration(
                          border: InputBorder.none,
                          isDense: true,
                          contentPadding: EdgeInsets.zero,
                        ),
                        onChanged: _onChanged,
                      ),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
                child: Container(
                  height: AppSize.hairline,
                  color: c.hudWash,
                ),
              ),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: <Widget>[
                  Icon(Icons.bookmark_add_rounded,
                      size: 18, color: _toVault ? c.hudOk : c.hudMuted),
                  const SizedBox(width: AppSpacing.xs),
                  Text(context.strings.reviewObsidianLabel,
                      style: TextStyle(color: c.hudText, fontSize: AppType.caption)),
                  const SizedBox(width: AppSpacing.xs),
                  Switch(
                    value: _toVault,
                    onChanged: _setVault,
                    // Thumb/track ignore ColorScheme.primary (brand purple): this card is a dark HUD surface.
                    thumbColor: WidgetStateProperty.resolveWith((states) =>
                        states.contains(WidgetState.selected) ? c.hudSurface : c.hudMuted),
                    trackColor: WidgetStateProperty.resolveWith((states) =>
                        states.contains(WidgetState.selected) ? c.hudOk : c.hudWash),
                    trackOutlineColor: WidgetStateProperty.resolveWith((states) =>
                        states.contains(WidgetState.selected) ? c.hudOk : c.hudEdge),
                    // No hover/focus glow ring: it was Material's default purple, not a token.
                    overlayColor: const WidgetStatePropertyAll(Colors.transparent),
                  ),
                  const SizedBox(width: AppSpacing.lg),
                  Icon(Icons.keyboard_tab_rounded, size: 15, color: c.hudMuted),
                  const SizedBox(width: AppSpacing.xs),
                  Text(context.strings.reviewHintDiscard,
                      style: TextStyle(color: c.hudText, fontSize: AppType.caption)),
                  const Spacer(),
                  Icon(Icons.keyboard_return_rounded, size: 15, color: c.hudMuted),
                  const SizedBox(width: AppSpacing.xs),
                  Text(context.strings.reviewHintSend,
                      style: TextStyle(color: c.hudText, fontSize: AppType.caption)),
                ],
              ),
            ],
          ),
          ),
        ),
      ),
    );
  }
}
