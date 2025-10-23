# C2 - Command and Control System

A modular Command and Control (C2) system implemented in Python with per-client token authentication for educational purposes.

**Security Features:** TLS encryption + Per-client token approval workflow

> **Note:** All examples in this documentation use placeholder values (e.g., `CLIENT-PC`, `LAPTOP-2`, `192.168.1.100`, `203.0.113.50`). Replace these with your actual values when using the system.

---

## Features

### Core Capabilities
- ✅ TCP-based client-server communication with TLS encryption
- ✅ Per-client token authentication with approval workflow
- ✅ Multi-client support with concurrent sessions
- ✅ Interactive session management with smart disambiguation
- ✅ Remote command execution with output capture
- ✅ Comprehensive logging system
- ✅ Token lifecycle management (pending, approved, revoked, denied)
- ✅ Direct connection (IP:port format) - no menu navigation
- ✅ Local and public IP detection for easy remote access

### Security Features
- ✅ TLS/SSL encryption for all communications
- ✅ Per-client token authentication (no shared tokens)
- ✅ Token request/approval workflow
- ✅ Token revocation and renewal capabilities
- ✅ Automatic certificate generation on first startup
- ✅ Secure token validation (constant-time comparison)
- ✅ Session tracking with unique IDs

### Token System
- ✅ Client token request mechanism (automatic)
- ✅ Server operator approval/denial (supports numbers or hostnames)
- ✅ Client-side token persistence
- ✅ Revoke and renew token capabilities
- ✅ Permanent token deletion
- ✅ Real-time visual notifications for token requests
- ✅ SQLite database for token storage

---

## Project Structure

```
C2/
├── common/                     # Shared modules
│   ├── __init__.py
│   ├── protocol.py            # Length-prefixed message protocol
│   ├── config.py              # Shared constants
│   └── auth.py                # Token generation and hashing
│
├── server/                     # Server modules
│   ├── __init__.py
│   ├── main.py                # Entry point
│   ├── listener.py            # TCP socket listener with TLS
│   ├── client_handler.py      # Client management & authentication
│   ├── cli.py                 # Operator interface
│   ├── logger_config.py       # Logging configuration
│   ├── token_manager.py       # Token database management
│   ├── setup_security.py      # Automatic TLS certificate generation
│   └── tokens.db              # SQLite token database (generated)
│
├── client/                     # Client modules
│   ├── __init__.py
│   ├── main.py                # Entry point with connection menu
│   ├── client.py              # Connection logic with TLS & token auth
│   └── executor.py            # Command execution
│
├── certs/                      # TLS certificates (generated)
│   ├── server.crt             # Server certificate
│   └── server.key             # Server private key
│
├── c2_server.py               # Quick launcher for server
├── c2_client.py               # Quick launcher for client
├── requirements.txt           # Python dependencies
├── .gitignore                 # Git ignore rules
├── c2_server.log              # Server logs (generated)
└── README.md                  # This file
```

---

## Setup Instructions

### ⚡ Quick Start

**Want to get started in 3 steps?** See **[QUICKSTART.md](QUICKSTART.md)** for a simple guide!

### Requirements

- Python 3.7 or higher
- `cryptography` package for TLS certificates

### Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install cryptography
   ```
3. **First-time setup is FULLY automatic!** Just run the server:
   ```bash
   python c2_server.py
   ```
   - Certificates are generated automatically (no prompts!)
   - Server starts immediately after setup
   - Takes about 2 seconds total

---

## Running the Server and Client

### 1. Start the Server

```bash
python c2_server.py
```

**Expected output:**
```
======================================================================
  C2 SERVER - READY FOR CONNECTIONS
======================================================================

📡 Server Information:
   • Listening on: 0.0.0.0:4444 (all interfaces)
   • Local Address: 192.168.1.100:4444 (same network)
   • Public Address: 203.0.113.50:4444 (remote access)
   • Security: TLS Encryption + Per-Client Tokens

📱 HOW TO CONNECT A CLIENT:
   Step 1: On the client machine, run:
           python c2_client.py
   Step 2: Enter server address:
           • Same WiFi/network: 192.168.1.100:4444
           • Different network: 203.0.113.50:4444
   Step 3: Client will request a token automatically
   Step 4: You'll see a notification here - approve it!

💡 HELPFUL TIPS:
   • Type help to see all available commands
   • Type list to see connected clients and pending requests
   • Approve token requests with: approve <hostname>
   • Use use <#> to interact with a client (e.g., use 1)

📝 Logs: c2_server.log
======================================================================

Security: TLS encryption + per-client token authentication
Token System: Per-client approval workflow enabled

======================================================================
  🎯 C2 OPERATOR CONSOLE - READY
======================================================================

Welcome! The C2 server is now running.
Waiting for clients to connect...

Quick Start:
  • Type help to see all commands
  • Type list to check system status
  • When a client connects, you'll see a notification!

======================================================================

c2>
```

### 2. Start the Client

```bash
python c2_client.py
```

**First-time connection flow:**
```
==================================================
  C2 CLIENT
==================================================

Server address (IP:port or just IP): 192.168.1.100:4444

[!] No token found in client_token.txt

[?] Request token from server? (y/n): y
[*] Connecting to 192.168.1.100:4444...
[*] Token request sent for hostname: CLIENT-PC
[*] Token request pending approval...
[*] Waiting for server operator to approve...
[+] Token approved!
[+] Token saved to client_token.txt
[+] You can now connect to the server
[*] Connecting to 192.168.1.100:4444...
[+] Authentication successful
[+] Connected to 192.168.1.100:4444
[+] Registered as: CLIENT-PC
```

**Note:** You can enter just the IP (`192.168.1.100`) and it will default to port 4444.

**Subsequent connections:**
```
==================================================
  C2 CLIENT
==================================================

Server address (IP:port or just IP): 192.168.1.100:4444

[+] Token found in client_token.txt
[*] Connecting to 192.168.1.100:4444...
[+] Authentication successful
[+] Connected to 192.168.1.100:4444
[+] Registered as: CLIENT-PC
```

---

## Token Management

### Server-Side Commands

#### View Pending Requests
```
c2> pending

============================================================
  Pending Token Requests
============================================================
  [1] CLIENT-PC (192.168.1.50) - 2025-10-21 14:32:01
  [2] LAPTOP-2 (192.168.1.75) - 2025-10-21 14:35:15
============================================================

Use 'approve <#|hostname>' to approve a request
```

#### Approve Token Request
```
c2> approve 1
[+] Token approved for CLIENT-PC
    Token: 5ae727dbe505...
```

#### Deny Token Request
```
c2> deny 2
[+] Token denied for LAPTOP-2
```

#### View All Clients and Tokens
```
c2> list

==========================================================================================
  C2 SERVER - CLIENT OVERVIEW
==========================================================================================

● ACTIVE CLIENTS (Connected & Authenticated)
──────────────────────────────────────────────────────────────────────────────────────────
  #    HOSTNAME                  STATUS          SESSION      IP ADDRESS
  --------------------------------------------------------------------------------------
  [1]  CLIENT-PC           ✓ Online         a3f2b1c4     192.168.1.50:54321

● APPROVED CLIENTS (Offline)
──────────────────────────────────────────────────────────────────────────────────────────
  LAPTOP-2              ✓ Offline                     192.168.1.75     2025-10-21 14:35:00

● PENDING REQUESTS (Awaiting Approval)
──────────────────────────────────────────────────────────────────────────────────────────
  No pending requests

● REVOKED / DENIED CLIENTS
──────────────────────────────────────────────────────────────────────────────────────────
  No revoked or denied clients

==========================================================================================
```

#### Revoke Access (Temporary)
```
c2> revoke 1
[+] Token revoked for CLIENT-PC
[*] Kicked CLIENT-PC from server
```

**Client sees:**
```
============================================================
[!] ACCESS SUSPENDED
============================================================
[*] Your token has been REVOKED by the server operator
[*] Your access is temporarily suspended
[*] Token file kept: client_token.txt
[*] Contact the server administrator to renew your access
[*] Your token can be renewed without requesting a new one
============================================================
```

#### Renew Revoked Token
```
c2> renew CLIENT-PC
[+] Token renewed for CLIENT-PC
[*] Client can reconnect with their existing token
```

#### Delete Token Permanently
```
c2> delete CLIENT-PC
⚠️  WARNING: Permanently delete token for CLIENT-PC
    This will:
    - Kick the client from server
    - Delete their token from database
    - Delete their client_token.txt file
    - Require new token request to reconnect

Type 'yes' to confirm: yes
[*] Kicked CLIENT-PC from server
[+] Token permanently deleted for CLIENT-PC
```

**Client sees:**
```
============================================================
[!] YOUR TOKEN HAS BEEN DELETED
============================================================
[*] Deleting local token file...
[+] Local token file 'client_token.txt' deleted
[*] You must request a new token to reconnect
============================================================
```

#### Manually Create Token
```
c2> addtoken NEW-MACHINE
[+] Token created and approved for NEW-MACHINE
    Token: a1b2c3d4e5f6...
[*] Client can now connect with this token
```

---

## Operating the Server

### Available Commands

```
c2> help

============================================================
  C2 SERVER - Available Commands
============================================================

Token Management:
  pending                 - List pending token requests
  approve <#|hostname>    - Approve a token request
  deny <#|hostname>       - Deny a token request
  addtoken <hostname>     - Manually create a new token
  revoke <#|hostname>     - Revoke client access and kick
  renew <hostname>        - Renew a revoked token
  delete <#|hostname>     - Permanently delete token and kick
  tokens                  - List all tokens and their status

Client Management:
  list / sessions         - Show all clients and tokens
  use <#|hostname>        - Select client session
  help                    - Show this help message
  exit                    - Shutdown server

Session Commands (when in client session):
  <command>               - Execute command on active client
  back / exit / q         - Exit current session

Smart Disambiguation:
  When you type 'list', 'help', or similar commands in a session,
  you'll be asked whether you want to run it on the client or server.
============================================================
```

### Client Session Usage

#### Select Client

You can use either the client number or hostname:
```
c2> use 1
# or
c2> use CLIENT-PC
[+] Session opened with CLIENT-PC
[CLIENT-PC]>
```

#### Execute Commands
```
[CLIENT-PC]> whoami
==================================================
Output from CLIENT-PC
==================================================
STDOUT:
user
==================================================

[CLIENT-PC]> ipconfig
==================================================
Output from CLIENT-PC
==================================================
STDOUT:
Windows IP Configuration
...
==================================================
```

#### Exit Session
```
[CLIENT-PC]> exit
[*] Session closed
c2>
```

#### Smart Disambiguation

When you type ambiguous commands (like `list`, `help`, etc.) in a session, the system will ask if you want to run it on the client or server:

```
[CLIENT-PC]> list

⚠️  Ambiguous command 'list'
[1] Run 'list' on client CLIENT-PC (list directory contents)
[2] Execute server command (show server client list)
[3] Cancel

Choice (1/2/3): 1
```

This prevents accidentally running the wrong command.

---

## Protocol Description

### Message Format

All messages use **length-prefixed encoding**:

1. **4-byte length header** (big-endian unsigned integer)
2. **Message payload** (UTF-8 encoded string)

### Message Types

- `TOKEN_REQUEST:<hostname>:<ip>` - Client requests new token
- `TOKEN_STATUS:<status>:<token>` - Server sends token status
- `REGISTER:<hostname>:<token>` - Client registration with token
- `CMD:<command>` - Server sends command to client
- `RESULT:<stdout>|||<stderr>` - Client sends command results

### Token States

- `pending` - Token request awaiting approval
- `approved` - Token approved, client can connect
- `revoked` - Token temporarily suspended (can be renewed)
- `denied` - Token request denied
- `invalid` - Token doesn't exist or is corrupted

### Communication Flow

```
1. Client connects to server (TCP + TLS)
2. Client checks for token file
3. If no token:
   a. Client → Server: TOKEN_REQUEST:hostname:ip
   b. Server creates pending token
   c. Server notifies operator
   d. Operator approves/denies
   e. Server → Client: TOKEN_STATUS:approved:token
   f. Client saves token to file
4. If token exists:
   a. Client → Server: REGISTER:hostname:token
   b. Server validates token
   c. Server → Client: TOKEN_STATUS:APPROVED (if valid)
   d. Client receives confirmation, connection established
   e. If revoked: Server → Client: TOKEN_STATUS:REVOKED
   f. If invalid: Server → Client: TOKEN_STATUS:INVALID, client deletes token
5. Operator selects client: use 1
6. Operator enters command: whoami
7. Server → Client: CMD:whoami
8. Client executes and responds: RESULT:user\n|||
9. Repeat steps 6-8
```

---

## Logging

### Dual Logging System

- **Console Output:** INFO level messages
- **File Output:** `c2_server.log` with DEBUG level
- **Format:** `[YYYY-MM-DD HH:MM:SS] [LEVEL] [SESSION:id] message`

### Logged Events

1. Client connections and registrations
2. Token requests and approvals
3. Commands sent to clients
4. Responses received from clients
5. Token revocations and deletions
6. Client disconnections

---

## Security Features

### TLS/SSL Encryption

- TLS 1.2+ using Python's `ssl` module
- Self-signed certificates for development
- All client-server communications encrypted

### Per-Client Token Authentication

- 64-character random hex token (256 bits)
- Unique token per client hostname
- SQLite database storage
- Constant-time comparison (timing attack resistant)
- Token hashed in logs (never logged in plaintext)

### Token Lifecycle

1. **Request** - Client requests token
2. **Pending** - Awaits operator approval
3. **Approved** - Client can connect
4. **Revoked** - Temporarily suspended (renewable)
5. **Deleted** - Permanently removed

---

## Troubleshooting

### "TLS certificates not found"

**Solution:**
The server automatically generates certificates on first startup. If you need to regenerate them manually:
```bash
python server/setup_security.py
```

### "Authentication failed - token has been REVOKED"

**Cause:** Your access has been suspended

**Solution:** Contact server administrator to renew your token

### "Authentication failed - token is invalid"

**Cause:** Token is corrupted or deleted

**Solution:** Request a new token from server

### Client can't connect

- Verify server is running
- Check IP address and port
- Ensure port 4444 is not blocked by firewall
- Check if token is revoked (server-side)

### "Address already in use" error

- Another process is using port 4444
- Wait 30 seconds or change PORT in `common/config.py`

---

## Security Notice

⚠️ **This is an educational project for understanding C2 architecture.**

**Production considerations:**
- Use CA-signed certificates instead of self-signed
- Implement certificate pinning
- Add rate limiting for authentication attempts
- Use IP whitelisting
- Implement heartbeat/keepalive mechanisms
- Consider mutual TLS (client certificates)
- Add command auditing and approval workflow
- Implement role-based access control

**Do not use in production or on systems you don't own.**

---

## License

Educational use only. Use responsibly and legally.
