"""
Command Executor Module
Executes system commands and handles output encoding
"""

import subprocess
from common.config import COMMAND_TIMEOUT


def execute_command(command):
    """
    Execute system command and return stdout and stderr

    Args:
        command: Command string to execute

    Returns:
        tuple: (stdout, stderr) as strings
    """
    try:
        # Execute command with timeout
        # Use binary mode to avoid encoding issues, decode manually
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=False  # Binary mode to avoid encoding errors
        )

        # Wait for completion with timeout
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout_bytes, stderr_bytes = process.communicate()
            stderr_bytes += b"\n[Command timed out after 30 seconds]"

        # Decode with error handling - try multiple encodings
        stdout = decode_output(stdout_bytes)
        stderr = decode_output(stderr_bytes)

        return stdout, stderr

    except Exception as e:
        return "", f"Error executing command: {str(e)}"


def decode_output(data):
    """
    Decode command output, trying multiple encodings

    Args:
        data: Bytes to decode

    Returns:
        str: Decoded string
    """
    if not data:
        return ""

    # Try encodings in order of preference
    encodings = ['utf-8', 'cp1252', 'latin-1', 'ascii']

    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    # Last resort: decode with replacement characters
    return data.decode('utf-8', errors='replace')
