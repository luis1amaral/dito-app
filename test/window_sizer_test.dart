import 'package:dito_app/platform/window_sizer.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

class SpyPlacer implements WindowPlacer {
  final List<({double w, double h, double dpr, double margin})> placements =
      <({double w, double h, double dpr, double margin})>[];
  int shows = 0;
  int hides = 0;

  @override
  Future<void> place({
    required double width,
    required double height,
    required double devicePixelRatio,
    required double margin,
  }) async {
    placements.add((w: width, h: height, dpr: devicePixelRatio, margin: margin));
  }

  @override
  Future<void> show() async => shows++;

  @override
  Future<void> hide() async => hides++;
}

void main() {
  late SpyPlacer placer;
  late WindowSizer sizer;

  setUp(() {
    placer = SpyPlacer();
    sizer = WindowSizer(margin: 32, placer: placer);
  });

  Future<void> sync(
    Size size, {
    bool show = true,
    double dpr = 1.0,
    double min = 0,
    double minHeight = 0,
  }) =>
      sizer.sync(
        content: size,
        devicePixelRatio: dpr,
        shouldShow: show,
        minWidth: min,
        minHeight: minHeight,
      );

  group('placement', () {
    test('applies the content size and shows once', () async {
      await sync(const Size(598, 320));

      expect(placer.placements, hasLength(1));
      expect(placer.placements.single.w, 598);
      expect(placer.placements.single.h, 320);
      expect(placer.shows, 1);
    });

    test('a repeated identical size costs no native call', () async {
      await sync(const Size(598, 320));
      await sync(const Size(598, 320));
      await sync(const Size(598, 320));

      expect(placer.placements, hasLength(1));
      expect(placer.shows, 1);
    });

    test('a real change is applied, a sub-pixel one is not', () async {
      await sync(const Size(598, 320));
      await sync(const Size(598.3, 320.2));
      expect(placer.placements, hasLength(1));

      await sync(const Size(598, 400));
      expect(placer.placements, hasLength(2));
      expect(placer.placements.last.h, 400);
    });

    test('the floor widens a narrow pill without touching its height', () async {
      await sync(const Size(200, 90), min: 378);

      expect(placer.placements.single.w, 378);
      expect(placer.placements.single.h, 90);
    });

    test('the device ratio is passed through, never applied twice here', () async {
      await sync(const Size(598, 320), dpr: 1.5);

      expect(placer.placements.single.w, 598, reason: 'a escala e aplicada uma vez, no plugin');
      expect(placer.placements.single.dpr, 1.5);
    });
  });

  group('the collapse that shrank the card to 19px', () {
    test('a height below the floor is never applied', () async {
      // 486x19 is exactly what the card collapsed to before the fix.
      await sync(const Size(486, 19), minHeight: 120);
      await sync(const Size(486, 0), minHeight: 120);

      expect(placer.placements, isEmpty,
          reason: 'altura degenerada e sintoma do laco de realimentacao');
      expect(placer.shows, 0, reason: 'sem tamanho valido, nada aparece');
    });

    test('once the layout settles the real size goes through', () async {
      await sync(const Size(486, 19), minHeight: 120);
      await sync(const Size(598, 320), minHeight: 120);

      expect(placer.placements, hasLength(1));
      expect(placer.placements.single.h, 320);
      expect(placer.shows, 1);
    });

    test('once a real size arrives it settles instead of shrinking', () async {
      await sync(const Size(598, 320));
      await sync(const Size(598, 320));
      await sync(const Size(598, 320));

      expect(placer.placements, hasLength(1));
      expect(placer.placements.single.h, 320);
    });
  });

  group('visibility', () {
    test('hiding happens once and resets the applied size', () async {
      await sync(const Size(598, 320));
      await sync(Size.zero, show: false);

      expect(placer.hides, 1);
      expect(sizer.isVisible, isFalse);
      expect(sizer.appliedSize, Size.zero);
    });

    test('hiding twice does not spam the native side', () async {
      await sync(const Size(598, 320));
      await sync(Size.zero, show: false);
      await sync(Size.zero, show: false);

      expect(placer.hides, 1);
    });

    test('showing again after hiding places the window afresh', () async {
      await sync(const Size(598, 320));
      await sync(Size.zero, show: false);
      await sync(const Size(598, 320));

      expect(placer.placements, hasLength(2));
      expect(placer.shows, 2);
    });
  });

  group('MeasuredContent', () {
    testWidgets('reports the natural size, not the window size', (tester) async {
      Size? measured;
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: SizedBox(
            // A deliberately tiny window: the content must not be squeezed into it.
            width: 100,
            height: 40,
            child: MeasuredContent(
              minWidth: 0,
              onMeasured: (size) => measured = size,
              child: const SizedBox(width: 598, height: 320),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(measured, isNotNull);
      expect(measured!.width, 598);
      expect(measured!.height, 320);
    });

    testWidgets('honours the minimum width', (tester) async {
      Size? measured;
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: MeasuredContent(
            minWidth: 378,
            onMeasured: (size) => measured = size,
            child: const SizedBox(width: 120, height: 50),
          ),
        ),
      );
      await tester.pump();

      expect(measured!.width, 378);
    });
  });
}
