import 'package:dito_app/engine/native_engine.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('WAV desligado por padrão (CHANGELOG 1.6.4)', () {
    test('sem DITO_SALVAR_WAV, savesWav é falso', () {
      expect(NativeEngine.savesWav(<String, String>{}), isFalse);
    });

    test('DITO_SALVAR_WAV diferente de "1" continua falso', () {
      expect(NativeEngine.savesWav(<String, String>{'DITO_SALVAR_WAV': '0'}), isFalse);
      expect(NativeEngine.savesWav(<String, String>{'DITO_SALVAR_WAV': 'true'}), isFalse);
    });

    test('DITO_SALVAR_WAV=1 liga a válvula de depuração', () {
      expect(NativeEngine.savesWav(<String, String>{'DITO_SALVAR_WAV': '1'}), isTrue);
    });
  });
}
