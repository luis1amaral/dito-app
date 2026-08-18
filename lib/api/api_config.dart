import 'package:flutter_dotenv/flutter_dotenv.dart';

class ApiConfig {
  ApiConfig._();

  static String get baseUrl =>
      (dotenv.isInitialized ? dotenv.env['API_BASE_URL'] : null) ?? 'https://dito-api.defaltm.com';
}
