import 'dart:io';

/// Como a atualizacao chega ao usuario nesta plataforma.
enum UpdateDelivery {
  /// Windows: o app baixa o zip e troca a propria instalacao.
  inAppDownload,

  /// Android: quem baixa e instala e o navegador — ver [DefaltUpdater.apply].
  browserHandoff,

  /// Linux: quem troca os arquivos e o apt, chamado como root pelo polkit.
  packageManager,

  /// Plataforma sem caminho de atualizacao (web, macOS, Linux fora do APT).
  none,
}

/// Que garantia de integridade o manifesto permite exigir do arquivo baixado.
enum IntegrityCheck {
  /// O manifesto trouxe `sha256`: conteudo conferido byte a byte.
  sha256,

  /// So o tamanho: pega truncamento, nao pega troca de conteudo.
  size,

  /// Manifesto sem `size` nem `sha256` — nada a conferir.
  none,
}

/// Release mais nova, ja filtrada pela plataforma atual.
class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.current,
    this.notes = '',
    this.size = 0,
    this.sha256,
  });

  final String version;
  final String current;
  final String notes;

  /// Bytes do asset desta plataforma. 0 = o manifesto nao informou.
  final int size;

  /// Hash do asset desta plataforma, minusculo. null = o manifesto nao informou.
  final String? sha256;

  IntegrityCheck get integrity => sha256 != null && sha256!.isNotEmpty
      ? IntegrityCheck.sha256
      : (size > 0 ? IntegrityCheck.size : IntegrityCheck.none);

  String get sizeLabel => size <= 0 ? '' : '${(size / 1048576).toStringAsFixed(0)} MB';

  /// Le o objeto da plataforma dentro do manifesto (`{version, notes, windows:{...}}`).
  /// Devolve null quando o manifesto nao tem versao ou nao tem asset para [platform].
  static UpdateInfo? fromManifest(
    Map<String, dynamic> json,
    String platform,
    String current,
  ) {
    final version = (json['version'] as String?)?.trim() ?? '';
    final asset = json[platform];
    if (version.isEmpty || asset is! Map) return null;
    final hash = (asset['sha256'] as String?)?.trim().toLowerCase();
    return UpdateInfo(
      version: version,
      current: current,
      notes: (json['notes'] as String?)?.trim() ?? '',
      size: (asset['size'] as num?)?.toInt() ?? 0,
      sha256: (hash == null || hash.isEmpty) ? null : hash,
    );
  }

  @override
  String toString() => 'UpdateInfo($current -> $version, ${size}B, ${integrity.name})';
}

/// Falha de update com mensagem em pt-BR, pronta pra UI mostrar.
class UpdateException implements Exception {
  const UpdateException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// O arquivo baixado nao bateu com o manifesto — instalar isso e pior do que nao atualizar.
class IntegrityException extends UpdateException {
  const IntegrityException(super.message);
}

/// O usuario dispensou o update no meio do download.
class UpdateCancelled extends UpdateException {
  const UpdateCancelled() : super('download cancelado');
}

/// Cancelamento cooperativo do download.
class CancelToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
}

/// Tudo que muda de um app para outro. Sem isso o pacote nao sabe com quem falar.
class UpdaterConfig {
  const UpdaterConfig({
    required this.appId,
    required this.manifestUrl,
    required this.downloadUrl,
    this.displayName,
    this.aptPackage,
    this.aptPackagesUrl = defaultAptPackagesUrl,
    this.platforms = defaultPlatforms,
    this.checkTimeout = const Duration(seconds: 5),
    this.downloadTimeout = const Duration(seconds: 30),
  });

  /// Sem Android de proposito: app que publica na Play Store nao pode se auto-instalar —
  /// a loja atualiza, e um APK lateral colide com o que ela instalou. Quem esta fora da
  /// loja opta por Android explicitamente.
  static const defaultPlatforms = {'windows', 'linux'};

  /// Repositorio APT dos apps do Defalt — a mesma origem para os tres.
  static const defaultAptPackagesUrl =
      'https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages';

  /// Slug do app: nomeia o arquivo baixado, o log do updater e, por padrao, o pacote APT.
  final String appId;

  /// GET que devolve `{version, notes, windows:{size,sha256}, android:{...}, linux:{...}}`.
  final String manifestUrl;

  /// GET que responde o binario (ou 302 pra ele). O pacote acrescenta `?platform=`.
  final String downloadUrl;

  /// Nome exibido na janela do updater do Windows. Sem isso, usa [appId].
  final String? displayName;

  /// Pacote no repositorio APT. Sem isso, usa [appId].
  final String? aptPackage;

  final String aptPackagesUrl;

  /// Plataformas em que ESTE app se atualiza sozinho — ver [defaultPlatforms].
  final Set<String> platforms;

  final Duration checkTimeout;
  final Duration downloadTimeout;

  bool get selfUpdatesHere => platforms.contains(platformKey);

  String get name => displayName ?? appId;
  String get debPackage => aptPackage ?? appId;

  /// Chave da plataforma atual dentro do manifesto e no `?platform=` do download.
  static String get platformKey => Platform.isWindows
      ? 'windows'
      : Platform.isLinux
          ? 'linux'
          : 'android';

  Uri get manifestUri => Uri.parse(manifestUrl);

  Uri get downloadUri {
    final base = Uri.parse(downloadUrl);
    return base.replace(queryParameters: {...base.queryParameters, 'platform': platformKey});
  }
}
