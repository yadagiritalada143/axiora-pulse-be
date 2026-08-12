import os
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
TEST_TO_EMAIL = os.getenv("TEST_TO_EMAIL")


def send_test_email():
    msg = EmailMessage()

    msg["Subject"] = "Axiora Pulse - SMTP Test"
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = TEST_TO_EMAIL

    msg.set_content(
        """Hello,

This is a test email from Axiora Pulse.

The Zoho SMTP configuration is working successfully.

Regards,
Axiora Pulse
"""
    )

    try:
        print("Connecting to Zoho SMTP...")

        context = ssl.create_default_context()

        with smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            context=context,
            timeout=30
        ) as server:

            print("Connected to Zoho SMTP.")

            print("Authenticating...")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

            print("Authentication successful.")

            print("Sending email...")
            server.send_message(msg)

        print("✅ Email sent successfully!")

    except smtplib.SMTPAuthenticationError as e:
        print("❌ SMTP authentication failed.")
        print(f"Server response: {e}")

    except smtplib.SMTPException as e:
        print("❌ SMTP error.")
        print(f"Server response: {e}")

    except Exception as e:
        print("❌ Unexpected error.")
        print(f"Error: {e}")


if __name__ == "__main__":
    send_test_email()