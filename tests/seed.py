from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, Subscription, Account, Trade, EquitySnapshot
import os
from datetime import datetime, timedelta

def seed(db: Session):
    u = User(email="test@example.com", status="ACTIVE", email_verified=True)
    db.add(u); db.flush()
    s = Subscription(user_id=u.id, status="active", plan="25_month")
    db.add(s); db.flush()
    a = Account(user_id=u.id, broker="OANDA", account_id="101-001-00000000-001", label="Demo", is_primary=True)
    db.add(a); db.flush()
    # trades
    now = datetime.utcnow()
    t1 = Trade(account_id=a.id, instrument="EUR_USD", side="LONG", units=100, opened_at=now-timedelta(days=2, hours=2), closed_at=now-timedelta(days=2), entry_price=1.1, exit_price=1.101, pnl_net=10)
    t2 = Trade(account_id=a.id, instrument="GBP_USD", side="SHORT", units=100, opened_at=now-timedelta(days=1, hours=2), closed_at=now-timedelta(days=1), entry_price=1.2, exit_price=1.195, pnl_net=5)
    t3 = Trade(account_id=a.id, instrument="USD_JPY", side="LONG", units=100, opened_at=now-timedelta(hours=12), closed_at=now-timedelta(hours=10), entry_price=150.0, exit_price=149.7, pnl_net=-30)
    db.add_all([t1,t2,t3])
    # equity
    for d in range(3):
        snap = EquitySnapshot(account_id=a.id, taken_at=now-timedelta(days=d), balance=10000+d, equity=10000+d*5, margin_used=0)
        db.add(snap)
    db.commit()
    print("Seeded user:", u.email, "account_id:", a.id)

if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "sqlite:///./autopip.db")
    engine = create_engine(url, future=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
