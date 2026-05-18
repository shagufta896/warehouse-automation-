from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import User, OTPRecord
from app.auth.utils import (
    hash_password, verify_password,
    generate_otp, otp_expiry,
    create_access_token, decode_access_token,
    send_otp_email,
)

router  = APIRouter(prefix="/auth", tags=["auth"])
bearer  = HTTPBearer(auto_error=False)


# ── Schemas ───────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    full_name:  str
    store_name: str = ""
    email:      EmailStr
    password:   str

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class OTPRequest(BaseModel):
    email:   EmailStr
    purpose: str = "login"          # "signup" | "login" | "reset"

class OTPVerifyRequest(BaseModel):
    email:   EmailStr
    otp:     str
    purpose: str = "login"

class PasswordResetRequest(BaseModel):
    email:       EmailStr
    otp:         str
    new_password: str

class UpdateProfileRequest(BaseModel):
    full_name:  str = None
    store_name: str = None
    email:      EmailStr = None
    phone:      str = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ── Helpers ───────────────────────────────────────────────────────────────────
def _invalidate_old_otps(db: Session, email: str, purpose: str):
    db.query(OTPRecord).filter(
        OTPRecord.email == email,
        OTPRecord.purpose == purpose,
        OTPRecord.is_used == False,
    ).update({"is_used": True})
    db.commit()

def _create_otp_record(db: Session, email: str, purpose: str) -> str:
    _invalidate_old_otps(db, email, purpose)
    code = generate_otp()
    record = OTPRecord(
        email=email, otp_code=code,
        purpose=purpose, expires_at=otp_expiry(10),
    )
    db.add(record)
    db.commit()
    return code

def _get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    from app.database.database import current_tenant_id
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    current_tenant_id.set(user.id)
    return user


# ── Routes ────────────────────────────────────────────────────────────────────

# 1. Send OTP (signup email verification OR passwordless login)
@router.post("/send-otp")
def send_otp(req: OTPRequest, db: Session = Depends(get_db)):
    if req.purpose == "signup":
        # Don't block if user already exists — let verify step handle it
        pass
    elif req.purpose in ("login", "reset"):
        user = db.query(User).filter(User.email == req.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Email not registered")

    code = _create_otp_record(db, req.email, req.purpose)
    ok = send_otp_email(req.email, code, req.purpose)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send OTP email")
    return {"message": "OTP sent", "expires_in_minutes": 10}


# 2. Signup — step 2: verify OTP then create account
@router.post("/signup")
def signup(req: SignupRequest, otp: str, db: Session = Depends(get_db)):
    """
    Client first calls /send-otp with purpose=signup,
    then submits this form with the otp query param.
    """
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    record = db.query(OTPRecord).filter(
        OTPRecord.email == req.email,
        OTPRecord.purpose == "signup",
        OTPRecord.is_used == False,
        OTPRecord.otp_code == otp,
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    record.is_used = True
    user = User(
        full_name=req.full_name,
        store_name=req.store_name,
        email=req.email,
        password_hash=hash_password(req.password),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user.id, "full_name": user.full_name,
        "store_name": user.store_name, "email": user.email,
    }}


# 3. Login with password
@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Trigger OTP for 2FA — frontend then calls /verify-login-otp
    code = _create_otp_record(db, req.email, "login")
    send_otp_email(req.email, code, "login")

    return {"message": "OTP sent to email", "next": "verify_otp"}


# 4. Verify login OTP → issue JWT
@router.post("/verify-login-otp")
def verify_login_otp(req: OTPVerifyRequest, db: Session = Depends(get_db)):
    record = db.query(OTPRecord).filter(
        OTPRecord.email == req.email,
        OTPRecord.purpose == "login",
        OTPRecord.is_used == False,
        OTPRecord.otp_code == req.otp,
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    user = db.query(User).filter(User.email == req.email).first()
    record.is_used = True
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token({"sub": user.id, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user.id, "full_name": user.full_name,
        "store_name": user.store_name, "email": user.email,
    }}


# 5. Password reset
@router.post("/reset-password")
def reset_password(req: PasswordResetRequest, db: Session = Depends(get_db)):
    record = db.query(OTPRecord).filter(
        OTPRecord.email == req.email,
        OTPRecord.purpose == "reset",
        OTPRecord.is_used == False,
        OTPRecord.otp_code == req.otp,
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    user = db.query(User).filter(User.email == req.email).first()
    user.password_hash = hash_password(req.new_password)
    record.is_used = True
    db.commit()
    return {"message": "Password updated successfully"}


# 6. Get current logged-in user profile
@router.get("/me")
def me(current_user: User = Depends(_get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "store_name": current_user.store_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "is_verified": current_user.is_verified,
        "last_login": current_user.last_login,
    }

@router.put("/profile")
def update_profile(req: UpdateProfileRequest, db: Session = Depends(get_db), current_user: User = Depends(_get_current_user)):
    if req.full_name is not None:
        current_user.full_name = req.full_name
    if req.store_name is not None:
        current_user.store_name = req.store_name
    if req.email is not None:
        # Check if email is already taken by another user
        existing = db.query(User).filter(User.email == req.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already taken")
        current_user.email = req.email
    if req.phone is not None:
        current_user.phone = req.phone
    
    db.commit()
    db.refresh(current_user)
    return {"message": "Profile updated", "user": {
        "full_name": current_user.full_name,
        "store_name": current_user.store_name,
        "email": current_user.email,
        "phone": current_user.phone
    }}

@router.post("/change-password")
def change_password(req: ChangePasswordRequest, db: Session = Depends(get_db), current_user: User = Depends(_get_current_user)):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


# 7. Logout (client just deletes token, but this can blacklist if needed)
@router.post("/logout")
def logout(_: User = Depends(_get_current_user)):
    return {"message": "Logged out successfully"}