/// Compares "1.11.2" with "1.9.10" numerically (string comparison would say 1.9 > 1.11); >0 means [a] is newer.
int compareVersions(String a, String b) {
  List<int> parts(String v) => v
      .split(RegExp(r'[+\-]'))
      .first
      .split('.')
      .map((p) => int.tryParse(p.trim()) ?? 0)
      .toList();
  final x = parts(a), y = parts(b);
  for (var i = 0; i < (x.length > y.length ? x.length : y.length); i++) {
    final d = (i < x.length ? x[i] : 0) - (i < y.length ? y[i] : 0);
    if (d != 0) return d;
  }
  return 0;
}
