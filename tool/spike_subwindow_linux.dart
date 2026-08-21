// Proves whether a desktop_multi_window sub-window actually renders content on Linux/GTK/GL.
import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/material.dart';

const String kSubArg = 'sub';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final controller = await WindowController.fromCurrentEngine();
  if (controller.arguments == kSubArg) {
    runApp(const _SubWindow());
    return;
  }
  runApp(_Main());
}

class _Main extends StatefulWidget {
  const _Main();
  @override
  State<_Main> createState() => _MainState();
}

class _MainState extends State<_Main> {
  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    await Future<void>.delayed(const Duration(seconds: 1));
    final sub = await WindowController.create(
      const WindowConfiguration(arguments: kSubArg, focusable: false),
    );
    await Future<void>.delayed(const Duration(milliseconds: 300));
    await sub.show();
  }

  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: Colors.deepPurple,
          body: Center(
            child: Text('MAIN', style: TextStyle(color: Colors.white, fontSize: 40)),
          ),
        ),
      );
}

class _SubWindow extends StatelessWidget {
  const _SubWindow();
  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: Colors.green,
          body: Center(
            child: Text('SUB WINDOW OK', style: TextStyle(color: Colors.white, fontSize: 30)),
          ),
        ),
      );
}
