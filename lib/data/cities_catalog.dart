import 'dart:convert';

import 'package:flutter/services.dart';

/// Offline city lists keyed by ISO-3166-1 alpha-2 country code.
class CitiesCatalog {
  CitiesCatalog._();

  static Map<String, List<String>>? _byCountry;

  static const countryIso = <String, String>{
    'Россия': 'RU',
    'Китай': 'CN',
    'Беларусь': 'BY',
    'Казахстан': 'KZ',
    'Узбекистан': 'UZ',
    'Армения': 'AM',
    'Азербайджан': 'AZ',
    'Кыргызстан': 'KG',
    'Таджикистан': 'TJ',
    'Турция': 'TR',
    'Германия': 'DE',
    'Индия': 'IN',
    'ОАЭ': 'AE',
    'США': 'US',
  };

  static const isoCountry = <String, String>{
    'RU': 'Россия',
    'CN': 'Китай',
    'BY': 'Беларусь',
    'KZ': 'Казахстан',
    'UZ': 'Узбекистан',
    'AM': 'Армения',
    'AZ': 'Азербайджан',
    'KG': 'Кыргызстан',
    'TJ': 'Таджикистан',
    'TR': 'Турция',
    'DE': 'Германия',
    'IN': 'Индия',
    'AE': 'ОАЭ',
    'US': 'США',
  };

  static Future<void> ensureLoaded() async {
    if (_byCountry != null) return;
    final raw = await rootBundle.loadString('assets/data/cities_by_country.json');
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    _byCountry = {
      for (final entry in decoded.entries)
        entry.key: List<String>.from(entry.value as List),
    };
  }

  static List<String> citiesForCountryName(String countryName) {
    final iso = countryIso[countryName];
    if (iso == null) return const [];
    return _byCountry?[iso] ?? const [];
  }

  /// Unique city names across [countryNames], preserving alphabetical order.
  static List<String> citiesForCountries(Iterable<String> countryNames) {
    final seen = <String>{};
    final result = <String>[];
    for (final country in countryNames) {
      for (final city in citiesForCountryName(country)) {
        if (seen.add(city)) result.add(city);
      }
    }
    result.sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return result;
  }

  static String? countryForCity(String city, Iterable<String> countryNames) {
    for (final country in countryNames) {
      if (citiesForCountryName(country).contains(city)) return country;
    }
    return null;
  }
}
