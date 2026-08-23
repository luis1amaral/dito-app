// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_strings.g.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppStringsPt extends AppStrings {
  AppStringsPt([String locale = 'pt']) : super(locale);

  @override
  String get appTitle => 'Dito';

  @override
  String get tabHistory => 'Histórico';

  @override
  String get tabSettings => 'Configurações';

  @override
  String get statusReady => 'Pronto';

  @override
  String get historyEmptyTitle => 'Nenhuma gravação recente';

  @override
  String historyEmptySubtitle(String hotkey) {
    return 'Use os botões acima ou segure $hotkey para ditar.';
  }

  @override
  String get dictationLabel => 'Ditado';

  @override
  String get meetingLabel => 'Reunião';

  @override
  String get sectionModel => 'Modelo de Voz (Whisper)';

  @override
  String get transcriptionLanguage => 'Idioma de Transcrição';

  @override
  String get optLangPt => 'Português (Brasil)';

  @override
  String get optLangEn => 'Inglês (English)';

  @override
  String get optLangEs => 'Espanhol (Español)';

  @override
  String get optDeviceAuto => 'Automático (GPU se disponível, senão CPU)';

  @override
  String get optDeviceCuda => 'GPU NVIDIA (CUDA)';

  @override
  String get optDeviceCpu => 'Processador (CPU)';

  @override
  String get muteAlertTitle => 'Alerta de microfone mudo / sem áudio';

  @override
  String get sectionHotkeys => 'Teclas de Atalho';

  @override
  String get hotkeyDictation => 'Ditado Rápido (Segurar)';

  @override
  String get hotkeyMeeting => 'Modo Reunião (Alternar)';

  @override
  String get sectionOutput => 'Comportamento de Saída';

  @override
  String get autoPasteTitle => 'Colar automaticamente';

  @override
  String get pressEnterTitle => 'Pressionar Enter após colar';

  @override
  String get reviewBeforePasteTitle => 'Revisar antes de colar';

  @override
  String get reviewBeforePasteSubtitle =>
      'Exibe uma janela para editar a transcrição antes de colar.';

  @override
  String get sectionInterface => 'Interface e Idioma';

  @override
  String get interfaceTheme => 'Tema Visual';

  @override
  String get themeLight => 'Claro';

  @override
  String get themeDark => 'Escuro';

  @override
  String get interfaceLanguage => 'Idioma da Interface';

  @override
  String get langPt => 'Português (Brasil)';

  @override
  String get langEn => 'English';

  @override
  String get sectionUpdates => 'Atualizações e Versão';

  @override
  String get installedVersion => 'Versão instalada';

  @override
  String get btnCheckUpdates => 'Verificar agora';

  @override
  String get upToDateMessage => 'Você está usando a versão mais recente.';

  @override
  String get updateAvailable => 'Nova versão disponível: v';

  @override
  String get updateReady => 'Atualização pronta: v';

  @override
  String get downloadingUpdate => 'Baixando atualização';

  @override
  String get installingUpdate => 'Instalando atualização...';

  @override
  String get btnDownload => 'Baixar';

  @override
  String get btnInstall => 'Instalar';

  @override
  String get btnSkip => 'Pular versão';

  @override
  String get btnLater => 'Depois';

  @override
  String get btnDownloadNow => 'Baixar agora';

  @override
  String get btnDiscard => 'Descartar';

  @override
  String get trayOpen => 'Abrir Dito';

  @override
  String get trayCopyLast => 'Copiar último texto';

  @override
  String get trayPause => 'Pausar ditado';

  @override
  String get trayQuit => 'Sair do Dito';

  @override
  String get hudRecording => 'Gravando';

  @override
  String get hudQuiet => 'Áudio muito baixo';

  @override
  String get hudNoAudio => 'SEM ÁUDIO';

  @override
  String get hudStarting => 'Iniciando...';

  @override
  String get hudTranscribing => 'Transcrevendo...';

  @override
  String get hudSaving => 'Salvando a gravação...';

  @override
  String get hudStop => 'Parar';

  @override
  String get hudFix => 'Corrigir';

  @override
  String get toastEngineStarting => 'O motor ainda está subindo';

  @override
  String get toastEngineUnreachable => 'Não consegui falar com o motor';

  @override
  String get toastRecordingEnded => 'Gravação encerrada';

  @override
  String get toastRecordingEndedWhy => 'A tecla ficou presa por 10 minutos.';

  @override
  String get toastFailed => 'Não deu certo';

  @override
  String get toastPasteFailed => 'Não consegui colar';

  @override
  String get toastDiscarded => 'Descartado';

  @override
  String get toastCopied => 'Copiado';

  @override
  String get toastPasted => 'Texto colado';

  @override
  String get reviewHintSend => 'Enter envia';

  @override
  String get reviewHintDiscard => 'Tab descarta';

  @override
  String get reviewObsidianLabel => 'Obsidian';

  @override
  String hudMinutesDone(int minutes) {
    return '$minutes min transcritos';
  }

  @override
  String get sectionAlerts => 'Alertas';

  @override
  String get sectionLibrary => 'Biblioteca';

  @override
  String get sectionTranscription => 'Transcrição';

  @override
  String get restoreClipboardTitle => 'Devolver a área de transferência';

  @override
  String get notifyAlertTitle => 'Notificação';

  @override
  String get libraryFolder => 'Pasta das gravações';

  @override
  String get libraryKeep => 'Guardar por';

  @override
  String get modelHint => 'Maior transcreve melhor e demora mais.';

  @override
  String get deviceLabel => 'Processamento';

  @override
  String get deviceHint =>
      'A placa de vídeo NVIDIA transcreve cerca de 3x mais rápido.';

  @override
  String get optModelTinyName => 'Mínimo';

  @override
  String get optModelBaseName => 'Básico';

  @override
  String get optModelSmallName => 'Equilibrado';

  @override
  String get optModelMediumName => 'Bom';

  @override
  String get optModelLargeName => 'Melhor';

  @override
  String get keyCaptureHint => 'Aperte a tecla desejada | Esc cancela';

  @override
  String get keyConflictOther => 'a outra tecla';

  @override
  String get booting => 'Iniciando...';

  @override
  String get themeFollowSystem => 'Seguir o sistema';

  @override
  String libraryKeepDays(int days) {
    return '$days dias';
  }

  @override
  String get trayTipRecording => 'Gravando - solte para transcrever';

  @override
  String get trayTipMeeting => 'Gravando - aperte de novo para parar';

  @override
  String get trayTipNoAudio => 'Sem áudio - verifique o microfone';

  @override
  String get trayTipPaused => 'Ditado pausado';

  @override
  String get notifyEngineDied => 'Dito - o motor caiu';

  @override
  String get notifyEngineDiedWhy => 'O áudio está salvo na pasta da sessão.';

  @override
  String get notifyNoAudio => 'o microfone parou de captar';

  @override
  String get keyErrorTypes =>
      'Essa tecla digita - use uma que nao digita nada.';

  @override
  String get warnKeysFailed =>
      'Nao consegui registrar as teclas: elas nao vao funcionar.';

  @override
  String get warnUnknownReason => 'motivo desconhecido';

  @override
  String get openFolder => 'Abrir a pasta';

  @override
  String get toastPasteToClipboard =>
      'Nao consegui colar - o texto esta na area de transferencia';

  @override
  String get toastPasteToFolder =>
      'Nao consegui colar nem copiar - o texto esta na pasta da sessao';

  @override
  String trayTipReady(String hotkey) {
    return 'Pronto - segure $hotkey para ditar';
  }

  @override
  String keyErrorTaken(String other) {
    return 'Essa tecla ja e usada por $other.';
  }

  @override
  String warnEngineDown(String reason) {
    return 'O motor de transcricao parou: $reason.';
  }

  @override
  String warnNoAudio(String reason) {
    return 'Sem audio: $reason.';
  }

  @override
  String get toastStillBusy => 'Ainda terminando o anterior';

  @override
  String get errMicUnavailable => 'Não foi possível acessar o microfone';

  @override
  String errModelLoadFailed(String detail) {
    return 'Falha ao carregar o modelo: $detail';
  }

  @override
  String get errEngineDiedRecording => 'o motor caiu durante a gravação';

  @override
  String get errEngineDiedIdle => 'o motor parou de responder';

  @override
  String errEngineStartFailed(String detail) {
    return 'falha ao iniciar o motor nativo: $detail';
  }

  @override
  String errKeyTaken(String key, String action) {
    return 'A tecla $key está tomada por outro programa: $action não responde';
  }

  @override
  String errKeyBack(String key, String action) {
    return 'Tecla $key liberada: $action voltou a funcionar';
  }

  @override
  String get toastNoVoiceHeard => 'O microfone não captou sua voz';

  @override
  String get toastNoVoiceHeardWhy =>
      'Só chegou ruído de fundo: confira o headset e tente de novo';

  @override
  String get errEngineNoResponse => 'o motor não respondeu';

  @override
  String get errTranscribeNoResponse => 'a transcrição não respondeu';

  @override
  String errCheckUpdatesFailed(String detail) {
    return 'Falha ao verificar atualizações: $detail';
  }

  @override
  String upToDateMessageVersion(String version) {
    return 'Você já está usando a versão mais recente (v$version).';
  }
}
