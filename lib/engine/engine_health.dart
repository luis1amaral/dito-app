/// Engine health, in the shape the interface has to show it.
enum EngineState {
  /// Process launched, no engine_ready yet.
  starting,

  /// Ready to take commands.
  ready,

  /// Alive but wrong, e.g. a command went unanswered.
  degraded,

  /// Process dead; if it died recording the WAV survived, guarantee 1 holds.
  dead,
}

class EngineHealth {
  const EngineHealth({
    required this.state,
    this.reason,
    this.model = '',
    this.backend = '',
    this.restarts = 0,
  });

  final EngineState state;
  final String? reason;
  final String model;
  final String backend;
  final int restarts;

  bool get canAcceptCommands => state == EngineState.ready || state == EngineState.degraded;

  EngineHealth copyWith({
    EngineState? state,
    String? reason,
    bool clearReason = false,
    String? model,
    String? backend,
    int? restarts,
  }) =>
      EngineHealth(
        state: state ?? this.state,
        reason: clearReason ? null : (reason ?? this.reason),
        model: model ?? this.model,
        backend: backend ?? this.backend,
        restarts: restarts ?? this.restarts,
      );

  @override
  bool operator ==(Object other) =>
      other is EngineHealth &&
      other.state == state &&
      other.reason == reason &&
      other.model == model &&
      other.backend == backend &&
      other.restarts == restarts;

  @override
  int get hashCode => Object.hash(state, reason, model, backend, restarts);
}
