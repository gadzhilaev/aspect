import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';

/// Lightweight Markdown for assistant chat (parity with web SafeMarkdown).
/// Supports: **bold**, *italic*, `code`, [links](url), lists, # headings.
class AssistantMarkdown extends StatelessWidget {
  const AssistantMarkdown(
    this.text, {
    super.key,
    required this.style,
    this.boldStyle,
    this.headingStyle,
    this.linkColor,
  });

  final String text;
  final TextStyle style;
  final TextStyle? boldStyle;
  final TextStyle? headingStyle;
  final Color? linkColor;

  @override
  Widget build(BuildContext context) {
    if (text.isEmpty) return const SizedBox.shrink();
    final blocks = _parseBlocks(text);
    final children = <Widget>[];
    for (var i = 0; i < blocks.length; i++) {
      if (i > 0) children.add(SizedBox(height: style.fontSize! * 0.55));
      children.add(_buildBlock(blocks[i]));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    );
  }

  Widget _buildBlock(_MdBlock block) {
    final strong = boldStyle ?? style.copyWith(fontWeight: FontWeight.w700);
    final heading = headingStyle ?? strong.copyWith(fontSize: (style.fontSize ?? 13) + 1);
    final link = linkColor ?? AppColors.brandRed;

    if (block.kind == _MdKind.ul || block.kind == _MdKind.ol) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < block.items.length; i++) ...[
            if (i > 0) SizedBox(height: (style.fontSize ?? 13) * 0.25),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: (style.fontSize ?? 13) * 1.2,
                  child: Text(
                    block.kind == _MdKind.ol ? '${i + 1}.' : '•',
                    style: style,
                  ),
                ),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: _parseInline(
                        block.items[i],
                        base: style,
                        strong: strong,
                        linkColor: link,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      );
    }

    final useHeading = block.kind == _MdKind.heading;
    final lines = block.lines;
    final spans = <InlineSpan>[];
    for (var i = 0; i < lines.length; i++) {
      if (i > 0) spans.add(const TextSpan(text: '\n'));
      spans.addAll(
        _parseInline(
          lines[i],
          base: useHeading ? heading : style,
          strong: strong,
          linkColor: link,
        ),
      );
    }
    return Text.rich(TextSpan(children: spans));
  }
}

enum _MdKind { p, heading, ul, ol }

class _MdBlock {
  const _MdBlock({required this.kind, this.lines = const [], this.items = const []});
  final _MdKind kind;
  final List<String> lines;
  final List<String> items;
}

bool _isUl(String line) => RegExp(r'^\s*[-*]\s+').hasMatch(line);
bool _isOl(String line) => RegExp(r'^\s*\d+\.\s+').hasMatch(line);

List<_MdBlock> _parseBlocks(String text) {
  final lines = text.replaceAll('\r\n', '\n').split('\n');
  final blocks = <_MdBlock>[];
  var buf = <String>[];

  void flush() {
    if (buf.isEmpty) return;
    if (buf.every(_isUl)) {
      blocks.add(
        _MdBlock(
          kind: _MdKind.ul,
          items: buf.map((ln) => ln.replaceFirst(RegExp(r'^\s*[-*]\s+'), '')).toList(),
        ),
      );
    } else if (buf.every(_isOl)) {
      blocks.add(
        _MdBlock(
          kind: _MdKind.ol,
          items: buf.map((ln) => ln.replaceFirst(RegExp(r'^\s*\d+\.\s+'), '')).toList(),
        ),
      );
    } else if (buf.length == 1 && RegExp(r'^#{1,3}\s+').hasMatch(buf.first)) {
      blocks.add(
        _MdBlock(
          kind: _MdKind.heading,
          lines: [buf.first.replaceFirst(RegExp(r'^#{1,3}\s+'), '')],
        ),
      );
    } else {
      blocks.add(_MdBlock(kind: _MdKind.p, lines: List.of(buf)));
    }
    buf = [];
  }

  for (final line in lines) {
    if (line.trim().isEmpty) {
      flush();
      continue;
    }
    if (buf.isNotEmpty) {
      final prevList = _isUl(buf.first) || _isOl(buf.first);
      final curList = _isUl(line) || _isOl(line);
      if (prevList != curList) {
        flush();
      } else if (prevList && _isUl(buf.first) != _isUl(line)) {
        flush();
      }
    }
    buf.add(line);
  }
  flush();
  return blocks;
}

bool _safeHref(String href) {
  final t = href.trim().toLowerCase();
  return t.startsWith('https://') || t.startsWith('http://') || t.startsWith('/');
}

List<InlineSpan> _parseInline(
  String text, {
  required TextStyle base,
  required TextStyle strong,
  required Color linkColor,
}) {
  final nodes = <InlineSpan>[];
  final re = RegExp(
    r'(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))',
  );
  var last = 0;
  for (final m in re.allMatches(text)) {
    if (m.start > last) {
      nodes.add(TextSpan(text: text.substring(last, m.start), style: base));
    }
    final token = m.group(0)!;
    if (token.startsWith('`')) {
      nodes.add(
        TextSpan(
          text: token.substring(1, token.length - 1),
          style: base.copyWith(
            fontFamily: 'monospace',
            backgroundColor: Colors.black.withValues(alpha: 0.06),
          ),
        ),
      );
    } else if (token.startsWith('**')) {
      nodes.add(
        TextSpan(text: token.substring(2, token.length - 2), style: strong),
      );
    } else if (token.startsWith('*')) {
      nodes.add(
        TextSpan(
          text: token.substring(1, token.length - 1),
          style: base.copyWith(fontStyle: FontStyle.italic),
        ),
      );
    } else if (token.startsWith('[')) {
      final lm = RegExp(r'^\[([^\]]+)\]\(([^)]+)\)$').firstMatch(token);
      if (lm != null && _safeHref(lm.group(2)!)) {
        final href = lm.group(2)!;
        nodes.add(
          TextSpan(
            text: lm.group(1),
            style: base.copyWith(
              color: linkColor,
              decoration: TextDecoration.underline,
            ),
            recognizer: TapGestureRecognizer()
              ..onTap = () async {
                final uri = Uri.tryParse(href);
                if (uri == null) return;
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              },
          ),
        );
      } else {
        nodes.add(TextSpan(text: token, style: base));
      }
    } else {
      nodes.add(TextSpan(text: token, style: base));
    }
    last = m.end;
  }
  if (last < text.length) {
    nodes.add(TextSpan(text: text.substring(last), style: base));
  }
  return nodes;
}

/// Compact bank evidence card for chat bubbles.
class BankEvidenceChatCard extends StatelessWidget {
  const BankEvidenceChatCard({
    super.key,
    required this.title,
    required this.body,
    required this.typeLabel,
    required this.meta,
    required this.onOpen,
    required this.openLabel,
  });

  final String title;
  final String body;
  final String typeLabel;
  final String meta;
  final VoidCallback onOpen;
  final String openLabel;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    // В dark textPrimary светлый — нельзя класть на жёсткий светлый фон карточки.
    final bg = AppColors.isDark
        ? AppColors.card
        : const Color(0xFFF7F8FA);
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(12 * s),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12 * s),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'МАТЕРИАЛ БАНКА',
            style: AppTypography.medium(
              10 * s,
              color: AppColors.brandRedBright,
            ),
          ),
          SizedBox(height: 6 * s),
          Text(
            title,
            style: AppTypography.bold(13 * s, color: AppColors.textPrimary),
          ),
          if (meta.isNotEmpty) ...[
            SizedBox(height: 4 * s),
            Text(
              meta,
              style: AppTypography.regular(11 * s, color: AppColors.textMuted),
            ),
          ],
          if (typeLabel.isNotEmpty) ...[
            SizedBox(height: 6 * s),
            Text(
              typeLabel,
              style: AppTypography.medium(12 * s, color: AppColors.textPrimary),
            ),
          ],
          if (body.isNotEmpty) ...[
            SizedBox(height: 8 * s),
            Text(
              body,
              style: AppTypography.regular(
                12 * s,
                color: AppColors.textPrimary,
              ).copyWith(height: 1.35),
              maxLines: 5,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          SizedBox(height: 10 * s),
          GestureDetector(
            onTap: onOpen,
            behavior: HitTestBehavior.opaque,
            child: Text(
              openLabel,
              style: AppTypography.bold(
                12 * s,
                color: AppColors.brandRedBright,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
