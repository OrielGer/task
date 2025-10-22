#!/usr/bin/env python3
"""
C2 Server - Main Entry Point
Starts listener and operator CLI
"""

import threading
import time
import socket
import os
from server.listener import start_listener
from server.cli import operator_cli, Colors
from server.logger_config import logger
from server import token_manager
from server import notifications
from common.config import HOST, PORT, TLS_ENABLED, SERVER_CERT, SERVER_KEY


def get_public_ip():
    """Get public IP address for remote connections"""
    try:
        import urllib.request
        # Try multiple services in case one is down
        services = [
            'https://api.ipify.org',
            'https://icanhazip.com',
            'https://ifconfig.me/ip'
        ]

        for service in services:
            try:
                response = urllib.request.urlopen(service, timeout=3)
                public_ip = response.read().decode('utf-8').strip()
                if public_ip:
                    return public_ip
            except:
                continue
        return None
    except:
        return None


def show_startup_banner():
    """Display server startup banner with connection instructions"""
    # Get local IP (for same network)
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except:
        local_ip = "Unable to detect"

    # Get public IP (for remote connections)
    public_ip = get_public_ip()

    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}  C2 SERVER - READY FOR CONNECTIONS{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    print(f"{Colors.CYAN}{Colors.BOLD}📡 Server Information:{Colors.RESET}")
    print(f"   • Listening on: {Colors.BOLD}{HOST}:{PORT}{Colors.RESET} (all interfaces)")

    # Display both IPs with port
    print(f"   • Local Address: {Colors.BOLD}{Colors.GREEN}{local_ip}:{PORT}{Colors.RESET} {Colors.CYAN}(same network){Colors.RESET}")
    if public_ip:
        print(f"   • Public Address: {Colors.BOLD}{Colors.YELLOW}{public_ip}:{PORT}{Colors.RESET} {Colors.CYAN}(remote access){Colors.RESET}")
    else:
        print(f"   • Public Address: {Colors.YELLOW}Unable to detect{Colors.RESET} {Colors.CYAN}(check manually if needed){Colors.RESET}")

    print(f"   • Security: {Colors.GREEN}TLS Encryption + Per-Client Tokens{Colors.RESET}")

    print(f"\n{Colors.YELLOW}{Colors.BOLD}📱 HOW TO CONNECT A CLIENT:{Colors.RESET}")
    print(f"{Colors.BOLD}   Step 1:{Colors.RESET} On the client machine, run:")
    print(f"           {Colors.CYAN}python c2_client.py{Colors.RESET}")
    print(f"{Colors.BOLD}   Step 2:{Colors.RESET} Enter server address:")
    print(f"           • Same WiFi/network: {Colors.GREEN}{Colors.BOLD}{local_ip}:{PORT}{Colors.RESET}")
    if public_ip:
        print(f"           • Different network: {Colors.YELLOW}{Colors.BOLD}{public_ip}:{PORT}{Colors.RESET}")
    print(f"{Colors.BOLD}   Step 3:{Colors.RESET} Client will request a token automatically")
    print(f"{Colors.BOLD}   Step 4:{Colors.RESET} You'll see a notification here - approve it!")

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}💡 HELPFUL TIPS:{Colors.RESET}")
    print(f"   • Type {Colors.BOLD}help{Colors.RESET} to see all available commands")
    print(f"   • Type {Colors.BOLD}list{Colors.RESET} to see connected clients and pending requests")
    print(f"   • Approve token requests with: {Colors.BOLD}approve <hostname>{Colors.RESET}")
    print(f"   • Use {Colors.BOLD}use <#>{Colors.RESET} to interact with a client (e.g., {Colors.BOLD}use 1{Colors.RESET})")

    print(f"\n{Colors.CYAN}📝 Logs: {Colors.BOLD}c2_server.log{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")


def run_auto_setup():
    """Run automatic security setup if certificates are missing"""
    print(f"\n{Colors.YELLOW}{'='*70}{Colors.RESET}")
    print(f"{Colors.YELLOW}  🔧 AUTOMATIC SECURITY SETUP{Colors.RESET}")
    print(f"{Colors.YELLOW}{'='*70}{Colors.RESET}\n")
    print(f"{Colors.CYAN}TLS certificates not found.{Colors.RESET}")
    print(f"{Colors.CYAN}Generating certificates automatically...{Colors.RESET}\n")

    # Automatically run setup without prompting
    print(f"{Colors.GREEN}[*] Running automatic setup...{Colors.RESET}\n")

    # Import and run setup
    try:
        from server import setup_security
        print(f"\n{Colors.GREEN}[+] Certificates generated successfully!{Colors.RESET}")
        print(f"{Colors.GREEN}[+] Security configured!{Colors.RESET}")
        print(f"{Colors.GREEN}[*] Starting server...{Colors.RESET}\n")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"{Colors.RED}[!] Setup failed: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}[*] Please run manually: python server/setup_security.py{Colors.RESET}")
        return False


def main():
    """Main entry point for C2 server"""
    logger.info("="*60)
    logger.info("C2 Server starting...")
    logger.info("="*60)

    # Check security setup with auto-setup option
    if TLS_ENABLED:
        if not os.path.exists(SERVER_CERT) or not os.path.exists(SERVER_KEY):
            if not run_auto_setup():
                return
            # Verify setup worked
            if not os.path.exists(SERVER_CERT) or not os.path.exists(SERVER_KEY):
                print(f"{Colors.RED}[!] Setup verification failed{Colors.RESET}")
                return

    # Initialize token database
    try:
        token_manager.init_database()
        logger.info("Token database initialized")

        # Sync pending count with database
        pending = token_manager.get_pending_requests()
        notifications.set_pending_count(len(pending))
        logger.info(f"Loaded {len(pending)} pending token requests")

    except Exception as e:
        logger.error(f"Failed to initialize token database: {e}")
        print(f"{Colors.RED}[!] Error initializing token database: {e}{Colors.RESET}")
        return

    # Show startup banner
    show_startup_banner()

    # Display security status
    if TLS_ENABLED:
        print(f"{Colors.GREEN}Security: TLS encryption + per-client token authentication{Colors.RESET}")
        print(f"{Colors.GREEN}Token System: Per-client approval workflow enabled{Colors.RESET}\n")
    else:
        print(f"{Colors.RED}Warning: Running without encryption{Colors.RESET}\n")

    # Start listener in background thread
    listener_thread = threading.Thread(target=start_listener, daemon=True)
    listener_thread.start()

    # Give listener time to start
    time.sleep(0.5)

    # Run operator CLI in main thread
    try:
        operator_cli()
    except KeyboardInterrupt:
        logger.info("Server shutdown by operator")
        print("\n[*] Goodbye!")


if __name__ == '__main__':
    main()
