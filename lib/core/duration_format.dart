/// mm:ss growing to h:mm:ss: a meeting has no time limit, so it must not wrap at 60 min.
String formatClock(double seconds) {
  final total = seconds.isNaN || seconds < 0 ? 0 : seconds.floor();
  final hours = total ~/ 3600;
  final minutes = (total % 3600) ~/ 60;
  final secs = total % 60;
  final mm = minutes.toString().padLeft(2, '0');
  final ss = secs.toString().padLeft(2, '0');
  return hours > 0 ? '$hours:$mm:$ss' : '$mm:$ss';
}
