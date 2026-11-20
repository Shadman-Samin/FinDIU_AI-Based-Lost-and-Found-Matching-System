from types import SimpleNamespace

import httpx

from backend.app.notifications import BrevoNotifier


def test_email_escapes_user_supplied_markup(monkeypatch):
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return httpx.Response(201)

    monkeypatch.setattr(httpx, "post", post)
    notifier = BrevoNotifier("test-key", "desk@example.com", "https://example.com")
    item = SimpleNamespace(title='<img src=x onerror="bad()">')
    notifier.send_match("student@example.com", "<b>Student</b>", item, item, "match-id")
    assert "<img" not in sent["htmlContent"]
    assert "<b>Student</b>" not in sent["htmlContent"]
    assert "&lt;img" not in sent["htmlContent"]
    assert "&lt;b&gt;Student" in sent["htmlContent"]
