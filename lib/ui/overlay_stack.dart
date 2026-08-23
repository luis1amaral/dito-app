import 'package:flutter/material.dart';

import '../engine/engine_protocol.dart';
import 'hud/hud_pill.dart';
import 'hud/hud_state.dart';
import 'review/review_card.dart';
import 'tokens.dart';

/// The pill plus, when active, the review card above it; everything by constructor, so it mounts in a test without a DitoApp.
class OverlayStack extends StatelessWidget {
  const OverlayStack({
    super.key,
    required this.canvasKey,
    required this.pillKey,
    required this.hudState,
    required this.review,
    required this.onHudAction,
    required this.onReviewSend,
    required this.onReviewDiscard,
    required this.onReviewContentChanged,
  });

  final Key canvasKey;
  final Key pillKey;
  final HudState hudState;
  final FinishedEvent? review;
  final void Function() onHudAction;
  final void Function(String text, {required bool toVault}) onReviewSend;
  final void Function() onReviewDiscard;
  final VoidCallback onReviewContentChanged;

  @override
  Widget build(BuildContext context) {
    final review = this.review;
    if (!hudState.isOnScreen && review == null) {
      return const SizedBox.shrink();
    }

    return RepaintBoundary(
      key: canvasKey,
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Column(
          key: pillKey,
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.end,
          children: <Widget>[
            if (review != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: ReviewCard(
                  key: ValueKey<String>(review.sessionId),
                  text: review.text,
                  meeting: review.isMeeting,
                  onSend: onReviewSend,
                  onDiscard: onReviewDiscard,
                  onContentChanged: onReviewContentChanged,
                ),
              ),
            if (hudState.isOnScreen) HudPill(state: hudState, onAction: onHudAction),
          ],
        ),
      ),
    );
  }
}
