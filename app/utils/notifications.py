# app/utils/notifications.py
from typing import Dict
from datetime import datetime

def notify_overspend(user_id: str, category_name: str, overspend_amt: float) -> None:
    """
    Placeholder: Send overspend alert to user (e.g., push notification, email).
    Right now, just print to console or store in a notifications table.
    """
    # TODO: Integrate with actual notification system (Redis + Celery + Email/push)
    print(f"[{datetime.utcnow()}] User {user_id} overspent {overspend_amt} in {category_name}")
    # Optionally: insert into a Notification DB table

def notify_savings_milestone(user_id: str, saved_amt: float, target: float) -> None:
    """
    Notify user that they've hit a savings milestone.
    """
    print(f"[{datetime.utcnow()}] User {user_id} saved {saved_amt}/{target}!")
    # TODO: enqueue to truly send
