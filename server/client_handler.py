"""
Client Handler Module
Manages individual client connections and command/response communication
"""

import socket
import threading
import time
import uuid
import secrets
from common.protocol import send_message, recv_message
from common.config import (
    SOCKET_TIMEOUT,
    MSG_REGISTER, MSG_CMD, MSG_RESULT, MSG_TOKEN_REQUEST, MSG_TOKEN_STATUS,
    TOKEN_PENDING, TOKEN_APPROVED, TOKEN_DENIED, TOKEN_REVOKED, TOKEN_INVALID
)
from common.auth import hash_token
from server.logger_config import logger
from server import token_manager
from server import notifications


# ANSI Color codes (avoid circular import with cli.py)
class _Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'

Colors = _Colors()


# Global client registry (authenticated clients only)
clients = {}  # {hostname: {session_id, socket, address, thread, lock}}
clients_lock = threading.Lock()

# Pending token request connections (waiting for approval)
pending_clients = {}  # {hostname: {socket, address, session_id}}
pending_clients_lock = threading.Lock()


def handle_client(client_socket, client_address):
    """
    Handle individual client connection lifecycle

    Args:
        client_socket: Connected socket object
        client_address: Tuple of (IP, port)
    """
    # Generate unique session ID
    session_id = str(uuid.uuid4())[:8]

    logger.info(f"[SESSION:{session_id}] Client connected: {client_address[0]}:{client_address[1]}")

    hostname = None

    try:
        # Wait for first message (either REGISTER or TOKEN_REQUEST)
        first_message = recv_message(client_socket)

        if not first_message:
            logger.warning(f"[SESSION:{session_id}] No message from {client_address}")
            client_socket.close()
            return

        # Handle token request
        if first_message.startswith(MSG_TOKEN_REQUEST):
            handle_token_request(client_socket, client_address, session_id, first_message)
            return

        # Handle registration
        if first_message.startswith(MSG_REGISTER):
            hostname = handle_registration(client_socket, client_address, session_id, first_message)
            if not hostname:
                return

            # Registration successful - keep connection alive
            logger.info(f"[SESSION:{session_id}] Client authenticated: {hostname}")

            # Keep thread alive - socket managed by CLI thread
            while True:
                time.sleep(60)

        else:
            logger.warning(f"[SESSION:{session_id}] Invalid message type from {client_address}")
            client_socket.close()
            return

    except Exception as e:
        logger.error(f"[SESSION:{session_id}] Error handling client {hostname or client_address}: {e}")
    finally:
        # Cleanup on disconnection or error
        with clients_lock:
            if hostname and hostname in clients:
                del clients[hostname]
                logger.info(f"[SESSION:{session_id}] Client disconnected: {hostname}")

        try:
            client_socket.close()
        except:
            pass


def handle_registration(client_socket, client_address, session_id, reg_message):
    """
    Handle client registration with token validation

    Returns:
        str: hostname if successful, None otherwise
    """
    # Parse registration: REGISTER:hostname:token
    parts = reg_message.split(':', 2)
    if len(parts) != 3:
        logger.warning(f"[SESSION:{session_id}] Invalid registration format from {client_address}")
        client_socket.close()
        return None

    hostname = parts[1]
    client_token = parts[2]

    # Check token status first
    stored_token, token_status = token_manager.get_token_by_hostname(hostname)

    # If token exists and matches, check status
    if stored_token and token_status:
        if secrets.compare_digest(stored_token, client_token):
            # Token matches, check status
            if token_status == 'revoked':
                logger.warning(f"[SESSION:{session_id}] Revoked token used by {hostname} from {client_address[0]}")

                # Send revoked status (not invalid)
                try:
                    send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_REVOKED}")
                except:
                    pass

                client_socket.close()
                return None
            elif token_status == 'approved':
                # Token is valid, proceed with registration
                pass
            else:
                # Token exists but not approved (pending, denied, etc.)
                logger.warning(f"[SESSION:{session_id}] Non-approved token ({token_status}) used by {hostname}")
                try:
                    send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
                except:
                    pass

                client_socket.close()
                return None
        else:
            # Token doesn't match
            logger.warning(f"[SESSION:{session_id}] Invalid token for {hostname} from {client_address[0]}")
            try:
                send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
            except:
                pass

            client_socket.close()
            return None
    else:
        # No token found for hostname
        logger.warning(f"[SESSION:{session_id}] No token found for {hostname} from {client_address[0]}")
        try:
            send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
        except:
            pass

        client_socket.close()
        return None

    logger.info(f"[SESSION:{session_id}] Client authenticated: {hostname} from {client_address[0]}")

    # Check for duplicate hostname
    with clients_lock:
        if hostname in clients:
            old_session = clients[hostname]['session_id']
            logger.warning(f"[SESSION:{session_id}] Duplicate hostname '{hostname}' - overwriting session {old_session}")

        clients[hostname] = {
            'session_id': session_id,
            'socket': client_socket,
            'address': client_address,
            'thread': threading.current_thread(),
            'lock': threading.Lock()  # Per-client socket lock
        }

    # Get client number for display
    with clients_lock:
        client_number = len(clients)

    # Notify operator with visual alert
    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}  ✅ CLIENT CONNECTED!{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}   Hostname: {Colors.BOLD}{hostname}{Colors.RESET}")
    print(f"{Colors.CYAN}   Session ID: {Colors.BOLD}{session_id}{Colors.RESET}")
    print(f"{Colors.CYAN}   IP Address: {Colors.BOLD}{client_address[0]}{Colors.RESET}")
    print(f"\n{Colors.YELLOW}   Quick Action:{Colors.RESET}")
    print(f"   → Type: {Colors.BOLD}use {hostname}{Colors.RESET} or {Colors.BOLD}use {client_number}{Colors.RESET} to interact")
    print(f"   → Or use: {Colors.BOLD}list{Colors.RESET} to see all clients")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    return hostname


def handle_token_request(client_socket, client_address, session_id, request_message):
    """
    Handle token request from client and keep connection alive for polling

    Args:
        client_socket: Connected socket
        client_address: Client address tuple
        session_id: Session ID
        request_message: TOKEN_REQUEST message
    """
    # Parse: TOKEN_REQUEST:hostname:ip
    parts = request_message.split(':', 2)
    if len(parts) < 2:
        logger.warning(f"[SESSION:{session_id}] Invalid token request format from {client_address}")
        client_socket.close()
        return

    hostname = parts[1]
    ip_address = client_address[0] if len(parts) < 3 else parts[2]

    # Check if this is a status check (polling for approval)
    if len(parts) > 2 and parts[2] == 'status_check':
        # Client is polling for status update
        token, status = token_manager.get_token_by_hostname(hostname)

        if status == TOKEN_APPROVED:
            send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_APPROVED}:{token}")
        elif status == TOKEN_DENIED:
            send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_DENIED}")
        elif status == TOKEN_PENDING:
            send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_PENDING}")
        else:
            send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
        return

    logger.info(f"[SESSION:{session_id}] Token request from {hostname} ({ip_address})")

    # Request token from token manager
    success, token, status = token_manager.request_token(hostname, ip_address)

    if not success:
        logger.error(f"[SESSION:{session_id}] Failed to create token request for {hostname}")
        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
        client_socket.close()
        return

    # Send status to client
    if status == TOKEN_APPROVED:
        # Already approved - send token immediately
        logger.info(f"[SESSION:{session_id}] Token already approved for {hostname}")
        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_APPROVED}:{token}")

    elif status == TOKEN_PENDING:
        # New or updated pending request
        logger.info(f"[SESSION:{session_id}] Token request pending for {hostname}")

        # Add to notification queue
        notifications.notify_token_request(hostname, ip_address)

        # Send pending status
        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_PENDING}")

        # Display visual notification to operator
        print(f"\n{Colors.YELLOW}{Colors.BOLD}{'='*70}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}  🔔 NEW TOKEN REQUEST!{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}{'='*70}{Colors.RESET}")
        print(f"{Colors.CYAN}   Hostname: {Colors.BOLD}{hostname}{Colors.RESET}")
        print(f"{Colors.CYAN}   IP Address: {Colors.BOLD}{ip_address}{Colors.RESET}")
        print(f"\n{Colors.GREEN}   Quick Action:{Colors.RESET}")
        print(f"   → Type: {Colors.BOLD}approve {hostname}{Colors.RESET}")
        print(f"   → Or use: {Colors.BOLD}pending{Colors.RESET} to see all requests")
        print(f"{Colors.YELLOW}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    # Keep connection alive and handle polling
    # This loop will process status check requests until client disconnects
    try:
        while True:
            # Wait for next message from client (polling requests)
            message = recv_message(client_socket)

            if not message:
                # Client disconnected
                logger.info(f"[SESSION:{session_id}] Client {hostname} disconnected while waiting for approval")
                break

            if message.startswith(MSG_TOKEN_REQUEST):
                # Handle polling request
                parts = message.split(':', 2)
                if len(parts) > 2 and parts[2] == 'status_check':
                    # Check current status
                    token, status = token_manager.get_token_by_hostname(hostname)

                    if status == TOKEN_APPROVED:
                        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_APPROVED}:{token}")
                        logger.info(f"[SESSION:{session_id}] Token approved sent to {hostname}")
                        # Client will disconnect after receiving approval
                        break
                    elif status == TOKEN_DENIED:
                        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_DENIED}")
                        logger.info(f"[SESSION:{session_id}] Token denied sent to {hostname}")
                        break
                    elif status == TOKEN_PENDING:
                        # Still pending, send pending status
                        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_PENDING}")
                    else:
                        send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_INVALID}")
                        break
            else:
                # Unexpected message type
                logger.warning(f"[SESSION:{session_id}] Unexpected message from pending client {hostname}: {message[:50]}")
                break

    except Exception as e:
        logger.error(f"[SESSION:{session_id}] Error handling token polling for {hostname}: {e}")
    finally:
        # Clean up when done
        logger.info(f"[SESSION:{session_id}] Closing token request connection for {hostname}")


def send_command_to_client(hostname, command):
    """
    Send command to specific client and receive response

    Args:
        hostname: Target client hostname
        command: Command string to execute

    Returns:
        tuple: (stdout, stderr) or (None, None) on error
    """
    with clients_lock:
        if hostname not in clients:
            return None, "Client not found or not authenticated"

        client_info = clients[hostname]
        client_socket = client_info['socket']
        socket_lock = client_info['lock']
        session_id = client_info['session_id']

    # Use per-client lock to prevent race conditions
    with socket_lock:
        try:
            logger.debug(f"[SESSION:{session_id}] Sending command to {hostname}: {command}")

            # Send command
            if not send_message(client_socket, f"{MSG_CMD}:{command}"):
                logger.warning(f"[SESSION:{session_id}] Failed to send command to {hostname}")
                return None, "Failed to send command"

            logger.info(f"[SESSION:{session_id}] Command sent to {hostname}: {command}")

            # Wait for response with timeout
            client_socket.settimeout(SOCKET_TIMEOUT)
            response = recv_message(client_socket)

            if response is None:
                logger.warning(f"[SESSION:{session_id}] No response from {hostname}")
                return None, "No response from client (may be disconnected)"

            if not response.startswith(MSG_RESULT):
                logger.warning(f"[SESSION:{session_id}] Invalid response format from {hostname}")
                return None, "Invalid response format"

            # Parse result: RESULT:stdout|||stderr
            result_data = response.split(':', 1)[1]
            parts = result_data.split('|||')

            stdout = parts[0] if len(parts) > 0 else ''
            stderr = parts[1] if len(parts) > 1 else ''

            logger.info(f"[SESSION:{session_id}] Response received from {hostname}: {len(stdout)} bytes stdout, {len(stderr)} bytes stderr")

            return stdout, stderr

        except socket.timeout:
            logger.error(f"[SESSION:{session_id}] Timeout waiting for response from {hostname}")
            return None, "Timeout waiting for response"
        except Exception as e:
            logger.error(f"[SESSION:{session_id}] Error communicating with {hostname}: {e}")
            return None, f"Error: {e}"


def get_clients_list():
    """
    Get list of connected and authenticated clients

    Returns:
        list: List of tuples (index, hostname, info_dict)
    """
    with clients_lock:
        return [(idx, hostname, info)
                for idx, (hostname, info) in enumerate(clients.items(), 1)]


def get_hostname_by_number(number):
    """
    Convert client number to hostname

    Args:
        number: Client number (as string or int)

    Returns:
        str: Hostname or None if not found
    """
    try:
        num = int(number)
        client_list = get_clients_list()

        for idx, hostname, info in client_list:
            if idx == num:
                return hostname
        return None
    except (ValueError, IndexError):
        return None
