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
      color: colors.hudSurface,
      shape: Border(
        bottom: BorderSide(
          color: colors.border.withValues(alpha: 0.4),
          width: AppSize.hairline,
        ),
      ),
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
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: failed
                        ? colors.danger.withValues(alpha: 0.15)
                        : colors.primary.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(AppRadius.control),
                  ),
                  child: Icon(
                    failed ? Icons.error_outline_rounded : Icons.system_update_rounded,
                    size: 16,
                    color: failed ? colors.danger : colors.primary,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: InkWell(
                    onTap: busy ? null : () => showUpdateDialog(context, c),
                    borderRadius: BorderRadius.circular(AppRadius.control),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                      child: Text(
                        size.isEmpty || busy || failed ? label : '$label | $size',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: colors.textPrimary,
                            ),
                      ),
                    ),
                  ),
                ),
                if (!busy && !failed) ...[
                  const SizedBox(width: AppSpacing.sm),
                  FilledButton(
                    onPressed: ready ? c.install : c.startDownload,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.only(
                          left: AppSpacing.md, right: AppSpacing.md),
                      minimumSize: const Size(60, 32),
                      backgroundColor: colors.primary,
                      foregroundColor: colors.textInverse,
                    ),
                    child: Text(ready ? strings.btnInstall : strings.btnDownload),
                  ),
                ],
                if (!installing)
                  IconButton(
                    tooltip: downloading ? strings.btnLater : strings.btnSkip,
                    icon: Icon(Icons.close_rounded,
                        size: 18, color: colors.textSecondary),
                    onPressed: downloading ? c.cancelDownload : c.dismissBanner,
                  ),
              ],
            ),
          ),
          if (busy)
            LinearProgressIndicator(
              value: downloading && c.progress > 0 ? c.progress : null,
              minHeight: 2,
              backgroundColor: colors.hudWash,
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

  await showDialog<void>(
    context: context,
    builder: (ctx) => _UpdateDialogContent(controller: c),
  );
}

class _UpdateDialogContent extends StatelessWidget {
  const _UpdateDialogContent({required this.controller});

  final UpdateController controller;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (ctx, _) {
        final c = controller;
        final info = c.info;
        if (info == null) return const SizedBox.shrink();

        final colors = ctx.appColors;
        final strings = ctx.strings;
        final size = info.sizeLabel;

        final downloading = c.stage == UpdateStage.downloading;
        final installing = c.stage == UpdateStage.installing;
        final ready = c.stage == UpdateStage.ready;
        final failed = c.stage == UpdateStage.error;

        return AlertDialog(
          backgroundColor: colors.hudSurface,
          surfaceTintColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.overlay),
            side: BorderSide(
              color: colors.border.withValues(alpha: 0.35),
              width: AppSize.hairline,
            ),
          ),
          contentPadding: const EdgeInsets.fromLTRB(
              AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.md),
          title: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: colors.primary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(AppRadius.card),
                ),
                child: Icon(Icons.system_update_rounded,
                    color: colors.primary, size: 20),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${strings.appTitle} v${info.version}',
                      style: Theme.of(ctx).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w700,
                            color: colors.textPrimary,
                          ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      size.isEmpty
                          ? '${strings.installedVersion}: v${info.current}'
                          : '${strings.installedVersion}: v${info.current} | $size',
                      style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                            color: colors.textMuted,
                          ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          content: SizedBox(
            width: 460,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (info.notes.isNotEmpty) ...[
                  Container(
                    decoration: BoxDecoration(
                      color: colors.hudField,
                      borderRadius: BorderRadius.circular(AppRadius.card),
                      border: Border.all(
                        color: colors.border.withValues(alpha: 0.25),
                        width: AppSize.hairline,
                      ),
                    ),
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 220),
                      child: SingleChildScrollView(
                        child: Text(
                          info.notes,
                          style: Theme.of(ctx).textTheme.bodyMedium?.copyWith(
                                color: colors.textSecondary,
                                height: 1.45,
                              ),
                        ),
                      ),
                    ),
                  ),
                ],
                if (downloading || installing || failed) ...[
                  const SizedBox(height: AppSpacing.lg),
                  if (downloading) ...[
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          strings.downloadingUpdate,
                          style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                                color: colors.textSecondary,
                                fontWeight: FontWeight.w500,
                              ),
                        ),
                        Text(
                          '${(c.progress * 100).round()}%',
                          style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                                color: colors.primary,
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    ClipRRect(
                      // Radius bigger than half the bar height still renders fully rounded caps.
                      borderRadius: BorderRadius.circular(AppRadius.pill),
                      child: LinearProgressIndicator(
                        value: c.progress > 0 ? c.progress : null,
                        minHeight: 6,
                        backgroundColor: colors.hudWash,
                        color: colors.primary,
                      ),
                    ),
                  ] else if (installing) ...[
                    Row(
                      children: [
                        const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Text(
                          strings.installingUpdate,
                          style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                                color: colors.textSecondary,
                              ),
                        ),
                      ],
                    ),
                  ] else if (failed) ...[
                    Text(
                      c.error ?? 'Erro ao atualizar',
                      style: Theme.of(ctx).textTheme.bodySmall?.copyWith(
                            color: colors.danger,
                          ),
                    ),
                  ],
                ],
              ],
            ),
          ),
          actionsPadding: const EdgeInsets.only(
              left: AppSpacing.xl, right: AppSpacing.xl, bottom: AppSpacing.lg),
          actions: [
            if (!downloading && !installing) ...[
              TextButton(
                onPressed: () {
                  c.skipCurrent();
                  Navigator.pop(ctx);
                },
                child: Text(strings.btnSkip,
                    style: TextStyle(color: colors.textMuted)),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: Text(strings.btnLater,
                    style: TextStyle(color: colors.textSecondary)),
              ),
            ],
            if (downloading) ...[
              TextButton(
                onPressed: () {
                  c.cancelDownload();
                },
                child: Text(strings.btnDiscard,
                    style: TextStyle(color: colors.danger)),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: Text(strings.btnLater,
                    style: TextStyle(color: colors.textSecondary)),
              ),
            ],
            if (!downloading && !installing)
              FilledButton.icon(
                onPressed: () {
                  if (ready) {
                    c.install();
                  } else {
                    c.startDownload();
                  }
                },
                style: FilledButton.styleFrom(
                  backgroundColor: colors.primary,
                  foregroundColor: colors.textInverse,
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
                ),
                icon: Icon(
                  ready
                      ? Icons.restart_alt_rounded
                      : (c.downloadsInApp
                          ? Icons.download_rounded
                          : Icons.system_update_rounded),
                  size: 18,
                ),
                label: Text(ready
                    ? strings.btnInstall
                    : (c.downloadsInApp
                        ? strings.btnDownloadNow
                        : strings.btnInstall)),
              ),
          ],
        );
      },
    );
  }
}
