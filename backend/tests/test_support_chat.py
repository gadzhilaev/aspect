"""Support chat: FAQ, AI escalate stub, operator ticket helpers."""

from __future__ import annotations

from app.services.support_ai import decide_support_reply, match_faq
from app.services.support_chat import craft_support_reply
from app.services.support_operator import ticket_code


def test_faq_password_reply():
    text = craft_support_reply(user_text="Не могу войти, забыл пароль", thread_id="abc")
    assert "войти" in text.lower() or "парол" in text.lower() or "email" in text.lower()


def test_faq_news_feed_reply():
    text = craft_support_reply(user_text="Почему пустая лента новостей?", thread_id="abc")
    assert "лент" in text.lower() or "бренд" in text.lower() or "продукт" in text.lower()


def test_unknown_escalates_user_copy():
    tid = "12345678-aaaa-bbbb-cccc-dddddddddddd"
    text = craft_support_reply(user_text="Случайный вопрос про зелёных слонов", thread_id=tid)
    assert text == "Передал оператору"
    assert "SUP-" not in text


def test_match_faq_direct():
    assert match_faq("Как удалить аккаунт?") is not None
    assert match_faq("зелёные слоны в космосе") is None


def test_decide_faq_no_escalate():
    d = decide_support_reply("Не могу войти")
    assert d.escalate is False
    assert d.reply
    assert d.source == "faq"


def test_ticket_code():
    assert ticket_code("abcdef12-3456-7890-abcd-ef1234567890") == "SUP-ABCDEF12"
