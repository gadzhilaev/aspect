import 'package:flutter/widgets.dart';

import '../app/app_controller.dart';

/// Локализация RU / EN. Доступ: `context.l10n`.
class AppLocalizations {
  AppLocalizations(this.locale);

  final Locale locale;

  static AppLocalizations of(BuildContext context) {
    final inherited = context.dependOnInheritedWidgetOfExactType<_L10nScope>();
    if (inherited != null) return inherited.l10n;
    return AppLocalizations(AppController.instance.locale);
  }

  bool get isRu => locale.languageCode != 'en';

  String _t(String ru, String en) => isRu ? ru : en;

  // —— App / common ——
  String get appName => _t('Аспект', 'Aspect');
  String get splashTagline => _t(
        'Рынок - в контексте вашего бизнеса',
        'The market — in the context of your business',
      );
  String get back => _t('‹ Назад', '‹ Back');
  String get cancel => _t('Отмена', 'Cancel');
  String get continueAction => _t('Продолжить', 'Continue');
  String get skipAction => _t('Пропустить', 'Skip');
  String get save => _t('Сохранить', 'Save');
  String get delete => _t('Удалить', 'Delete');
  String get edit => _t('Редактировать', 'Edit');
  String get search => _t('Поиск', 'Search');
  String get open => _t('Открыть', 'Open');
  String get done => _t('Готово', 'Done');
  String get yes => _t('Да', 'Yes');
  String get no => _t('Нет', 'No');
  String get loading => _t('Загрузка…', 'Loading…');

  // —— Nav ——
  String get navOverview => _t('Обзор', 'Overview');
  String get navEvents => _t('События', 'Events');
  String get navScenarios => _t('Сценарии', 'Scenarios');
  String get navCompany => _t('Компания', 'Company');

  // —— Auth / login ——
  String get loginTitle => _t('Войти в Аспект', 'Log in to Aspect');
  String get loginSubtitle => _t(
        'Продолжите работу с вашей компанией. Введите свои данные с приложения Альфа-Бизнес',
        'Continue with your company. Enter your Alfa Business credentials',
      );
  String get workEmail => _t('Рабочая почта', 'Work email');
  String get emailHint => 'name@company.ru';
  String get password => _t('Пароль', 'Password');
  String get forgotPassword => _t('Забыли пароль?', 'Forgot password?');
  String get signIn => _t('Войти', 'Log in');
  String get demoLoginVia => _t('Демо вход через', 'Demo sign-in via');
  String get noAccount => _t('Нет аккаунта? ', 'No account? ');
  String get registerAction => _t('Зарегистрируйтесь', 'Sign up');
  String get defaultUserName => _t('Пользователь Аспект', 'Aspect user');

  // —— Register / code ——
  String get registerTitle => _t('Регистрация', 'Sign up');
  String get codeTitle => _t('Подтверждение кода', 'Code confirmation');
  String get codeSentTo => _t('Код отправлен', 'Code sent');
  String verifyHintEmail(String email) => _t('на почту $email', 'to $email');

  // —— Settings ——
  String get settingsTitle => _t('Настройки', 'Settings');
  String get settingsBackCompany => _t('‹ Компания', '‹ Company');
  String get sectionNotifications => _t('Уведомления', 'Notifications');
  String get pushNotifications => _t('Push-уведомления', 'Push notifications');
  String get pushNotificationsSub =>
      _t('События и важные изменения', 'Events and important updates');
  String get notifPermissionTitle =>
      _t('Разрешите уведомления', 'Allow notifications');
  String get notifPermissionBody => _t(
        'Аспект будет сообщать о важных событиях и изменениях по вашей компании. Без уведомлений можно пропустить критичные сигналы.',
        'Aspect will notify you about important events and changes for your company. Without notifications you may miss critical signals.',
      );
  String get telegramAlerts =>
      _t('Уведомления в Telegram', 'Telegram notifications');
  String get telegramAlertsSub => _t(
        'Присылать важные сообщения в Telegram',
        'Send important messages to Telegram',
      );
  String get quietHours => _t('Тихие часы', 'Quiet hours');
  String get quietHoursOffSub =>
      _t('Не беспокоить ночью', 'Do not disturb at night');
  String get quietStart => _t('Начало', 'Start');
  String get quietEnd => _t('Конец', 'End');
  String get sectionApp => _t('Приложение', 'App');
  String get language => _t('Язык', 'Language');
  String get languageRu => _t('Русский', 'Russian');
  String get languageEn => _t('English', 'English');
  String get theme => _t('Тема', 'Theme');
  String get themeLight => _t('Светлая', 'Light');
  String get themeDark => _t('Тёмная', 'Dark');
  String get themeSystem => _t('Системная', 'System');
  String get sectionAbout => _t('О приложении', 'About');
  String get version => _t('Версия', 'Version');
  String get privacy => _t('Политика', 'Privacy');
  String get support => _t('Поддержка', 'Support');
  String get deleteAccount => _t('Удалить аккаунт', 'Delete account');
  String get deleteAccountTitle => _t('Удалить аккаунт?', 'Delete account?');
  String get deleteAccountBody => _t(
        'Вы уверены? После подтверждения кода на почте аккаунт будет удалён.',
        'Are you sure? After email code confirmation the account will be deleted.',
      );
  String get deleteAccountNoEmail => _t(
        'Не удалось отправить код: почта не указана',
        'Could not send code: email is missing',
      );

  // —— Company ——
  String get companyTitle => _t('Компания', 'Company');
  String get myData => _t('Мои данные', 'My data');
  String get settings => _t('Настройки', 'Settings');
  String get logout => _t('Выйти', 'Log out');
  String get logoutConfirmTitle => _t('Выйти из аккаунта?', 'Log out?');
  String get logoutConfirmBody => _t(
        'Вы выйдете из Аспекта. Для входа снова понадобятся данные.',
        'You will leave Aspect. You will need to sign in again.',
      );
  String get telegramConnect => _t('Подключить Telegram', 'Connect Telegram');
  String get telegramConnected => _t('Telegram подключён', 'Telegram connected');
  String get finance => _t('Финансы', 'Finance');
  String get counterparties => _t('Контрагенты', 'Counterparties');
  String get companyCard => _t('Карточка компании', 'Company card');
  String get yourCompany => _t('Ваша компания', 'Your company');
  String get yourContext => _t('Ваш контекст', 'Your context');
  String get emptyPlaceholder => _t('Пока пусто', 'Nothing yet');
  String get sectionProducts => _t('Продукты', 'Products');
  String get sectionMarkets => _t('Рынки', 'Markets');
  String get sectionGeography => _t('География', 'Geography');
  String get counterpartiesAndLinks =>
      _t('Контрагенты и связи', 'Counterparties and links');
  String get companyNameMissing =>
      _t('Компания не указана', 'Company not specified');
  String get industryNotSpecified =>
      _t('Отрасль не указана', 'Industry not specified');
  String get companySizeMissing =>
      _t('Размер не указан', 'Size not specified');
  String get logoutFromAccount =>
      _t('Выйти из аккаунта', 'Log out of account');
  String get telegramDisconnect => _t('Отключить', 'Disconnect');
  String get telegramEventsSub => _t(
        'Уведомления о событиях и сценариях',
        'Alerts for events and scenarios',
      );
  String get selectHint => _t('Выберите', 'Select');

  // —— Overview / events / scenarios ——
  String overviewGreeting(String name) =>
      _t('Здравствуйте, $name', 'Hello, $name');
  String overviewGoodMorning(String name) =>
      _t('Доброе утро, $name', 'Good morning, $name');
  String get eventsTitle =>
      _t('Главные новости для вас', 'Top news for you');
  String get eventsSubtitle => _t(
        'Сигналы, отобранные для вашей компании',
        'Signals selected for your company',
      );
  String get filterAll => _t('Все', 'All');
  String get filterNew => _t('Новые', 'New');
  String get filterHighImpact => _t('Высокое влияние', 'High impact');
  String get whyForYou => _t('Почему вам:', 'Why it matters to you:');
  String get openImpact => _t('Открыть влияние', 'Open impact');
  String get openAction => _t('Открыть', 'Open');
  String get viewScenario =>
      _t('Посмотреть сценарий', 'View scenario');
  String get onWatch => _t('На контроле', 'On watch');
  String get feedNoCompanyTitle =>
      _t('Компания не выбрана', 'No company selected');
  String get feedNoCompanyBody => _t(
        'Завершите онбординг компании, чтобы увидеть персональную ленту.',
        'Finish company onboarding to see your personal feed.',
      );
  String get feedErrorTitle =>
      _t('Не удалось загрузить ленту', 'Could not load feed');
  String get feedErrorBody => _t(
        'Проверьте соединение с API. Demo-события не подставляются.',
        'Check the API connection. Demo events are not substituted.',
      );
  String get feedEmptyTitle =>
      _t('Пока нет персональных событий', 'No personal events yet');
  String get feedEmptyBody => _t(
        'Для вашей компании сейчас нет совпадений в персональной ленте.',
        'There are no matches in your personal feed right now.',
      );
  String get telegramPending => _t(
        'Откройте бота и подтвердите связь. Статус обновится после подтверждения.',
        'Open the bot and confirm linking. Status updates after confirmation.',
      );
  String get bankEvidenceUnavailable => _t(
        'Банковские материалы для этого события не подключены или не найдены.',
        'Bank materials for this event are not configured or not found.',
      );
  String get countryChina => _t('Китай', 'China');
  String get countryArmenia => _t('Армения', 'Armenia');
  String get countrySouthKorea => _t('Южная Корея', 'South Korea');
  String get eventChinaTitle => _t(
        'Китай ограничивает экспорт электроники',
        'China restricts electronics exports',
      );
  String get eventChinaContext => _t(
        'Китай указан как страна поставки электронных компонентов',
        'China is listed as a supply country for electronic components',
      );
  String get eventChinaWarning => _t(
        'Риск роста себестоимости и переноса сроков поставки',
        'Risk of higher costs and delayed deliveries',
      );
  String get eventCnyTitle => _t(
        'Курс CNY вырос на 1,8% за неделю',
        'CNY rose 1.8% over the week',
      );
  String get eventCnyContext => _t(
        'Валюта используется в расчетах с поставщиками',
        'Currency is used in supplier settlements',
      );
  String get eventKzTitle => _t(
        'Спрос на электронику в Казахстане растет',
        'Electronics demand is growing in Kazakhstan',
      );
  String get eventKzContext => _t(
        'Казахстан указан как рынок сбыта',
        'Kazakhstan is listed as a sales market',
      );
  String get scenarioChinaSub => _t(
        'Аспект: подготовил сценарии для поставок',
        'Aspect: prepared supply scenarios',
      );
  String get scenarioCnySub => _t(
        'Аспект: оценил влияние на покупки',
        'Aspect: assessed impact on purchases',
      );
  String get scenarioKzSub => _t(
        'Аспект: Возможное окно для роста',
        'Aspect: a possible growth window',
      );
  String get mondayShort => _t('Пн', 'Mon');
  String impactMeta(String impact, String when) => '$impact · $when';
  String get scenariosTitle => _t('Сценарии', 'Scenarios');
  String get scenariosSubtitle =>
      _t('Диалоги по важным событиям', 'Dialogs on important events');
  String get scenariosSearchHint =>
      _t('Поиск по событиям', 'Search events');
  String get discussWithAspect =>
      _t('Обсудить с Аспект', 'Discuss with Aspect');

  // —— Chat / plan ——
  String get actionPlan => _t('План действий', 'Action plan');
  String get confirmPlan => _t('Подтвердить план', 'Confirm plan');
  String get savedPlan => _t('Сохранённый план', 'Saved plan');
  String get bankMaterials => _t('Материалы банка', 'Bank materials');
  String get conclusionBasis =>
      _t('Основания выводов', 'Conclusion basis');
  String get send => _t('Отправить', 'Send');
  String get messageHint =>
      _t('Напишите сообщение…', 'Write a message…');
  String get aiExplanation => _t('AI-объяснение', 'AI explanation');
  String get showThreeScenarios =>
      _t('Покажи 3 сценария', 'Show 3 scenarios');
  String get showBankMaterial =>
      _t('Показать материал банка', 'Show bank material');
  String get askAboutEvent =>
      _t('Спросите об этом событии', 'Ask about this event');
  String get backEvent => _t('Событие', 'Event');
  String get eventAnalysis => _t('Разбор события', 'Event analysis');
  String get discussionBack => _t('Обсуждение', 'Discussion');
  String get actionOptions => _t('Варианты действий', 'Action options');
  String get qualityComparison =>
      _t('Качественное сравнение', 'Qualitative comparison');
  String get selectForPlan =>
      _t('Выбрать для плана', 'Select for plan');
  String planForEvent(String eventTitle) => _t(
        'По событию «$eventTitle»',
        'For event «$eventTitle»',
      );
  String get whyThisOption =>
      _t('Почему выбран этот вариант', 'Why this option');
  String get confirmAndSave =>
      _t('Подтвердить и сохранить', 'Confirm and save');
  String progressCompleted(int done, int total) => _t(
        'Выполнено $done из $total',
        '$done of $total completed',
      );
  String get changePlan => _t('Сменить план', 'Change plan');
  String get planHistoryNote => _t(
        'Предыдущие выводы сохранены в истории обсуждения.',
        'Previous conclusions are saved in the discussion history.',
      );
  String get bankMaterialHeading =>
      _t('Материал Банка', 'Bank material');
  String get openOriginalDocument =>
      _t('Открыть оригинал документа', 'Open original document');
  String get conclusionBasisHeading =>
      _t('На чем основан вывод', 'What the conclusion is based on');
  String get conclusionBasisPrompt =>
      _t('На чем основан вывод?', 'What is the conclusion based on?');
  String get backMyData => _t('‹ Мои данные', '‹ My data');
  String get passwordSection => _t('Пароль', 'Password');
  String get currentPasswordHint =>
      _t('Введите текущий пароль', 'Enter current password');
  String get newPasswordMinHint =>
      _t('Не меньше 6 символов', 'At least 6 characters');
  String get confirmNewPasswordHint =>
      _t('Повторите новый пароль', 'Re-enter new password');
  String get wrongCurrentPassword => _t(
        'Текущий пароль неверный',
        'Current password is incorrect',
      );
  String get savePassword => _t('Сохранить пароль', 'Save password');
  String get createAccount => _t('Создайте аккаунт', 'Create an account');
  String get registerSubtitle => _t(
        'Рабочая почта подойдёт лучше всего',
        'A work email works best',
      );
  String get fullName => _t('ФИО', 'Full name');
  String get fullNameHint => _t('Иванов Иван Иванович', 'John Smith');
  String get passwordMin8Hint =>
      _t('Не менее 8 символов', 'At least 8 characters');
  String get acceptTerms => _t(
        'Принимаю условия использования и политику данных',
        'I accept the terms of use and data policy',
      );
  String get alreadyHaveAccount =>
      _t('Уже есть аккаунт? ', 'Already have an account? ');
  String get codeConfirmHeading => _t('Подтверждение', 'Confirmation');
  String codeSentBody(String maskedEmail) => _t(
        'Мы отправили код на почту\n$maskedEmail',
        'We sent a code to\n$maskedEmail',
      );
  String get codeFromEmail => _t('КОД ИЗ ПИСЬМА', 'CODE FROM EMAIL');
  String get wrongCode => _t('Неверный код', 'Incorrect code');
  String get resendCode => _t('Отправить код повторно', 'Resend code');
  String resendCodeIn(String timer) => _t(
        'Отправить код повторно через $timer',
        'Resend code in $timer',
      );
  String get financeSubtitle => _t(
        'Банковские продукты и параметры расчёта',
        'Bank products and calculation parameters',
      );
  String get productsFromSource =>
      _t('Продукты по данным источника', 'Products from source data');
  String get forFinanceScenarios =>
      _t('Для финансовых сценариев', 'For financial scenarios');
  String get noMonetaryCalcYet =>
      _t('Пока без денежного расчёта', 'No monetary calculation yet');
  String get noMonetaryCalcBody => _t(
        'Наличие кредита не раскрывает его условия. Нужны параметры долга и ставок.',
        'Having a loan does not reveal its terms. Debt and rate parameters are needed.',
      );
  String get supplementFinanceParams => _t(
        'Дополнить финансовые параметры',
        'Add financial parameters',
      );
  String get counterpartiesSubtitle => _t(
        'Разные типы связей — разные основания',
        'Different link types — different grounds',
      );
  String get paymentLinks => _t('Платежные связи', 'Payment links');
  String get companyGroupSection =>
      _t('Группа компаний', 'Company group');
  String get listedSuppliers =>
      _t('Указанные поставщики', 'Listed suppliers');
  String get supplierNameHint =>
      _t('Название поставщика', 'Supplier name');
  String get addSupplier => _t('+ Добавить поставщика', '+ Add supplier');
  String get supplierRole => _t('Поставщик', 'Supplier');
  String get sourcePrefix => _t('Источник: ', 'Source: ');
  String get whatHappened => _t('Что произошло', 'What happened');
  String get whatItMeansForYou =>
      _t('Что это значит для вас', 'What this means for you');
  String get riskLabel => _t('Риск:', 'Risk:');
  String get opportunityLabel => _t('Возможность:', 'Opportunity:');
  String get nextActionTitle =>
      _t('Следующее действие', 'Next action');
  String get alfaBankAnalytics =>
      _t('Аналитика Альфа-Банка', 'Alfa-Bank analytics');
  String get viewMaterial => _t('Посмотреть материал', 'View material');

  // —— Alfa Business demo ——
  String get enterAspect => _t('Войти в Аспект', 'Enter Aspect');
  String get aspectCardTitle => _t('Аспект', 'Aspect');
  String get aspectCardBody => _t(
        'Аспект — помощник для бизнеса на данных Альфа-Бизнес. Следите за новостями отрасли и тем, что влияет на компанию. Смотрите финансы, контрагентов и собирайте план действий. Входите одним нажатием — компания подтянется из банка.',
        'Aspect is a business assistant powered by Alfa Business data. Track industry news and what affects your company. Review finances and counterparties, and build an action plan. Sign in in one tap — your company comes from the bank.',
      );
  String get chooseCompany => _t('Выберите компанию', 'Choose a company');
  String get chooseCompanySub => _t(
        'Компания из Альфа-Бизнес для работы в Аспекте',
        'A company from Alfa Business for Aspect',
      );
  String get companySearchHint =>
      _t('Поиск компании', 'Search company');
  String get companyPickerTitle =>
      _t('Выбор компании', 'Select company');
  String get tasksInProgress => _t('Дела в работе', 'Tasks in progress');
  String get availableBalance =>
      _t('Доступный остаток', 'Available balance');
  String onRubleAccounts(int n) =>
      _t('на $n рублёвых счетах', 'across $n ruble accounts');
  String get allAccountsCards =>
      _t('Все счета и карты', 'All accounts and cards');
  String get myProducts => _t('Мои продукты', 'My products');
  String get profile => _t('Профиль', 'Profile');
  String get companyData => _t('Данные компании', 'Company data');

  // —— Password ——
  String get changePassword => _t('Сменить пароль', 'Change password');
  String get currentPassword => _t('Текущий пароль', 'Current password');
  String get newPassword => _t('Новый пароль', 'New password');
  String get confirmPassword =>
      _t('Повторите пароль', 'Confirm password');

  // —— Impact ——
  String get impactHigh => _t('Высокое влияние', 'High impact');
  String get impactMedium => _t('Среднее влияние', 'Medium impact');
  String get impactOpportunity => _t('Возможность', 'Opportunity');

  // —— Dates (simple) ——
  String get today => _t('Сегодня', 'Today');
  String get yesterday => _t('Вчера', 'Yesterday');
  String get yearSuffix => _t('г.', '');
  List<String> get monthGenitive => isRu
      ? const [
          'января',
          'февраля',
          'марта',
          'апреля',
          'мая',
          'июня',
          'июля',
          'августа',
          'сентября',
          'октября',
          'ноября',
          'декабря',
        ]
      : const [
          'January',
          'February',
          'March',
          'April',
          'May',
          'June',
          'July',
          'August',
          'September',
          'October',
          'November',
          'December',
        ];
  String formatDate(DateTime d) {
    final month = monthGenitive[d.month - 1];
    final suffix = yearSuffix.isEmpty ? '' : ' $yearSuffix';
    return isRu
        ? '${d.day} $month ${d.year}$suffix'
        : '$month ${d.day}, ${d.year}';
  }

  // —— Welcome ——
  String get welcomeHeadlineLead =>
      _t('Перемены именно для\n', 'Change made for\n');
  String get welcomeHeadlineAccent =>
      _t('вашего бизнеса', 'your business');
  String get welcomeSubtitle => _t(
        'События, которые влияют на вашу компанию. '
        'Последствия и варианты действий - в одном месте.',
        'Events that affect your company. '
        'Impact and options in one place.',
      );
  String get welcomeCreateAccount =>
      _t('Создать аккаунт', 'Create account');
  String get welcomeSignIn => _t('Войти', 'Log in');
  String get welcomeInsightCard =>
      _t('Персональные\nинсайты', 'Personal\ninsights');
  String get welcomeRisksCard =>
      _t('Риски и\nвозможности', 'Risks and\nopportunities');

  // —— Onboarding ——
  String get innLabel => _t('ИНН', 'INN');
  String get onboardingChange => _t('Изменить', 'Change');
  String get onboardingThisIsMyCompany =>
      _t('Это моя компания', 'This is my company');
  String get onboardingCompanyFooterHint => _t(
        'Данные компании можно будет исправить. И дополнить на следующем шаге.',
        'You can fix company details and add more on the next step.',
      );
  String get onboardingCompanyTitle =>
      _t('Ваша компания', 'Your company');
  String get onboardingCompanySubtitle => _t(
        'Найдите компанию по названию или ИНН. Мы подставим открытые данные для проверки.',
        'Find your company by name or tax ID. We will fill in public data for review.',
      );
  String get onboardingCompanyQueryLabel =>
      _t('Название или ИНН', 'Name or tax ID');
  String get onboardingCompanyQueryHint => _t(
        'Введите название или ИНН',
        'Enter name or tax ID',
      );
  String get onboardingNotInList => _t('Нет в списке? ', 'Not listed? ');
  String get onboardingAddManually =>
      _t('Добавить вручную', 'Add manually');
  String get onboardingVerifyTitle =>
      _t('Проверьте данные', 'Review details');
  String get onboardingVerifySubtitle => _t(
        'Мы нашли открытую карточку компании',
        'We found a public company profile',
      );
  String get onboardingYourRole => _t('Ваша роль', 'Your role');
  String get onboardingCompanySize =>
      _t('Размер компании', 'Company size');
  String get onboardingConfirmData =>
      _t('Подтвердить данные', 'Confirm details');
  String get onboardingVerifyFooterHint => _t(
        'Эти сведения нужны, чтобы подобрать релевантные события и отраслевые источники.',
        'This helps us pick relevant events and industry sources.',
      );
  String get onboardingBusinessTitle =>
      _t('Чем занимается бизнес?', 'What does the business do?');
  String get onboardingBusinessSubtitle =>
      _t('Выберите основное направление', 'Choose the main focus');
  String get onboardingProductsTitle =>
      _t('Что вы производите?', 'What do you make?');
  String get onboardingProductsSubtitle => _t(
        'Добавьте ключевые продукты. Так мы поймём, какие изменения важны.',
        'Add key products so we know which changes matter.',
      );
  String get onboardingProductsSection =>
      _t('ПРОДУКТЫ', 'PRODUCTS');
  String get onboardingProductNameHint =>
      _t('Название продукта', 'Product name');
  String get onboardingAddProduct =>
      _t('+ Добавить продукт', '+ Add product');
  String get onboardingMainMarket =>
      _t('Основной рынок', 'Primary market');
  String get onboardingSpecifyMarket =>
      _t('Укажите рынок', 'Specify market');
  String get onboardingMarketHintExample => _t(
        'Например, Ближний Восток',
        'For example, Middle East',
      );
  String get onboardingProductsFooterHint => _t(
        'Можно добавить детали позже. Начните с двух-трёх ключевых продуктов.',
        'You can add details later. Start with two or three key products.',
      );
  String get onboardingCountriesTitle => _t(
        'Страны поставок и партнёров',
        'Supply and partner countries',
      );
  String get onboardingCountriesSubtitle => _t(
        'Укажите страны, откуда идут производство, сырьё или комплектующие. Мы отберём события, которые влияют на вашу цепочку поставок.',
        'List countries for production, raw materials, or parts. We will filter events that affect your supply chain.',
      );
  String get onboardingCountriesSection =>
      _t('СТРАНЫ', 'COUNTRIES');
  String get onboardingAllCountriesAdded => _t(
        'Все страны добавлены',
        'All countries added',
      );
  String get onboardingAddCountry =>
      _t('+ Добавить страну', '+ Add country');
  String get onboardingCountriesFooterHint => _t(
        'Можно уточнить позже. Достаточно двух-трёх стран из цепочки поставок.',
        'You can refine later. Two or three countries from your chain is enough.',
      );
  String get onboardingLocationsTitle =>
      _t('Где работает бизнес?', 'Where does the business operate?');
  String get onboardingLocationsSubtitle => _t(
        'Сначала выберите регионы продаж, затем укажите города в этих странах.',
        'First pick sales regions, then cities in those countries.',
      );
  String get onboardingSalesRegionsSection =>
      _t('РЕГИОНЫ ПРОДАЖ', 'SALES REGIONS');
  String get onboardingCitiesSection => _t('ГОРОДА', 'CITIES');
  String get onboardingAllRegionsAdded => _t(
        'Все регионы добавлены',
        'All regions added',
      );
  String get onboardingAddRegion =>
      _t('+ Добавить регион', '+ Add region');
  String get onboardingLoadingCities =>
      _t('Загрузка городов…', 'Loading cities…');
  String get onboardingSelectRegionFirst => _t(
        'Сначала выберите регион',
        'Select a region first',
      );
  String get onboardingAddCity =>
      _t('+ Добавить город', '+ Add city');
  String get onboardingPickCityTitle =>
      _t('Выберите город', 'Choose a city');
  String get onboardingSearchCityHint =>
      _t('Поиск города', 'Search city');
  String onboardingCityCount(int shown, int total) => _t(
        '$shown из $total',
        '$shown of $total',
      );
  String get onboardingNothingFound =>
      _t('Ничего не найдено', 'Nothing found');
  String get onboardingReviewTitle =>
      _t('Проверьте профиль', 'Review profile');
  String get onboardingYourCompanySection =>
      _t('ВАША КОМПАНИЯ', 'YOUR COMPANY');
  String get onboardingReviewWhatBusiness =>
      _t('Чем занимается?', 'Business focus');
  String get onboardingReviewDirection =>
      _t('Направление', 'Segment');
  String get onboardingReviewSalesRegions =>
      _t('Регионы продаж', 'Sales regions');
  String get onboardingReviewCities => _t('Города', 'Cities');
  String get emptyValueDash => '—';
}

class _L10nScope extends InheritedWidget {
  const _L10nScope({required this.l10n, required super.child});

  final AppLocalizations l10n;

  @override
  bool updateShouldNotify(_L10nScope oldWidget) =>
      l10n.locale != oldWidget.l10n.locale;
}

extension AppLocalizationsX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}

Widget wrapWithL10n({required Locale locale, required Widget child}) {
  return _L10nScope(
    l10n: AppLocalizations(locale),
    child: child,
  );
}
