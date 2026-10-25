/// Декодирует частые HTML-сущности из текстов новостей API.
String decodeHtmlEntities(String input) {
  if (input.isEmpty) return input;
  var s = input
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&ndash;', '–')
      .replaceAll('&mdash;', '—')
      .replaceAll('&laquo;', '«')
      .replaceAll('&raquo;', '»')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll('&apos;', "'")
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&amp;', '&');
  s = s.replaceAllMapped(RegExp(r'&#(\d+);'), (m) {
    final code = int.tryParse(m.group(1)!);
    if (code == null) return m.group(0)!;
    return String.fromCharCode(code);
  });
  s = s.replaceAllMapped(RegExp(r'&#x([0-9a-fA-F]+);'), (m) {
    final code = int.tryParse(m.group(1)!, radix: 16);
    if (code == null) return m.group(0)!;
    return String.fromCharCode(code);
  });
  return s;
}

String displayHost(String url) {
  final uri = Uri.tryParse(url);
  if (uri == null || uri.host.isEmpty) {
    return url.length > 40 ? '${url.substring(0, 37)}…' : url;
  }
  final host = uri.host.replaceFirst(RegExp(r'^www\.'), '');
  return host;
}
