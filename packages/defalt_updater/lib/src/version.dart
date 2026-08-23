/// Compara "1.11.2" com "1.9.10" numericamente. >0 quando [a] e mais nova.
/// Feito na mao de proposito: comparar string a string diria que 1.9 > 1.11.
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
