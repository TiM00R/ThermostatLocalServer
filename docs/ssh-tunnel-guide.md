# 🔒 Persistent Reverse SSH Tunnel Setup (Multiple Local Servers)

This guide explains how to set up a **secure, persistent reverse SSH tunnel** between multiple **Local Servers** (behind firewalls) and a single **Public Aggregate Server** (with public IP).

---

## 🧱 Step 1 – Re-create it safely (no password, no login shell)

**Server:** Public (Aggregate)

```bash
sudo adduser --disabled-password --gecos "" --shell /usr/sbin/nologin tunneluser
sudo passwd -l tunneluser
```

## 🗂 Step 2 – Prepare .ssh directory

**Server:** Public (Aggregate)

```bash
sudo mkdir -p /home/tunneluser/.ssh
sudo chmod 700 /home/tunneluser/.ssh
sudo chown tunneluser:tunneluser /home/tunneluser/.ssh
```

## 🔐 Step 3 – Harden SSH configuration

**Server:** Public (Aggregate)

```bash
sudo nano /etc/ssh/sshd_config
```

Append the following block at the end:

```nginx
# ---- tunneluser restrictions ----
Match User tunneluser
    PasswordAuthentication no
    PubkeyAuthentication yes
    AllowTcpForwarding yes
    X11Forwarding no
    PermitTTY no
    ForceCommand /bin/false
    PermitOpen localhost:22
# ---------------------------------
```

Then reload SSH:

```bash
sudo systemctl reload ssh
```

Test SSH service:

```bash
sudo systemctl status ssh
```

## 🔑 Step 4 – Generate tunnel key on Local Server

**Server:** Local (each one, example: Cape)

```bash
sudo install -d -m 700 -o tstat -g tstat /home/tstat/.ssh
sudo -u tstat ssh-keygen -t ed25519 -C "reverse-tunnel-to-YOUR_PUBLIC_SERVER_IP" -f /home/tstat/.ssh/tunnel_id_ed25519 -N ""
```

## 📋 Step 5 – Prepare restricted key line

**Server:** Local (each one)

```bash
sudo -u tstat bash -c 'printf "no-agent-forwarding,no-X11-forwarding,no-pty,command=\"/bin/false\",permitopen=\"localhost:22\" %s\n" "$(cat /home/tstat/.ssh/tunnel_id_ed25519.pub)" | tee /tmp/tunnel_publine_restricted'
```

View and copy the line:

```bash
cat /tmp/tunnel_publine_restricted
```

## 🚀 Step 6 – Add the key on the Public Server

**Server:** Public (Aggregate)

Paste the copied line into this command:

```bash
sudo install -d -m 700 -o tunneluser -g tunneluser /home/tunneluser/.ssh
echo 'PASTE_THE_KEY_LINE_HERE' | sudo tee -a /home/tunneluser/.ssh/authorized_keys >/dev/null
sudo chown tunneluser:tunneluser /home/tunneluser/.ssh/authorized_keys
sudo chmod 600 /home/tunneluser/.ssh/authorized_keys
```

**Note:** Repeat this for each local server (each key on a new line). Add a comment like `# Cape`, `# Denver`, etc. to identify which key belongs to which local.

Example `authorized_keys` file:

```text
no-agent-forwarding,no-X11-forwarding,no-pty,command="/bin/false",permitopen="localhost:22" ssh-ed25519 AAAAC3Nza... reverse-tunnel-to-YOUR_PUBLIC_SERVER_IP  # Cape
no-agent-forwarding,no-X11-forwarding,no-pty,command="/bin/false",permitopen="localhost:22" ssh-ed25519 AAAAC3Nza... reverse-tunnel-to-YOUR_PUBLIC_SERVER_IP  # Denver
```

## ⚙️ Step 7 – Create persistent tunnel service

**Server:** Local (each one)

Create a new file:

```bash
sudo nano /etc/systemd/system/reverse-ssh.service
```

Paste the following content, adjusting port (unique per local server):

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
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -i /home/tstat/.ssh/tunnel_id_ed25519 -R 127.0.0.1:2222:localhost:22 tunneluser@YOUR_PUBLIC_SERVER_IP
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Port assignments for additional local servers:**
- Cape → port 2222
- Denver → port 2223
- Dallas → port 2224, etc.

## 🔧 Step 8 – Enable and test the service

**Server:** Local (each one)

```bash
sudo systemctl daemon-reload
sudo systemctl enable reverse-ssh.service
sudo systemctl start reverse-ssh.service
sudo systemctl status reverse-ssh.service
```

You should see `active (running)`.

## 🧾 Step 9 – Verify on the Public Server

**Server:** Public (Aggregate)

Check the listener:

```bash
ss -tlnp | grep 2222
```

Expected output:

```text
LISTEN 0 128 127.0.0.1:2222 0.0.0.0:*
```

## 🧪 Step 10 – Create login key on Public Server

**Server:** Public (Aggregate)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/local-login -N "" -C "aggregate->local login"
cat ~/.ssh/local-login.pub
```

## 🔐 Step 11 – Add login key to Local Server

**Server:** Local (each one)

Paste the public key from the previous step into:

```bash
echo 'PASTE_PUBLIC_KEY_LINE_HERE' | sudo tee -a /home/tstat/.ssh/authorized_keys >/dev/null
sudo chown tstat:tstat /home/tstat/.ssh/authorized_keys
sudo chmod 600 /home/tstat/.ssh/authorized_keys
```

## 🚪 Step 12 – Test SSH login through tunnel

**Server:** Public (Aggregate)

```bash
ssh -p 2222 -i ~/.ssh/local-login tstat@localhost
```

You should connect directly into the local server.

## 🧱 Step 13 – Create quick connect script

**Server:** Public (Aggregate)

```bash
echo '#!/bin/bash
ssh -p 2222 -i ~/.ssh/local-login tstat@localhost' | sudo tee /usr/local/bin/ssh-cape.sh >/dev/null
sudo chmod +x /usr/local/bin/ssh-cape.sh
```

Run it:

```bash
ssh-cape.sh
```

For more locals, duplicate and adjust:

```bash
sudo cp /usr/local/bin/ssh-cape.sh /usr/local/bin/ssh-denver.sh
sudo sed -i 's/2222/2223/' /usr/local/bin/ssh-denver.sh
```

## 🧩 Step 14 – Verify persistence and safety

**Server:** Local

Check auto-start and status:

```bash
sudo systemctl is-enabled reverse-ssh.service
sudo systemctl status reverse-ssh.service
```

**Server:** Public

Ensure the tunnel is only bound to loopback:

```bash
sudo ss -tlnp | grep 2222
```

If you see `127.0.0.1:2222`, it's secure and not exposed.

---

## ✅ Summary

| Role | Server | Key/Service | Port |
|------|--------|-------------|------|
| Reverse tunnel maintainer | Local (tstat-cape, etc.) | `/etc/systemd/system/reverse-ssh.service` | 2222, 2223, … |
| Tunnel access user | Public (YOUR_PUBLIC_SERVER_IP) | `/home/tunneluser/.ssh/authorized_keys` | N/A |
| Login keypair | Public (YOUR_PUBLIC_SERVER_IP) | `~/.ssh/local-login` | N/A |

**Each local server:**
- Has its own keypair
- Uses a unique port
- Is never exposed to the Internet
