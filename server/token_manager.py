"""
Token Manager Module
Handles per-client token storage, validation, and approval workflow
"""

import sqlite3
import secrets
import threading
from pathlib import Path
from common.auth import generate_token

# Database file location
DB_FILE = Path(__file__).parent / 'tokens.db'
db_lock = threading.Lock()


def init_database():
    """Initialize the token database with schema"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT UNIQUE NOT NULL,
                token TEXT NOT NULL,
                status TEXT NOT NULL,
                ip_address TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                revoked_at TIMESTAMP,
                notes TEXT
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON tokens(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hostname ON tokens(hostname)')

        conn.commit()
        conn.close()


def request_token(hostname, ip_address):
    """
    Handle a token request from a client
    Returns: (success: bool, token: str, status: str)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if hostname already exists
        cursor.execute('SELECT token, status FROM tokens WHERE hostname = ?', (hostname,))
        existing = cursor.fetchone()

        if existing:
            token, status = existing
            conn.close()

            # If already approved, return the existing token
            if status == 'approved':
                return (True, token, 'approved')
            # If pending, return pending status
            elif status == 'pending':
                return (True, token, 'pending')
            # If revoked or denied, update to pending with new token
            else:
                new_token = generate_token()
                cursor = sqlite3.connect(DB_FILE).cursor()
                cursor.execute('''
                    UPDATE tokens
                    SET token = ?, status = 'pending', ip_address = ?,
                        requested_at = CURRENT_TIMESTAMP, approved_at = NULL, revoked_at = NULL
                    WHERE hostname = ?
                ''', (new_token, ip_address, hostname))
                cursor.connection.commit()
                cursor.connection.close()
                return (True, new_token, 'pending')

        # New hostname - create pending token
        token = generate_token()
        try:
            cursor.execute('''
                INSERT INTO tokens (hostname, token, status, ip_address)
                VALUES (?, ?, 'pending', ?)
            ''', (hostname, token, ip_address))
            conn.commit()
            conn.close()
            return (True, token, 'pending')
        except sqlite3.IntegrityError:
            conn.close()
            return (False, None, 'error')


def validate_client_token(hostname, provided_token):
    """
    Validate a client's token
    Returns: True if token is valid and approved, False otherwise
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT token, status FROM tokens WHERE hostname = ?
        ''', (hostname,))

        result = cursor.fetchone()
        conn.close()

        if not result:
            return False

        stored_token, status = result

        # Token must match and status must be approved
        return secrets.compare_digest(stored_token, provided_token) and status == 'approved'


def approve_token(hostname):
    """
    Approve a pending token request
    Returns: (success: bool, token: str or None)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('SELECT token, status FROM tokens WHERE hostname = ?', (hostname,))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return (False, None)

        token, status = result

        if status == 'approved':
            conn.close()
            return (True, token)  # Already approved

        cursor.execute('''
            UPDATE tokens
            SET status = 'approved', approved_at = CURRENT_TIMESTAMP
            WHERE hostname = ?
        ''', (hostname,))

        conn.commit()
        conn.close()
        return (True, token)


def deny_token(hostname):
    """
    Deny a pending token request
    Returns: success: bool
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE tokens
            SET status = 'denied'
            WHERE hostname = ?
        ''', (hostname,))

        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0


def revoke_token(hostname):
    """
    Revoke an approved token
    Returns: success: bool
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE tokens
            SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP
            WHERE hostname = ?
        ''', (hostname,))

        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0


def add_token_manual(hostname):
    """
    Manually add and approve a token for a hostname
    Returns: (success: bool, token: str or None)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if already exists
        cursor.execute('SELECT token, status FROM tokens WHERE hostname = ?', (hostname,))
        existing = cursor.fetchone()

        if existing:
            token, status = existing
            if status != 'approved':
                # Update to approved
                cursor.execute('''
                    UPDATE tokens
                    SET status = 'approved', approved_at = CURRENT_TIMESTAMP
                    WHERE hostname = ?
                ''', (hostname,))
                conn.commit()
            conn.close()
            return (True, token)

        # Create new approved token
        token = generate_token()
        try:
            cursor.execute('''
                INSERT INTO tokens (hostname, token, status, approved_at)
                VALUES (?, ?, 'approved', CURRENT_TIMESTAMP)
            ''', (hostname, token))
            conn.commit()
            conn.close()
            return (True, token)
        except sqlite3.IntegrityError:
            conn.close()
            return (False, None)


def get_pending_requests():
    """
    Get all pending token requests
    Returns: List of (hostname, ip_address, requested_at)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT hostname, ip_address, requested_at
            FROM tokens
            WHERE status = 'pending'
            ORDER BY requested_at ASC
        ''')

        results = cursor.fetchall()
        conn.close()
        return results


def get_all_tokens():
    """
    Get all tokens with their status
    Returns: List of (hostname, status, ip_address, requested_at, approved_at)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT hostname, status, ip_address, requested_at, approved_at, revoked_at
            FROM tokens
            ORDER BY requested_at DESC
        ''')

        results = cursor.fetchall()
        conn.close()
        return results


def get_token_by_hostname(hostname):
    """
    Get token info for a specific hostname
    Returns: (token, status) or (None, None)
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('SELECT token, status FROM tokens WHERE hostname = ?', (hostname,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return result
        return (None, None)


def delete_token(hostname):
    """
    Completely delete a token entry
    Returns: success: bool
    """
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM tokens WHERE hostname = ?', (hostname,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0
