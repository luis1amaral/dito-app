import 'dart:async';

import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import '../../l10n/app_strings.dart';

import '../../app/boot.dart';
import '../../engine/engine_health.dart';
import '../../engine/engine_protocol.dart';
import '../../state/app_snapshot.dart';
import '../palette.dart';
import '../theme.dart';
import '../tokens.dart';
import 'sessions_page.dart';
import 'settings_page.dart';

class DitoMainApp extends StatelessWidget {
  const DitoMainApp({super.key, required this.app});

  final DitoApp app;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: app.config,
        builder: (_, _) => MaterialApp(
          title: 'Dito',
          debugShowCheckedModeBanner: false,
          theme: appTheme(Brightness.light),
          darkTheme: appTheme(Brightness.dark),
          themeMode: themeModeFrom(app.config.config.ui.theme),
          localizationsDelegates: AppStrings.localizationsDelegates,
          supportedLocales: AppStrings.supportedLocales,
          // null follows the system, which is what 'auto' means.
          locale: localeFromCode(app.config.config.ui.language),
          home: MainWindow(app: app),
        ),
      );
}

class MainWindow extends StatefulWidget {
  const MainWindow({super.key, required this.app});

  final DitoApp app;

  @override
  State<MainWindow> createState() => _MainWindowState();
}

class _MainWindowState extends State<MainWindow> with WindowListener {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    super.dispose();
  }

  /// Closing hides: quitting is an explicit choice in the tray.
  @override
  void onWindowClose() => unawaited(windowManager.hide());

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: AppSpacing.xxl,
              height: AppSpacing.xxl,
              decoration: BoxDecoration(
                color: colors.primary,
                borderRadius: BorderRadius.circular(AppRadius.control),
              ),
              child: Icon(Icons.graphic_eq_rounded,
                  color: colors.textInverse, size: AppSpacing.lg),
            ),
            const SizedBox(width: AppSpacing.md),
            Text(context.strings.appTitle),
          ],
        ),
      ),
      body: ValueListenableBuilder<bool>(
        valueListenable: widget.app.isReady,
        builder: (context, ready, _) => ready
            ? _content()
            : const Center(child: _Booting()),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: const <NavigationDestination>[
          NavigationDestination(icon: Icon(Icons.history_rounded), label: 'Histórico'),
          NavigationDestination(icon: Icon(Icons.settings_rounded), label: 'Ajustes'),
        ],
      ),
    );
  }

  Widget _content() {
    return Column(
        children: [
          ValueListenableBuilder<AppSnapshot>(
            valueListenable: widget.app.controller.snapshot,
            builder: (_, snapshot, _) => _Warnings(snapshot: snapshot),
          ),
          Expanded(
            child: IndexedStack(
              index: _tab,
              children: <Widget>[
                SessionsPage(library: widget.app.library, config: widget.app.config),
                SettingsPage(app: widget.app),
              ],
            ),
          ),
        ],
      );
  }
}

class _Booting extends StatelessWidget {
  const _Booting();

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const CircularProgressIndicator(),
          const SizedBox(height: AppSpacing.md),
          Text(context.strings.booting),
        ],
      );
}

/// Says out loud when the app cannot do its job; the old port failed silently here.
class _Warnings extends StatelessWidget {
  const _Warnings({required this.snapshot});

  final AppSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final s = context.strings;
    final messages = <String>[
      if (!snapshot.hookInstalled) s.warnKeysFailed,
      if (snapshot.engine.state == EngineState.dead)
        s.warnEngineDown(snapshot.engine.reason ?? s.warnUnknownReason),
      if (snapshot.alarm == AudioState.dead)
        s.warnNoAudio(snapshot.alarmReason ?? s.notifyNoAudio),
    ];
    if (messages.isEmpty) return const SizedBox.shrink();

    final c = context.appColors;
    return Container(
      width: double.infinity,
      color: c.danger.withValues(alpha: 0.12),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final message in messages)
            Text(message, style: TextStyle(color: c.danger, fontSize: AppType.caption)),
        ],
      ),
    );
  }
}
