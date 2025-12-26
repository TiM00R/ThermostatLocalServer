#!/bin/bash
# Secure SSH + UFW setup for Local Server (e.g., tstat-cape)
# Set PUBLIC_SERVER_IP environment variable before running:
# export PUBLIC_SERVER_IP="xxx.xxx.xxx.xxx"

# --- SSH CONFIG FIXES ---


# Check if PUBLIC_SERVER_IP is set
if [ -z "${PUBLIC_SERVER_IP}" ]; then
    echo "ERROR: PUBLIC_SERVER_IP environment variable is not set"
    echo ""
    echo "Usage:"
    echo "  export PUBLIC_SERVER_IP=\"your.server.ip.address\""
    echo "  $0"
    echo ""
    echo "Example:"
    echo "  export PUBLIC_SERVER_IP=\"1.234.56.78
    echo "  $0"
    exit 1
fi

echo "Using PUBLIC_SERVER_IP: ${PUBLIC_SERVER_IP}"


sudo sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/50-cloud-init.conf 2>/dev/null || true

sudo bash -c 'cat >/etc/ssh/sshd_config.d/99-local-secure.conf' <<'EOF'
# Local security policy
UsePAM yes
PasswordAuthentication no
PubkeyAuthentication yes

# Allow passwords only from LAN
Match Address 10.0.60.0/24
    PasswordAuthentication yes
EOF

sudo sshd -t && sudo systemctl reload ssh

# --- FIREWALL RULES ---
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 10.0.60.0/24 to any port 22 proto tcp
sudo ufw deny 22/tcp
sudo ufw allow out to ${PUBLIC_SERVER_IP} port 22 proto tcp
sudo ufw reload
sudo ufw --force enable

# --- VERIFY ---
echo "=== SSH Check ==="
sudo sshd -T -C user=tstat,host=$(hostname -f),addr=10.0.60.15 | grep -i passwordauthentication
sudo sshd -T -C user=tstat,host=$(hostname -f),addr=8.8.8.8 | grep -i passwordauthentication
echo "=== UFW Status ==="
sudo ufw status verbose
