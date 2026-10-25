import '../api/feed_models.dart';
import '../l10n/app_localizations.dart';
import '../models/onboarding_data.dart';

/// Локальный корпус для входа «через Альфа-демо» без JWT/companyId API.
abstract final class AlfaDemoData {
  /// Дополняет профиль выбранной компании демо-контекстом.
  static void enrichProfile(OnboardingData data, {required String industry}) {
    if (data.fullName.trim().isEmpty) {
      data.fullName = 'Владимир Бородин';
    }
    if (data.email.trim().isEmpty) {
      data.email = 'demo@mlechny-put.ru';
    }
    if (data.role.trim().isEmpty) {
      data.role = 'Генеральный директор';
    }
    if (data.companySize.trim().isEmpty) {
      data.companySize = '200–500 сотрудников';
    }
    if (data.businessType.trim().isEmpty) {
      data.businessType = industry;
      data.businessTypeSubtitle = 'Крупный бизнес · демо-профиль';
    }
    if (data.companyIndustry.trim().isEmpty) {
      data.companyIndustry = industry;
    }
    if (data.companyCity.trim().isEmpty) {
      data.companyCity = 'Москва';
    }
    if (data.mainMarket.trim().isEmpty) {
      data.mainMarket = 'Россия';
    }
    if (data.products.isEmpty) {
      data.products = const [
        'Основная продукция',
        'B2B-поставки',
        'Экспортные контракты',
      ];
    }
    if (data.countries.isEmpty) {
      data.countries = const ['Россия', 'Китай', 'Казахстан'];
    }
    if (data.cities.isEmpty) {
      data.cities = const ['Москва', 'Санкт-Петербург'];
    }
    if (data.salesRegions.isEmpty) {
      data.salesRegions = const ['ЦФО', 'СЗФО'];
    }
    if (data.finances.isEmpty) {
      data.finances = const [
        'Кредитная линия',
        'РКО',
        'Валютный контроль',
      ];
    }
    if (data.counterparties.isEmpty) {
      data.counterparties = const [
        'Поставщик комплектующих (CN)',
        'Дистрибьютор (РФ)',
        'Логистический оператор',
      ];
    }
  }

  /// Карточки ленты в форме API `priority_events` / `events.items`.
  static List<Map<String, dynamic>> feedCards() {
    final now = DateTime.now().toUtc();
    String iso(Duration ago) => now.subtract(ago).toIso8601String();
    return [
      {
        'id': 'demo_evt_policy_rate',
        'title':
            'Ключевая ставка ЦБ РФ: ставка без изменения на 14,0%, риторика стала жестче',
        'priority': 'high',
        'impact_score': 82,
        'score_kind': 'demo',
        'reason_summary':
            'Для компании с кредитной нагрузкой пауза в снижении ставки сохраняет высокую стоимость денег и давление на оборотный капитал.',
        'updated_at': iso(const Duration(hours: 2)),
        'exposure': {
          'label': 'Кредитная зависимость',
          'value': 'высокая',
          'unit': '',
        },
      },
      {
        'id': 'demo_evt_china_export',
        'title': 'Китай ограничивает экспорт электроники',
        'priority': 'high',
        'impact_score': 78,
        'score_kind': 'demo',
        'reason_summary':
            'Ограничения затрагивают цепочки поставок комплектующих — риск срыва сроков и роста закупочных цен.',
        'updated_at': iso(const Duration(hours: 5)),
        'exposure': {
          'label': 'Доля импорта из Китая',
          'value': '34',
          'unit': '%',
        },
      },
      {
        'id': 'demo_evt_fx',
        'title': 'Волатильность курса рубля усилилась',
        'priority': 'medium',
        'impact_score': 58,
        'score_kind': 'demo',
        'reason_summary':
            'Валютная выручка и импортные контракты чувствительны к колебаниям курса в ближайшие недели.',
        'updated_at': iso(const Duration(days: 1)),
      },
      {
        'id': 'demo_evt_inflation',
        'title': 'Инфляция 25–31 августа: основные выводы',
        'priority': 'low',
        'impact_score': null,
        'score_kind': 'case_profile_match',
        'reason_summary':
            'Материал Альфа-Банка полезен для сверки ценовых ожиданий с финансовым планом компании.',
        'updated_at': iso(const Duration(days: 2)),
      },
    ];
  }

  static List<FeedEvent> feedEvents(AppLocalizations l10n) => [
        for (final c in feedCards()) FeedEvent.fromCard(c, l10n),
      ];
}
