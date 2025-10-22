"""
Notification System
Handles real-time notifications for token requests and other events
"""

import queue
import threading
from datetime import datetime

# Global notification queue
notification_queue = queue.Queue()

# Pending token request counter
pending_count = 0
pending_count_lock = threading.Lock()


def notify_token_request(hostname, ip_address):
    """
    Add a token request notification to the queue
    """
    global pending_count

    with pending_count_lock:
        pending_count += 1

    notification = {
        'type': 'token_request',
        'hostname': hostname,
        'ip': ip_address,
        'timestamp': datetime.now()
    }

    notification_queue.put(notification)


def get_notification():
    """
    Get the next notification from the queue (non-blocking)
    Returns: notification dict or None
    """
    try:
        return notification_queue.get_nowait()
    except queue.Empty:
        return None


def get_pending_count():
    """
    Get the current count of pending token requests
    Returns: int
    """
    with pending_count_lock:
        return pending_count


def decrement_pending():
    """
    Decrement the pending count (called when request is approved/denied)
    """
    global pending_count

    with pending_count_lock:
        pending_count = max(0, pending_count - 1)


def set_pending_count(count):
    """
    Set the pending count to a specific value
    """
    global pending_count

    with pending_count_lock:
        pending_count = count
