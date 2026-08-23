/// Keys that can be bound: only those that type no character, mirroring src/dito/keys.py.
///
/// The same list exists as a C++ table in packages/dito_win32/windows/key_table.cpp.
const List<String> bindableKeys = <String>[
  'f1', 'f2', 'f3', 'f4', 'f5',
  'f9', 'f10', 'f11', 'f12', 'f13', 'f14', 'f15', 'f16',
  'space',
  'print_screen',
  'page_up',
  'page_down',
  'scroll_lock',
  'pause',
  'insert',
  'menu',
  'home',
  'end',
  'caps_lock',
];

String labelForKey(String key) => switch (key) {
      'print_screen' => 'Print Screen',
      'page_up' => 'Page Up',
      'page_down' => 'Page Down',
      'scroll_lock' => 'Scroll Lock',
      'caps_lock' => 'Caps Lock',
      'space' => 'Espaço',
      'menu' => 'Menu',
      'insert' => 'Insert',
      'home' => 'Home',
      'end' => 'End',
      'pause' => 'Pause',
      _ => key.toUpperCase(),
    };
