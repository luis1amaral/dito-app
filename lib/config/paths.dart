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

  static String get _sep => Platform.pathSeparator;

  static String get _home {
    if (Platform.isWindows) {
      return _env('USERPROFILE', 'C:\\');
    }
    return _env('HOME', '/home');
  }

  static String get configDir {
    if (Platform.isWindows) {
      return '${_env('APPDATA', '$_home\\AppData\\Roaming')}\\$app';
    }
    final xdg = _env('XDG_CONFIG_HOME', '$_home/.config');
    return '$xdg/$app';
  }

  static String get dataDir {
    if (Platform.isWindows) {
      return '${_env('LOCALAPPDATA', '$_home\\AppData\\Local')}\\$app';
    }
    final xdg = _env('XDG_DATA_HOME', '$_home/.local/share');
    return '$xdg/$app';
  }

  static String get stateDir {
    if (Platform.isWindows) {
      return '$dataDir\\state';
    }
    final xdg = _env('XDG_STATE_HOME', '$_home/.local/state');
    return '$xdg/$app';
  }

  static String get logsDir => '$dataDir${_sep}logs';

  static String get configFile => '$configDir${_sep}config.toml';

  /// SHGetFolderPath (OneDrive moves this folder); kept for config_service's pre-migration path check.
  static String get documents {
    if (Platform.isWindows) {
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
    return _env('XDG_DOCUMENTS_DIR', '$_home/Documents');
  }

  static String get defaultLibrary => '$_home${_sep}Dito';

  /// A path typed with a leading tilde is text, not a directory, until it is expanded here.
  static String expandHome(String path) =>
      path.startsWith('~') ? path.replaceFirst('~', _home) : path;

  static String resolveObsidianPath(String vault, String folder) {
    var v = vault.trim();
    if (v.startsWith('~')) {
      v = v.replaceFirst('~', _home);
    }
    return folder.trim().isEmpty ? v : '$v$_sep${folder.trim()}';
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
