"""Login email validation — demo accounts must use EmailStr-accepted domains."""

from pydantic import ValidationError

from app.schemas.auth import LoginIn


def test_login_rejects_reserved_test_tld():
    try:
        LoginIn(email="case-demo-a@example.test", password="CaseCtxDemo1!")
        raised = False
    except ValidationError:
        raised = True
    assert raised


def test_login_accepts_example_com_demo_accounts():
    body = LoginIn(email="case-demo-a@example.com", password="CaseCtxDemo1!")
    assert body.email == "case-demo-a@example.com"
