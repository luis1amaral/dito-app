// Estado do auto-update (checagem, download, instalacao). ChangeNotifier de proposito:
// serve ao provider dos apps e ao riverpod (ChangeNotifierProvider) sem adaptador.
//
// Regras que existem por um motivo:
//  • a checagem NUNCA bloqueia a UI e NUNCA mostra erro sozinha;
//  • throttle de 6h: abrir o app 10x no dia custa 1 request;
//  • NADA e baixado sem o usuario mandar — sao ~100 MB. `auto` e opt-in e so no Windows.
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';
import 'updater.dart';

/// Quanto o app pode fazer sozinho. O PADRAO e `notify`: avisa e espera o clique.
enum UpdateMode { notify, auto, off }

enum UpdateStage { idle, checking, available, downloading, ready, installing, error }

class UpdateController extends ChangeNotifier {
  UpdateController({required DefaltUpdater updater, this.checkInterval = const Duration(hours: 6)})
      : _u = updater {
    // le prefs + versao instalada em background: a tela de perfil mostra a versao mesmo
    // com o modo "off", em que checkQuiet() nunca roda
    unawaited(_load());
  }

  final DefaltUpdater _u;
  final Duration checkInterval;

  DefaltUpdater get updater => _u;

  String get _kMode => '${_u.config.appId}.update_mode';
  String get _kLastCheck => '${_u.config.appId}.update_last_check';
  String get _kSkipped => '${_u.config.appId}.update_skipped';

  UpdateStage stage = UpdateStage.idle;
  UpdateInfo? info;
  double progress = 0;
  String? error;
  String currentVersion = '';
  UpdateMode mode = UpdateMode.notify;
  bool bannerDismissed = false;

  File? _file;
  CancelToken? _cancel;
  bool _loaded = false;

  bool get supported => _u.supported;
  UpdateDelivery get delivery => _u.delivery;

  /// So o Windows baixa dentro do app — la existe progresso e estado "pronto pra instalar".
  bool get downloadsInApp => _u.delivery == UpdateDelivery.inAppDownload;

  bool get isBusy =>
      stage == UpdateStage.checking ||
      stage == UpdateStage.downloading ||
      stage == UpdateStage.installing;

  bool get showBanner =>
      !bannerDismissed &&
      (stage == UpdateStage.downloading ||
          stage == UpdateStage.ready ||
          stage == UpdateStage.available ||
          stage == UpdateStage.installing ||
          stage == UpdateStage.error);

  Future<void> _load() async {
    if (_loaded) return;
    _loaded = true;
    final p = await SharedPreferences.getInstance();
    mode = UpdateMode.values.firstWhere(
      (m) => m.name == p.getString(_kMode),
      orElse: () => UpdateMode.notify,
    );
    currentVersion = await _u.currentVersion();
    notifyListeners();
  }

  Future<void> setMode(UpdateMode m) async {
    mode = m;
    notifyListeners();
    await (await SharedPreferences.getInstance()).setString(_kMode, m.name);
  }

  /// Checagem de boot: silenciosa, com throttle, respeita "pular versao".
  /// Dispare SEM await (o retorno so existe pra testes).
  Future<void> checkQuiet() async {
    if (!supported) return;
    await _load();
    if (mode == UpdateMode.off) return;

    final p = await SharedPreferences.getInstance();
    final last = p.getInt(_kLastCheck) ?? 0;
    final agora = DateTime.now().millisecondsSinceEpoch;
    if (agora - last < checkInterval.inMilliseconds) return;

    final found = await _u.check();
    await p.setInt(_kLastCheck, agora);
    unawaited(_u.cleanup(keepVersion: found?.version));

    if (found == null) return;
    if (p.getString(_kSkipped) == found.version) return;

    info = found;
    _file = downloadsInApp ? await _u.downloaded(found) : null;
    stage = _file != null ? UpdateStage.ready : UpdateStage.available;
    notifyListeners();

    if (stage == UpdateStage.available && mode == UpdateMode.auto && downloadsInApp) {
      unawaited(startDownload());
    }
  }

  /// Checagem pedida na mao: ignora throttle e "pular versao".
  /// Devolve null quando ja esta na versao mais nova — a UI avisa.
  Future<UpdateInfo?> checkManual() async {
    if (!supported) return null;
    await _load();
    stage = UpdateStage.checking;
    error = null;
    notifyListeners();

    final found = await _u.check();
    await (await SharedPreferences.getInstance())
        .setInt(_kLastCheck, DateTime.now().millisecondsSinceEpoch);

    if (found == null) {
      stage = UpdateStage.idle;
      notifyListeners();
      return null;
    }

    info = found;
    bannerDismissed = false;
    _file = downloadsInApp ? await _u.downloaded(found) : null;
    stage = _file != null ? UpdateStage.ready : UpdateStage.available;
    notifyListeners();
    return found;
  }

  /// Acao do botao principal. No Windows baixa; no Android e no Linux ja aplica, porque
  /// nessas duas nao existe passo de download dentro do app.
  Future<void> startDownload() async {
    final target = info;
    if (target == null || isBusy) return;

    if (!downloadsInApp) {
      stage = UpdateStage.installing;
      error = null;
      bannerDismissed = false;
      notifyListeners();
      try {
        await _u.apply();
        // Android: quem instala e o navegador, entao aqui a faixa ja cumpriu o papel.
        // Linux: o apt terminou, mas o binario novo so vale na proxima abertura.
        stage = delivery == UpdateDelivery.packageManager ? UpdateStage.ready : UpdateStage.idle;
        if (stage == UpdateStage.idle) bannerDismissed = true;
      } on UpdateException catch (e) {
        error = e.message;
        stage = UpdateStage.error;
      }
      notifyListeners();
      return;
    }

    stage = UpdateStage.downloading;
    progress = 0;
    error = null;
    bannerDismissed = false;
    final token = CancelToken();
    _cancel = token;
    notifyListeners();

    try {
      _file = await _u.download(
        target,
        cancel: token,
        onProgress: (v) {
          progress = v;
          notifyListeners();
        },
      );
      stage = UpdateStage.ready;
    } on UpdateCancelled {
      stage = UpdateStage.available; // cancelado pelo usuario nao e erro
    } catch (e) {
      error = e is UpdateException ? e.message : '$e';
      stage = UpdateStage.error;
      debugPrint('[${_u.config.appId}] download do update falhou: $e');
    }
    notifyListeners();
  }

  void cancelDownload() => _cancel?.cancel();

  /// Windows: fecha o app e o updater troca os arquivos — nao retorna.
  Future<void> install() async {
    final f = _file;
    if (f == null || stage == UpdateStage.installing) return;
    // O app so fecha depois que o updater provar que subiu; ate la a pessoa precisa ver
    // que algo esta acontecendo, senao o clique parece nao ter feito nada.
    stage = UpdateStage.installing;
    bannerDismissed = false;
    error = null;
    notifyListeners();
    try {
      await _u.apply(file: f);
    } catch (e) {
      error = e is UpdateException ? e.message : '$e';
      stage = UpdateStage.error;
      notifyListeners();
    }
  }

  Future<void> skipCurrent() async {
    final v = info?.version;
    if (v != null) {
      await (await SharedPreferences.getInstance()).setString(_kSkipped, v);
    }
    dismissBanner();
  }

  void dismissBanner() {
    bannerDismissed = true;
    notifyListeners();
  }
}
