/// Scales ported from src/dito/ui/theme.py; nothing in lib/ui may hardcode these values.
library;

class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 48;
}

class AppRadius {
  static const double control = 8;
  static const double card = 12;
  static const double overlay = 18;
  static const double pill = 9999;
}

class AppType {
  // Desktop reads at arm's length: 11/13 was the port's, and it was too small to read.
  static const double caption = 12;
  static const double body = 14;
  static const double title = 17;
  static const double display = 24;

  static const int regular = 400;
  static const int semibold = 600;
  static const int bold = 700;
}

class AppSize {
  /// Degrau entre cartoes empilhados: embaixo, meio, cima, e o proximo volta para baixo.
  static const double reviewStackStep = 132;

  /// Floor, not width: in Portuguese "Corrigir" is wider than "Fix" and used to get clipped.
  static const double hudMinWidth = 340;
  static const double hudMinHeight = 52;
  static const double reviewWidth = 560;

  /// Minimum, never fixed: a fixed height clips the label when the system font grows.
  static const double control = 40;
  static const double hudControl = 32;

  /// Touch target floor, applied to anything visually smaller than this.
  static const double touchTarget = 44;

  static const double hairline = 1;
  static const double dotBox = 14;
  static const double dotMin = 8;
  static const double dotMax = 12;

  static const int waveBars = 13;
  static const double waveBarWidth = 3;
  static const double waveBarGap = 3;
  static const double waveMinHeight = 3;
  static const double waveHeight = 24;

  /// Ceiling for the pill's second line, so a long reason wraps instead of stretching it.
  static const double hudDetailWidth = 420;

  /// Thickness of the indeterminate bar shown while transcribing, where there is no audio left.
  static const double workingBarHeight = 6;

  /// Margin from the work area edge, for both the HUD and the review card.
  static const double screenMargin = AppSpacing.xxxl;

  /// Overlay windows are a FIXED canvas the content is centred in. Sizing a window to its
  /// own content means measuring inside the thing you are resizing, and that loop clipped
  /// the pill and collapsed the card.
  /// UMA sub-janela para a pilula E os cartoes: duas sub-janelas disputavam o contexto GL e a
  /// segunda nascia sem renderizar. Ver docs/armadilhas.md 4.4.
  static const double hudCanvasWidth = 900;
  static const double hudCanvasHeight = 900;
  static const double reviewCanvasWidth = 700;
  // Canvas ALTO de proposito: o cartao (ancorado no rodape) cresce PRA CIMA com o texto, sem
  // scroll. O clip-to-card mostra so o cartao, entao o espaco transparente extra e invisivel; ele
  // so garante que um texto de muitas linhas caiba inteiro em vez de cortar no topo da janela.
  static const double reviewCanvasHeight = 900;
}

class AppAlpha {
  static const double hudSurface = 0.96;
}

/// Motion constants for the pill: fades, pulses and the alarm shake.
class AppMotion {
  static const Duration press = Duration(milliseconds: 100);
  static const Duration fade = Duration(milliseconds: 180);
  static const Duration toast = Duration(milliseconds: 1800);
  static const Duration alarmPulse = Duration(milliseconds: 1000);
  static const Duration shake = Duration(milliseconds: 220);
  static const Duration spinner = Duration(milliseconds: 1000);

  /// HUD repaint tick; the clock and the wave both ride it.
  static const Duration tick = Duration(milliseconds: 50);

  /// Wait before retrying a native show/hide that failed.
  static const Duration retry = Duration(milliseconds: 300);

  static const double shakePixels = 7;
  static const double dotPeriodSeconds = 1.2;
  static const double waveEasing = 0.45;

  /// Speech RMS sits between 0.02 and 0.10; linear would leave the bars invisible.
  static const double waveGain = 18;
}

/// Hand-painted shadow: QGraphicsDropShadowEffect has no equivalent on a translucent window.
class AppShadow {
  static const double spread = 14;
  static const double offset = 5;
  static const int layers = 9;
  static const int alpha = 16;

  /// Every window that paints this must reserve it on all four sides.
  static const double margin = spread + offset;
}
