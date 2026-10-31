"""Email delivery through the Outbox.

Every message is written to ``OutboundEmail`` first, then handed to the real
delivery backend (SMTP in production, console in development). A failed SMTP
delivery is recorded on the Outbox row instead of breaking the business action
that sent it (e.g. confirming an invoice).
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class OutboxEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        from .models import OutboundEmail

        sent = 0
        delivery = get_connection(settings.OUTBOX_DELIVERY_BACKEND, fail_silently=False)
        for message in email_messages:
            html = ""
            for content, mimetype in getattr(message, "alternatives", []) or []:
                if mimetype == "text/html":
                    html = content
            row = OutboundEmail.objects.create(
                to=", ".join(message.to),
                subject=message.subject,
                body=message.body,
                html=html,
                attachments=[a[0] if isinstance(a, tuple) else a.filename for a in message.attachments],
                category=message.extra_headers.get("X-Category", ""),
            )
            try:
                delivery.send_messages([message])
            except Exception as exc:  # delivery problems must not undo business actions
                logger.warning("Email delivery failed for %s: %s", row.to, exc)
                row.status = "failed"
                row.error = str(exc)[:2000]
                row.save(update_fields=["status", "error"])
            sent += 1
        return sent


def send_email(
    to: str | list[str],
    subject: str,
    text: str,
    html: str = "",
    category: str = "",
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    recipients = [to] if isinstance(to, str) else to
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        to=recipients,
        headers={"X-Category": category} if category else None,
    )
    if html:
        message.attach_alternative(html, "text/html")
    for name, content, mimetype in attachments or []:
        message.attach(name, content, mimetype)
    message.send()
