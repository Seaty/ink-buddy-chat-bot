"""SMTP delivery. Never log message bodies, reset links or SMTP exceptions."""

import smtplib
import ssl
from email.message import EmailMessage

from loguru import logger


class Mailer:
    def __init__(self, settings):
        self.settings = settings

    def message(self, recipient, subject, content):
        message = EmailMessage()
        message["From"] = self.settings.smtp_sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(content)
        return message

    def send(self, message):
        settings = self.settings
        try:
            client = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
            options = {"timeout": settings.smtp_timeout_seconds}
            if settings.smtp_ssl:
                options["context"] = ssl.create_default_context()
            with client(settings.smtp_host, settings.smtp_port, **options) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(message)
            return True
        except Exception:
            logger.warning("Auth email delivery failed; check SMTP configuration")
            return False
