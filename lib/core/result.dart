/// Where the text ended up when pasting did not work.
enum PasteFallback { clipboard, sessionFolder }

/// Paste outcome that never throws and always says WHERE the text ended up.
class PasteResult {
  const PasteResult({required this.pasted, required this.copied, this.error});

  const PasteResult.ok() : pasted = true, copied = true, error = null;

  final bool pasted;
  final bool copied;
  final String? error;

  /// null on success; otherwise the role the window turns into wording.
  PasteFallback? get fallback {
    if (pasted) return null;
    return copied ? PasteFallback.clipboard : PasteFallback.sessionFolder;
  }
}

/// Outcome of writing the meeting note.
class PublishResult {
  const PublishResult({
    required this.path,
    required this.inVault,
    this.warning,
  });

  final String path;
  final bool inVault;

  /// Set when the note was written outside the vault: a caveat beats silence.
  final String? warning;
}
