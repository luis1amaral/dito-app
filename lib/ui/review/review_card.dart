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

  /// Fires whenever the text changes size so the window can re-clip and the card can grow upward.
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
    // Re-grabs the keyboard when the card reappears with new text; without this only the first card stayed active and later ones needed a click.
    _grabFocusSoon();
  }

  /// Requests focus next frame; with autofocus: true and DitoWin32.focusWindow() (dito_root_app.dart) the keyboard lands in the editor with no click.
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

  /// On Linux the Enter arrives as a text INSERTION, not only as a key; without this the first one just broke the line (CHANGELOG 1.6.7).
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

    // Anchored to the bottom edge and grows WITH the text (maxLines: null, no scroll): it rises to show it all, so the edge never leaves the screen.
    return SizedBox(
      width: AppSize.reviewWidth + AppShadow.margin * 2,
      // With several cards stacked, a click has to pick which one receives Enter/Tab.
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
