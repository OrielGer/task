#!/usr/bin/env python3
"""
C2 Client - Main Entry Point
Direct connection to C2 server
"""

import sys
from client.client import connect_and_run


def parse_address(address):
    """
    Parse server address in format IP:port or just IP

    Args:
        address: Server address (e.g., "192.168.1.100:4444" or "192.168.1.100")

    Returns:
        tuple: (ip, port)
    """
    if ':' in address:
        parts = address.rsplit(':', 1)
        server_ip = parts[0]
        try:
            port = int(parts[1])
            if 1 <= port <= 65535:
                return server_ip, port
            else:
                print("[!] Port must be between 1-65535")
                return None, None
        except ValueError:
            print("[!] Invalid port number")
            return None, None
    else:
        # No port specified, use default
        return address, 4444


def get_server_address():
    """Get server address from user"""
    print("\n" + "="*50)
    print("  C2 CLIENT")
    print("="*50)

    while True:
        address = input("\nServer address (IP:port or just IP): ").strip()

        if not address:
            print("[!] Address cannot be empty")
            continue

        server_ip, port = parse_address(address)

        if server_ip and port:
            return server_ip, port


def main():
    """Main entry point for C2 client"""
    try:
        server_ip, port = get_server_address()
        connect_and_run(server_ip, port)

    except KeyboardInterrupt:
        print("\n[*] Client shutdown")
        sys.exit(0)


if __name__ == '__main__':
    main()
