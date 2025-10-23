"""
Common Configuration Module
Shared constants and configuration for C2 system
"""

# Network configuration
HOST = '0.0.0.0'  # Server binds to all interfaces
PORT = 4444       # Default C2 port

# Protocol limits
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB max message size
COMMAND_TIMEOUT = 30                  # Command execution timeout (seconds)
SOCKET_TIMEOUT = 35                   # Socket response timeout (slightly more than command timeout)

# Logging
LOG_FILE = 'c2_server.log'
LOG_LEVEL_CONSOLE = 'INFO'
LOG_LEVEL_FILE = 'DEBUG'

# TLS/SSL Configuration
TLS_ENABLED = True
SERVER_CERT = 'certs/server.crt'
SERVER_KEY = 'certs/server.key'

# Token System
TOKEN_FILE_CLIENT = 'client_token.txt'  # Client-side token storage
TOKEN_POLL_INTERVAL = 5                  # Seconds between approval status checks

# Message Types
MSG_REGISTER = 'REGISTER'         # Client registration with token
MSG_CMD = 'CMD'                   # Server sends command to client
MSG_RESULT = 'RESULT'             # Client sends command result
MSG_TOKEN_REQUEST = 'TOKEN_REQUEST'  # Client requests new token
MSG_TOKEN_STATUS = 'TOKEN_STATUS'    # Server sends token status

# Token States
TOKEN_PENDING = 'pending'
TOKEN_APPROVED = 'approved'
TOKEN_REVOKED = 'revoked'
TOKEN_DENIED = 'denied'
TOKEN_INVALID = 'invalid'
