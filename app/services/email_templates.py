"""
Reusable Axiora Pulse HTML email components.

`render_email_shell()` is the single shared layout (header logo, card, footer)
used by every transactional email.

"""
import html
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_LOGO_LIGHT_URL = os.getenv(
    "EMAIL_LOGO_LIGHT_URL",
    "https://res.cloudinary.com/dg3v3lhay/image/upload/axiora_pulse_logo.png",
)
_LOGO_DARK_URL = os.getenv(
    "EMAIL_LOGO_DARK_URL",
    "https://res.cloudinary.com/dg3v3lhay/image/upload/axiora_logo.png",
)


def _logo_header_html() -> str:
    """Header markup: logo images that swap for dark-mode-aware clients."""
    return (
        f'<img src="{html.escape(_LOGO_LIGHT_URL, quote=True)}" alt="Axiora Pulse" width="176" '
        'class="logo-light" style="display:block;max-width:176px;height:auto;border:0;outline:none;margin:0 auto;">'
        f'<img src="{html.escape(_LOGO_DARK_URL, quote=True)}" alt="Axiora Pulse" width="176" '
        'class="logo-dark" style="display:none;max-width:176px;height:auto;border:0;outline:none;">'
    )


def render_email_shell(*, preheader: str, body_html: str) -> str:
    """Wrap `body_html` in the shared Axiora Pulse card layout.

    `preheader` is hidden text shown as the inbox preview snippet in most
    email clients — keep it short and specific to the email's purpose.
    """
    safe_preheader = html.escape(preheader)
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style>
  @media (prefers-color-scheme: dark) {{
    body, .email-bg {{ background:#0f0f10 !important; }}
    .card {{ background:#1a1a1a !important; border-color:#2a2a2a !important; }}
    .text-primary {{ color:#f5f5f5 !important; }}
    .text-secondary {{ color:#b5b5b5 !important; }}
    .divider {{ border-color:#2a2a2a !important; }}
    .logo-light {{ display:none !important; }}
    .logo-dark {{ display:block !important; margin:0 auto !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{safe_preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-bg" style="background:#f0f2f5;padding:40px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" class="card"
             style="background:#ffffff;border:1px solid #eeeeee;border-radius:16px;padding:48px 40px;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td align="center" style="padding-bottom:32px;">
            {_logo_header_html()}
          </td>
        </tr>
        {body_html}
        <tr>
          <td class="divider" style="text-align:center;padding-top:32px;border-top:1px solid #f0f0f0;">
            <p class="text-secondary" style="margin:16px 0 0 0;color:#bbb;font-size:12px;line-height:1.6;">
              &copy; 2025 Axiora Pulse. All rights reserved.<br>
              This is an automated message — please do not reply directly to this email.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_button(label: str, url: str) -> str:
    """A bulletproof-ish CTA button (table-based, inline-styled) for email clients."""
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
  <tr>
    <td align="center" style="border-radius:10px;background:#4f46e5;">
      <a href="{safe_url}" target="_blank"
         style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;
                color:#ffffff;text-decoration:none;border-radius:10px;">
        {safe_label}
      </a>
    </td>
  </tr>
</table>"""
