"""
Common Protocol Module
Handles length-prefixed message encoding/decoding for C2 communication
"""

import socket
import struct
from common.config import MAX_MESSAGE_SIZE


def send_message(sock, message):
    """
    Send a length-prefixed message over socket

    Args:
        sock: Socket object
        message: String or bytes to send

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if isinstance(message, str):
            message = message.encode('utf-8')

        # Send 4-byte length header (big-endian) + message
        length = struct.pack('>I', len(message))
        sock.sendall(length + message)
        return True
    except Exception as e:
        print(f"[!] Error sending message: {e}")
        return False


def recv_message(sock):
    """
    Receive a length-prefixed message from socket

    Args:
        sock: Socket object

    Returns:
        str: Decoded message, or None on error/disconnect

    Raises:
        socket.timeout: If socket timeout occurs (caller should handle)
    """
    try:
        # Read 4-byte length header
        length_data = recv_exact(sock, 4)
        if not length_data:
            return None

        message_length = struct.unpack('>I', length_data)[0]

        # Sanity check against configured max
        if message_length > MAX_MESSAGE_SIZE:
            raise Exception(f"Message size {message_length} exceeds limit {MAX_MESSAGE_SIZE}")

        # Read exact message length
        message_data = recv_exact(sock, message_length)
        if not message_data:
            return None

        return message_data.decode('utf-8', errors='replace')
    except socket.timeout:
        # Let timeout propagate to caller - they should decide how to handle it
        raise
    except Exception as e:
        print(f"[!] Error receiving message: {e}")
        return None


def recv_exact(sock, n):
    """
    Helper function to receive exactly n bytes from socket

    Args:
        sock: Socket object
        n: Number of bytes to receive

    Returns:
        bytes: Received data, or None if connection closed
    """
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data
