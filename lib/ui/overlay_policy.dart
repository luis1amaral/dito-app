import 'window_orchestrator.dart';

/// Decides what the single native window should do about the overlay and OS focus.
///
/// Pure: takes the combined signal, hands back what to do, touches nothing itself.
class OverlayPolicy {
  const OverlayPolicy();

  OverlayDecision decide({
    required bool hudOnScreen,
    required bool reviewActive,
    required AppWindowMode mode,
  }) {
    final wantsOverlay = hudOnScreen || reviewActive;
    final isOverlay = mode == AppWindowMode.overlay;
    final hideOverlay = !wantsOverlay && isOverlay;
    return OverlayDecision(
      showOverlay: wantsOverlay,
      hideOverlay: hideOverlay,
      // The review card is the only thing that types, so it is the only one that steals focus.
      takeFocus: reviewActive,
      giveFocus: hideOverlay,
    );
  }
}

class OverlayDecision {
  const OverlayDecision({
    required this.showOverlay,
    required this.hideOverlay,
    required this.takeFocus,
    required this.giveFocus,
  });

  final bool showOverlay;
  final bool hideOverlay;
  final bool takeFocus;
  final bool giveFocus;
}
