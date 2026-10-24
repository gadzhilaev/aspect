"""Static contract for Aspect web theme — no browser, no secrets."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_front_root import resolve_front_root, resolve_front_src  # noqa: E402

WEB = resolve_front_root()
SRC = resolve_front_src()


def test_theme_early_init_in_index_html():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "aspekt.theme" in html
    assert "data-theme" in html
    assert "prefers-color-scheme" in html
    assert "localStorage" in html


def test_theme_modules_and_toggle_wired():
    assert (SRC / "theme" / "theme.ts").exists()
    assert (SRC / "theme" / "ThemeContext.tsx").exists()
    assert (SRC / "components" / "ui" / "ThemeToggle.tsx").exists()
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "ThemeProvider" in app
    layout = (SRC / "layouts" / "SiteLayout.tsx").read_text(encoding="utf-8")
    assert "ThemeToggle" in layout


def test_theme_storage_key_and_modes():
    theme = (SRC / "theme" / "theme.ts").read_text(encoding="utf-8")
    assert "THEME_STORAGE_KEY = 'aspekt.theme'" in theme
    assert "'system'" in theme and "'light'" in theme and "'dark'" in theme
    assert "localStorage" in theme


def test_theme_menu_has_three_modes_not_cycle():
    toggle = (SRC / "components" / "ui" / "ThemeToggle.tsx").read_text(encoding="utf-8")
    assert "Система" in toggle
    assert "Светлая" in toggle
    assert "Тёмная" in toggle
    assert "setPreference" in toggle
    assert "useTheme" in toggle
    assert "cyclePreference" not in toggle
    assert "onClick={cyclePreference}" not in toggle
    assert 'aria-label="Выбрать тему оформления"' in toggle
    assert 'role="menuitemradio"' in toggle
    assert "aria-checked" in toggle
    assert "ArrowDown" in toggle
    assert "ArrowUp" in toggle
    assert "Escape" in toggle
    assert "mousedown" in toggle  # click outside


def test_tokens_define_semantic_and_data_theme():
    tokens = (SRC / "styles" / "tokens.css").read_text(encoding="utf-8")
    for name in (
        "--color-bg",
        "--color-surface",
        "--color-surface-muted",
        "--color-text",
        "--color-text-muted",
        "--color-border",
        "--color-accent",
        "--color-accent-hover",
        "--color-success",
        "--color-warning",
        "--color-danger",
        "--shadow-sm",
        "--shadow-md",
        "--shadow-lg",
    ):
        assert name in tokens
    assert "html[data-theme='light']" in tokens
    assert "html[data-theme='dark']" in tokens


def test_global_surfaces_use_semantic_tokens():
    global_css = (SRC / "styles" / "global.css").read_text(encoding="utf-8")
    assert "background: var(--color-bg)" in global_css
    assert "color: var(--color-text)" in global_css
    assert "var(--color-on-accent)" in global_css
    assert ".theme-toggle" in global_css
    assert ".theme-menu" in global_css


def test_home_hero_adapts_to_light_theme():
    home = (SRC / "styles" / "home.css").read_text(encoding="utf-8")
    assert "html[data-theme='light'] .home-hero" in home
    assert "html[data-theme='light'] .home-hero h1" in home
    assert "html[data-theme='light'] .home-hero .radar" in home
    assert "color: var(--color-text)" in home
