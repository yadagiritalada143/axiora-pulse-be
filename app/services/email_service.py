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
import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings

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
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse verification code is: {otp}\n\n"
        f"This code is valid for {settings.otp_expire_minutes} minutes.\n"
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
              This code expires in <strong>{settings.otp_expire_minutes} minutes</strong>.<br>
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
    """Blocking SMTP send with STARTTLS — intended to run in a thread pool."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
    logger.info("OTP email dispatched → %s", to_email)


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
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse password reset code is: {otp}\n\n"
        f"This code is valid for {settings.otp_expire_minutes} minutes.\n"
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
              This code expires in <strong>{settings.otp_expire_minutes} minutes</strong>.<br>
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
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    plain_body = (
        f"Hello,\n\n"
        f"Your Axiora Pulse login verification code is: {otp}\n\n"
        f"This code is valid for {settings.otp_expire_minutes} minutes.\n"
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
              This code expires in <strong>{settings.otp_expire_minutes} minutes</strong>.<br>
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


