import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

logger = logging.getLogger(__name__)

SMTP_CONFIG = {
    "hostname": os.getenv("SMTP_HOST", "smtp.qq.com"),
    "port": int(os.getenv("SMTP_PORT", 587)),
    "username": os.getenv("SMTP_USERNAME"),
    "password": os.getenv("SMTP_PASSWORD"),
    "use_tls": True,
}

async def send_email(to: str, subject: str, html_content: str, bcc: list = None):
    """异步发送HTML邮件"""
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_CONFIG["username"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_CONFIG["hostname"],
            port=SMTP_CONFIG["port"],
            username=SMTP_CONFIG["username"],
            password=SMTP_CONFIG["password"],
            start_tls=SMTP_CONFIG["use_tls"],
        )
        logger.info(f"邮件发送成功: {to}")
    except Exception as e:
        logger.error(f"邮件发送失败 {to}: {e}")
        raise