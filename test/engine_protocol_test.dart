import 'dart:convert';

import 'package:dito_app/engine/engine_protocol.dart';
import 'package:flutter_test/flutter_test.dart';

EngineEvent parse(String line) =>
    EngineEvent.parse(Map<String, dynamic>.from(jsonDecode(line) as Map));

void main() {
  group('handshake', () {
    test('engine_ready is NOT the start of a recording', () {
      final event = parse('{"event":"started","session_id":"engine_ready",'
          '"mode":"engine","device_name":"init"}');
      expect(event, isA<EngineReadyEvent>());
      expect(event, isNot(isA<StartedEvent>()));
    });

    test('a real start is still a StartedEvent', () {
      final event = parse('{"event":"started","session_id":"2026-08-16_07-42-13",'
          '"mode":"dictation","device_name":"H510"}');
      expect(event, isA<StartedEvent>());
      expect((event as StartedEvent).deviceName, 'H510');
      expect(event.isMeeting, isFalse);
    });

    test('meeting mode is recognised', () {
      final event = parse('{"event":"started","session_id":"x","mode":"meeting",'
          '"device_name":"mic"}') as StartedEvent;
      expect(event.isMeeting, isTrue);
    });
  });

  group('status', () {
    test('carries the state field the old port dropped', () {
      final idle = parse('{"event":"status","state":"idle","model":"small",'
          '"backend":"cpu (int8)"}') as StatusEvent;
      expect(idle.isRecording, isFalse);
      expect(idle.model, 'small');
      expect(idle.backend, 'cpu (int8)');

      final busy = parse('{"event":"status","state":"recording","model":"small",'
          '"backend":"cuda (float16)"}') as StatusEvent;
      expect(busy.isRecording, isTrue);
    });
  });

  group('alarm', () {
    test('all three states parse, including quiet', () {
      expect((parse('{"event":"alarm","state":"ok"}') as AlarmEvent).state, AudioState.ok);
      expect((parse('{"event":"alarm","state":"quiet","reason":"baixo"}') as AlarmEvent).state,
          AudioState.quiet);
      final dead = parse('{"event":"alarm","state":"dead","reason":"mudo",'
          '"fix_hint":"Corrigir"}') as AlarmEvent;
      expect(dead.state, AudioState.dead);
      expect(dead.fixHint, 'Corrigir');
    });

    test('missing optional fields become null, not empty strings', () {
      final event = parse('{"event":"alarm","state":"ok"}') as AlarmEvent;
      expect(event.reason, isNull);
      expect(event.fixHint, isNull);
    });
  });

  group('finished', () {
    test('every field survives', () {
      final event = parse('{"event":"finished","session_id":"s1","mode":"meeting",'
          '"text":"ola","seconds":12.34,"folder":"C:/x","ever_heard_audio":true}')
          as FinishedEvent;
      expect(event.text, 'ola');
      expect(event.seconds, 12.34);
      expect(event.folder, 'C:/x');
      expect(event.everHeardAudio, isTrue);
      expect(event.isMeeting, isTrue);
    });
  });

  group('partial and published', () {
    test('partial parses, so live meeting text can reach the screen', () {
      final event = parse('{"event":"partial","index":2,"start_s":21.4,"end_s":44.0,'
          '"text":"trecho"}') as PartialEvent;
      expect(event.index, 2);
      expect(event.endS, 44.0);
      expect(event.text, 'trecho');
    });

    test('published parses, so the Obsidian note can be reported', () {
      final event = parse('{"event":"published","folder":"C:/x","note":"nota.md",'
          '"note_in_vault":true,"minutes":42,"words":900}') as PublishedEvent;
      expect(event.note, 'nota.md');
      expect(event.noteInVault, isTrue);
      expect(event.minutes, 42);
    });
  });

  group('robustness', () {
    test('an unknown event does not throw', () {
      expect(parse('{"event":"brand_new"}'), isA<UnknownEvent>());
    });

    test('missing fields fall back instead of throwing', () {
      final event = parse('{"event":"level"}') as LevelEvent;
      expect(event.rms, 0);
      expect(event.peak, 0);
    });

    test('numbers arriving as strings still parse', () {
      final event = parse('{"event":"level","rms":"0.05","peak":"0.2","seconds":"3"}')
          as LevelEvent;
      expect(event.rms, 0.05);
      expect(event.seconds, 3);
    });

    test('devices list parses and tolerates junk entries', () {
      final event = parse('{"event":"devices","devices":[{"index":1,"name":"mic",'
          '"default":true},"lixo"]}') as DevicesEvent;
      expect(event.devices, hasLength(1));
      expect(event.devices.first.isDefault, isTrue);
    });
  });

  group('commands', () {
    test('start carries exactly the field names the engine reads', () {
      const cmd = StartCommand(
        mode: 'dictation',
        model: 'small',
        language: 'pt',
        device: '',
        devicePref: 'auto',
      );
      expect(cmd.toJson(), {
        'cmd': 'start',
        'mode': 'dictation',
        'model': 'small',
        'language': 'pt',
        'device': '',
        'device_pref': 'auto',
      });
    });

    test('the other four commands are bare', () {
      expect(const StopCommand().toJson(), {'cmd': 'stop'});
      expect(const StatusCommand().toJson(), {'cmd': 'status'});
      expect(const ListDevicesCommand().toJson(), {'cmd': 'list_devices'});
      expect(const QuitCommand().toJson(), {'cmd': 'quit'});
    });
  });

  group('acentos (UTF-8)', () {
    // O motor agora emite UTF-8 (entry_engine reconfigura os streams). Antes o stdout saia em
    // cp1252 e o Flutter, que le UTF-8, transformava os acentos em «replacement char». Estes
    // testes fixam o contrato: bytes UTF-8 do motor decodificam sem corromper o texto.
    final replacement = String.fromCharCode(0xFFFD);

    test('texto transcrito com acentos sobrevive ao round-trip UTF-8', () {
      const texto = 'Reunião: revisão da ação e do orçamento até quinta-feira. Café é ótimo.';
      final linha = jsonEncode(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': texto,
        'seconds': 1.0,
        'folder': '',
        'ever_heard_audio': true,
      });
      final bytes = utf8.encode(linha);
      final decodificada = const Utf8Decoder(allowMalformed: true).convert(bytes);
      final evento = EngineEvent.parse(
          Map<String, dynamic>.from(jsonDecode(decodificada) as Map));
      expect(evento, isA<FinishedEvent>());
      expect((evento as FinishedEvent).text, texto);
      expect(evento.text.contains(replacement), isFalse);
    });

    test('nome de dispositivo com acentos sobrevive ao round-trip UTF-8', () {
      const nome = 'Driver de captura de som primário (áudio estéreo)';
      final linha = jsonEncode(<String, Object?>{
        'event': 'devices',
        'devices': <Map<String, Object?>>[
          {'index': 0, 'name': nome, 'default': true},
        ],
      });
      final bytes = utf8.encode(linha);
      final decodificada = const Utf8Decoder(allowMalformed: true).convert(bytes);
      final evento = EngineEvent.parse(
          Map<String, dynamic>.from(jsonDecode(decodificada) as Map));
      expect(evento, isA<DevicesEvent>());
      expect((evento as DevicesEvent).devices.single.name, nome);
      expect(evento.devices.single.name.contains(replacement), isFalse);
    });
  });
}
