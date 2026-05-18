import random
import string
import smtplib
import logging
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from passlib.context import CryptContext
from jose import JWTError, jwt

from config import settings   # your existing config

logger = logging.getLogger(__name__)

import bcrypt

# ── Password hashing ────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# ── OTP ──────────────────────────────────────────────────────────────────────
def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def otp_expiry(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


# ── JWT ───────────────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_minutes: int = 60 * 24) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ── Email (SMTP) ─────────────────────────────────────────────────────────────
def send_otp_email(to_email: str, otp: str, purpose: str = "login") -> bool:
    """
    Sends OTP via SMTP. Set SMTP_* vars in your .env.
    Falls back to console-print in development if SMTP not configured.
    """
    if not settings.SMTP_HOST:
        # Dev fallback — print to console
        logger.info(f"[DEV OTP] To: {to_email}  Code: {otp}  Purpose: {purpose}")
        return True

    subject_map = {
        "signup": "Verify your StockSense account",
        "login":  "Your StockSense login OTP",
        "reset":  "Reset your StockSense password",
    }
    subject = subject_map.get(purpose, "Your OTP")

    html = f"""
    <div style="font-family:sans-serif;max-width:420px;margin:auto">
      <h2 style="color:#1D9E75">StockSense</h2>
      <p>Your one-time password is:</p>
      <div style="font-size:36px;font-weight:700;letter-spacing:10px;
                  color:#0F6E56;padding:16px 0">{otp}</div>
      <p style="color:#666">This code expires in <strong>10 minutes</strong>.
         Do not share it with anyone.</p>
      <hr style="border:none;border-top:1px solid #eee"/>
      <p style="font-size:12px;color:#999">
        If you did not request this, ignore this email.</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.SMTP_FROM
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as srv:
            srv.ehlo()
            if settings.SMTP_TLS:
                srv.starttls()
            if settings.SMTP_USER:
                srv.login(settings.SMTP_USER, settings.SMTP_PASS)
            srv.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False