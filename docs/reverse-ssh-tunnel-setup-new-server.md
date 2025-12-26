# Reverse SSH Tunnel Setup - New Local Server

This guide shows how to add a new Local Server to an existing Public Server (YOUR_PUBLIC_SERVER_IP) reverse SSH tunnel infrastructure.

## Prerequisites

- Public Server (YOUR_PUBLIC_SERVER_IP) already configured with:
  - `tunneluser` account created
  - SSH restrictions configured for `tunneluser`
  - `local-login` key pair already exists
- New Local Server behind firewall (can initiate outbound SSH)
- SSH access to both servers

## Port Assignments

Assign a unique port for each Local Server:
- Cape: 2222
- NH-house: 2223
- Fram: 2224
- **New server: 2225** (or next available)

---

## Part 1: Local Server Configuration

### Step 1: Generate Tunnel Key on Local Server

**Server:** Local Server (new)

Create the SSH directory and generate the tunnel key:

```bash
sudo install -d -m 700 -o tstat -g tstat /home/tstat/.ssh
```

```bash
sudo -u tstat ssh-keygen -t ed25519 -C "reverse-tunnel-to-YOUR_PUBLIC_SERVER_IP" -f /home/tstat/.ssh/tunnel_id_ed25519 -N ""
```

**Expected output:**
```
Generating public/private ed25519 key pair.
Your identification has been saved in /home/tstat/.ssh/tunnel_id_ed25519
Your public key has been saved in /home/tstat/.ssh/tunnel_id_ed25519.pub
```

**Verify:**
```bash
ls -la ~/.ssh/tunnel_id_ed25519*
```

---

### Step 2: Prepare Restricted Key Line

**Server:** Local Server (new)

Create the security-restricted version of the public key:

```bash
sudo -u tstat bash -c 'printf "no-agent-forwarding,no-X11-forwarding,no-pty,command=\"/bin/false\",permitopen=\"localhost:22\" %s\n" "$(cat /home/tstat/.ssh/tunnel_id_ed25519.pub)" | tee /tmp/tunnel_publine_restricted'
```

**View and copy the entire output:**

```bash
cat /tmp/tunnel_publine_restricted
```

**Copy the complete line** (it's very long, starts with `no-agent-forwarding...`)

---

## Part 2: Public Server Configuration

### Step 3: Add Tunnel Key to Public Server

**Server:** Public Server (YOUR_PUBLIC_SERVER_IP)

Open the authorized_keys file:

```bash
sudo nano /home/tunneluser/.ssh/authorized_keys
```

**Add to the file:**
1. Go to the end of the file
2. Add a comment line: `# NewServerName` (e.g., `# Dallas`)
3. On the next line, paste the complete restricted key line you copied
4. Save and exit (Ctrl+X, Y, Enter)

**Set correct permissions:**

```bash
sudo chown tunneluser:tunneluser /home/tunneluser/.ssh/authorized_keys
sudo chmod 600 /home/tunneluser/.ssh/authorized_keys
```

**Verify:**

```bash
sudo tail -5 /home/tunneluser/.ssh/authorized_keys
```

You should see your comment and the key line.

---

## Part 3: Create Persistent Tunnel Service

### Step 4: Create Systemd Service File

**Server:** Local Server (new)

Create the service file:

```bash
sudo nano /etc/systemd/system/reverse-ssh.service
```

**Paste this content** (adjust port number 2225 to your assigned port):

```ini
[Unit]
Description=Persistent reverse SSH tunnel to YOUR_PUBLIC_SERVER_IP
After=network-online.target
Wants=network-online.target

[Service]
User=tstat
Group=tstat
WorkingDirectory=/home/tstat
Environment=AUTOSSH_GATETIME=0
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -i /home/tstat/.ssh/tunnel_id_ed25519 -R 127.0.0.1:2225:localhost:22 tunneluser@YOUR_PUBLIC_SERVER_IP
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Important:** Change `2225` to your assigned port number.

Save and exit (Ctrl+X, Y, Enter).

---

### Step 5: Install autossh (if not already installed)

**Server:** Local Server (new)

```bash
sudo apt update && sudo apt install -y autossh
```

---

### Step 6: Accept Public Server Host Key

**Server:** Local Server (new)

Accept the Public Server's SSH fingerprint:

```bash
sudo -u tstat ssh -i /home/tstat/.ssh/tunnel_id_ed25519 -o StrictHostKeyChecking=accept-new tunneluser@YOUR_PUBLIC_SERVER_IP exit
```

**Expected output:**
```
Warning: Permanently added 'YOUR_PUBLIC_SERVER_IP' (ED25519) to the list of known hosts.
This account is currently not available.
```

This is correct - the `tunneluser` account has no shell by design.

---

### Step 7: Enable and Start Tunnel Service

**Server:** Local Server (new)

Reload systemd, enable, and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable reverse-ssh.service
sudo systemctl start reverse-ssh.service
```

**Check status:**

```bash
sudo systemctl status reverse-ssh.service
```

**Expected output:**
```
Active: active (running)
```

You should see two processes (autossh parent + ssh child) with no error messages.

---

### Step 8: Verify Tunnel on Public Server

**Server:** Public Server (YOUR_PUBLIC_SERVER_IP)

Check that the port is listening:

```bash
ss -tlnp | grep 2225
```

**Expected output:**
```
LISTEN 0 128 127.0.0.1:2225 0.0.0.0:*
```

This confirms the tunnel is established and listening only on localhost (secure).

---

## Part 4: Enable Login Through Tunnel

### Step 9: Get Login Public Key

**Server:** Public Server (YOUR_PUBLIC_SERVER_IP)

Display the login public key:

```bash
cat ~/.ssh/local-login.pub
```

**Copy the entire line** (starts with `ssh-ed25519` or `ssh-rsa`).

---

### Step 10: Add Login Key to Local Server

**Server:** Local Server (new)

Open authorized_keys:

```bash
nano ~/.ssh/authorized_keys
```

**Add to the file:**
1. Go to the end of the file
2. Add a new line
3. Paste the public key you copied
4. Save and exit (Ctrl+X, Y, Enter)

**Set correct permissions:**

```bash
chmod 600 ~/.ssh/authorized_keys
```

---

### Step 11: Test SSH Login Through Tunnel

**Server:** Public Server (YOUR_PUBLIC_SERVER_IP)

Test the connection:

```bash
ssh -p 2225 -i ~/.ssh/local-login tstat@localhost
```

**Expected result:**
- Should connect without asking for a password
- You'll be on the Local Server
- Type `hostname` to verify
- Type `exit` to disconnect

---

### Step 12: Create Quick Connect Script

**Server:** Public Server (YOUR_PUBLIC_SERVER_IP)

Create a convenient connection script (adjust name and port):

```bash
echo '#!/bin/bash
ssh -p 2225 -i ~/.ssh/local-login tstat@localhost' | sudo tee /usr/local/bin/ssh-newserver.sh >/dev/null
```

**Make it executable:**

```bash
sudo chmod +x /usr/local/bin/ssh-newserver.sh
```

**Test it:**

```bash
ssh-newserver.sh
```

Should connect directly to the new Local Server.

---

## Part 5: Security Hardening

### Step 13: Run Security Script

**Server:** Local Server (new)

Run the security hardening script:

```bash
bash ~/local-server/deployment/secure-local-ssh.sh
```

This script will:
- Disable password authentication from external IPs
- Allow password authentication from LAN (10.0.60.0/24)
- Configure UFW firewall rules
- Verify configuration

**Expected output:**
- SSH configuration changes applied
- Firewall rules created
- Verification showing correct settings

---

### Step 14: Fix Firewall Rule Order (if needed)

**Server:** Local Server (new)

Check the firewall rule order:

```bash
sudo ufw status numbered
```

**Correct order should be:**
1. ALLOW from 10.0.60.0/24 to port 22
2. ALLOW OUT to YOUR_PUBLIC_SERVER_IP port 22
3. DENY to port 22 (general)

**If the DENY rule is before the ALLOW rule, fix it:**

```bash
sudo ufw delete deny 22/tcp
sudo ufw deny 22/tcp
sudo ufw reload
```

**Verify the new order:**

```bash
sudo ufw status numbered
```

---

### Step 15: Test LAN Access

**Server:** Your Windows PC or another device on the LAN

Test SSH from the local network:

```bash
ssh tstat@10.0.60.XX
```

(Replace XX with the actual Local Server IP)

**Should connect successfully.**

---

## Part 6: Final Verification

### Step 16: Verify All Security Settings

**Server:** Local Server (new)

**Test password auth is denied from external IPs:**

```bash
sudo sshd -T -C user=tstat,host=$(hostname -f),addr=8.8.8.8 | grep -i passwordauthentication
```

**Expected:** `passwordauthentication no`

**Test password auth is allowed from LAN:**

```bash
sudo sshd -T -C user=tstat,host=$(hostname -f),addr=10.0.60.26 | grep -i passwordauthentication
```

**Expected:** `passwordauthentication yes`

**Check firewall status:**

```bash
sudo ufw status verbose
```

**Expected:**
- Default: deny incoming, allow outgoing
- ALLOW from 10.0.60.0/24 to port 22
- ALLOW OUT to YOUR_PUBLIC_SERVER_IP port 22
- DENY port 22 from anywhere

---

## Setup Complete! ✅

### Summary of Access Methods

**From Public Server:**
```bash
ssh-newserver.sh
```

**From LAN (Windows/WSL or other devices):**
```bash
ssh tstat@10.0.60.XX
```

### Port Assignments Updated

| Location | Server | Port | Quick Command |
|----------|--------|------|---------------|
| Cape | tstat-cape | 2222 | `ssh-cape.sh` |
| NH-house | nh-house | 2223 | `ssh-nh-house.sh` |
| Fram | tstat-fram | 2224 | `ssh-fram.sh` |
| **New** | **new-server** | **2225** | **`ssh-newserver.sh`** |

### What's Protected

✅ **Persistent tunnel** - Automatically reconnects, survives reboots  
✅ **Secure access** - Key-based authentication only from internet  
✅ **LAN convenience** - Password auth allowed from local network  
✅ **Firewall protected** - Only authorized connections allowed  
✅ **Minimal exposure** - Tunnel port only on localhost (127.0.0.1)

---

## Troubleshooting

### Tunnel Service Won't Start

Check logs:
```bash
sudo journalctl -u reverse-ssh.service -n 50
```

Common issues:
- autossh not installed: `sudo apt install -y autossh`
- Host key not accepted: Run Step 6 again
- Wrong permissions on key: `chmod 600 ~/.ssh/tunnel_id_ed25519`

### Can't Connect Through Tunnel

Verify tunnel is listening on Public Server:
```bash
ss -tlnp | grep 2225
```

If not listening, check Local Server service status:
```bash
sudo systemctl status reverse-ssh.service
```

### Can't Connect from LAN

Check firewall rules order:
```bash
sudo ufw status numbered
```

ALLOW rule must come before DENY rule.

### Password Prompt on Tunnel Connection

Check authorized_keys on Local Server:
```bash
cat ~/.ssh/authorized_keys
```

Verify `local-login.pub` key is present and on one line.

---

## Notes

- Each Local Server needs a unique port number (2222, 2223, 2224, 2225, etc.)
- The same `local-login` key pair is reused for all Local Servers
- Each Local Server has its own unique `tunnel_id_ed25519` key
- All tunnel keys go into `/home/tunneluser/.ssh/authorized_keys` on Public Server
- All Local Servers use the `tstat` user account
- Security hardening must be done on each Local Server individually
