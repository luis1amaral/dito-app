import 'dart:async';
import 'dart:collection';
import 'dart:io';

/// Ring buffer plus file log, one per window; writes are queued, never sync on the hot path.
class Logbook {
  Logbook(this.name, {this.directory, this.ringSize = 500});

  final String name;
  final String? directory;
  final int ringSize;

  final Queue<String> _ring = Queue<String>();
  final List<String> _pending = <String>[];
  IOSink? _sink;
  bool _broken = false;
  bool _closed = false;

  /// Serialises every write, so close never lands on top of a flush in flight.
  Future<void> _chain = Future<void>.value();

  List<String> get recent => List.unmodifiable(_ring);

  void call(String message) => write(message);

  void write(String message) {
    if (_closed) return;
    final line = '[${DateTime.now().toIso8601String()}] [$name] $message';
    _ring.addLast(line);
    while (_ring.length > ringSize) {
      _ring.removeFirst();
    }
    if (_broken) return;
    _pending.add(line);
    _chain = _chain.then((_) => _flush());
  }

  Future<void> _flush() async {
    if (_broken || _closed || _pending.isEmpty) return;
    try {
      final sink = _sink ??= _open();
      if (sink == null) {
        _broken = true;
        _pending.clear();
        return;
      }
      final batch = List<String>.from(_pending);
      _pending.clear();
      sink.writeln(batch.join('\n'));
      await sink.flush();
    } catch (_) {
      // Losing the log must never take the app down; the memory ring still holds it.
      _broken = true;
      _pending.clear();
    }
  }

  IOSink? _open() {
    try {
      final dir = directory ?? _defaultDirectory();
      if (dir == null) return null;
      Directory(dir).createSync(recursive: true);
      return File('$dir/$name.log').openWrite(mode: FileMode.append);
    } catch (_) {
      return null;
    }
  }

  static String? _defaultDirectory() {
    final local = Platform.environment['LOCALAPPDATA'];
    return local == null || local.isEmpty ? null : '$local\\dito\\logs';
  }

  Future<void> close() async {
    if (_closed) return;
    final chain = _chain;
    _closed = true;
    await chain;
    try {
      await _sink?.close();
    } catch (_) {
      // Closing twice, or after a failed open, is not worth propagating.
    }
    _sink = null;
  }
}
