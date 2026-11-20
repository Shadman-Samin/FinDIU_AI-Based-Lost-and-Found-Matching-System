"""Match notification email.

Only public fields leave the system. The private verification detail never
appears in an email, and images are linked, not attached.
"""

from html import escape

import httpx

from backend.app.errors import ServiceFailure, retry_after_seconds

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class BrevoNotifier:
    def __init__(self, api_key: str, sender_email: str, frontend_url: str):
        self.api_key = api_key
        self.sender_email = sender_email
        self.frontend_url = frontend_url.rstrip("/")

    def send_match(
        self, to_email: str, to_name: str, lost, found, match_id: str, locale="en"
    ) -> None:
        if not self.api_key or not self.sender_email:
            raise ServiceFailure("email_not_configured")
        link = escape(f"{self.frontend_url}/dashboard.html", quote=True)
        subject = "FinDIU: a possible match for your report"
        body = (
            f"<p>Hello {escape(to_name)},</p>"
            "<p>A new possible match was found for your report.</p>"
            f"<p>Open your match trail and check the evidence: "
            f'<a href="{link}">{link}</a></p>'
            "<p>For privacy, the private verification detail is never included in email. "
            "An admin reviews every claim before an item is returned.</p>"
            "<p>— FinDIU</p>"
        )
        if locale == "bn":
            subject = "FinDIU: আপনার রিপোর্টের সম্ভাব্য মিল"
            body = (
                f"<p>{escape(to_name)}, আপনার রিপোর্টের একটি সম্ভাব্য মিল পাওয়া গেছে।</p>"
                f'<p><a href="{link}">ড্যাশবোর্ড দেখুন</a></p>'
            )
        try:
            response = httpx.post(
                BREVO_ENDPOINT,
                headers={"api-key": self.api_key, "Content-Type": "application/json"},
                json={
                    "sender": {"email": self.sender_email, "name": "FinDIU"},
                    "to": [{"email": to_email, "name": to_name}],
                    "subject": subject,
                    "htmlContent": body,
                },
                timeout=10,
            )
        except httpx.HTTPError:
            raise ServiceFailure("email_unavailable", retryable=True) from None
        if response.status_code >= 500 or response.status_code == 429:
            retry_after = retry_after_seconds(response.headers.get("Retry-After"))
            raise ServiceFailure("email_unavailable", retryable=True, retry_after=retry_after)
        if response.status_code >= 400:
            raise ServiceFailure("email_rejected")


def build_notifier(settings):
    key = settings.brevo_api_key.get_secret_value()
    return BrevoNotifier(key, settings.brevo_sender_email, settings.frontend_url)
