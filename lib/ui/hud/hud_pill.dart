import 'package:flutter/material.dart';

import '../../l10n/app_strings.dart';
import '../../state/hud_commands.dart';
import '../palette.dart';
import '../tokens.dart';
import '../widgets/floating_surface.dart';
import '../widgets/status_dot.dart';
import '../widgets/waveform.dart';
import 'hud_state.dart';

/// The pill: dot, title, wave, clock and at most one action.
class HudPill extends StatelessWidget {
  const HudPill({super.key, required this.state, required this.onAction});

  final HudState state;
  final void Function() onAction;

  /// Every colour of the pill, per state, in one place.
  static ({Color dot, Color fill, Color? border, Color wave}) _colorsFor(
      HudState state, AppColors c) {
    return switch (state.visual) {
      HudVisual.recording => (
          dot: state.meeting ? c.hudOk : c.hudRecording,
          fill: c.hudSurface,
          border: null,
          wave: c.hudText,
        ),
      // Prolonged silence screams in red like the Python did; the live wave still tells it
      // apart from dead, where nothing arrives at all.
      HudVisual.quiet => (
          dot: c.hudText,
          fill: c.hudDanger,
          border: null,
          wave: c.hudText,
        ),
      // hudDanger, never the theme's danger: that token flips and vanishes in dark mode.
      HudVisual.dead => (
          dot: c.hudText,
          fill: c.hudDanger,
          border: null,
          wave: c.hudText,
        ),
      HudVisual.working => (
          dot: c.hudAlert,
          fill: c.hudSurface,
          border: null,
          wave: c.hudAlert,
        ),
      HudVisual.toast => (
          dot: c.hudOk,
          fill: c.hudSurface,
          border: null,
          wave: c.hudText,
        ),
      HudVisual.hidden => (
          dot: c.hudMuted,
          fill: c.hudSurface,
          border: null,
          wave: c.hudMuted,
        ),
    };
  }

  /// Wording comes from the catalogue; the state only carries what the pill MEANS.
  static String _titleFor(HudState state, AppStrings s) => switch (state.visual) {
        HudVisual.recording => s.hudRecording,
        HudVisual.quiet => s.hudQuiet,
        HudVisual.dead => s.hudNoAudio,
        HudVisual.working => switch (state.work) {
            HudWork.transcribing => s.hudTranscribing,
            HudWork.minutesDone => s.hudMinutesDone(state.minutes),
            HudWork.saving => s.hudSaving,
          },
        HudVisual.toast => switch (state.toast) {
            HudToast.engineStarting => s.toastEngineStarting,
            HudToast.engineUnreachable => s.toastEngineUnreachable,
            HudToast.stillBusy => s.toastStillBusy,
            HudToast.recordingEnded => s.toastRecordingEnded,
            HudToast.failed => s.toastFailed,
            HudToast.pasteFailed => s.toastPasteFailed,
            HudToast.pasteToClipboard => s.toastPasteToClipboard,
            HudToast.pasteToFolder => s.toastPasteToFolder,
            HudToast.discarded => s.toastDiscarded,
            HudToast.copied => s.toastCopied,
            HudToast.pasted => s.toastPasted,
          },
        HudVisual.hidden => '',
      };

  static String? _detailFor(HudState state, AppStrings s) =>
      state.visual == HudVisual.toast && state.toast == HudToast.recordingEnded
          ? s.toastRecordingEndedWhy
          : state.detail;

  static String? _actionFor(HudState state, AppStrings s) => switch (state.action) {
        HudAction.none => null,
        HudAction.stop => s.hudStop,
        HudAction.fix => s.hudFix,
      };

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final s = context.strings;
    final titulo = _titleFor(state, s);
    final detalhe = _detailFor(state, s);
    final acao = _actionFor(state, s);
    final colors = _colorsFor(state, c);
    final onRed = state.visual == HudVisual.dead || state.visual == HudVisual.quiet;
    final showWave = state.visual != HudVisual.toast;
    final showClock = state.visual == HudVisual.recording ||
        state.visual == HudVisual.quiet ||
        state.visual == HudVisual.dead;

    // Opacity and a horizontal shake only. Translating vertically inside a window sized to
    // the content clips the pill's base, and growing the window to fit the travel leaves a
    // dead strip: the entry reads just as well as a fade.
    return ValueListenableBuilder<int>(
      valueListenable: state.frame,
      builder: (_, _, child) => AnimatedOpacity(
        opacity: state.isOnScreen ? 1 : 0,
        duration: AppMotion.fade,
        curve: Curves.easeOut,
        child: Transform.translate(offset: Offset(state.shake, 0), child: child),
      ),
      // The pill hugs its row; the floor lives here, not in the window.
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          minWidth: AppSize.hudMinWidth + AppShadow.margin * 2,
        ),
        child: FloatingSurface(
          fill: colors.fill.withValues(alpha: AppAlpha.hudSurface),
          border: colors.border,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl,
              vertical: AppSpacing.lg,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    StatusDot(
                      color: colors.dot,
                      repaint: state.frame,
                      phase: state.dotPhase,
                      pulsing: state.visual != HudVisual.toast,
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Text(
                      titulo,
                      style: TextStyle(
                        color: c.hudText,
                        fontSize: AppType.title,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.2,
                        height: 1.2,
                      ),
                    ),
                    if (state.visual == HudVisual.working) ...<Widget>[
                      const SizedBox(width: AppSpacing.lg),
                      _WorkingBar(color: colors.wave),
                    ] else if (showWave) ...<Widget>[
                      const SizedBox(width: AppSpacing.lg),
                      Waveform(
                        model: state.wave,
                        repaint: state.frame,
                        color: colors.wave,
                      ),
                    ],
                    if (showClock) ...<Widget>[
                      const SizedBox(width: AppSpacing.lg),
                      ValueListenableBuilder<String>(
                        valueListenable: state.clock,
                        builder: (_, text, _) => Text(
                          text,
                          style: TextStyle(
                            color: onRed ? c.hudOnDangerMuted : c.hudMuted,
                            fontSize: AppType.body,
                            fontFeatures: const <FontFeature>[
                              FontFeature.tabularFigures(),
                            ],
                          ),
                        ),
                      ),
                    ],
                    if (acao != null) ...<Widget>[
                      const SizedBox(width: AppSpacing.lg),
                      _PillButton(
                        label: acao,
                        onTap: onAction,
                        onRed: onRed,
                      ),
                    ],
                  ],
                ),
                if (detalhe != null) ...<Widget>[
                  const SizedBox(height: AppSpacing.sm),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: AppSize.hudDetailWidth),
                    child: Text(
                      detalhe,
                      style: TextStyle(
                        color: onRed ? c.hudOnDanger : c.hudMuted,
                        fontSize: AppType.body,
                        height: 1.35,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Handle for the test that proves the bar has real size, not just a widget in the tree.
const Key workingBarKey = Key('hud-working-bar');

/// A sliding bar for the transcribing state: there is no audio left to draw, but the work
/// is still happening and a frozen pill reads as a hang.
class _WorkingBar extends StatefulWidget {
  const _WorkingBar({required this.color});

  final Color color;

  @override
  State<_WorkingBar> createState() => _WorkingBarState();
}

class _WorkingBarState extends State<_WorkingBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: AppMotion.spinner,
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
        width: Waveform.width,
        height: AppSize.waveHeight,
        child: Center(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.pill),
            child: AnimatedBuilder(
              animation: _controller,
              // Childless CustomPaint needs its size stated, or it lays out at zero and
              // the bar renders as nothing - which reads as a hung transcription.
              builder: (context, _) => CustomPaint(
                key: workingBarKey,
                size: const Size(Waveform.width, AppSize.workingBarHeight),
                painter: _WorkingPainter(
                  progress: _controller.value,
                  color: widget.color,
                ),
              ),
            ),
          ),
        ),
      );
}

class _WorkingPainter extends CustomPainter {
  const _WorkingPainter({required this.progress, required this.color});

  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
      Offset.zero & size,
      Paint()..color = color.withValues(alpha: 0.25),
    );
    final width = size.width * 0.4;
    final x = (size.width + width) * progress - width;
    canvas.drawRect(
      Rect.fromLTWH(x, 0, width, size.height),
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(_WorkingPainter old) =>
      old.progress != progress || old.color != color;
}

class _PillButton extends StatefulWidget {
  const _PillButton({required this.label, required this.onTap, required this.onRed});

  final String label;
  final void Function() onTap;
  final bool onRed;

  @override
  State<_PillButton> createState() => _PillButtonState();
}

class _PillButtonState extends State<_PillButton> {
  bool _hovering = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final fill = _pressed
        ? c.hudSolidActive
        : (_hovering ? c.hudSolidHover : c.hudWashStrong);

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(
        onTapDown: (_) => setState(() => _pressed = true),
        onTapUp: (_) => setState(() => _pressed = false),
        onTapCancel: () => setState(() => _pressed = false),
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: AppMotion.press,
          curve: Curves.easeOut,
          constraints: const BoxConstraints(minHeight: AppSize.hudControl),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppRadius.pill),
            border: Border.all(color: c.hudEdge, width: AppSize.hairline),
          ),
          child: Center(
            widthFactor: 1,
            child: Text(
              widget.label,
              style: TextStyle(
                // Solid fill flips the text: on the wash it is light, on the solid it is dark.
                color: _hovering || _pressed ? c.hudSurface : c.hudText,
                fontSize: AppType.body,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
