# 🚀 Quick Start Guide - C2 System

Get up and running in **3 simple steps**!

> **Note:** Examples use placeholder values like `CLIENT-PC`, `192.168.1.100:4444`, and `203.0.113.50:4444`. Replace these with your actual server address and hostnames.

---

## Step 1: Start the Server

On the **server machine** (the machine you want to control FROM):

```bash
python c2_server.py
```

**What happens:**
- If this is your first time, certificates are generated **automatically** (no prompts!)
- Server starts and shows you connection addresses
- You'll see:
  - Local Address: `192.168.1.100:4444` (for same network)
  - Public Address: `203.0.113.50:4444` (for remote connections)
- Total time: ~2 seconds

**📝 Write down the server address you need (local or public) - you'll need it in Step 2!**

---

## Step 2: Connect a Client

On the **client machine** (the machine you want to control):

```bash
python c2_client.py
```

**Enter the server address:**

1. Enter the **Server Address** from Step 1
   - Same network: `192.168.1.100:4444`
   - Or just: `192.168.1.100` (defaults to port 4444)
2. Client will request a token automatically
3. Wait for server operator to approve...

**Client will display:**
```
Server address (IP:port or just IP): 192.168.1.100:4444

[*] Token request sent for hostname: CLIENT-PC
[*] Waiting for server operator to approve...
```

---

## Step 3: Approve the Client (on Server)

Back on the **server**, you'll see a notification:

```
============================================================
  🔔 NEW TOKEN REQUEST!
============================================================
   Hostname: CLIENT-PC
   IP Address: 192.168.1.50

   Quick Action:
   → Type: approve CLIENT-PC
============================================================
```

**Approve the client:**
```
c2> approve CLIENT-PC
```

**Back on the client, you'll see:**
```
[+] Token approved!
[+] Token saved to client_token.txt
[+] You can now connect to the server
[*] Connecting to 192.168.1.100:4444...
[+] Authentication successful
[+] Connected to 192.168.1.100:4444
[+] Registered as: CLIENT-PC
[*] Awaiting commands...
```

**That's it! The client is now connected!** ✅

---

## Using Your C2 System

### View Connected Clients

```
c2> list
```

You'll see:
```
● ACTIVE CLIENTS (Connected & Authenticated)
  [1]  CLIENT-PC           ✓ Online         a3f2b1c4     192.168.1.50:54321
```

### Connect to a Client

You can use either the client number or hostname:

```
c2> use 1
# or
c2> use CLIENT-PC
```

### Execute Commands

Once connected to a client, type any command:

```
[CLIENT-PC]> whoami
[CLIENT-PC]> ipconfig
[CLIENT-PC]> dir
```

**Smart Disambiguation:** If you type `list`, `help`, or similar commands in a session, the system will ask if you want to run it on the client or server.

### Exit Client Session

```
[CLIENT-PC]> exit
```

### Get Help

```
c2> help
```

---

## Common Commands

| Command | Description |
|---------|-------------|
| `list` | Show all clients and pending requests |
| `pending` | Show pending token requests |
| `approve <#\|hostname>` | Approve a token request (e.g., `approve 1` or `approve DESKTOP-ABC`) |
| `use <#\|hostname>` | Connect to a client (e.g., `use 1` or `use DESKTOP-ABC`) |
| `help` | Show all available commands |
| `exit` | Close session or shutdown server |

---

## Troubleshooting

### "TLS certificates not found"
- This shouldn't happen! Certificates are generated automatically on first startup.
- If it does, run: `python server/setup_security.py`

### Client can't connect
- Make sure server is running
- Check you entered the correct server address (IP:port format)
- **Same network:** Use the local address (e.g., `192.168.1.100:4444`)
- **Different network:** Use the public address AND configure port forwarding on your router
- Check firewall isn't blocking port 4444

### Token request not showing on server
- Check if client is still waiting (it polls every 5 seconds)
- Type `pending` on server to see all requests

### Using public IP from same WiFi doesn't work
- This is normal! Most routers don't support NAT hairpinning
- Use the local address when on the same network

---

## What's Next?

- **Token Management**: Learn about `revoke`, `renew`, and `delete` commands in README
- **Multiple Clients**: Connect multiple clients and switch between them with `use <#>`
- **Smart Disambiguation**: Learn how the system prevents accidental commands in sessions
- **Remote Access**: Set up port forwarding to connect clients from anywhere
- **Advanced Features**: Read the full documentation in README.md

For detailed documentation, see **[README.md](README.md)**

---

## Key Features Summary

✅ **Automatic Setup** - No manual certificate generation needed
✅ **Direct Connection** - Just enter `IP:port` and connect
✅ **Smart Commands** - Use numbers (`use 1`) or hostnames (`use DESKTOP-ABC`)
✅ **Safe Sessions** - System asks when commands are ambiguous
✅ **Remote Ready** - Shows both local and public IPs automatically

---

**You're all set!** 🎉

Have questions? Check the full documentation or type `help` on the server.
