"""
Mailchimp → Users table sync script.

This script syncs Mailchimp subscribers to the local users table:
- Retrieves all subscribers from a Mailchimp audience/list
- Creates pre-provisioned User records for new subscribers
- Updates status for existing users based on Mailchimp subscription status

Run with:
    python -m app.scripts.sync_mailchimp_users
"""

import logging
import os
import sys
from typing import List, Optional

from mailchimp_marketing import Client
from mailchimp_marketing.api_client import ApiClientError
from sqlalchemy.orm import Session

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db import SessionLocal
from app.models import User
from app.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _get_datacenter(api_key: str) -> Optional[str]:
    """Extract the datacenter suffix from a Mailchimp API key.
    
    Mailchimp API keys are in the format: <key>-<datacenter>
    Example: abc123def456-us1
    """
    if "-" not in api_key:
        return None
    return api_key.split("-")[-1]


def _normalize_email(email: str) -> str:
    """Normalize email address: lowercase and strip whitespace."""
    return email.lower().strip()


def _fetch_all_subscribers(api_key: str, server_prefix: str, list_id: str) -> List[dict]:
    """Retrieve all subscribers from Mailchimp audience/list.
    
    Returns a list of subscriber dictionaries with email and status.
    """
    mailchimp = Client()
    mailchimp.set_config({
        "api_key": api_key,
        "server": server_prefix,
    })
    
    subscribers = []
    offset = 0
    count = 1000  # Maximum allowed by Mailchimp API
    
    try:
        # Fetch subscribed members
        logger.info("Fetching subscribed members from Mailchimp...")
        total_subscribed = None
        
        while True:
            logger.info(f"  Fetching batch (offset: {offset})...")
            
            try:
                response = mailchimp.lists.get_list_members_info(
                    list_id,
                    count=count,
                    offset=offset,
                    status="subscribed",
                )
            except ApiClientError as e:
                # Try without status filter if it fails
                logger.warning(f"  Error with status filter, trying without: {e}")
                try:
                    response = mailchimp.lists.get_list_members_info(
                        list_id,
                        count=count,
                        offset=offset,
                    )
                except ApiClientError as e2:
                    logger.error(f"  Mailchimp API error: {e2}")
                    raise
            
            if total_subscribed is None:
                total_subscribed = response.get("total_items", 0)
                logger.info(f"  Total subscribed members: {total_subscribed}")
            
            members = response.get("members", [])
            if not members:
                break
            
            # Filter to only subscribed status if we didn't use status filter
            for member in members:
                email = member.get("email_address", "").strip()
                status = member.get("status", "").lower()
                
                if email and status == "subscribed":
                    subscribers.append({
                        "email": email,
                        "status": "subscribed",
                    })
            
            # Check if there are more members
            if len(members) < count or (total_subscribed and offset + len(members) >= total_subscribed):
                break
            
            offset += count
        
        # Reset offset for unsubscribed members
        offset = 0
        
        # Also fetch unsubscribed members to potentially mark them as INACTIVE
        logger.info("Fetching unsubscribed members from Mailchimp...")
        
        while True:
            try:
                logger.info(f"  Fetching batch (offset: {offset})...")
                response = mailchimp.lists.get_list_members_info(
                    list_id,
                    count=count,
                    offset=offset,
                    status="unsubscribed",
                )
                
                members = response.get("members", [])
                if not members:
                    break
                
                for member in members:
                    email = member.get("email_address", "").strip()
                    status = member.get("status", "").lower()
                    
                    if email and status == "unsubscribed":
                        subscribers.append({
                            "email": email,
                            "status": "unsubscribed",
                        })
                
                if len(members) < count:
                    break
                
                offset += count
            except ApiClientError as e:
                logger.warning(f"  Error fetching unsubscribed members (may be none): {e}")
                break
        
        logger.info(f"Total subscribers retrieved: {len(subscribers)} (subscribed + unsubscribed)")
        return subscribers
        
    except ApiClientError as e:
        logger.error(f"Mailchimp API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching subscribers: {e}")
        raise


def _sync_subscribers_to_db(db: Session, subscribers: List[dict], batch_size: int = 100):
    """Sync Mailchimp subscribers to the users table.
    
    Args:
        db: SQLAlchemy session
        subscribers: List of subscriber dicts with email and status
        batch_size: Number of records to commit in each batch
    """
    new_users_count = 0
    updated_users_count = 0
    skipped_count = 0
    
    # Normalize and deduplicate subscribers (keep latest status if duplicate email)
    subscriber_map = {}
    for sub in subscribers:
        email = _normalize_email(sub["email"])
        if email:
            subscriber_map[email] = sub["status"]
    
    logger.info(f"Processing {len(subscriber_map)} unique subscribers...")
    
    for idx, (email, mailchimp_status) in enumerate(subscriber_map.items(), 1):
        try:
            # Check if user exists
            user = db.query(User).filter(User.email == email).one_or_none()
            
            if user is None:
                # Create new user
                user = User(
                    email=email,
                    status="INVITED",
                    email_verified=False,
                    password_hash=None,
                    role="USER",
                    has_tier1=False,
                )
                db.add(user)
                new_users_count += 1
                
                if new_users_count % 10 == 0:
                    logger.info(f"  Added {new_users_count} new users so far...")
            
            else:
                # Update existing user status if needed
                status_updated = False
                
                if mailchimp_status == "subscribed":
                    # If subscribed in Mailchimp, ensure status is INVITED (if not already set to something else)
                    # Only update if user is in a pre-registration state
                    if user.status in ["PENDING_PASSWORD", None] or user.password_hash is None:
                        if user.status != "INVITED":
                            user.status = "INVITED"
                            status_updated = True
                
                elif mailchimp_status == "unsubscribed":
                    # If unsubscribed in Mailchimp, set to INACTIVE
                    if user.status != "INACTIVE":
                        user.status = "INACTIVE"
                        status_updated = True
                
                if status_updated:
                    updated_users_count += 1
                else:
                    skipped_count += 1
            
            # Commit in batches
            if idx % batch_size == 0:
                try:
                    db.commit()
                    logger.info(f"  Committed batch (processed {idx}/{len(subscriber_map)})...")
                except Exception as e:
                    logger.error(f"Error committing batch at index {idx}: {e}")
                    db.rollback()
                    # Re-raise to stop processing on commit errors
                    raise
        
        except Exception as e:
            logger.error(f"Error processing subscriber {email}: {e}")
            # On individual subscriber errors, log and continue
            # We'll commit successful records at the next batch boundary
            skipped_count += 1
            continue
    
    # Final commit for remaining records
    try:
        db.commit()
        logger.info("Final commit completed.")
    except Exception as e:
        logger.error(f"Error in final commit: {e}")
        db.rollback()
        raise
    
    logger.info("=" * 60)
    logger.info("Sync Summary:")
    logger.info(f"  New users added: {new_users_count}")
    logger.info(f"  Existing users updated: {updated_users_count}")
    logger.info(f"  Existing users skipped (no changes): {skipped_count}")
    logger.info(f"  Total processed: {new_users_count + updated_users_count + skipped_count}")
    logger.info("=" * 60)


def main():
    """Main entry point for the sync script."""
    logger.info("Starting Mailchimp → Users sync...")
    
    # Validate configuration
    api_key = settings.MAILCHIMP_API_KEY
    list_id = settings.MAILCHIMP_LIST_ID
    
    if not api_key:
        logger.error("MAILCHIMP_API_KEY environment variable is not set")
        sys.exit(1)
    
    if not list_id:
        logger.error("MAILCHIMP_LIST_ID environment variable is not set")
        sys.exit(1)
    
    # Extract server prefix from API key
    server_prefix = _get_datacenter(api_key)
    if not server_prefix:
        logger.error(
            "Failed to extract server prefix from MAILCHIMP_API_KEY. "
            "API key should be in format: <key>-<datacenter> (e.g., abc123-us1)"
        )
        sys.exit(1)
    
    logger.info(f"Using Mailchimp server: {server_prefix}")
    logger.info(f"Using Mailchimp list ID: {list_id}")
    
    # Fetch subscribers from Mailchimp
    try:
        subscribers = _fetch_all_subscribers(api_key, server_prefix, list_id)
    except Exception as e:
        logger.error(f"Failed to fetch subscribers from Mailchimp: {e}")
        sys.exit(1)
    
    if not subscribers:
        logger.warning("No subscribers found in Mailchimp. Exiting.")
        return
    
    # Sync to database
    db = SessionLocal()
    try:
        _sync_subscribers_to_db(db, subscribers)
    except Exception as e:
        logger.error(f"Failed to sync subscribers to database: {e}")
        sys.exit(1)
    finally:
        db.close()
    
    logger.info("Mailchimp → Users sync completed successfully!")


if __name__ == "__main__":
    main()

