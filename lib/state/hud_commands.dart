/// Vocabulary the main window speaks to the HUD; each message carries only its own signal.
///
/// Never "here is the whole state": at 20 Hz that would be the mistake that kills the idea.
library;

enum HudKind { recording, quiet, dead, working, toast, dismiss, level }

/// What a toast MEANS. The wording lives in the ARB catalogue and is resolved by the window
/// that draws it, so nothing on screen is nailed to one language.
enum HudToast {
  engineStarting,
  engineUnreachable,
  stillBusy,
  recordingEnded,
  failed,
  pasteFailed,
  pasteToClipboard,
  pasteToFolder,
  discarded,
  copied,
  pasted,
}

/// What the app is busy with while transcribing.
enum HudWork { transcribing, minutesDone, saving }

/// The single action the pill may offer.
enum HudAction { none, stop, fix }

T _enumFrom<T extends Enum>(List<T> values, Object? name, T fallback) =>
    values.firstWhere((v) => v.name == name, orElse: () => fallback);

class HudMessage {
  const HudMessage(this.kind, [this.data = const <String, Object?>{}]);

  final HudKind kind;
  final Map<String, Object?> data;

  Map<String, Object?> toMap() => <String, Object?>{'kind': kind.name, ...data};

  static HudMessage fromMap(Map<Object?, Object?> raw) {
    final map = Map<String, Object?>.from(raw);
    final kind = HudKind.values.firstWhere(
      (k) => k.name == map['kind'],
      orElse: () => HudKind.dismiss,
    );
    return HudMessage(kind, map);
  }

  static HudMessage recording({required bool meeting}) =>
      HudMessage(HudKind.recording, <String, Object?>{'meeting': meeting});

  static HudMessage quiet(String? reason) =>
      HudMessage(HudKind.quiet, <String, Object?>{'reason': reason});

  // The reason comes from the engine's own diagnosis and passes through untranslated.
  static HudMessage dead(String? reason, {required bool canFix}) => HudMessage(
      HudKind.dead, <String, Object?>{'reason': reason, 'canFix': canFix});

  static HudMessage working(HudWork work, {int minutes = 0}) => HudMessage(
      HudKind.working, <String, Object?>{'work': work.name, 'minutes': minutes});

  static HudMessage toast(HudToast toast, {String? detail, int ms = 1800}) => HudMessage(
      HudKind.toast,
      <String, Object?>{'toast': toast.name, 'detail': detail, 'ms': ms});

  static const HudMessage dismiss = HudMessage(HudKind.dismiss);

  static HudMessage level(double rms) =>
      HudMessage(HudKind.level, <String, Object?>{'rms': rms});

  bool get meeting => data['meeting'] == true;
  bool get canFix => data['canFix'] == true;
  String? get reason => data['reason'] as String?;
  String? get detail => data['detail'] as String?;
  int get minutes => (data['minutes'] as num?)?.toInt() ?? 0;
  HudToast get toastKind => _enumFrom(HudToast.values, data['toast'], HudToast.failed);
  HudWork get work => _enumFrom(HudWork.values, data['work'], HudWork.transcribing);
  double get rms => (data['rms'] as num?)?.toDouble() ?? 0;
  int get ms => (data['ms'] as num?)?.toInt() ?? 1800;
}

/// What the HUD can ask the main window to do.
enum HudIntent { fixRequested, stopRequested }
