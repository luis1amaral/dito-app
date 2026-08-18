import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../app/boot.dart';
import '../../config/config_model.dart';
import '../../l10n/app_strings.dart';
import 'key_capture_field.dart';
import '../palette.dart';
import '../tokens.dart';
import '../widgets/update_banner.dart';

/// Every setting applies and persists on change; there is no Save button on purpose.
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key, required this.app});

  final DitoApp app;

  Future<void> _update(AppConfig next) async {
    await app.config.update(next);
    // Rebinding is live: the gap between changing a shortcut and it working must be zero.
    await app.hotkeys.apply(next.hotkeys);
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: app.config,
        builder: (context, _) {
          final cfg = app.config.config;
          final s = context.strings;
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            children: <Widget>[
              _Section(title: s.sectionUpdates, children: <Widget>[
                ListTile(
                  title: Text(s.installedVersion),
                  subtitle: FutureBuilder<PackageInfo>(
                    future: PackageInfo.fromPlatform(),
                    builder: (context, snapshot) {
                      final version = snapshot.data?.version ?? '';
                      return Text(version.isEmpty ? '...' : 'v$version');
                    },
                  ),
                  trailing: ListenableBuilder(
                    listenable: app.updateController,
                    builder: (context, _) {
                      final isBusy = app.updateController.isBusy;
                      return FilledButton.icon(
                        onPressed: isBusy
                            ? null
                            : () async {
                                final info = await app.updateController.checkManual();
                                if (!context.mounted) return;
                                if (info != null) {
                                  await showUpdateDialog(context, app.updateController);
                                } else if (app.updateController.error != null) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text('Falha ao verificar atualizações: ${app.updateController.error}'),
                                    ),
                                  );
                                } else {
                                  final v = app.updateController.currentVersion;
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text('Você já está usando a versão mais recente${v.isEmpty ? "" : " (v$v)"}.'),
                                      duration: const Duration(seconds: 3),
                                    ),
                                  );
                                }
                              },
                        icon: isBusy
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.system_update_rounded, size: 16),
                        label: Text(isBusy ? s.booting : s.btnCheckUpdates),
                      );
                    },
                  ),
                ),
              ]),
              _Section(title: s.sectionHotkeys, children: <Widget>[
                KeyCaptureField(
                  label: s.hotkeyDictation,
                  value: cfg.hotkeys.pushToTalk,
                  conflictFor: (key) => key == cfg.hotkeys.meetingToggle ? s.keyConflictOther : null,
                  onCaptureStart: app.hotkeys.pause,
                  onCaptureEnd: app.hotkeys.resume,
                  onChanged: (key) => _update(
                      cfg.copyWith(hotkeys: cfg.hotkeys.copyWith(pushToTalk: key))),
                ),
                KeyCaptureField(
                  label: s.hotkeyMeeting,
                  value: cfg.hotkeys.meetingToggle,
                  conflictFor: (key) => key == cfg.hotkeys.pushToTalk ? s.keyConflictOther : null,
                  onCaptureStart: app.hotkeys.pause,
                  onCaptureEnd: app.hotkeys.resume,
                  onChanged: (key) => _update(
                      cfg.copyWith(hotkeys: cfg.hotkeys.copyWith(meetingToggle: key))),
                ),
              ]),
              _Section(title: s.sectionOutput, children: <Widget>[
                SwitchListTile(
                  title: Text(s.reviewBeforePasteTitle),
                  subtitle: Text(s.reviewBeforePasteSubtitle),
                  value: cfg.output.confirm,
                  onChanged: (v) =>
                      _update(cfg.copyWith(output: cfg.output.copyWith(confirm: v))),
                ),
                SwitchListTile(
                  title: Text(s.autoPasteTitle),
                  value: cfg.output.paste,
                  onChanged: (v) =>
                      _update(cfg.copyWith(output: cfg.output.copyWith(paste: v))),
                ),
                SwitchListTile(
                  title: Text(s.pressEnterTitle),
                  value: cfg.output.enter,
                  onChanged: (v) =>
                      _update(cfg.copyWith(output: cfg.output.copyWith(enter: v))),
                ),
                SwitchListTile(
                  title: Text(s.restoreClipboardTitle),
                  value: cfg.output.restoreClipboard,
                  onChanged: (v) => _update(
                      cfg.copyWith(output: cfg.output.copyWith(restoreClipboard: v))),
                ),
              ]),
              _Section(title: s.sectionAlerts, children: <Widget>[
                SwitchListTile(
                  title: Text(s.muteAlertTitle),
                  value: cfg.audio.alerts.sound,
                  onChanged: (v) => _update(cfg.copyWith(
                      audio: cfg.audio
                          .copyWith(alerts: cfg.audio.alerts.copyWith(sound: v)))),
                ),
                SwitchListTile(
                  title: Text(s.notifyAlertTitle),
                  value: cfg.audio.alerts.notify,
                  onChanged: (v) => _update(cfg.copyWith(
                      audio: cfg.audio
                          .copyWith(alerts: cfg.audio.alerts.copyWith(notify: v)))),
                ),
              ]),
              _Section(title: s.sectionTranscription, children: <Widget>[
                _Options(
                  label: s.sectionModel,
                  hint: s.modelHint,
                  value: cfg.stt.model,
                  options: <String, String>{
                    'tiny': s.optModelTinyName,
                    'base': s.optModelBaseName,
                    'small': s.optModelSmallName,
                    'medium': s.optModelMediumName,
                    'large-v3': s.optModelLargeName,
                  },
                  onChanged: (v) =>
                      _update(cfg.copyWith(stt: cfg.stt.copyWith(model: v))),
                ),
                _Options(
                  label: s.transcriptionLanguage,
                  value: cfg.stt.language,
                  options: <String, String>{
                    'pt': s.optLangPt,
                    'en': s.optLangEn,
                    'es': s.optLangEs,
                  },
                  onChanged: (v) =>
                      _update(cfg.copyWith(stt: cfg.stt.copyWith(language: v))),
                ),
                _Options(
                  label: s.deviceLabel,
                  hint: s.deviceHint,
                  value: cfg.stt.device,
                  options: <String, String>{
                    'auto': s.optDeviceAuto,
                    'cpu': s.optDeviceCpu,
                    'cuda': s.optDeviceCuda,
                  },
                  onChanged: (v) =>
                      _update(cfg.copyWith(stt: cfg.stt.copyWith(device: v))),
                ),
              ]),
              _Section(title: s.sectionInterface, children: <Widget>[
                _Options(
                  label: s.interfaceLanguage,
                  value: cfg.ui.language,
                  options: <String, String>{
                    'auto': s.themeFollowSystem,
                    'pt_BR': s.langPt,
                    'en': s.langEn,
                  },
                  onChanged: (v) =>
                      _update(cfg.copyWith(ui: cfg.ui.copyWith(language: v))),
                ),
                _Options(
                  label: s.interfaceTheme,
                  value: cfg.ui.theme,
                  options: <String, String>{
                    'auto': s.themeFollowSystem,
                    'light': s.themeLight,
                    'dark': s.themeDark,
                  },
                  onChanged: (v) => _update(cfg.copyWith(ui: cfg.ui.copyWith(theme: v))),
                ),
              ]),
              _Section(title: s.sectionLibrary, children: <Widget>[
                ListTile(
                  title: Text(s.libraryFolder),
                  subtitle: SelectableText(cfg.library.resolved()),
                ),
                ListTile(
                  title: Text(s.libraryKeep),
                  trailing: Text(s.libraryKeepDays(cfg.library.keepDays)),
                ),
              ]),
            ],
          );
        },
      );
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.only(
              top: AppSpacing.lg, bottom: AppSpacing.sm, left: AppSpacing.sm),
          child: Text(
            title,
            style: TextStyle(
              color: c.textMuted,
              fontSize: AppType.caption,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Card(child: Column(children: children)),
      ],
    );
  }
}

/// Every choice is visible at once: no dropdown to open, nothing hidden behind a click.
class _Options extends StatelessWidget {
  const _Options({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
    this.hint,
  });

  final String label;
  final String value;
  final Map<String, String> options;
  final void Function(String) onChanged;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final selected = options.containsKey(value) ? value : options.keys.first;

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(label, style: TextStyle(fontSize: AppType.body, color: c.textPrimary)),
          if (hint != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(hint!,
                style: TextStyle(fontSize: AppType.caption, color: c.textMuted)),
          ],
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: <Widget>[
              for (final entry in options.entries)
                _Chip(
                  label: entry.value,
                  selected: entry.key == selected,
                  onTap: () => onChanged(entry.key),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final void Function() onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    return Material(
      color: selected ? c.primary : c.surfaceAlt,
      borderRadius: BorderRadius.circular(AppRadius.pill),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.pill),
        child: Container(
          constraints: const BoxConstraints(minHeight: AppSize.control),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppType.body,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              color: selected ? c.textInverse : c.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}
