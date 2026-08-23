import 'dart:async';

import 'package:dito_win32/dito_win32.dart';

import '../core/logbook.dart';

/// Desktop alerts (balloon + alarm sound); capture itself lives in the engine, not here.
abstract class AlertService {
  void notify({required String title, required String body});
  void playAlarm();
}

/// DitoWin32 already abstracts the platform (Win32 balloon/PlaySound vs notify-send/canberra-gtk-play), so one impl suffices.
AlertService createAlertService({Logbook? log}) => NativeAlertService(log: log);

class NativeAlertService implements AlertService {
  NativeAlertService({Logbook? log}) : _log = log ?? Logbook('alerts');

  final Logbook _log;

  @override
  void notify({required String title, required String body}) => unawaited(
      DitoWin32.notifyBalloon(title: title, body: body)
          .then((ok) => ok ? null : _log('notificacao falhou: $title')));

  @override
  void playAlarm() => unawaited(
      DitoWin32.playAlarmSound().then((ok) => ok ? null : _log('som de alarme falhou')));
}
