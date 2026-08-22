// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_strings.g.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppStringsEn extends AppStrings {
  AppStringsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Dito';

  @override
  String get tabHistory => 'History';

  @override
  String get tabSettings => 'Settings';

  @override
  String get statusReady => 'Ready';

  @override
  String get historyEmptyTitle => 'No recent recordings';

  @override
  String historyEmptySubtitle(String hotkey) {
    return 'Use the buttons above or hold $hotkey to dictate.';
  }

  @override
  String get dictationLabel => 'Dictation';

  @override
  String get meetingLabel => 'Meeting';

  @override
  String get sectionModel => 'Voice Model (Whisper)';

  @override
  String get transcriptionLanguage => 'Transcription Spoken Language';

  @override
  String get optLangPt => 'Portuguese (Brazil)';

  @override
  String get optLangEn => 'English';

  @override
  String get optLangEs => 'Spanish';

  @override
  String get optDeviceAuto => 'Automatic (GPU if available, else CPU)';

  @override
  String get optDeviceCuda => 'NVIDIA GPU (CUDA)';

  @override
  String get optDeviceCpu => 'Processor (CPU)';

  @override
  String get muteAlertTitle => 'Mute / No Audio Warning';

  @override
  String get sectionHotkeys => 'Global Hotkeys';

  @override
  String get hotkeyDictation => 'Push-to-Talk (Hold)';

  @override
  String get hotkeyMeeting => 'Meeting Mode (Toggle)';

  @override
  String get sectionOutput => 'Output Behavior';

  @override
  String get autoPasteTitle => 'Auto-paste';

  @override
  String get pressEnterTitle => 'Press Enter after paste';

  @override
  String get reviewBeforePasteTitle => 'Review before paste';

  @override
  String get reviewBeforePasteSubtitle =>
      'Opens a window to edit transcript before pasting.';

  @override
  String get sectionInterface => 'Interface & Language';

  @override
  String get interfaceTheme => 'Theme';

  @override
  String get themeLight => 'Light';

  @override
  String get themeDark => 'Dark';

  @override
  String get interfaceLanguage => 'App Language';

  @override
  String get langPt => 'Português (Brasil)';

  @override
  String get langEn => 'English';

  @override
  String get sectionUpdates => 'Updates & About';

  @override
  String get installedVersion => 'Installed version';

  @override
  String get btnCheckUpdates => 'Check now';

  @override
  String get upToDateMessage => 'You are using the latest version.';

  @override
  String get updateAvailable => 'New version available: v';

  @override
  String get updateReady => 'Update ready: v';

  @override
  String get downloadingUpdate => 'Downloading update';

  @override
  String get installingUpdate => 'Installing update...';

  @override
  String get btnDownload => 'Download';

  @override
  String get btnInstall => 'Install';

  @override
  String get btnSkip => 'Skip version';

  @override
  String get btnLater => 'Later';

  @override
  String get btnDownloadNow => 'Download now';

  @override
  String get btnDiscard => 'Discard';

  @override
  String get trayOpen => 'Open Dito';

  @override
  String get trayCopyLast => 'Copy last text';

  @override
  String get trayPause => 'Pause dictation';

  @override
  String get trayQuit => 'Quit Dito';

  @override
  String get hudRecording => 'Recording';

  @override
  String get hudQuiet => 'Audio too low';

  @override
  String get hudNoAudio => 'NO AUDIO';

  @override
  String get hudStarting => 'Starting...';

  @override
  String get hudTranscribing => 'Transcribing...';

  @override
  String get hudSaving => 'Saving the recording...';

  @override
  String get hudStop => 'Stop';

  @override
  String get hudFix => 'Fix';

  @override
  String get toastEngineStarting => 'The engine is still starting';

  @override
  String get toastEngineUnreachable => 'Could not reach the engine';

  @override
  String get toastRecordingEnded => 'Recording ended';

  @override
  String get toastRecordingEndedWhy => 'The key was held down for 10 minutes.';

  @override
  String get toastFailed => 'It did not work';

  @override
  String get toastPasteFailed => 'Could not paste';

  @override
  String get toastDiscarded => 'Discarded';

  @override
  String get toastCopied => 'Copied';

  @override
  String get toastPasted => 'Text pasted';

  @override
  String get reviewHintSend => 'Enter sends';

  @override
  String get reviewHintDiscard => 'Tab discards';

  @override
  String get reviewObsidianLabel => 'Obsidian';

  @override
  String hudMinutesDone(int minutes) {
    return '$minutes min transcribed';
  }

  @override
  String get sectionAlerts => 'Alerts';

  @override
  String get sectionLibrary => 'Library';

  @override
  String get sectionTranscription => 'Transcription';

  @override
  String get restoreClipboardTitle => 'Give the clipboard back';

  @override
  String get notifyAlertTitle => 'Notification';

  @override
  String get libraryFolder => 'Recordings folder';

  @override
  String get libraryKeep => 'Keep for';

  @override
  String get modelHint => 'Bigger transcribes better and takes longer.';

  @override
  String get deviceLabel => 'Processing';

  @override
  String get deviceHint =>
      'An NVIDIA graphics card transcribes about 3x faster.';

  @override
  String get optModelTinyName => 'Minimum';

  @override
  String get optModelBaseName => 'Basic';

  @override
  String get optModelSmallName => 'Balanced';

  @override
  String get optModelMediumName => 'Good';

  @override
  String get optModelLargeName => 'Best';

  @override
  String get keyCaptureHint => 'Press the key you want | Esc cancels';

  @override
  String get keyConflictOther => 'the other shortcut';

  @override
  String get booting => 'Starting...';

  @override
  String get themeFollowSystem => 'Follow the system';

  @override
  String libraryKeepDays(int days) {
    return '$days days';
  }

  @override
  String get trayTipRecording => 'Recording - release to transcribe';

  @override
  String get trayTipMeeting => 'Recording - press again to stop';

  @override
  String get trayTipNoAudio => 'No audio - check the microphone';

  @override
  String get trayTipPaused => 'Dictation paused';

  @override
  String get notifyEngineDied => 'Dito - the engine crashed';

  @override
  String get notifyEngineDiedWhy => 'The audio is safe in the session folder.';

  @override
  String get notifyNoAudio => 'the microphone stopped picking up';

  @override
  String get keyErrorTypes => 'That key types - pick one that does not.';

  @override
  String get warnKeysFailed =>
      'Could not register the shortcuts: they will not work.';

  @override
  String get warnUnknownReason => 'reason unknown';

  @override
  String get openFolder => 'Open the folder';

  @override
  String get toastPasteToClipboard =>
      'Could not paste - the text is on the clipboard';

  @override
  String get toastPasteToFolder =>
      'Could not paste or copy - the text is in the session folder';

  @override
  String trayTipReady(String hotkey) {
    return 'Ready - hold $hotkey to dictate';
  }

  @override
  String keyErrorTaken(String other) {
    return 'That key already belongs to $other.';
  }

  @override
  String warnEngineDown(String reason) {
    return 'The transcription engine stopped: $reason.';
  }

  @override
  String warnNoAudio(String reason) {
    return 'No audio: $reason.';
  }

  @override
  String get toastStillBusy => 'Still finishing the previous one';

  @override
  String get errMicUnavailable => 'Could not access the microphone';

  @override
  String errModelLoadFailed(String detail) {
    return 'Failed to load the model: $detail';
  }

  @override
  String get errEngineDiedRecording =>
      'the engine crashed during the recording';

  @override
  String get errEngineDiedIdle => 'the engine stopped responding';

  @override
  String errEngineStartFailed(String detail) {
    return 'failed to start the native engine: $detail';
  }

  @override
  String errKeyTaken(Object key, Object action) {
    return 'The $key key is held by another program: $action does not respond';
  }

  @override
  String errKeyBack(Object key, Object action) {
    return 'Key $key released: $action works again';
  }

  @override
  String get toastNoVoiceHeard => 'The microphone did not pick up your voice';

  @override
  String get toastNoVoiceHeardWhy =>
      'Only background noise arrived: check the headset and try again';

  @override
  String get errEngineNoResponse => 'the engine did not respond';

  @override
  String get errTranscribeNoResponse => 'the transcription did not respond';

  @override
  String errCheckUpdatesFailed(String detail) {
    return 'Failed to check for updates: $detail';
  }

  @override
  String upToDateMessageVersion(String version) {
    return 'You are already using the latest version (v$version).';
  }
}
