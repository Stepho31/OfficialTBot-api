from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.entitlements import compute_entitlements, should_email_user_signal
from app.schemas import PaidEmailsOut

router = APIRouter(prefix="/access", tags=["access"])

@router.get("/paid-emails", response_model=PaidEmailsOut)
def paid_emails(db: Session = Depends(get_db)):
    """
    Return all user emails that should receive email signals.
    Uses entitlements logic which respects FREE_SIGNALS_UNTIL cutoff date.
    """
    all_users = db.query(User).all()
    emails = []
    for user in all_users:
        if should_email_user_signal(db, user.id):
            emails.append(user.email)
    return PaidEmailsOut(emails=emails)
