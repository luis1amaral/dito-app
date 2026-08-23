// Errar aqui e caro dos dois lados: comparar como string diria que "1.9" > "1.11"
// (nunca mais atualiza), e um sinal invertido faria o app oferecer downgrade.
import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('compareVersions', () {
    int cmp(String a, String b) => compareVersions(a, b);

    test('minor de dois digitos nao e menor que o de um', () {
      expect(cmp('1.11.2', '1.9.10'), greaterThan(0));
      expect(cmp('1.9.10', '1.11.2'), lessThan(0));
    });

    test('versoes iguais empatam', () {
      expect(cmp('1.11.2', '1.11.2'), 0);
    });

    test('compara patch, minor e major', () {
      expect(cmp('1.11.3', '1.11.2'), greaterThan(0));
      expect(cmp('1.12.0', '1.11.9'), greaterThan(0));
      expect(cmp('2.0.0', '1.99.99'), greaterThan(0));
      expect(cmp('6.13.0', '6.12.0'), greaterThan(0));
    });

    test('numero de partes diferente: o que falta vale zero', () {
      expect(cmp('1.12', '1.12.0'), 0);
      expect(cmp('1.12.1', '1.12'), greaterThan(0));
      expect(cmp('2', '1.99.99'), greaterThan(0));
    });

    test('ignora build number e sufixo (o "+41" do pubspec)', () {
      expect(cmp('1.11.2+41', '1.11.2'), 0);
      expect(cmp('1.12.0+42', '1.11.2+41'), greaterThan(0));
    });

    test('lixo nao explode nem vira update falso', () {
      expect(cmp('', '1.11.2'), lessThan(0));
      expect(cmp('abc', '1.11.2'), lessThan(0));
      expect(cmp('1.11.2', ''), greaterThan(0));
    });
  });
}
