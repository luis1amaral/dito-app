// O manifesto vem do worker: um campo com nome errado nao explode, so faz o update
// sumir em silencio. Por isso cada ramo de leitura tem teste.
import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('UpdateInfo.fromManifest', () {
    final manifest = <String, dynamic>{
      'version': '1.13.0',
      'notes': 'correcoes',
      'windows': {'size': 22337073, 'sha256': 'AB12'},
      'linux': {'size': 20091465},
    };

    test('le a plataforma pedida com size e sha256 (normalizado minusculo)', () {
      final i = UpdateInfo.fromManifest(manifest, 'windows', '1.12.0')!;
      expect(i.version, '1.13.0');
      expect(i.current, '1.12.0');
      expect(i.notes, 'correcoes');
      expect(i.size, 22337073);
      expect(i.sha256, 'ab12');
      expect(i.integrity, IntegrityCheck.sha256);
      expect(i.sizeLabel, '21 MB');
    });

    test('sem sha256 no manifesto, a garantia cai pro tamanho — e diz isso', () {
      final i = UpdateInfo.fromManifest(manifest, 'linux', '1.12.0')!;
      expect(i.sha256, isNull);
      expect(i.integrity, IntegrityCheck.size);
    });

    test('plataforma ausente devolve null em vez de chutar outra', () {
      expect(UpdateInfo.fromManifest(manifest, 'android', '1.12.0'), isNull);
    });

    test('manifesto sem versao devolve null', () {
      expect(
        UpdateInfo.fromManifest({'windows': {'size': 1}}, 'windows', '1.0.0'),
        isNull,
      );
    });

    test('sha256 vazio conta como ausente, nao como hash valido', () {
      final i = UpdateInfo.fromManifest(
        {'version': '2.0.0', 'windows': {'size': 10, 'sha256': ''}},
        'windows',
        '1.0.0',
      )!;
      expect(i.sha256, isNull);
      expect(i.integrity, IntegrityCheck.size);
    });

    test('sem size e sem sha256 nao ha o que conferir — e a API admite', () {
      final i = UpdateInfo.fromManifest(
        {'version': '2.0.0', 'windows': <String, dynamic>{}},
        'windows',
        '1.0.0',
      )!;
      expect(i.integrity, IntegrityCheck.none);
    });
  });
}
