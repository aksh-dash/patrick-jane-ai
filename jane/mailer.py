"""Email with a hard boundary: Jane composes freely, but only ever *sends*
the one draft she has already read back to the user and been told to send.

There is no way to send arbitrary text — `send()` sends whatever `compose()`
last staged, and nothing else. Compose is cheap and reversible; send is the
single outward step, and it is gated on the user's confirmation upstream (the
persona is told never to call it before the user says yes).
"""
from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage
from email.utils import parseaddr

from . import config
from .logbus import bus

_lock = threading.Lock()
_pending: dict | None = None      # {to, subject, body}


def _valid(addr: str) -> bool:
    name, email = parseaddr(addr or "")
    return "@" in email and "." in email.split("@")[-1]


def compose(to: str, subject: str, body: str) -> str:
    """Stage a draft and read it back. Does not send anything."""
    global _pending
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not _valid(to):
        return f"'{to}' doesn't look like an email address, so I haven't staged anything."
    if not body:
        return "There's no body to send. Tell me what it should say."
    with _lock:
        _pending = {"to": to, "subject": subject or "(no subject)", "body": body}
    bus.log(f"Email drafted to {to}", "info")
    preview = body if len(body) <= 400 else body[:400] + "…"
    return (f"Drafted to {to}, subject '{_pending['subject']}':\n{preview}\n"
            f"Say the word and I'll send it.")


def discard() -> str:
    global _pending
    with _lock:
        had = _pending is not None
        _pending = None
    return "Torn up." if had else "There was nothing drafted."


def send() -> str:
    """Send the staged draft over SMTP. Sends only what compose() prepared."""
    global _pending
    if not config.ALLOW_EMAIL:
        return ("Email is switched off. Set JANE_ALLOW_EMAIL=1 and the JANE_SMTP_* "
                "values in .env, then restart me.")
    if not (config.SMTP_USER and config.SMTP_PASS):
        return "There's no outbox configured — I need JANE_SMTP_USER and JANE_SMTP_PASS in .env."
    with _lock:
        draft = _pending
    if not draft:
        return "Nothing's drafted, so there's nothing to send. Compose it first."

    msg = EmailMessage()
    msg["From"] = config.EMAIL_FROM or config.SMTP_USER
    msg["To"] = draft["to"]
    msg["Subject"] = draft["subject"]
    msg.set_content(draft["body"])

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return ("The mail server rejected the login. For Gmail you need an App "
                "Password, not your normal one.")
    except (smtplib.SMTPException, OSError) as exc:
        bus.log(f"Email failed: {exc}", "error")
        return f"The send failed: {exc}"

    with _lock:
        _pending = None
    bus.log(f"Email sent to {draft['to']}", "ok")
    return f"Sent to {draft['to']}."
