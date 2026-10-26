import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../api/api_client.dart';
import '../../api/api_exception.dart';
import '../../api/support_api.dart';
import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class _Line {
  const _Line({
    required this.id,
    required this.role,
    required this.text,
  });

  final String id;
  final String role; // user | support | system | operator
  final String text;
}

Future<void> openSupportChatScreen(BuildContext context) {
  return Navigator.of(context).push(
    AppPageRoute<void>(builder: (_) => const SupportChatScreen()),
  );
}

class SupportChatScreen extends StatefulWidget {
  const SupportChatScreen({super.key});

  @override
  State<SupportChatScreen> createState() => _SupportChatScreenState();
}

class _SupportChatScreenState extends State<SupportChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  List<_Line> _lines = const [];
  bool _loading = true;
  bool _busy = false;
  String? _error;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _bootstrap();
    // Fast poll so operator replies appear without leaving the screen.
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _pollNew());
  }

  @override
  void dispose() {
    _poll?.cancel();
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final companyId = await AuthStore.companyId();
      final thread = await SupportApi.instance.getThread(companyId: companyId);
      final lines = _parseMessages(thread['messages']);
      if (!mounted) return;
      setState(() {
        _lines = lines;
        _loading = false;
      });
      _scrollToEnd();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.message;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = ApiClient.isNetworkFailure(e)
            ? ApiClient.networkUnavailable(e).message
            : e.toString();
      });
    }
  }

  List<_Line> _parseMessages(dynamic raw) {
    if (raw is! List) return const [];
    final out = <_Line>[];
    for (final item in raw) {
      if (item is! Map) continue;
      final id = item['id']?.toString() ?? '';
      final role = item['role']?.toString() ?? '';
      final text = (item['content'] ?? '').toString().trim();
      if (id.isEmpty || text.isEmpty) continue;
      if (role != 'user' &&
          role != 'support' &&
          role != 'system' &&
          role != 'operator') {
        continue;
      }
      out.add(_Line(id: id, role: role, text: text));
    }
    return out;
  }

  Future<void> _pollNew() async {
    if (_busy || _loading) return;
    try {
      // Full list merge — after_id by created_at can miss same-second inserts.
      final fresh = await SupportApi.instance.listMessages();
      if (!mounted || fresh.isEmpty) return;
      final parsed = _parseMessages(fresh);
      if (parsed.isEmpty) return;
      final known = {for (final l in _lines) l.id};
      final changed = parsed.length != _lines.length ||
          parsed.any((l) => !known.contains(l.id));
      if (!changed) return;
      setState(() => _lines = parsed);
      _scrollToEnd();
    } catch (_) {}
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _busy) return;
    _input.clear();
    setState(() {
      _busy = true;
      _error = null;
      _lines = [
        ..._lines,
        _Line(
          id: 'local_${DateTime.now().microsecondsSinceEpoch}',
          role: 'user',
          text: trimmed,
        ),
      ];
    });
    _scrollToEnd();
    try {
      final companyId = await AuthStore.companyId();
      final res = await SupportApi.instance.postMessage(
        content: trimmed,
        clientMessageId: 'c_${DateTime.now().microsecondsSinceEpoch}',
        companyId: companyId,
      );
      final userMsg = res['user_message'];
      final supportMsg = res['support_message'];
      final next = <_Line>[
        for (final l in _lines)
          if (!l.id.startsWith('local_')) l,
      ];
      if (userMsg is Map) {
        next.add(
          _Line(
            id: userMsg['id']?.toString() ?? 'u',
            role: 'user',
            text: (userMsg['content'] ?? trimmed).toString(),
          ),
        );
      }
      if (supportMsg is Map) {
        final t = (supportMsg['content'] ?? '').toString().trim();
        final role = supportMsg['role']?.toString() ?? 'support';
        if (t.isNotEmpty) {
          next.add(
            _Line(
              id: supportMsg['id']?.toString() ?? 's',
              role: (role == 'operator' ||
                      role == 'system' ||
                      role == 'support')
                  ? role
                  : 'support',
              text: t,
            ),
          );
        }
      }
      if (!mounted) return;
      setState(() {
        _lines = next;
        _busy = false;
      });
      _scrollToEnd();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = ApiClient.isNetworkFailure(e)
            ? ApiClient.networkUnavailable(e).message
            : e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    const hPad = AppColors.screenPadding;
    final bottomInset = MediaQuery.paddingOf(context).bottom;

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
                          '‹ ${l10n.settingsTitle}',
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
                              color: AppColors.brandRed,
                              borderRadius: BorderRadius.circular(2 * s),
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Text(
                              l10n.supportChatTitle,
                              style: AppTypography.bold(
                                18.88 * s,
                                color: AppColors.textInput,
                              ),
                            ),
                          ),
                        ],
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
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : ListView.builder(
                        controller: _scroll,
                        padding: EdgeInsets.fromLTRB(
                          hPad * s,
                          16 * s,
                          hPad * s,
                          16 * s,
                        ),
                        itemCount: _lines.length + (_error != null ? 1 : 0),
                        itemBuilder: (context, i) {
                          if (_error != null && i == _lines.length) {
                            return Padding(
                              padding: EdgeInsets.only(top: 12 * s),
                              child: Text(
                                _error!,
                                textAlign: TextAlign.center,
                                style: AppTypography.regular(
                                  13 * s,
                                  color: AppColors.brandRed,
                                ),
                              ),
                            );
                          }
                          final line = _lines[i];
                          if (line.role == 'user') {
                            return Padding(
                              padding: EdgeInsets.only(bottom: 12 * s),
                              child: _UserBubble(text: line.text),
                            );
                          }
                          if (line.role == 'system') {
                            return Padding(
                              padding: EdgeInsets.only(bottom: 12 * s),
                              child: Text(
                                line.text,
                                textAlign: TextAlign.center,
                                style: AppTypography.regular(
                                  12 * s,
                                  color: AppColors.textMuted,
                                ),
                              ),
                            );
                          }
                          final label = line.role == 'operator'
                              ? l10n.supportOperator
                              : l10n.supportAi;
                          return Padding(
                            padding: EdgeInsets.only(bottom: 12 * s),
                            child: _SupportBubble(
                              text: line.text,
                              senderLabel: label,
                            ),
                          );
                        },
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
                  child: Container(
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
                            enabled: !_busy,
                            textCapitalization: TextCapitalization.sentences,
                            textInputAction: TextInputAction.send,
                            onSubmitted: _busy ? null : _send,
                            style: AppTypography.regular(
                              15.9 * s,
                              color: AppColors.textPrimary,
                            ),
                            cursorColor: AppColors.brandRed,
                            decoration: InputDecoration(
                              isDense: true,
                              border: InputBorder.none,
                              filled: false,
                              hintText: l10n.supportChatHint,
                              hintStyle: AppTypography.regular(
                                15.9 * s,
                                color: AppColors.textMuted,
                              ),
                              contentPadding: EdgeInsets.zero,
                            ),
                          ),
                        ),
                        GestureDetector(
                          onTap: _busy ? null : () => _send(_input.text),
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
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SupportBubble extends StatelessWidget {
  const _SupportBubble({required this.text, required this.senderLabel});

  final String text;
  final String senderLabel;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
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
            constraints: BoxConstraints(maxWidth: 280 * s),
            child: Container(
              padding: EdgeInsets.all(16 * s),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16 * s),
                border: Border.all(
                  color: Colors.black.withValues(alpha: 0.11),
                  width: 0.5,
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
              child: Text(
                text,
                style: AppTypography.regular(
                  13 * s,
                  color: AppColors.textPrimary,
                ),
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
          style: AppTypography.regular(13 * s, color: AppColors.surface),
        ),
      ),
    );
  }
}
