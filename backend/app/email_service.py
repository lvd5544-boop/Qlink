import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

logger = logging.getLogger(__name__)


def _smtp_config() -> dict:
    return {
        "hostname": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_address": os.getenv("SMTP_FROM", "").strip()
        or os.getenv("SMTP_USERNAME", "").strip(),
        "use_tls": os.getenv("SMTP_START_TLS", "true").strip().lower()
        in {"1", "true", "yes", "on"},
    }


def smtp_configured() -> bool:
    config = _smtp_config()
    return all(config[key] for key in ("hostname", "username", "password", "from_address"))


def _mask_email(value: str) -> str:
    local, separator, domain = (value or "").partition("@")
    if not separator:
        return "***"
    return f"{local[:2]}***@{domain}"


async def send_email(to: str, subject: str, html_content: str, bcc: list = None):
    """异步发送HTML邮件"""
    config = _smtp_config()
    if not smtp_configured():
        raise RuntimeError("SMTP is not fully configured")
    msg = MIMEMultipart("alternative")
    msg["From"] = config["from_address"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    try:
        await aiosmtplib.send(
            msg,
            hostname=config["hostname"],
            port=config["port"],
            username=config["username"],
            password=config["password"],
            start_tls=config["use_tls"],
        )
        logger.info("邮件发送成功 recipient=%s", _mask_email(to))
    except Exception as e:
        logger.error(
            "邮件发送失败 recipient=%s error_type=%s",
            _mask_email(to),
            type(e).__name__,
        )
        raise
