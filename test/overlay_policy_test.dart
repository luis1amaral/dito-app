import 'package:dito_app/ui/overlay_policy.dart';
import 'package:dito_app/ui/window_orchestrator.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const policy = OverlayPolicy();

  test('hud alone asks to show, never steals focus', () {
    final d = policy.decide(
        hudOnScreen: true, reviewActive: false, mode: AppWindowMode.hidden);
    expect(d.showOverlay, isTrue);
    expect(d.hideOverlay, isFalse);
    expect(d.takeFocus, isFalse);
    expect(d.giveFocus, isFalse);
  });

  test('review alone asks to show and steals focus', () {
    final d = policy.decide(
        hudOnScreen: false, reviewActive: true, mode: AppWindowMode.hidden);
    expect(d.showOverlay, isTrue);
    expect(d.takeFocus, isTrue);
  });

  test('both on screen still shows once and steals focus once', () {
    final d = policy.decide(
        hudOnScreen: true, reviewActive: true, mode: AppWindowMode.overlay);
    expect(d.showOverlay, isTrue);
    expect(d.hideOverlay, isFalse);
    expect(d.takeFocus, isTrue);
    expect(d.giveFocus, isFalse);
  });

  test('nothing left and the window is the overlay: hide and give focus back', () {
    final d = policy.decide(
        hudOnScreen: false, reviewActive: false, mode: AppWindowMode.overlay);
    expect(d.showOverlay, isFalse);
    expect(d.hideOverlay, isTrue);
    expect(d.giveFocus, isTrue);
  });

  test('nothing left but the window was never the overlay: nothing to hide', () {
    final d = policy.decide(
        hudOnScreen: false, reviewActive: false, mode: AppWindowMode.hidden);
    expect(d.showOverlay, isFalse);
    expect(d.hideOverlay, isFalse);
    expect(d.giveFocus, isFalse);
  });

  test('the main window is never told to hide itself as an overlay', () {
    final d = policy.decide(
        hudOnScreen: false, reviewActive: false, mode: AppWindowMode.mainWindow);
    expect(d.hideOverlay, isFalse);
    expect(d.giveFocus, isFalse);
  });

  test('review ends while the hud is still up: keep showing, no focus grab', () {
    final d = policy.decide(
        hudOnScreen: true, reviewActive: false, mode: AppWindowMode.overlay);
    expect(d.showOverlay, isTrue);
    expect(d.hideOverlay, isFalse);
    expect(d.takeFocus, isFalse);
    expect(d.giveFocus, isFalse);
  });
}
