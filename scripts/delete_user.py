#!/usr/bin/env python3
"""
Script to delete a user and all their related data from the database.

Usage:
    python scripts/delete_user.py <email>

This will delete:
- All equity snapshots for the user's accounts
- All trades for the user
- All broker credentials for the user
- All accounts for the user
- All subscriptions for the user
- The user record itself

After deletion, you can recreate the user profile from the dashboard.
"""

import sys
import os

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import (
    User,
    Subscription,
    Account,
    Trade,
    EquitySnapshot,
    BrokerCredential,
)


def delete_user_by_email(email: str, confirm: bool = False) -> bool:
    """
    Delete a user and all their related data.
    
    Args:
        email: The email address of the user to delete
        confirm: If True, skip confirmation prompt
        
    Returns:
        True if user was deleted, False if not found or cancelled
    """
    db: Session = SessionLocal()
    
    try:
        # Normalize email (lowercase, strip)
        email = email.strip().lower()
        
        # Find the user
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ User with email '{email}' not found in database.")
            return False
        
        # Show what will be deleted
        subscriptions_count = db.query(Subscription).filter(Subscription.user_id == user.id).count()
        accounts_count = db.query(Account).filter(Account.user_id == user.id).count()
        broker_cred_count = 1 if user.broker_credential else 0
        
        # Count trades and equity snapshots
        account_ids = [acc.id for acc in user.accounts]
        trades_count = db.query(Trade).filter(Trade.user_id == user.id).count()
        equity_count = db.query(EquitySnapshot).filter(EquitySnapshot.account_id.in_(account_ids)).count() if account_ids else 0
        
        print(f"\n📋 User found: {user.email}")
        print(f"   ID: {user.id}")
        print(f"   Status: {user.status}")
        print(f"   Role: {user.role}")
        print(f"   Created: {user.created_at}")
        print(f"\n📊 Data to be deleted:")
        print(f"   - Subscriptions: {subscriptions_count}")
        print(f"   - Accounts: {accounts_count}")
        print(f"   - Broker Credentials: {broker_cred_count}")
        print(f"   - Trades: {trades_count}")
        print(f"   - Equity Snapshots: {equity_count}")
        print(f"   - User record: 1")
        
        # Confirm deletion
        if not confirm:
            response = input(f"\n⚠️  Are you sure you want to delete user '{email}' and ALL their data? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("❌ Deletion cancelled.")
                return False
        
        # Delete in correct order to respect foreign key constraints
        print("\n🗑️  Deleting user data...")
        
        # 1. Delete equity snapshots (via accounts)
        if account_ids:
            deleted_equity = db.query(EquitySnapshot).filter(EquitySnapshot.account_id.in_(account_ids)).delete(synchronize_session=False)
            print(f"   ✓ Deleted {deleted_equity} equity snapshots")
        
        # 2. Delete trades (references both account_id and user_id)
        deleted_trades = db.query(Trade).filter(Trade.user_id == user.id).delete(synchronize_session=False)
        print(f"   ✓ Deleted {deleted_trades} trades")
        
        # 3. Delete broker credentials (one-to-one with user)
        if user.broker_credential:
            db.delete(user.broker_credential)
            print(f"   ✓ Deleted broker credentials")
        
        # 4. Delete accounts (references user_id)
        deleted_accounts = db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False)
        print(f"   ✓ Deleted {deleted_accounts} accounts")
        
        # 5. Delete subscriptions (references user_id)
        deleted_subs = db.query(Subscription).filter(Subscription.user_id == user.id).delete(synchronize_session=False)
        print(f"   ✓ Deleted {deleted_subs} subscriptions")
        
        # 6. Finally, delete the user
        db.delete(user)
        print(f"   ✓ Deleted user record")
        
        # Commit the transaction
        db.commit()
        
        print(f"\n✅ Successfully deleted user '{email}' and all related data!")
        print(f"   You can now recreate their profile from the dashboard.")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error deleting user: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    email = sys.argv[1]
    confirm = "--yes" in sys.argv or "-y" in sys.argv
    
    success = delete_user_by_email(email, confirm=confirm)
    sys.exit(0 if success else 1)








