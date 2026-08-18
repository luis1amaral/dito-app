import '../../l10n/app_strings.dart';
import 'dart:io';

import 'package:flutter/material.dart';

import '../../config/config_service.dart';
import '../../core/duration_format.dart';
import '../../library/library_reader.dart';
import '../palette.dart';
import '../tokens.dart';

/// The recordings on disk, newest first.
class SessionsPage extends StatelessWidget {
  const SessionsPage({super.key, required this.library, required this.config});

  final LibraryReader library;
  final ConfigService config;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: library,
        builder: (context, _) {
          if (library.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }
          if (library.sessions.isEmpty) {
            return _Empty(
              folder: config.config.library.resolved(),
              hotkey: config.config.hotkeys.pushToTalk,
            );
          }
          return RefreshIndicator(
            onRefresh: () => library.load(config.config.library.resolved()),
            child: ListView.separated(
              padding: const EdgeInsets.all(AppSpacing.lg),
              itemCount: library.sessions.length,
              separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
              itemBuilder: (context, i) => _SessionTile(ref: library.sessions[i]),
            ),
          );
        },
      );
}

class _Empty extends StatelessWidget {
  const _Empty({required this.folder, required this.hotkey});

  final String folder;
  final String hotkey;

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.mic_none_rounded, size: AppSpacing.huge, color: c.textMuted),
            const SizedBox(height: AppSpacing.md),
            Text(context.strings.historyEmptyTitle,
                style: TextStyle(color: c.textSecondary, fontSize: AppType.title)),
            const SizedBox(height: AppSpacing.xs),
            Text(context.strings.historyEmptySubtitle(hotkey),
                style: TextStyle(color: c.textMuted, fontSize: AppType.body)),
            const SizedBox(height: AppSpacing.lg),
            SelectableText(folder,
                style: TextStyle(color: c.textMuted, fontSize: AppType.caption)),
          ],
        ),
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({required this.ref});

  final SessionRef ref;

  static String _stamp(DateTime when) =>
      '${when.day.toString().padLeft(2, '0')}/'
      '${when.month.toString().padLeft(2, '0')} '
      '${when.hour.toString().padLeft(2, '0')}:'
      '${when.minute.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  ref.isMeeting ? Icons.groups_rounded : Icons.mic_rounded,
                  size: AppSpacing.lg,
                  color: c.textMuted,
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(_stamp(ref.started),
                    style: TextStyle(color: c.textSecondary, fontSize: AppType.caption)),
                const SizedBox(width: AppSpacing.sm),
                Text(formatClock(ref.seconds),
                    style: TextStyle(color: c.textMuted, fontSize: AppType.caption)),
                if (!ref.isDone) ...<Widget>[
                  const SizedBox(width: AppSpacing.sm),
                  Text(ref.state,
                      style: TextStyle(color: c.alert, fontSize: AppType.caption)),
                ],
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.folder_open_rounded, size: AppSpacing.lg),
                  tooltip: context.strings.openFolder,
                  onPressed: () => Process.run('explorer', <String>[ref.folder]),
                ),
              ],
            ),
            if (ref.preview.isNotEmpty) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(ref.preview,
                  style: TextStyle(color: c.textPrimary, fontSize: AppType.body)),
            ],
          ],
        ),
      ),
    );
  }
}
