import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:win32/win32.dart';

/// Every filesystem location the app uses; one place decides and the rest asks here.
class DitoPaths {
  static const String app = 'dito';

  /// A variable can be defined AND empty, so `env[x] ?? fallback` lies.
  static String _env(String name, String fallback) {
    final value = Platform.environment[name]?.trim() ?? '';
    return value.isEmpty ? fallback : value;
  }

  static String get _home => _env('USERPROFILE', 'C:\\');

  static String get configDir => '${_env('APPDATA', '$_home\\AppData\\Roaming')}\\$app';

  static String get dataDir => '${_env('LOCALAPPDATA', '$_home\\AppData\\Local')}\\$app';

  static String get stateDir => '$dataDir\\state';

  static String get logsDir => '$dataDir\\logs';

  static String get configFile => '$configDir\\config.toml';

  /// Documents via SHGetFolderPath, because OneDrive moves the folder elsewhere.
  static String get documents {
    final buffer = wsalloc(MAX_PATH);
    try {
      final hr = SHGetFolderPath(NULL, CSIDL_PERSONAL, NULL, 0, buffer);
      if (hr == S_OK) {
        final path = buffer.toDartString();
        if (path.isNotEmpty) return path;
      }
    } catch (_) {
      // Falls through to the plain profile path below.
    } finally {
      free(buffer);
    }
    return '$_home\\Documents';
  }

  static String get defaultLibrary => '$documents\\Dito';

  static String resolveObsidianPath(String vault, String folder) {
    var v = vault.trim();
    if (v.startsWith('~')) {
      v = v.replaceFirst('~', _home);
    }
    return folder.trim().isEmpty ? v : '$v\\${folder.trim()}';
  }

  static void ensureDirs() {
    for (final dir in <String>[configDir, dataDir, stateDir, logsDir]) {
      try {
        Directory(dir).createSync(recursive: true);
      } catch (_) {
        // A directory we cannot create is reported by whoever needs to write in it.
      }
    }
  }

  /// Session files live at `<library>/YYYY/MM/DD/<HH-MM-SS>.json`, never session.json.
  static const String sessionSuffix = '.json';
  static const String audioSuffix = '.wav';
  static const String partialsSuffix = '.jsonl';
}
