import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_strings.dart';
import '../palette.dart';
import '../tokens.dart';

class UpdateBanner extends StatelessWidget {
  const UpdateBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<UpdateController>();
    final info = c.info;
    if (!c.showBanner || info == null) return const SizedBox.shrink();

    final colors = context.appColors;
    final strings = context.strings;
    final downloading = c.stage == UpdateStage.downloading;
    final installing = c.stage == UpdateStage.installing;
    final failed = c.stage == UpdateStage.error;
    final ready = c.stage == UpdateStage.ready;
    final busy = downloading || installing;

    final label = switch (c.stage) {
      UpdateStage.downloading => '${strings.downloadingUpdate} (${(c.progress * 100).round()}%)...',
      UpdateStage.installing => strings.installingUpdate,
      UpdateStage.ready => '${strings.updateReady}${info.version}',
      UpdateStage.error => c.error ?? 'Error',
      _ => '${strings.updateAvailable}${info.version}',
    };
    final size = info.sizeLabel;

    return Material(
      color: colors.surfaceAlt,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.sm,
            ),
            child: Row(
              children: [
                Icon(
                  failed ? Icons.error_outline_rounded : Icons.system_update_rounded,
                  size: 18,
                  color: failed ? colors.danger : colors.primary,
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: InkWell(
                    onTap: busy ? null : () => showUpdateDialog(context, c),
                    child: Text(
                      size.isEmpty || busy || failed ? label : '$label | $size',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
                if (!busy && !failed)
                  FilledButton(
                    onPressed: ready ? c.install : c.startDownload,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 0),
                      minimumSize: const Size(60, 32),
                    ),
                    child: Text(ready ? strings.btnInstall : strings.btnDownload),
                  ),
                if (!installing)
                  IconButton(
                    tooltip: downloading ? strings.btnLater : strings.btnSkip,
                    icon: Icon(Icons.close_rounded, size: 18, color: colors.textSecondary),
                    onPressed: downloading ? c.cancelDownload : c.dismissBanner,
                  ),
              ],
            ),
          ),
          if (busy)
            LinearProgressIndicator(
              value: downloading && c.progress > 0 ? c.progress : null,
              minHeight: 2,
              backgroundColor: colors.border,
              color: colors.primary,
            ),
        ],
      ),
    );
  }
}

Future<void> showUpdateDialog(BuildContext context, UpdateController c) async {
  final info = c.info;
  if (info == null) return;
  final colors = context.appColors;
  final strings = context.strings;
  final size = info.sizeLabel;

  await showDialog<void>(
    context: context,
    builder: (ctx) {
      return AlertDialog(
        backgroundColor: colors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.card)),
        title: Row(
          children: [
            Icon(Icons.system_update_rounded, color: colors.primary),
            const SizedBox(width: AppSpacing.md),
            Expanded(child: Text('${strings.appTitle} v${info.version}')),
          ],
        ),
        content: SizedBox(
          width: 440,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                size.isEmpty
                    ? '${strings.installedVersion.split(':').first}: ${info.current}'
                    : '${strings.installedVersion.split(':').first}: ${info.current} | $size',
                style: Theme.of(ctx).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              ),
              if (info.notes.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.lg),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 240),
                  child: SingleChildScrollView(
                    child: Text(info.notes, style: Theme.of(ctx).textTheme.bodyMedium),
                  ),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              c.skipCurrent();
              Navigator.pop(ctx);
            },
            child: Text(strings.btnSkip, style: TextStyle(color: colors.textSecondary)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(strings.btnLater),
          ),
          FilledButton.icon(
            onPressed: () {
              Navigator.pop(ctx);
              c.startDownload();
            },
            icon: Icon(c.downloadsInApp ? Icons.download_rounded : Icons.system_update_rounded,
                size: 18),
            label: Text(c.downloadsInApp ? strings.btnDownloadNow : strings.btnInstall),
          ),
        ],
      );
    },
  );
}
