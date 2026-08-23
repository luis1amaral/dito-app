import 'dart:io';

/// How the update reaches the user on this platform.
enum UpdateDelivery {
  /// Windows: the app downloads the zip and replaces its own install.
  inAppDownload,

  /// Android: the browser downloads and installs it; see [DefaltUpdater.apply].
  browserHandoff,

  /// Linux: apt replaces the files, invoked as root via polkit.
  packageManager,

  /// Platform with no update path (web, macOS, Linux outside APT).
  none,
}

/// What integrity guarantee the manifest lets the package require from the downloaded file.
enum IntegrityCheck {
  /// The manifest carried `sha256`: content checked byte for byte.
  sha256,

  /// Size only: catches truncation, not content swaps.
  size,

  /// Manifest with neither `size` nor `sha256` — nothing to check.
  none,
}

/// Newest release, already filtered to the current platform.
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

  /// Bytes of this platform's asset; 0 means the manifest did not report it.
  final int size;

  /// Hash of this platform's asset, lowercase; null means the manifest did not report it.
  final String? sha256;

  IntegrityCheck get integrity => sha256 != null && sha256!.isNotEmpty
      ? IntegrityCheck.sha256
      : (size > 0 ? IntegrityCheck.size : IntegrityCheck.none);

  String get sizeLabel => size <= 0 ? '' : '${(size / 1048576).toStringAsFixed(0)} MB';

  /// Reads the platform object inside the manifest; returns null with no version or no asset for [platform].
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

/// Update failure with a pt-BR message, ready for the UI to show.
class UpdateException implements Exception {
  const UpdateException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// The downloaded file did not match the manifest; installing it is worse than not updating.
class IntegrityException extends UpdateException {
  const IntegrityException(super.message);
}

/// The user dismissed the update mid-download.
class UpdateCancelled extends UpdateException {
  const UpdateCancelled() : super('download cancelado');
}

/// Cooperative cancellation for the download.
class CancelToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
}

/// Everything that changes from one app to another; without it the package cannot know who to talk to.
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

  /// No Android on purpose: a Play Store app cannot self-install, or a sideloaded APK collides with the store's own install.
  static const defaultPlatforms = {'windows', 'linux'};

  /// APT repository for the Defalt apps — the same origin for all three.
  static const defaultAptPackagesUrl =
      'https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages';

  /// App slug: names the downloaded file, the updater log and, by default, the APT package.
  final String appId;

  /// GET returning `{version, notes, windows:{size,sha256}, android:{...}, linux:{...}}`.
  final String manifestUrl;

  /// GET that serves the binary (or a 302 to it); the package appends `?platform=`.
  final String downloadUrl;

  /// Name shown in the Windows updater window; falls back to [appId].
  final String? displayName;

  /// Package name in the APT repository; falls back to [appId].
  final String? aptPackage;

  final String aptPackagesUrl;

  /// Platforms where THIS app updates itself — see [defaultPlatforms].
  final Set<String> platforms;

  final Duration checkTimeout;
  final Duration downloadTimeout;

  bool get selfUpdatesHere => platforms.contains(platformKey);

  String get name => displayName ?? appId;
  String get debPackage => aptPackage ?? appId;

  /// Current platform's key inside the manifest and in the download's `?platform=`.
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
