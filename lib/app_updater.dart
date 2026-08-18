import 'package:defalt_updater/defalt_updater.dart';

import '../api/api_config.dart';

export 'package:defalt_updater/defalt_updater.dart'
    show DefaltUpdater, UpdateController, UpdateDelivery, UpdateInfo, UpdateMode, UpdateStage;

const String kUpdateManifestPath = '/api/app/latest';
const String kUpdateDownloadPath = '/api/app/download';

UpdaterConfig ditoUpdaterConfig() => UpdaterConfig(
      appId: 'dito',
      displayName: 'Dito',
      manifestUrl: '${ApiConfig.baseUrl}$kUpdateManifestPath',
      downloadUrl: '${ApiConfig.baseUrl}$kUpdateDownloadPath',
    );

DefaltUpdater buildDitoUpdater() => DefaltUpdater(config: ditoUpdaterConfig());
