import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_strings_en.g.dart';
import 'app_strings_pt.g.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppStrings
/// returned by `AppStrings.of(context)`.
///
/// Applications need to include `AppStrings.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_strings.g.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppStrings.localizationsDelegates,
///   supportedLocales: AppStrings.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppStrings.supportedLocales
/// property.
abstract class AppStrings {
  AppStrings(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppStrings of(BuildContext context) {
    return Localizations.of<AppStrings>(context, AppStrings)!;
  }

  static const LocalizationsDelegate<AppStrings> delegate =
      _AppStringsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('pt'),
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Dito'**
  String get appTitle;

  /// No description provided for @appSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Offline voice dictation'**
  String get appSubtitle;

  /// No description provided for @tabHistory.
  ///
  /// In en, this message translates to:
  /// **'History'**
  String get tabHistory;

  /// No description provided for @tabSettings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get tabSettings;

  /// No description provided for @statusReady.
  ///
  /// In en, this message translates to:
  /// **'Ready'**
  String get statusReady;

  /// No description provided for @statusReadyHotkey.
  ///
  /// In en, this message translates to:
  /// **'Ready ({hotkey} to dictate)'**
  String statusReadyHotkey(String hotkey);

  /// No description provided for @statusRecordingDictation.
  ///
  /// In en, this message translates to:
  /// **'Recording dictation...'**
  String get statusRecordingDictation;

  /// No description provided for @statusRecordingMeeting.
  ///
  /// In en, this message translates to:
  /// **'Recording meeting...'**
  String get statusRecordingMeeting;

  /// No description provided for @statusTranscribing.
  ///
  /// In en, this message translates to:
  /// **'Transcribing...'**
  String get statusTranscribing;

  /// No description provided for @statusPaused.
  ///
  /// In en, this message translates to:
  /// **'Paused'**
  String get statusPaused;

  /// No description provided for @statusNoAudio.
  ///
  /// In en, this message translates to:
  /// **'NO AUDIO - {reason}'**
  String statusNoAudio(String reason);

  /// No description provided for @dictatingDuration.
  ///
  /// In en, this message translates to:
  /// **'Dictating ({duration})'**
  String dictatingDuration(String duration);

  /// No description provided for @meetingDuration.
  ///
  /// In en, this message translates to:
  /// **'Meeting ({duration})'**
  String meetingDuration(String duration);

  /// No description provided for @btnDictate.
  ///
  /// In en, this message translates to:
  /// **'Dictate ({hotkey})'**
  String btnDictate(String hotkey);

  /// No description provided for @btnStopDictate.
  ///
  /// In en, this message translates to:
  /// **'Stop Dictation'**
  String get btnStopDictate;

  /// No description provided for @btnMeeting.
  ///
  /// In en, this message translates to:
  /// **'Meeting ({hotkey})'**
  String btnMeeting(String hotkey);

  /// No description provided for @btnStopMeeting.
  ///
  /// In en, this message translates to:
  /// **'Stop Meeting'**
  String get btnStopMeeting;

  /// No description provided for @btnListening.
  ///
  /// In en, this message translates to:
  /// **'Listening...'**
  String get btnListening;

  /// No description provided for @historyEmptyTitle.
  ///
  /// In en, this message translates to:
  /// **'No recent recordings'**
  String get historyEmptyTitle;

  /// No description provided for @historyEmptySubtitle.
  ///
  /// In en, this message translates to:
  /// **'Use the buttons above or hold {hotkey} to dictate.'**
  String historyEmptySubtitle(String hotkey);

  /// No description provided for @dictationLabel.
  ///
  /// In en, this message translates to:
  /// **'Dictation'**
  String get dictationLabel;

  /// No description provided for @meetingLabel.
  ///
  /// In en, this message translates to:
  /// **'Meeting'**
  String get meetingLabel;

  /// No description provided for @copyText.
  ///
  /// In en, this message translates to:
  /// **'Copy text'**
  String get copyText;

  /// No description provided for @textCopied.
  ///
  /// In en, this message translates to:
  /// **'Text copied to clipboard'**
  String get textCopied;

  /// No description provided for @deleteSession.
  ///
  /// In en, this message translates to:
  /// **'Delete recording'**
  String get deleteSession;

  /// No description provided for @noTranscriptionText.
  ///
  /// In en, this message translates to:
  /// **'(no recognizable speech)'**
  String get noTranscriptionText;

  /// No description provided for @formatTodayAt.
  ///
  /// In en, this message translates to:
  /// **'Today at {time}'**
  String formatTodayAt(String time);

  /// No description provided for @formatDateAt.
  ///
  /// In en, this message translates to:
  /// **'{date} at {time}'**
  String formatDateAt(String date, String time);

  /// No description provided for @formatSeconds.
  ///
  /// In en, this message translates to:
  /// **'{sec}s'**
  String formatSeconds(String sec);

  /// No description provided for @formatMinutesSeconds.
  ///
  /// In en, this message translates to:
  /// **'{min} min {sec}s'**
  String formatMinutesSeconds(int min, int sec);

  /// No description provided for @sectionModel.
  ///
  /// In en, this message translates to:
  /// **'Voice Model (Whisper)'**
  String get sectionModel;

  /// No description provided for @modelSize.
  ///
  /// In en, this message translates to:
  /// **'Model Size'**
  String get modelSize;

  /// No description provided for @modelSizeSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Larger models offer higher accuracy but use more RAM/VRAM.'**
  String get modelSizeSubtitle;

  /// No description provided for @transcriptionLanguage.
  ///
  /// In en, this message translates to:
  /// **'Transcription Spoken Language'**
  String get transcriptionLanguage;

  /// No description provided for @transcriptionLanguageSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Spoken language to be recognized.'**
  String get transcriptionLanguageSubtitle;

  /// No description provided for @hardwareAcceleration.
  ///
  /// In en, this message translates to:
  /// **'Hardware Acceleration'**
  String get hardwareAcceleration;

  /// No description provided for @hardwareAccelerationSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Uses NVIDIA GPU if available.'**
  String get hardwareAccelerationSubtitle;

  /// No description provided for @optModelTiny.
  ///
  /// In en, this message translates to:
  /// **'tiny (~75 MB - ultra fast)'**
  String get optModelTiny;

  /// No description provided for @optModelBase.
  ///
  /// In en, this message translates to:
  /// **'base (~145 MB - recommended)'**
  String get optModelBase;

  /// No description provided for @optModelSmall.
  ///
  /// In en, this message translates to:
  /// **'small (~480 MB - high accuracy)'**
  String get optModelSmall;

  /// No description provided for @optModelMedium.
  ///
  /// In en, this message translates to:
  /// **'medium (~1.5 GB)'**
  String get optModelMedium;

  /// No description provided for @optModelLarge.
  ///
  /// In en, this message translates to:
  /// **'large-v3 (~3 GB)'**
  String get optModelLarge;

  /// No description provided for @optLangPt.
  ///
  /// In en, this message translates to:
  /// **'Portuguese (Brazil)'**
  String get optLangPt;

  /// No description provided for @optLangEn.
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get optLangEn;

  /// No description provided for @optLangEs.
  ///
  /// In en, this message translates to:
  /// **'Spanish'**
  String get optLangEs;

  /// No description provided for @optDeviceAuto.
  ///
  /// In en, this message translates to:
  /// **'Automatic (GPU if available, else CPU)'**
  String get optDeviceAuto;

  /// No description provided for @optDeviceCuda.
  ///
  /// In en, this message translates to:
  /// **'NVIDIA GPU (CUDA)'**
  String get optDeviceCuda;

  /// No description provided for @optDeviceCpu.
  ///
  /// In en, this message translates to:
  /// **'Processor (CPU)'**
  String get optDeviceCpu;

  /// No description provided for @sectionMicrophone.
  ///
  /// In en, this message translates to:
  /// **'Microphone'**
  String get sectionMicrophone;

  /// No description provided for @inputDevice.
  ///
  /// In en, this message translates to:
  /// **'Input Device'**
  String get inputDevice;

  /// No description provided for @inputDeviceSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Select which microphone to record from.'**
  String get inputDeviceSubtitle;

  /// No description provided for @systemDefaultDevice.
  ///
  /// In en, this message translates to:
  /// **'System Default'**
  String get systemDefaultDevice;

  /// No description provided for @refreshDevices.
  ///
  /// In en, this message translates to:
  /// **'Refresh list'**
  String get refreshDevices;

  /// No description provided for @muteAlertTitle.
  ///
  /// In en, this message translates to:
  /// **'Mute / No Audio Warning'**
  String get muteAlertTitle;

  /// No description provided for @muteAlertSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Visually warns when the microphone delivers silence.'**
  String get muteAlertSubtitle;

  /// No description provided for @sectionHotkeys.
  ///
  /// In en, this message translates to:
  /// **'Global Hotkeys'**
  String get sectionHotkeys;

  /// No description provided for @hotkeyDictation.
  ///
  /// In en, this message translates to:
  /// **'Push-to-Talk (Hold)'**
  String get hotkeyDictation;

  /// No description provided for @hotkeyDictationSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Hold while speaking.'**
  String get hotkeyDictationSubtitle;

  /// No description provided for @hotkeyMeeting.
  ///
  /// In en, this message translates to:
  /// **'Meeting Mode (Toggle)'**
  String get hotkeyMeeting;

  /// No description provided for @hotkeyMeetingSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Press to start, press again to stop.'**
  String get hotkeyMeetingSubtitle;

  /// No description provided for @sectionOutput.
  ///
  /// In en, this message translates to:
  /// **'Output Behavior'**
  String get sectionOutput;

  /// No description provided for @autoPasteTitle.
  ///
  /// In en, this message translates to:
  /// **'Auto-paste'**
  String get autoPasteTitle;

  /// No description provided for @autoPasteSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Pastes text directly where the cursor is focused.'**
  String get autoPasteSubtitle;

  /// No description provided for @pressEnterTitle.
  ///
  /// In en, this message translates to:
  /// **'Press Enter after paste'**
  String get pressEnterTitle;

  /// No description provided for @pressEnterSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Useful for instant message sending.'**
  String get pressEnterSubtitle;

  /// No description provided for @reviewBeforePasteTitle.
  ///
  /// In en, this message translates to:
  /// **'Review before paste'**
  String get reviewBeforePasteTitle;

  /// No description provided for @reviewBeforePasteSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Opens a window to edit transcript before pasting.'**
  String get reviewBeforePasteSubtitle;

  /// No description provided for @sectionInterface.
  ///
  /// In en, this message translates to:
  /// **'Interface & Language'**
  String get sectionInterface;

  /// No description provided for @interfaceTheme.
  ///
  /// In en, this message translates to:
  /// **'Theme'**
  String get interfaceTheme;

  /// No description provided for @interfaceThemeSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Choose light, dark, or system mode.'**
  String get interfaceThemeSubtitle;

  /// No description provided for @themeAuto.
  ///
  /// In en, this message translates to:
  /// **'System Default'**
  String get themeAuto;

  /// No description provided for @themeLight.
  ///
  /// In en, this message translates to:
  /// **'Light'**
  String get themeLight;

  /// No description provided for @themeDark.
  ///
  /// In en, this message translates to:
  /// **'Dark'**
  String get themeDark;

  /// No description provided for @interfaceLanguage.
  ///
  /// In en, this message translates to:
  /// **'App Language'**
  String get interfaceLanguage;

  /// No description provided for @interfaceLanguageSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Select UI language.'**
  String get interfaceLanguageSubtitle;

  /// No description provided for @langAuto.
  ///
  /// In en, this message translates to:
  /// **'System Default'**
  String get langAuto;

  /// No description provided for @langPt.
  ///
  /// In en, this message translates to:
  /// **'Português (Brasil)'**
  String get langPt;

  /// No description provided for @langEn.
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get langEn;

  /// No description provided for @sectionUpdates.
  ///
  /// In en, this message translates to:
  /// **'Updates & About'**
  String get sectionUpdates;

  /// No description provided for @installedVersion.
  ///
  /// In en, this message translates to:
  /// **'Installed version'**
  String get installedVersion;

  /// No description provided for @btnCheckUpdates.
  ///
  /// In en, this message translates to:
  /// **'Check now'**
  String get btnCheckUpdates;

  /// No description provided for @checkingUpdates.
  ///
  /// In en, this message translates to:
  /// **'Checking...'**
  String get checkingUpdates;

  /// No description provided for @upToDateMessage.
  ///
  /// In en, this message translates to:
  /// **'You are using the latest version.'**
  String get upToDateMessage;

  /// No description provided for @updateAvailable.
  ///
  /// In en, this message translates to:
  /// **'New version available: v'**
  String get updateAvailable;

  /// No description provided for @updateReady.
  ///
  /// In en, this message translates to:
  /// **'Update ready: v'**
  String get updateReady;

  /// No description provided for @downloadingUpdate.
  ///
  /// In en, this message translates to:
  /// **'Downloading update'**
  String get downloadingUpdate;

  /// No description provided for @installingUpdate.
  ///
  /// In en, this message translates to:
  /// **'Installing update...'**
  String get installingUpdate;

  /// No description provided for @btnDownload.
  ///
  /// In en, this message translates to:
  /// **'Download'**
  String get btnDownload;

  /// No description provided for @btnInstall.
  ///
  /// In en, this message translates to:
  /// **'Install'**
  String get btnInstall;

  /// No description provided for @btnSkip.
  ///
  /// In en, this message translates to:
  /// **'Skip version'**
  String get btnSkip;

  /// No description provided for @btnLater.
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get btnLater;

  /// No description provided for @btnDownloadNow.
  ///
  /// In en, this message translates to:
  /// **'Download now'**
  String get btnDownloadNow;

  /// No description provided for @reviewDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Review Transcription'**
  String get reviewDialogTitle;

  /// No description provided for @btnDiscard.
  ///
  /// In en, this message translates to:
  /// **'Discard'**
  String get btnDiscard;

  /// No description provided for @btnPasteSend.
  ///
  /// In en, this message translates to:
  /// **'Paste / Send'**
  String get btnPasteSend;

  /// No description provided for @trayOpen.
  ///
  /// In en, this message translates to:
  /// **'Open Dito'**
  String get trayOpen;

  /// No description provided for @trayCopyLast.
  ///
  /// In en, this message translates to:
  /// **'Copy last text'**
  String get trayCopyLast;

  /// No description provided for @trayPause.
  ///
  /// In en, this message translates to:
  /// **'Pause dictation'**
  String get trayPause;

  /// No description provided for @trayCheckUpdates.
  ///
  /// In en, this message translates to:
  /// **'Check for updates...'**
  String get trayCheckUpdates;

  /// No description provided for @trayQuit.
  ///
  /// In en, this message translates to:
  /// **'Quit Dito'**
  String get trayQuit;

  /// No description provided for @hudRecording.
  ///
  /// In en, this message translates to:
  /// **'Recording'**
  String get hudRecording;

  /// No description provided for @hudQuiet.
  ///
  /// In en, this message translates to:
  /// **'Audio too low'**
  String get hudQuiet;

  /// No description provided for @hudNoAudio.
  ///
  /// In en, this message translates to:
  /// **'NO AUDIO'**
  String get hudNoAudio;

  /// No description provided for @hudStarting.
  ///
  /// In en, this message translates to:
  /// **'Starting...'**
  String get hudStarting;

  /// No description provided for @hudTranscribing.
  ///
  /// In en, this message translates to:
  /// **'Transcribing...'**
  String get hudTranscribing;

  /// No description provided for @hudSaving.
  ///
  /// In en, this message translates to:
  /// **'Saving the recording...'**
  String get hudSaving;

  /// No description provided for @hudStop.
  ///
  /// In en, this message translates to:
  /// **'Stop'**
  String get hudStop;

  /// No description provided for @hudFix.
  ///
  /// In en, this message translates to:
  /// **'Fix'**
  String get hudFix;

  /// No description provided for @toastEngineStarting.
  ///
  /// In en, this message translates to:
  /// **'The engine is still starting'**
  String get toastEngineStarting;

  /// No description provided for @toastEngineUnreachable.
  ///
  /// In en, this message translates to:
  /// **'Could not reach the engine'**
  String get toastEngineUnreachable;

  /// No description provided for @toastRecordingEnded.
  ///
  /// In en, this message translates to:
  /// **'Recording ended'**
  String get toastRecordingEnded;

  /// No description provided for @toastRecordingEndedWhy.
  ///
  /// In en, this message translates to:
  /// **'The key was held down for 10 minutes.'**
  String get toastRecordingEndedWhy;

  /// No description provided for @toastFailed.
  ///
  /// In en, this message translates to:
  /// **'It did not work'**
  String get toastFailed;

  /// No description provided for @toastPasteFailed.
  ///
  /// In en, this message translates to:
  /// **'Could not paste'**
  String get toastPasteFailed;

  /// No description provided for @toastDiscarded.
  ///
  /// In en, this message translates to:
  /// **'Discarded'**
  String get toastDiscarded;

  /// No description provided for @toastCopied.
  ///
  /// In en, this message translates to:
  /// **'Copied'**
  String get toastCopied;

  /// No description provided for @toastPasted.
  ///
  /// In en, this message translates to:
  /// **'Text pasted'**
  String get toastPasted;

  /// No description provided for @reviewHintSend.
  ///
  /// In en, this message translates to:
  /// **'Enter sends'**
  String get reviewHintSend;

  /// No description provided for @reviewHintDiscard.
  ///
  /// In en, this message translates to:
  /// **'Tab discards'**
  String get reviewHintDiscard;

  /// No description provided for @reviewObsidianOn.
  ///
  /// In en, this message translates to:
  /// **'Obsidian: yes'**
  String get reviewObsidianOn;

  /// No description provided for @reviewObsidianOff.
  ///
  /// In en, this message translates to:
  /// **'Obsidian: no'**
  String get reviewObsidianOff;

  /// No description provided for @reviewObsidianLabel.
  ///
  /// In en, this message translates to:
  /// **'Obsidian'**
  String get reviewObsidianLabel;

  /// No description provided for @hudMinutesDone.
  ///
  /// In en, this message translates to:
  /// **'{minutes} min transcribed'**
  String hudMinutesDone(int minutes);

  /// No description provided for @sectionAlerts.
  ///
  /// In en, this message translates to:
  /// **'Alerts'**
  String get sectionAlerts;

  /// No description provided for @sectionLibrary.
  ///
  /// In en, this message translates to:
  /// **'Library'**
  String get sectionLibrary;

  /// No description provided for @sectionTranscription.
  ///
  /// In en, this message translates to:
  /// **'Transcription'**
  String get sectionTranscription;

  /// No description provided for @restoreClipboardTitle.
  ///
  /// In en, this message translates to:
  /// **'Give the clipboard back'**
  String get restoreClipboardTitle;

  /// No description provided for @notifyAlertTitle.
  ///
  /// In en, this message translates to:
  /// **'Notification'**
  String get notifyAlertTitle;

  /// No description provided for @libraryFolder.
  ///
  /// In en, this message translates to:
  /// **'Recordings folder'**
  String get libraryFolder;

  /// No description provided for @libraryKeep.
  ///
  /// In en, this message translates to:
  /// **'Keep for'**
  String get libraryKeep;

  /// No description provided for @modelHint.
  ///
  /// In en, this message translates to:
  /// **'Bigger transcribes better and takes longer.'**
  String get modelHint;

  /// No description provided for @deviceLabel.
  ///
  /// In en, this message translates to:
  /// **'Processing'**
  String get deviceLabel;

  /// No description provided for @deviceHint.
  ///
  /// In en, this message translates to:
  /// **'An NVIDIA graphics card transcribes about 3x faster.'**
  String get deviceHint;

  /// No description provided for @optModelTinyName.
  ///
  /// In en, this message translates to:
  /// **'Minimum'**
  String get optModelTinyName;

  /// No description provided for @optModelBaseName.
  ///
  /// In en, this message translates to:
  /// **'Basic'**
  String get optModelBaseName;

  /// No description provided for @optModelSmallName.
  ///
  /// In en, this message translates to:
  /// **'Balanced'**
  String get optModelSmallName;

  /// No description provided for @optModelMediumName.
  ///
  /// In en, this message translates to:
  /// **'Good'**
  String get optModelMediumName;

  /// No description provided for @optModelLargeName.
  ///
  /// In en, this message translates to:
  /// **'Best'**
  String get optModelLargeName;

  /// No description provided for @keyCaptureHint.
  ///
  /// In en, this message translates to:
  /// **'Press the key you want | Esc cancels'**
  String get keyCaptureHint;

  /// No description provided for @keyConflictOther.
  ///
  /// In en, this message translates to:
  /// **'the other shortcut'**
  String get keyConflictOther;

  /// No description provided for @booting.
  ///
  /// In en, this message translates to:
  /// **'Starting...'**
  String get booting;

  /// No description provided for @themeFollowSystem.
  ///
  /// In en, this message translates to:
  /// **'Follow the system'**
  String get themeFollowSystem;

  /// No description provided for @libraryKeepDays.
  ///
  /// In en, this message translates to:
  /// **'{days} days'**
  String libraryKeepDays(int days);

  /// No description provided for @trayTipRecording.
  ///
  /// In en, this message translates to:
  /// **'Recording - release to transcribe'**
  String get trayTipRecording;

  /// No description provided for @trayTipMeeting.
  ///
  /// In en, this message translates to:
  /// **'Recording - press again to stop'**
  String get trayTipMeeting;

  /// No description provided for @trayTipNoAudio.
  ///
  /// In en, this message translates to:
  /// **'No audio - check the microphone'**
  String get trayTipNoAudio;

  /// No description provided for @trayTipPaused.
  ///
  /// In en, this message translates to:
  /// **'Dictation paused'**
  String get trayTipPaused;

  /// No description provided for @notifyEngineDied.
  ///
  /// In en, this message translates to:
  /// **'Dito - the engine crashed'**
  String get notifyEngineDied;

  /// No description provided for @notifyEngineDiedWhy.
  ///
  /// In en, this message translates to:
  /// **'The audio is safe in the session folder.'**
  String get notifyEngineDiedWhy;

  /// No description provided for @notifyNoAudio.
  ///
  /// In en, this message translates to:
  /// **'the microphone stopped picking up'**
  String get notifyNoAudio;

  /// No description provided for @keyErrorTypes.
  ///
  /// In en, this message translates to:
  /// **'That key types - pick one that does not.'**
  String get keyErrorTypes;

  /// No description provided for @warnKeysFailed.
  ///
  /// In en, this message translates to:
  /// **'Could not register the shortcuts: they will not work.'**
  String get warnKeysFailed;

  /// No description provided for @warnUnknownReason.
  ///
  /// In en, this message translates to:
  /// **'reason unknown'**
  String get warnUnknownReason;

  /// No description provided for @openFolder.
  ///
  /// In en, this message translates to:
  /// **'Open the folder'**
  String get openFolder;

  /// No description provided for @toastPasteToClipboard.
  ///
  /// In en, this message translates to:
  /// **'Could not paste - the text is on the clipboard'**
  String get toastPasteToClipboard;

  /// No description provided for @toastPasteToFolder.
  ///
  /// In en, this message translates to:
  /// **'Could not paste or copy - the text is in the session folder'**
  String get toastPasteToFolder;

  /// No description provided for @trayTipReady.
  ///
  /// In en, this message translates to:
  /// **'Ready - hold {hotkey} to dictate'**
  String trayTipReady(String hotkey);

  /// No description provided for @keyErrorTaken.
  ///
  /// In en, this message translates to:
  /// **'That key already belongs to {other}.'**
  String keyErrorTaken(String other);

  /// No description provided for @warnEngineDown.
  ///
  /// In en, this message translates to:
  /// **'The transcription engine stopped: {reason}.'**
  String warnEngineDown(String reason);

  /// No description provided for @warnNoAudio.
  ///
  /// In en, this message translates to:
  /// **'No audio: {reason}.'**
  String warnNoAudio(String reason);

  /// No description provided for @toastStillBusy.
  ///
  /// In en, this message translates to:
  /// **'Still finishing the previous one'**
  String get toastStillBusy;

  /// No description provided for @errMicUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Could not access the microphone'**
  String get errMicUnavailable;

  /// No description provided for @errModelLoadFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to load the model: {detail}'**
  String errModelLoadFailed(String detail);

  /// No description provided for @errEngineDiedRecording.
  ///
  /// In en, this message translates to:
  /// **'the engine crashed during the recording'**
  String get errEngineDiedRecording;

  /// No description provided for @errEngineDiedIdle.
  ///
  /// In en, this message translates to:
  /// **'the engine stopped responding'**
  String get errEngineDiedIdle;

  /// No description provided for @errEngineStartFailed.
  ///
  /// In en, this message translates to:
  /// **'failed to start the native engine: {detail}'**
  String errEngineStartFailed(String detail);

  /// No description provided for @errKeyTaken.
  ///
  /// In en, this message translates to:
  /// **'The {key} key is held by another program: {action} does not respond'**
  String errKeyTaken(Object key, Object action);

  /// No description provided for @errKeyBack.
  ///
  /// In en, this message translates to:
  /// **'Key {key} released: {action} works again'**
  String errKeyBack(Object key, Object action);

  /// No description provided for @toastNoVoiceHeard.
  ///
  /// In en, this message translates to:
  /// **'The microphone did not pick up your voice'**
  String get toastNoVoiceHeard;

  /// No description provided for @toastNoVoiceHeardWhy.
  ///
  /// In en, this message translates to:
  /// **'Only background noise arrived: check the headset and try again'**
  String get toastNoVoiceHeardWhy;

  /// No description provided for @errEngineNoResponse.
  ///
  /// In en, this message translates to:
  /// **'the engine did not respond'**
  String get errEngineNoResponse;

  /// No description provided for @errTranscribeNoResponse.
  ///
  /// In en, this message translates to:
  /// **'the transcription did not respond'**
  String get errTranscribeNoResponse;

  /// No description provided for @errCheckUpdatesFailed.
  ///
  /// In en, this message translates to:
  /// **'Failed to check for updates: {detail}'**
  String errCheckUpdatesFailed(String detail);

  /// No description provided for @upToDateMessageVersion.
  ///
  /// In en, this message translates to:
  /// **'You are already using the latest version (v{version}).'**
  String upToDateMessageVersion(String version);
}

class _AppStringsDelegate extends LocalizationsDelegate<AppStrings> {
  const _AppStringsDelegate();

  @override
  Future<AppStrings> load(Locale locale) {
    return SynchronousFuture<AppStrings>(lookupAppStrings(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'pt'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppStringsDelegate old) => false;
}

AppStrings lookupAppStrings(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppStringsEn();
    case 'pt':
      return AppStringsPt();
  }

  throw FlutterError(
    'AppStrings.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
