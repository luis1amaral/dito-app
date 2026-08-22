import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// One recording on disk: `<library>/YYYY/MM/DD/<HH-MM-SS>.json`, never `session.json`.
class SessionRef {
  const SessionRef({
    required this.id,
    required this.started,
    required this.mode,
    required this.state,
    required this.seconds,
    required this.preview,
    required this.jsonPath,
    required this.hasAudio,
    required this.sizeBytes,
  });

  final String id;
  final DateTime started;
  final String mode;
  final String state;
  final double seconds;
  final String preview;
  final String jsonPath;
  final bool hasAudio;
  final int sizeBytes;

  bool get isDone => state == 'done';
  bool get isMeeting => mode == 'meeting';
  String get folder => File(jsonPath).parent.path;
}

/// Reads the library defensively: a folder it cannot parse becomes 'unknown', never skipped.
class LibraryReader extends ChangeNotifier {
  List<SessionRef> sessions = <SessionRef>[];
  bool isLoading = false;

  static final RegExp _timeName = RegExp(r'^(\d{2})-(\d{2})-(\d{2})$');

  Future<void> load(String root) async {
    isLoading = true;
    notifyListeners();

    final found = <SessionRef>[];
    try {
      final dir = Directory(root);
      if (dir.existsSync()) {
        await for (final entity in dir.list(recursive: true, followLinks: false)) {
          if (entity is! File) continue;
          if (!entity.path.toLowerCase().endsWith('.json')) continue;
          final ref = await _read(entity);
          if (ref != null) found.add(ref);
        }
      }
    } catch (_) {
      // A library we cannot walk still shows whatever was already read.
    }

    found.sort((a, b) => b.started.compareTo(a.started));
    sessions = found;
    isLoading = false;
    notifyListeners();
  }

  Future<SessionRef?> _read(File file) async {
    final stem = _stemOf(file.path);
    // The date comes from the PATH, so a broken JSON still lists with the right day.
    final fromPath = _dateFromPath(file.path, stem);
    if (fromPath == null) return null;

    Map<String, dynamic> meta = <String, dynamic>{};
    try {
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is Map) meta = Map<String, dynamic>.from(decoded);
    } catch (_) {
      // Unreadable metadata is not a reason to hide a recording.
    }

    final wav = File('${file.parent.path}${Platform.pathSeparator}$stem.wav');
    final hasAudio = wav.existsSync();
    var seconds = (meta['seconds'] as num?)?.toDouble() ?? 0;
    if (seconds == 0 && hasAudio) {
      // Physical size beats the RIFF header, which understates a growing file.
      seconds = (wav.lengthSync() - 44) / (16000 * 2);
    }

    final text = (meta['text'] as String?)?.trim() ?? '';
    return SessionRef(
      id: meta['id'] as String? ?? stem,
      started: fromPath,
      mode: meta['mode'] as String? ?? 'dictation',
      state: meta['state'] as String? ?? 'unknown',
      seconds: seconds,
      preview: _preview(text),
      jsonPath: file.path,
      hasAudio: hasAudio,
      sizeBytes: file.lengthSync() + (hasAudio ? wav.lengthSync() : 0),
    );
  }

  static String _stemOf(String path) {
    final name = path.split(RegExp(r'[\\/]')).last;
    final dot = name.lastIndexOf('.');
    return dot < 0 ? name : name.substring(0, dot);
  }

  static DateTime? _dateFromPath(String path, String stem) {
    final parts = path.split(RegExp(r'[\\/]'));
    if (parts.length < 4) return null;
    final day = int.tryParse(parts[parts.length - 2]);
    final month = int.tryParse(parts[parts.length - 3]);
    final year = int.tryParse(parts[parts.length - 4]);
    if (year == null || month == null || day == null) return null;

    final match = _timeName.firstMatch(stem);
    if (match == null) return null;
    return DateTime(
      year,
      month,
      day,
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    );
  }

  static String _preview(String text) {
    if (text.isEmpty) return '';
    if (text.length <= 90) return text;
    final cut = text.substring(0, 90);
    final space = cut.lastIndexOf(' ');
    return '${space > 40 ? cut.substring(0, space) : cut}...';
  }

  /// Removes only what the app writes, and only from day folders older than the cutoff.
  Future<({int sessions, int bytes})> sweep(String root, int keepDays) async {
    if (keepDays <= 0) return (sessions: 0, bytes: 0);
    final cutoff = DateTime.now().subtract(Duration(days: keepDays));
    var removed = 0;
    var freed = 0;

    final dir = Directory(root);
    if (!dir.existsSync()) return (sessions: 0, bytes: 0);

    for (final year in dir.listSync().whereType<Directory>()) {
      if (int.tryParse(_leaf(year.path)) == null) continue;
      for (final month in year.listSync().whereType<Directory>()) {
        if (int.tryParse(_leaf(month.path)) == null) continue;
        for (final day in month.listSync().whereType<Directory>()) {
          final when = _dayOf(year.path, month.path, day.path);
          if (when == null || !when.isBefore(cutoff)) continue;

          for (final file in day.listSync().whereType<File>()) {
            final lower = file.path.toLowerCase();
            // Only our own extensions: a note the owner left beside a recording stays.
            if (!lower.endsWith('.json') &&
                !lower.endsWith('.wav') &&
                !lower.endsWith('.jsonl')) {
              continue;
            }
            freed += file.lengthSync();
            if (lower.endsWith('.json')) removed++;
            file.deleteSync();
          }
          _pruneEmpty(day);
        }
        _pruneEmpty(month);
      }
      _pruneEmpty(year);
    }
    return (sessions: removed, bytes: freed);
  }

  static String _leaf(String path) => path.split(RegExp(r'[\\/]')).last;

  static DateTime? _dayOf(String year, String month, String day) {
    final y = int.tryParse(_leaf(year));
    final m = int.tryParse(_leaf(month));
    final d = int.tryParse(_leaf(day));
    if (y == null || m == null || d == null) return null;
    return DateTime(y, m, d);
  }

  static void _pruneEmpty(Directory dir) {
    try {
      if (dir.listSync().isEmpty) dir.deleteSync();
    } catch (_) {
      // A folder that refuses to go is not worth failing the sweep over.
    }
  }
}
