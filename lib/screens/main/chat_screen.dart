import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'dart:async';

import '../../api/api_exception.dart';
import '../../api/events_api.dart';
import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/assistant_markdown.dart';
import '../../widgets/main_widgets.dart';
import 'action_plan_screen.dart';
import 'bank_material_screen.dart';
import 'confirm_plan_screen.dart';
import 'saved_plan_screen.dart';

class _BankEvidenceItem {
  const _BankEvidenceItem({
    required this.title,
    required this.body,
    required this.typeLabel,
    required this.meta,
  });
  final String title;
  final String body;
  final String typeLabel;
  final String meta;
}

class _ChatLine {
  const _ChatLine({
    required this.role,
    required this.text,
    this.analysisSteps = const [],
    this.bankEvidence = const [],
  });
  final String role; // user | assistant
  final String text;
  final List<String> analysisSteps;
  final List<_BankEvidenceItem> bankEvidence;
}

String _bankContentTypeLabel(String? raw) {
  switch ((raw ?? '').toLowerCase()) {
    case 'fact':
      return 'Факт из материала';
    case 'forecast':
      return 'Прогноз банка';
    case 'interpretation':
      return 'Оценка банка';
    default:
      return '';
  }
}

String _formatBankMeta(Map item) {
  final parts = <String>[];
  final pub = (item['publication_date'] ?? '').toString().trim();
  if (pub.isNotEmpty) {
    // Keep ISO date readable: 2026-09-11 → 11.09.2026 when possible
    final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})').firstMatch(pub);
    parts.add(m != null ? '${m[3]}.${m[2]}.${m[1]}' : pub);
  }
  final page = item['page_number'];
  if (page is num) parts.add('стр. ${page.toInt()}');
  return parts.join(' · ');
}

List<_BankEvidenceItem> _bankEvidenceFromBlocks(dynamic blocks) {
  if (blocks is! List) return const [];
  final out = <_BankEvidenceItem>[];
  for (final raw in blocks) {
    if (raw is! Map) continue;
    if ((raw['type'] ?? '').toString() != 'bank_evidence_list') continue;
    final data = raw['data'];
    if (data is! Map) continue;
    final used = data['used'];
    if (used is! List) continue;
    for (final u in used) {
      if (u is! Map) continue;
      final title = (u['document_title'] ?? 'Документ банка').toString().trim();
      final body = (u['text'] ?? '').toString().trim();
      if (title.isEmpty && body.isEmpty) continue;
      out.add(
        _BankEvidenceItem(
          title: title.isEmpty ? 'Документ банка' : title,
          body: body,
          typeLabel: _bankContentTypeLabel(u['content_type']?.toString()),
          meta: _formatBankMeta(u),
        ),
      );
      if (out.length >= 6) return out;
    }
  }
  return out;
}

_ChatLine? _lineFromMessage(Map raw) {
  final role = (raw['role'] ?? '').toString();
  final content = (raw['content'] ?? '').toString();
  final bank = _bankEvidenceFromBlocks(raw['blocks']);
  if (content.isEmpty && bank.isEmpty) return null;
  return _ChatLine(
    role: role,
    text: content,
    bankEvidence: bank,
  );
}

class ChatScreenData {
  const ChatScreenData({
    required this.title,
    required this.meta,
    required this.level,
    this.backLabel,
    this.eventId,
  });

  final String title;
  final String meta;
  final ImpactLevel level;
  final String? backLabel;
  final String? eventId;
}

const chinaExportChat = ChatScreenData(
  title: 'Китай ограничивает экспорт электроники',
  meta: 'Высокое влияние · Сегодня 08:24',
  level: ImpactLevel.high,
);

Future<void> openChatScreen(
  BuildContext context,
  ChatScreenData data,
) {
  return Navigator.of(context).push(
    AppPageRoute<void>(
      builder: (_) => ChatScreen(data: data),
    ),
  );
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.data});

  final ChatScreenData data;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  static const _thinkingPhases = [
    'Смотрю материалы и контекст компании…',
    'Сопоставляю событие с профилем…',
    'Формулирую ответ…',
  ];

  ConfirmPlanData? _savedPlan;
  final _input = TextEditingController();
  final _scroll = ScrollController();
  String? _conversationId;
  bool _busy = false;
  bool _apiMode = false;
  List<_ChatLine> _lines = const [];
  List<String> _chips = const [];
  String _thinkingLabel = _thinkingPhases.first;
  Timer? _thinkingTimer;
  int _thinkingPhase = 0;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _thinkingTimer?.cancel();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _startThinking() {
    _thinkingTimer?.cancel();
    _thinkingPhase = 0;
    _thinkingLabel = _thinkingPhases.first;
    _thinkingTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!mounted || !_busy) return;
      setState(() {
        _thinkingPhase = (_thinkingPhase + 1) % _thinkingPhases.length;
        _thinkingLabel = _thinkingPhases[_thinkingPhase];
      });
      _scrollToEnd(jump: true);
    });
  }

  void _stopThinking() {
    _thinkingTimer?.cancel();
    _thinkingTimer = null;
  }

  Future<void> _reloadMessages() async {
    final convId = _conversationId;
    if (convId == null || convId.isEmpty) return;
    try {
      final msgs = await EventsApi.instance.listMessages(convId);
      final items = (msgs['items'] as List?) ??
          (msgs['messages'] as List?) ??
          const [];
      final lines = <_ChatLine>[];
      for (final raw in items) {
        if (raw is! Map) continue;
        final line = _lineFromMessage(Map<String, dynamic>.from(raw));
        if (line != null) lines.add(line);
      }
      if (!mounted || lines.isEmpty) return;
      setState(() => _lines = lines);
    } catch (_) {}
  }

  Future<void> _bootstrap() async {
    final eventId = widget.data.eventId;
    final companyId = await AuthStore.companyId();
    if (eventId == null ||
        eventId.isEmpty ||
        companyId == null ||
        companyId.isEmpty) {
      return;
    }
    try {
      final conv = await EventsApi.instance.createAssistantConversation(
        eventId: eventId,
        companyId: companyId,
      );
      final id = conv['id']?.toString();
      if (id == null || id.isEmpty) return;
      final msgs = await EventsApi.instance.listMessages(id);
      final items = (msgs['items'] as List?) ??
          (msgs['messages'] as List?) ??
          const [];
      final lines = <_ChatLine>[];
      for (final raw in items) {
        if (raw is! Map) continue;
        final line = _lineFromMessage(Map<String, dynamic>.from(raw));
        if (line != null) lines.add(line);
      }
      final chips = [
        for (final c in (conv['suggestion_chips'] as List?) ?? const [])
          if (c != null && c.toString().trim().isNotEmpty) c.toString(),
      ];
      if (!mounted) return;
      setState(() {
        _conversationId = id;
        _apiMode = true;
        _lines = lines;
        _chips = chips;
      });
      _scrollToEnd(jump: true);
    } catch (_) {
      // Empty history on API failure — do not invent a transcript.
      if (!mounted) return;
      setState(() {
        _apiMode = false;
        _lines = const [];
        _chips = const [];
      });
    }
  }

  Future<void> _send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _busy) return;
    _input.clear();
    setState(() {
      _lines = [..._lines, _ChatLine(role: 'user', text: trimmed)];
      _busy = true;
    });
    _startThinking();
    _scrollToEnd();
    final convId = _conversationId;
    if (!_apiMode || convId == null) {
      _stopThinking();
      setState(() => _busy = false);
      return;
    }
    try {
      final res = await EventsApi.instance.postMessage(
        conversationId: convId,
        content: trimmed,
        clientMessageId: 'c_${DateTime.now().microsecondsSinceEpoch}',
      );
      final assistant = res['assistant_message'] ?? res['message'] ?? res;
      String reply = '';
      List<_BankEvidenceItem> bank = const [];
      if (assistant is Map) {
        reply = (assistant['content'] ?? '').toString();
        bank = _bankEvidenceFromBlocks(assistant['blocks']);
      }
      if (reply.isEmpty && res['content'] != null) {
        reply = res['content'].toString();
      }
      final steps = <String>[
        for (final s in (res['analysis_steps'] as List?) ?? const [])
          if (s != null && s.toString().trim().isNotEmpty) s.toString().trim(),
      ];
      if (!mounted) return;
      _stopThinking();
      setState(() {
        if (reply.isNotEmpty || steps.isNotEmpty || bank.isNotEmpty) {
          _lines = [
            ..._lines,
            _ChatLine(
              role: 'assistant',
              text: reply.isEmpty && bank.isEmpty
                  ? 'Анализ выполнен.'
                  : reply,
              analysisSteps: steps,
              bankEvidence: bank,
            ),
          ];
        }
        _busy = false;
      });
      _scrollToEnd();
    } on ApiException catch (e) {
      // 504: ответ уже мог сохраниться в истории на сервере.
      await _reloadMessages();
      if (!mounted) return;
      _stopThinking();
      final alreadyHasReply = _lines.isNotEmpty &&
          _lines.last.role == 'assistant' &&
          _lines.last.text.trim().isNotEmpty;
      setState(() {
        _busy = false;
        if (!alreadyHasReply) {
          _lines = [
            ..._lines,
            _ChatLine(
              role: 'assistant',
              text: e.message.isNotEmpty
                  ? e.message
                  : 'Не удалось завершить разбор. Попробуйте ещё раз.',
            ),
          ];
        }
      });
      _scrollToEnd();
    } catch (_) {
      await _reloadMessages();
      if (!mounted) return;
      _stopThinking();
      final alreadyHasReply = _lines.isNotEmpty &&
          _lines.last.role == 'assistant' &&
          _lines.last.text.trim().isNotEmpty;
      setState(() {
        _busy = false;
        if (!alreadyHasReply) {
          _lines = [
            ..._lines,
            const _ChatLine(
              role: 'assistant',
              text:
                  'Сервер ещё обрабатывает ответ или сеть оборвалась. Откройте чат снова или отправьте вопрос ещё раз.',
            ),
          ];
        }
      });
      _scrollToEnd();
    }
  }

  void _scrollToEnd({bool jump = false}) {
    void go() {
      if (!mounted || !_scroll.hasClients) return;
      final target = _scroll.position.maxScrollExtent;
      if (jump) {
        _scroll.jumpTo(target);
      } else {
        _scroll.animateTo(
          target,
          duration: const Duration(milliseconds: 280),
          curve: Curves.easeOut,
        );
      }
    }

    // Два кадра: после setState список ещё может не знать maxScrollExtent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      go();
      WidgetsBinding.instance.addPostFrameCallback((_) => go());
    });
  }

  Future<void> _openScenarios() async {
    final plan = await openActionPlanScreen(
      context,
      eventTitle: widget.data.title,
    );
    if (plan != null && mounted) {
      setState(() => _savedPlan = plan);
    }
  }

  Future<void> _openSavedPlan() async {
    final plan = _savedPlan;
    if (plan == null) return;
    final updated = await openSavedPlanScreen(context, plan);
    if (updated != null && mounted) {
      setState(() => _savedPlan = updated);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final accent = ImpactColors.accent(widget.data.level);
    const hPad = AppColors.screenPadding;
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final backLabel = widget.data.backLabel ?? l10n.navScenarios;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Material(
                color: AppColors.surface,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(hPad * s, 8 * s, hPad * s, 0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GestureDetector(
                        onTap: () => Navigator.of(context).maybePop(),
                        behavior: HitTestBehavior.opaque,
                        child: Text(
                          '‹ $backLabel',
                          style: AppTypography.regular(
                            15 * s,
                            color: AppColors.brandRed,
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Container(
                            width: 3.8 * s,
                            height: 40 * s,
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(2 * s),
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Text(
                              widget.data.title,
                              style: AppTypography.bold(
                                18.88 * s,
                                color: AppColors.textInput,
                              ),
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 10 * s),
                      IntrinsicWidth(
                        child: Container(
                          height: 25 * s,
                          padding: EdgeInsets.symmetric(horizontal: 6 * s),
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: AppColors.brandRed,
                            borderRadius: BorderRadius.circular(6 * s),
                          ),
                          child: Text(
                            l10n.aiExplanation,
                            softWrap: false,
                            style: AppTypography.medium(
                              9.4 * s,
                              color: AppColors.surface,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      Divider(
                        height: 1 * s,
                        thickness: 1 * s,
                        color: Colors.black.withValues(alpha: 0.1),
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  controller: _scroll,
                  padding: EdgeInsets.fromLTRB(
                    hPad * s,
                    16 * s,
                    hPad * s,
                    16 * s,
                  ),
                  children: [
                    if (_apiMode) ...[
                      for (var i = 0; i < _lines.length; i++) ...[
                        if (i > 0) SizedBox(height: 12 * s),
                        if (_lines[i].role == 'user')
                          _UserBubble(text: _lines[i].text)
                        else
                          _AspectBubble(
                            text: _lines[i].text,
                            senderLabel: l10n.appName,
                            analysisSteps: _lines[i].analysisSteps,
                            bankEvidence: _lines[i].bankEvidence,
                            bankMaterialsTitle: l10n.bankMaterials,
                            analysisStepsTitle: 'Шаги анализа',
                            viewMaterialLabel: l10n.viewMaterial,
                            showBankLink: i == 0 &&
                                _lines[i].bankEvidence.isEmpty,
                            bankLinkLabel: l10n.showBankMaterial,
                            onBankLinkTap: i == 0
                                ? () => openBankMaterialScreen(
                                      context,
                                      data: BankMaterialData(
                                        backLabel: l10n.backEvent,
                                      ),
                                    )
                                : null,
                            onOpenBankItem: (item) => openBankMaterialScreen(
                              context,
                              data: BankMaterialData(
                                backLabel: l10n.backEvent,
                                headline: item.title,
                                meta: item.meta.isEmpty
                                    ? 'Материал банка'
                                    : item.meta,
                                fragmentBody: item.body,
                              ),
                            ),
                          ),
                      ],
                      if (_busy) ...[
                        SizedBox(height: 12 * s),
                        _AspectBubble(
                          text: _thinkingLabel,
                          senderLabel: l10n.appName,
                          markdown: false,
                        ),
                      ],
                    ] else ...[
                      _AspectBubble(
                        text:
                            'Я подготовил варианты действий по этой новости. Начнём с влияния на ваши поставки из Китая?',
                        showBankLink: true,
                        senderLabel: l10n.appName,
                        bankLinkLabel: l10n.showBankMaterial,
                        onBankLinkTap: () => openBankMaterialScreen(
                          context,
                          data: BankMaterialData(backLabel: l10n.backEvent),
                        ),
                      ),
                      SizedBox(height: 12 * s),
                      const _UserBubble(text: 'Какие контракты под риском?'),
                      SizedBox(height: 12 * s),
                      _AspectBubble(
                        text:
                            'В первую очередь — контракты с поставкой критичных компонентов в ближайшие 60 дней. Риск выше по договорам без альтернативного поставщика и запаса по срокам.\n\nМогу сравнить три сценария: ждать разъяснений, искать замену или пересогласовать сроки поставки.',
                        senderLabel: l10n.appName,
                      ),
                    ],
                  ],
                ),
              ),
              Material(
                color: AppColors.surface,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(
                    hPad * s,
                    8 * s,
                    hPad * s,
                    12 * s + bottomInset,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            if (_savedPlan == null)
                              _QuickChip(
                                label: l10n.showThreeScenarios,
                                onTap: _openScenarios,
                              )
                            else
                              _QuickChip(
                                label: l10n.actionPlan,
                                filled: true,
                                onTap: _openSavedPlan,
                              ),
                            for (final chip in _chips) ...[
                              SizedBox(width: 8 * s),
                              _QuickChip(
                                label: chip,
                                onTap: () => _send(chip),
                              ),
                            ],
                          ],
                        ),
                      ),
                      SizedBox(height: 10 * s),
                      Container(
                        height: 50 * s,
                        decoration: BoxDecoration(
                          color: Colors.transparent,
                          borderRadius: BorderRadius.circular(10 * s),
                          border: Border.all(
                            color: AppColors.border,
                            width: 1,
                          ),
                        ),
                        padding: EdgeInsets.only(left: 16 * s, right: 10 * s),
                        child: Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _input,
                                textCapitalization:
                                    TextCapitalization.sentences,
                                textInputAction: TextInputAction.send,
                                onSubmitted: _send,
                                style: AppTypography.regular(
                                  15.9 * s,
                                  color: AppColors.textPrimary,
                                ),
                                cursorColor: AppColors.brandRed,
                                decoration: InputDecoration(
                                  isDense: true,
                                  border: InputBorder.none,
                                  filled: false,
                                  hintText: l10n.askAboutEvent,
                                  hintStyle: AppTypography.regular(
                                    15.9 * s,
                                    color: AppColors.textMuted,
                                  ),
                                  contentPadding: EdgeInsets.zero,
                                ),
                              ),
                            ),
                            GestureDetector(
                              onTap: () => _send(_input.text),
                              behavior: HitTestBehavior.opaque,
                              child: SvgPicture.asset(
                                'assets/images/icon_send.svg',
                                width: 30 * s,
                                height: 30 * s,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AspectBubble extends StatelessWidget {
  const _AspectBubble({
    required this.text,
    this.showBankLink = false,
    this.onBankLinkTap,
    this.senderLabel = 'Аспект',
    this.bankLinkLabel = 'Показать материал банка',
    this.analysisSteps = const [],
    this.bankEvidence = const [],
    this.bankMaterialsTitle = 'Материалы банка',
    this.analysisStepsTitle = 'Шаги анализа',
    this.viewMaterialLabel = 'Посмотреть материал',
    this.onOpenBankItem,
    this.markdown = true,
  });

  final String text;
  final bool showBankLink;
  final VoidCallback? onBankLinkTap;
  final String senderLabel;
  final String bankLinkLabel;
  final List<String> analysisSteps;
  final List<_BankEvidenceItem> bankEvidence;
  final String bankMaterialsTitle;
  final String analysisStepsTitle;
  final String viewMaterialLabel;
  final void Function(_BankEvidenceItem item)? onOpenBankItem;
  final bool markdown;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final bodyStyle = AppTypography.regular(
      13 * s,
      color: AppColors.textPrimary,
    ).copyWith(height: 1.35);
    final boldStyle = AppTypography.bold(
      13 * s,
      color: AppColors.textPrimary,
    ).copyWith(height: 1.35);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(left: 10 * s),
          child: Text(
            senderLabel,
            style: AppTypography.medium(13 * s, color: AppColors.textMuted),
          ),
        ),
        SizedBox(height: 10 * s),
        Align(
          alignment: Alignment.centerLeft,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: 300 * s),
            child: Container(
              padding: EdgeInsets.all(16 * s),
              decoration: BoxDecoration(
                color: AppColors.card,
                borderRadius: BorderRadius.circular(16 * s),
                border: Border.all(
                  color: AppColors.border,
                  width: 1,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.15),
                    offset: Offset(-1 * s, 0),
                    blurRadius: 5.8 * s,
                    spreadRadius: 0,
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (text.isNotEmpty)
                    markdown
                        ? AssistantMarkdown(
                            text,
                            style: bodyStyle,
                            boldStyle: boldStyle,
                            headingStyle: boldStyle,
                          )
                        : Text(text, style: bodyStyle),
                  if (bankEvidence.isNotEmpty) ...[
                    SizedBox(height: 14 * s),
                    Text(
                      bankMaterialsTitle,
                      style: AppTypography.bold(
                        12 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    SizedBox(height: 8 * s),
                    for (var i = 0; i < bankEvidence.length; i++) ...[
                      if (i > 0) SizedBox(height: 8 * s),
                      BankEvidenceChatCard(
                        title: bankEvidence[i].title,
                        body: bankEvidence[i].body,
                        typeLabel: bankEvidence[i].typeLabel,
                        meta: bankEvidence[i].meta,
                        openLabel: viewMaterialLabel,
                        onOpen: () =>
                            onOpenBankItem?.call(bankEvidence[i]),
                      ),
                    ],
                  ],
                  if (analysisSteps.isNotEmpty) ...[
                    SizedBox(height: 12 * s),
                    Text(
                      analysisStepsTitle,
                      style: AppTypography.bold(
                        12 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    SizedBox(height: 6 * s),
                    for (final step in analysisSteps) ...[
                      Text(
                        '• $step',
                        style: AppTypography.regular(
                          12 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                      SizedBox(height: 2 * s),
                    ],
                  ],
                  if (showBankLink) ...[
                    SizedBox(height: 14 * s),
                    GestureDetector(
                      onTap: onBankLinkTap,
                      behavior: HitTestBehavior.opaque,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Text(
                            bankLinkLabel,
                            style: AppTypography.bold(
                              13 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                          SizedBox(width: 4 * s),
                          Icon(
                            Icons.arrow_forward,
                            size: 14 * s,
                            color: AppColors.brandRed,
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(maxWidth: 248 * s),
        padding: EdgeInsets.all(16 * s),
        decoration: BoxDecoration(
          color: AppColors.brandRed,
          borderRadius: BorderRadius.circular(16 * s),
        ),
        child: Text(
          text,
          style: AppTypography.regular(13 * s, color: AppColors.onBrand),
        ),
      ),
    );
  }
}

class _QuickChip extends StatelessWidget {
  const _QuickChip({
    required this.label,
    required this.onTap,
    this.filled = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 30 * s,
        padding: EdgeInsets.symmetric(horizontal: 10 * s),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: filled ? AppColors.brandRed : Colors.transparent,
          borderRadius: BorderRadius.circular(16 * s),
          border: filled
              ? null
              : Border.all(color: AppColors.textMuted, width: 1),
        ),
        child: Text(
          label,
          style: AppTypography.regular(
            13 * s,
            color: filled ? AppColors.onBrand : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}
