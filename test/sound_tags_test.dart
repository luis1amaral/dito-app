import 'package:dito_app/engine/native_engine.dart';
import 'package:flutter_test/flutter_test.dart';

/// Recording silence made Whisper invent "[Musica]" and the app pasted it as if it were speech.
void main() {
  group('dropSoundTags', () {
    test('a transcript that is only an invented sound tag becomes empty', () {
      expect(NativeEngine.dropSoundTags('[Musica]'), '');
      expect(NativeEngine.dropSoundTags('[Som de futebol]'), '');
      expect(NativeEngine.dropSoundTags('  [MUSICA DE FUNDO]  '), '');
      expect(NativeEngine.dropSoundTags('[Som de futebol] [Som de futebol]'), '');
      expect(NativeEngine.dropSoundTags('(risos)'), '');
      expect(NativeEngine.dropSoundTags('*musica*'), '');
    });

    test('real speech is never touched', () {
      expect(NativeEngine.dropSoundTags('testando, testando'), 'testando, testando');
      expect(NativeEngine.dropSoundTags('  ola mundo  '), 'ola mundo');
    });

    test('speech that merely contains a tag is kept whole', () {
      expect(NativeEngine.dropSoundTags('[Musica] bom dia a todos'),
          '[Musica] bom dia a todos');
    });

    test('an already empty transcript stays empty', () {
      expect(NativeEngine.dropSoundTags(''), '');
      expect(NativeEngine.dropSoundTags('   '), '');
    });
  });
}
