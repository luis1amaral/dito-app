import 'dart:async';
import 'dart:io';

import 'package:dito_win32/dito_win32.dart';

import '../core/logbook.dart';

/// Desktop alerts (balloon + alarm sound); capture itself lives in the engine, not here.
abstract class AlertService {
  void notify({required String title, required String body});
  void playAlarm();
}

/// Picks the platform implementation; Linux only logs until the native alerts land.
AlertService createAlertService({Logbook? log}) =>
    Platform.isWindows ? const WindowsAlertService() : LinuxAlertService(log: log);

class WindowsAlertService implements AlertService {
  const WindowsAlertService();

  @override
  void notify({required String title, required String body}) =>
      unawaited(DitoWin32.notifyBalloon(title: title, body: body));

  @override
  void playAlarm() => unawaited(DitoWin32.playAlarmSound());
}

class LinuxAlertService implements AlertService {
  LinuxAlertService({Logbook? log}) : _log = log ?? Logbook('alerts');

  final Logbook _log;

  @override
  void notify({required String title, required String body}) =>
      _log('notificacao no Linux ainda nao implementada: $title');

  @override
  void playAlarm() => _log('som de alarme no Linux ainda nao implementado');
}
