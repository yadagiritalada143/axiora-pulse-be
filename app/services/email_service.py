"""
app/services/email_service.py
────────────────────────────────────────────────────────────────────────────────
Email OTP service using Python's built-in smtplib (SMTP / STARTTLS).

Returns an OTPResult dataclass so callers get structured success/failure info
rather than catching raw exceptions.

All blocking SMTP I/O is offloaded to asyncio.to_thread() to keep the
FastAPI event loop non-blocking.

Configuration (from .env):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
  SMTP_FROM_EMAIL, SMTP_FROM_NAME, OTP_EXPIRE_MINUTES
"""
import asyncio
import html
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from app.services.email_templates import render_button, render_email_shell

load_dotenv()

# ── SMTP environment variable helpers ─────────────────────────────────────────
_SMTP_HOST       = os.getenv("SMTP_HOST", "")
_SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER       = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME", "")
_SMTP_PASSWORD   = os.getenv("SMTP_PASSWORD", "")
_SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL") or _SMTP_USER
_SMTP_FROM_NAME  = os.getenv("SMTP_FROM_NAME", "Axiora Pulse")
_OTP_EXPIRE_MINS = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
_SUPPORT_EMAIL   = os.getenv("SUPPORT_EMAIL", "no.reply@axiorapulse.com")
_DASHBOARD_LOGIN_URL = os.getenv("DASHBOARD_LOGIN_URL", "https://qa.axiorapulse.com/login")


def _resolve_email_timezone(name: str) -> timezone | ZoneInfo:
    """Resolve the IANA zone name, falling back to a fixed UTC+5:30 offset"""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logging.getLogger(__name__).warning(
            "Timezone database not found for '%s' (is the 'tzdata' package installed?). "
            "Falling back to a fixed UTC+5:30 offset for email timestamps.", name
        )
        return timezone(timedelta(hours=5, minutes=30))


_EMAIL_TIMEZONE = _resolve_email_timezone(os.getenv("EMAIL_TIMEZONE", "Asia/Kolkata"))

logger = logging.getLogger(__name__)


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class OTPResult:
    """Structured result returned from every OTP dispatch attempt."""
    success: bool
    channel: str            # "email" | "sms" (future)
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return f"OTPResult(success=True, channel={self.channel!r})"
        return f"OTPResult(success=False, channel={self.channel!r}, error={self.error!r})"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_otp_email(to_email: str, otp: int) -> MIMEMultipart:
    """Construct the branded OTP email (plain-text + HTML multipart)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Axiora Pulse Verification Code"
    msg["From"] = f"{_SMTP_FROM_NAME} <{_SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse verification code is: {otp}\n\n"
        f"This code is valid for {_OTP_EXPIRE_MINS} minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— The Axiora Pulse Team"
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:16px;padding:48px 40px;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td style="text-align:center;padding-bottom:8px;">
            <span style="font-size:22px;font-weight:700;color:#1a1a2e;letter-spacing:-0.5px;">
              Axiora Pulse
            </span>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:8px;padding-bottom:32px;">
            <p style="margin:0;color:#555;font-size:15px;">
              Use the code below to verify your account.
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-bottom:32px;">
            <div style="display:inline-block;background:#f5f3ff;border-radius:12px;
                        padding:20px 40px;">
              <span style="font-size:48px;font-weight:800;letter-spacing:14px;color:#4f46e5;">
                {otp}
              </span>
            </div>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;">
            <p style="margin:0;color:#888;font-size:13px;line-height:1.6;">
              This code expires in <strong>{_OTP_EXPIRE_MINS} minutes</strong>.<br>
              If you didn&rsquo;t request this, you can safely ignore this email.
            </p>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:32px;border-top:1px solid #f0f0f0;margin-top:32px;">
            <p style="margin:0;color:#bbb;font-size:12px;">
              &copy; 2025 Axiora Pulse. All rights reserved.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _smtp_send(to_email: str, msg: MIMEMultipart) -> None:
    """Blocking SMTP send supporting SSL (Port 465) and STARTTLS (Port 587/25)."""
    if _SMTP_PORT == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=context, timeout=30) as server:
            server.login(_SMTP_USER, _SMTP_PASSWORD)
            server.sendmail(_SMTP_FROM_EMAIL, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(_SMTP_USER, _SMTP_PASSWORD)
            server.sendmail(_SMTP_FROM_EMAIL, [to_email], msg.as_string())
    logger.info("OTP email dispatched via SMTP (%s:%s) → %s", _SMTP_HOST, _SMTP_PORT, to_email)


# ── Public async interface ─────────────────────────────────────────────────────

async def send_otp_email(to_email: str, otp: int) -> OTPResult:
    """Send a 6-digit OTP via email (async, non-blocking).

    Returns:
        OTPResult with success=True on delivery, or success=False + error string
        on SMTP failure. Never raises — callers decide how to handle failure.
    """
    msg = _build_otp_email(to_email, otp)
    try:
        await asyncio.to_thread(_smtp_send, to_email, msg)
        return OTPResult(success=True, channel="email")
    except smtplib.SMTPAuthenticationError as exc:
        error = "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env"
        logger.error("OTP email auth error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        logger.error("OTP email SMTP error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except Exception as exc:
        error = f"Unexpected error: {exc}"
        logger.error("OTP email unexpected error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)


def _build_password_reset_email(to_email: str, otp: int) -> MIMEMultipart:
    """Construct the branded password reset email (plain-text + HTML multipart)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset Your Axiora Pulse Password"
    msg["From"] = f"{_SMTP_FROM_NAME} <{_SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse password reset code is: {otp}\n\n"
        f"This code is valid for {_OTP_EXPIRE_MINS} minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— The Axiora Pulse Team"
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:16px;padding:48px 40px;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td style="text-align:center;padding-bottom:8px;">
            <span style="font-size:22px;font-weight:700;color:#1a1a2e;letter-spacing:-0.5px;">
              Axiora Pulse
            </span>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:8px;padding-bottom:32px;">
            <p style="margin:0;color:#555;font-size:15px;">
              Use the code below to reset your password.
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-bottom:32px;">
            <div style="display:inline-block;background:#f5f3ff;border-radius:12px;
                        padding:20px 40px;">
              <span style="font-size:48px;font-weight:800;letter-spacing:14px;color:#4f46e5;">
                {otp}
              </span>
            </div>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;">
            <p style="margin:0;color:#888;font-size:13px;line-height:1.6;">
              This code expires in <strong>{_OTP_EXPIRE_MINS} minutes</strong>.<br>
              If you didn&rsquo;t request this, you can safely ignore this email.
            </p>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:32px;border-top:1px solid #f0f0f0;margin-top:32px;">
            <p style="margin:0;color:#bbb;font-size:12px;">
              &copy; 2025 Axiora Pulse. All rights reserved.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


async def send_password_reset_email(to_email: str, otp: int) -> OTPResult:
    """Send a 6-digit password reset OTP via email (async, non-blocking).

    Returns:
        OTPResult with success=True on delivery, or success=False + error string
        on SMTP failure. Never raises — callers decide how to handle failure.
    """
    msg = _build_password_reset_email(to_email, otp)
    try:
        await asyncio.to_thread(_smtp_send, to_email, msg)
        return OTPResult(success=True, channel="email")
    except smtplib.SMTPAuthenticationError as exc:
        error = "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env"
        logger.error("Password reset email auth error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        logger.error("Password reset email SMTP error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except Exception as exc:
        error = f"Unexpected error: {exc}"
        logger.error("Password reset email unexpected error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)


def _build_login_otp_email(to_email: str, otp: int) -> MIMEMultipart:
    """Construct the branded login OTP email (plain-text + HTML multipart)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Axiora Pulse Login Verification Code"
    msg["From"] = f"{_SMTP_FROM_NAME} <{_SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse login verification code is: {otp}\n\n"
        f"This code is valid for {_OTP_EXPIRE_MINS} minutes.\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— The Axiora Pulse Team"
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
</head>
<body style="margin:0;padding:0;background-color:#f9fafb;font-family:'Segoe UI',system-ui,sans-serif;-webkit-font-smoothing:antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#f9fafb;padding:48px 0;">
    <tr><td align="center">
      <table width="100%" max-width="500" border="0" cellspacing="0" cellpadding="0" 
             style="max-width:500px;background-color:#ffffff;border:1px solid #e5e7eb;
                    border-radius:16px;padding:40px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
        <tr>
          <td style="text-align:center;padding-bottom:32px;border-bottom:1px solid #f0f0f0;">
            <h1 style="margin:0;font-size:24px;font-weight:800;color:#111827;letter-spacing:-0.5px;">
              Axiora Pulse
            </h1>
            <p style="margin:4px 0 0 0;font-size:14px;color:#6b7280;">Login Verification</p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 0;text-align:center;">
            <p style="margin:0 0 24px 0;font-size:16px;color:#374151;line-height:1.5;">
              Use the following verification code to complete your login:
            </p>
            <div style="display:inline-block;background:#eff6ff;border-radius:12px;
                        padding:20px 40px;">
              <span style="font-size:48px;font-weight:800;letter-spacing:14px;color:#2563eb;">
                {otp}
              </span>
            </div>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;">
            <p style="margin:0;color:#888;font-size:13px;line-height:1.6;">
              This code expires in <strong>{_OTP_EXPIRE_MINS} minutes</strong>.<br>
              If you didn&rsquo;t request this, you can safely ignore this email.
            </p>
          </td>
        </tr>
        <tr>
          <td style="text-align:center;padding-top:32px;border-top:1px solid #f0f0f0;margin-top:32px;">
            <p style="margin:0;color:#bbb;font-size:12px;">
              &copy; 2025 Axiora Pulse. All rights reserved.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


async def send_login_otp_email(to_email: str, otp: int) -> OTPResult:
    """Send a 6-digit login OTP via email (async, non-blocking)."""
    msg = _build_login_otp_email(to_email, otp)
    try:
        await asyncio.to_thread(_smtp_send, to_email, msg)
        return OTPResult(success=True, channel="email")
    except smtplib.SMTPAuthenticationError as exc:
        error = "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env"
        logger.error("Login OTP email auth error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        logger.error("Login OTP email SMTP error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except Exception as exc:
        error = f"Unexpected error: {exc}"
        logger.error("Login OTP email unexpected error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)


# Registration success (welcome) email

def _build_registration_success_email(to_email: str, display_name: Optional[str] = None) -> MIMEMultipart:
    """Construct the branded 'account created' welcome email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Welcome to Axiora Pulse. Your Account is Ready"
    msg["From"] = f"{_SMTP_FROM_NAME} <{_SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    greeting_name = display_name.strip() if display_name else to_email
    safe_name = html.escape(greeting_name)

    plain_body = (
        f"Hello {greeting_name},\n\n"
        f"Welcome to Axiora Pulse! Your account has been created successfully "
        f"and is ready to use.\n\n"
        f"You can sign in any time at {_DASHBOARD_LOGIN_URL}\n\n"
        f"If you did not create this account, please contact us at {_SUPPORT_EMAIL}.\n\n"
        f"— The Axiora Pulse Team"
    )

    body_html = f"""\
        <tr>
          <td align="center" style="padding-bottom:8px;">
            <h1 class="text-primary" style="margin:0;font-size:22px;font-weight:700;color:#1a1a2e;letter-spacing:-0.5px;">
              Welcome to Axiora Pulse!
            </h1>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-top:8px;padding-bottom:28px;">
            <p class="text-secondary" style="margin:0;color:#555;font-size:15px;line-height:1.6;">
              Hi {safe_name}, your account has been created successfully and is ready to go.
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-bottom:28px;">
            {render_button("Go to Dashboard", _DASHBOARD_LOGIN_URL)}
          </td>
        </tr>
        <tr>
          <td align="center">
            <p class="text-secondary" style="margin:0;color:#888;font-size:13px;line-height:1.6;">
              If you didn&rsquo;t create this account, please contact us at
              <a href="mailto:{html.escape(_SUPPORT_EMAIL, quote=True)}" style="color:#4f46e5;">{html.escape(_SUPPORT_EMAIL)}</a>.
            </p>
          </td>
        </tr>"""

    html_body = render_email_shell(
        preheader="Your Axiora Pulse account is ready.",
        body_html=body_html,
    )

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


async def send_registration_success_email(to_email: str, display_name: Optional[str] = None) -> OTPResult:
    """Send the welcome / account-created confirmation email (async, non-blocking).

    Best-effort — never raises. Returns OTPResult with success=False + error
    string on delivery failure so callers/background jobs can log or retry.
    """
    msg = _build_registration_success_email(to_email, display_name)
    try:
        await asyncio.to_thread(_smtp_send, to_email, msg)
        return OTPResult(success=True, channel="email")
    except smtplib.SMTPAuthenticationError as exc:
        error = "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env"
        logger.error("Registration success email auth error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        logger.error("Registration success email SMTP error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except Exception as exc:
        error = f"Unexpected error: {exc}"
        logger.error("Registration success email unexpected error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)


# Password reset success email 

def _build_password_reset_success_email(to_email: str, changed_at: Optional[datetime] = None) -> MIMEMultipart:
    """Construct the branded 'password changed' confirmation email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Axiora Pulse Password Was Changed"
    msg["From"] = f"{_SMTP_FROM_NAME} <{_SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    when = changed_at or datetime.now(tz=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local_when = when.astimezone(_EMAIL_TIMEZONE)
    timestamp_str = local_when.strftime("%B %d, %Y at %I:%M %p %Z")
    safe_timestamp = html.escape(timestamp_str)

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse account password was changed successfully on {timestamp_str}.\n\n"
        f"If you made this change, no further action is needed.\n\n"
        f"If you did NOT make this change, your account may be compromised — "
        f"please contact us immediately at {_SUPPORT_EMAIL}.\n\n"
        f"— The Axiora Pulse Team"
    )

    body_html = f"""\
        <tr>
          <td align="center" style="padding-bottom:8px;">
            <h1 class="text-primary" style="margin:0;font-size:22px;font-weight:700;color:#1a1a2e;letter-spacing:-0.5px;">
              Password Changed Successfully
            </h1>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-top:8px;padding-bottom:28px;">
            <p class="text-secondary" style="margin:0;color:#555;font-size:15px;line-height:1.6;">
              Your account password was changed on<br><strong>{safe_timestamp}</strong>.
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-bottom:8px;">
            <div style="background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:16px 20px;">
              <p style="margin:0;color:#9a3412;font-size:13px;line-height:1.6;">
                <strong>Didn&rsquo;t make this change?</strong> Your account may be compromised.
                Contact us immediately at
                <a href="mailto:{html.escape(_SUPPORT_EMAIL, quote=True)}" style="color:#9a3412;font-weight:700;">{html.escape(_SUPPORT_EMAIL)}</a>.
              </p>
            </div>
          </td>
        </tr>"""

    html_body = render_email_shell(
        preheader="Your Axiora Pulse password was changed.",
        body_html=body_html,
    )

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


async def send_password_reset_success_email(to_email: str, changed_at: Optional[datetime] = None) -> OTPResult:
    """Send the 'password changed successfully' confirmation email (async, non-blocking).

    Best-effort — never raises. Never includes the password itself.
    """
    msg = _build_password_reset_success_email(to_email, changed_at)
    try:
        await asyncio.to_thread(_smtp_send, to_email, msg)
        return OTPResult(success=True, channel="email")
    except smtplib.SMTPAuthenticationError as exc:
        error = "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env"
        logger.error("Password reset success email auth error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        logger.error("Password reset success email SMTP error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)
    except Exception as exc:
        error = f"Unexpected error: {exc}"
        logger.error("Password reset success email unexpected error for %s: %s", to_email, exc)
        return OTPResult(success=False, channel="email", error=error)


