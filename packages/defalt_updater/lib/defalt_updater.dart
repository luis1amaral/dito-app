/// Auto-update fora das lojas para os apps Flutter do Defalt. Sem UI.
library;

export 'src/linux_apt.dart' show LinuxApt;
export 'src/models.dart';
export 'src/update_controller.dart';
export 'src/updater.dart' show DefaltUpdater, UrlOpener, WorkDirResolver;
export 'src/version.dart' show compareVersions;
export 'src/windows_installer.dart' show WindowsInstaller;
