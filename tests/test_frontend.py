from pathlib import Path

ROOT = Path(__file__).parents[1] / "frontend"


def test_frontend_has_six_user_facing_pages():
    pages = ("index.html", "auth.html", "report.html", "dashboard.html", "match.html", "admin.html")
    for page in pages:
        assert (ROOT / page).exists()


def test_report_form_collects_a_private_verification_detail():
    report = (ROOT / "report.html").read_text(encoding="utf-8")
    assert 'name="private_detail"' in report
    assert "Private verification detail" in report
    assert "consent" in report.lower()
    assert "নাম" in report


def test_private_detail_is_never_rendered_into_the_ui():
    for page in ROOT.glob("*.html"):
        assert "private_detail:" not in page.read_text(encoding="utf-8")
    for script in (ROOT / "js").glob("*.js"):
        text = script.read_text(encoding="utf-8")
        if script.name not in {"report.js", "admin.js"}:
            assert "private_detail" not in text, script.name


def test_user_text_is_rendered_without_inner_html():
    api = (ROOT / "js" / "api.js").read_text(encoding="utf-8")
    i18n = (ROOT / "js" / "i18n.js").read_text(encoding="utf-8")
    assert "innerHTML" not in api
    assert "textContent" in i18n
