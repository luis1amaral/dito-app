import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:flutter/foundation.dart';
import 'package:win32/win32.dart';

import '../core/logbook.dart';
import 'config_codec.dart';
import 'config_model.dart';
import 'paths.dart';

/// The only writer of config.toml; sub-windows read a copy and never touch the file.
class ConfigService extends ChangeNotifier {
  ConfigService({
    String? path,
    Logbook? log,
    this.codec = const ConfigCodec(),
    String? oldDefaultLibrary,
    String? newDefaultLibrary,
  })  : _path = path ?? DitoPaths.configFile,
        _log = log ?? Logbook('config'),
        _oldDefaultLibrary =
            oldDefaultLibrary ?? '${DitoPaths.documents}${Platform.pathSeparator}Dito',
        _newDefaultLibrary = newDefaultLibrary ?? DitoPaths.defaultLibrary;

  final String _path;
  final Logbook _log;
  final ConfigCodec codec;
  /// Overridable in tests; production always resolves from [DitoPaths].
  final String _oldDefaultLibrary;
  final String _newDefaultLibrary;

  AppConfig _config = const AppConfig();
  Map<String, dynamic> _extras = <String, dynamic>{};

  AppConfig get config => _config;
  String get path => _path;

  /// An unreadable file is renamed aside and never overwritten; startup is never blocked.
  Future<void> load() async {
    final file = File(_path);
    if (!file.existsSync()) {
      _log('sem config em $_path; usando os padroes');
      return;
    }
    try {
      final decoded = codec.decode(await file.readAsString());
      if (decoded.error != null) {
        await _setAside(file, decoded.error!);
        return;
      }
      _config = decoded.config;
      _extras = decoded.extras;
      await _migrateOldDefaultLibrary();
      notifyListeners();
    } catch (e) {
      await _setAside(file, '$e');
    }
  }

  /// One-time move of the pre-2026-08 default library into the profile root; see CHANGELOG.
  Future<void> _migrateOldDefaultLibrary() async {
    final folder = _config.library.folder.trim();
    // Empty followed the old default implicitly, so it moves too or the history vanishes.
    final followsOldDefault = folder.isEmpty || folder == _oldDefaultLibrary;
    if (!followsOldDefault) return;
    if (!Directory(_oldDefaultLibrary).existsSync()) return;
    if (Directory(_newDefaultLibrary).existsSync()) return;
    try {
      Directory(_oldDefaultLibrary).renameSync(_newDefaultLibrary);
    } catch (e) {
      _log('falha ao migrar biblioteca de $_oldDefaultLibrary para $_newDefaultLibrary: $e');
      return;
    }
    if (folder.isEmpty) return;
    _config = _config.copyWith(library: _config.library.copyWith(folder: ''));
    await save();
  }

  Future<void> _setAside(File file, String reason) async {
    _log('config ilegivel ($reason); guardando como .broken e seguindo com os padroes');
    try {
      final broken = '$_path.broken';
      if (File(broken).existsSync()) File(broken).deleteSync();
      await file.rename(broken);
    } catch (e) {
      _log('nao consegui guardar a config quebrada: $e');
    }
  }

  Future<bool> update(AppConfig next) async {
    if (next == _config) return true;
    _config = next;
    notifyListeners();
    return save();
  }

  /// Writes to a temp file and replaces atomically, so a crash never truncates the config.
  Future<bool> save() async {
    try {
      Directory(File(_path).parent.path).createSync(recursive: true);
      final temp = '$_path.tmp';
      await File(temp).writeAsString(codec.encode(_config, _extras), flush: true);
      if (!_replace(temp, _path)) {
        _log('falha ao substituir a config (erro ${GetLastError()})');
        return false;
      }
      return true;
    } catch (e) {
      _log('falha ao gravar a config: $e');
      return false;
    }
  }

  /// Dart's File.rename does not replace an existing file on Windows; MoveFileEx does.
  /// POSIX rename() is already an atomic replace, so Linux never needed the Win32 call.
  static bool _replace(String from, String to) {
    if (!Platform.isWindows) {
      File(from).renameSync(to);
      return true;
    }
    final src = from.toNativeUtf16();
    final dst = to.toNativeUtf16();
    try {
      return MoveFileEx(src, dst,
              MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) !=
          0;
    } finally {
      free(src);
      free(dst);
    }
  }
}
