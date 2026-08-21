import 'dart:async';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/services.dart';

/// Message bus between windows; an interface because each window is its own engine.
abstract class WindowBus {
  /// Sends one message to a window, dropping it silently if that window is gone.
  Future<void> send(String windowId, String method, Map<String, Object?> payload);

  /// Sends and waits for the answer; used by diagnostics, never on the hot path.
  Future<Object?> request(String windowId, String method,
      [Map<String, Object?> payload = const <String, Object?>{}]);

  /// Handles messages addressed to this window.
  void onMessage(Future<Object?> Function(String method, Map<String, Object?> data) handler);
}

class MultiWindowBus implements WindowBus {
  MultiWindowBus(this._self);

  final WindowController? _self;

  @override
  Future<void> send(String windowId, String method, Map<String, Object?> payload) async {
    try {
      await WindowController.fromWindowId(windowId).invokeMethod(method, payload);
    } catch (_) {
      // A closed window is not an error: the sender must never care.
    }
  }

  @override
  Future<Object?> request(String windowId, String method,
      [Map<String, Object?> payload = const <String, Object?>{}]) async {
    try {
      return await WindowController.fromWindowId(windowId)
          .invokeMethod<Object?>(method, payload);
    } catch (e) {
      return 'erro: $e';
    }
  }

  @override
  void onMessage(
      Future<Object?> Function(String method, Map<String, Object?> data) handler) {
    try {
      _self?.setWindowMethodHandler((MethodCall call) async {
        final args = call.arguments;
        return handler(
          call.method,
          args is Map ? Map<String, Object?>.from(args) : <String, Object?>{},
        );
      }).catchError((_) {});
    } catch (_) {}
  }
}

/// In-memory bus for tests and for running windows in a single process.
class FakeWindowBus implements WindowBus {
  final List<(String, String, Map<String, Object?>)> sent =
      <(String, String, Map<String, Object?>)>[];

  Future<Object?> Function(String, Map<String, Object?>)? _handler;

  @override
  Future<void> send(String windowId, String method, Map<String, Object?> payload) async {
    sent.add((windowId, method, payload));
  }

  @override
  Future<Object?> request(String windowId, String method,
          [Map<String, Object?> payload = const <String, Object?>{}]) async =>
      _handler == null ? null : _handler!(method, payload);

  @override
  void onMessage(
      Future<Object?> Function(String method, Map<String, Object?> data) handler) {
    _handler = handler;
  }

  Future<Object?> deliver(String method, Map<String, Object?> data) async =>
      _handler == null ? null : _handler!(method, data);
}
