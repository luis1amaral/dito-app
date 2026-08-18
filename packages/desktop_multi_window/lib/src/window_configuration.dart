class WindowConfiguration {
  const WindowConfiguration({
    required this.arguments,
    this.hiddenAtLaunch = true,
    this.focusable = true,
  });

  /// The arguments passed to the new window.
  final String arguments;

  final bool hiddenAtLaunch;

  /// Fork: false makes the window never take focus (WS_EX_NOACTIVATE, no SetFocus).
  /// Decided at creation time — it cannot be applied afterwards. See FORK.md.
  final bool focusable;

  factory WindowConfiguration.fromJson(Map<String, dynamic> json) {
    return WindowConfiguration(
      arguments: json['arguments'] as String? ?? '',
      hiddenAtLaunch: json['hiddenAtLaunch'] as bool? ?? false,
      focusable: json['focusable'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'arguments': arguments,
      'hiddenAtLaunch': hiddenAtLaunch,
      'focusable': focusable,
    };
  }

  @override
  String toString() {
    return 'WindowConfiguration(arguments: $arguments, hiddenAtLaunch: $hiddenAtLaunch)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is WindowConfiguration &&
        other.arguments == arguments &&
        other.hiddenAtLaunch == hiddenAtLaunch &&
        other.focusable == focusable;
  }

  @override
  int get hashCode {
    return arguments.hashCode ^ hiddenAtLaunch.hashCode ^ focusable.hashCode;
  }
}
