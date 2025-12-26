# File: D:\ThermostatPublicServer\scripts\ssh-local.ps1
# Purpose: SSH to a local server through the public server using the shared "local-login" key.

param(
  [int]$Port = 2222,                  # Reverse-tunnel port on the public server (2222=Cape, 2223=nh-house, etc.)
  [string]$LocalUser = 'tstat'        # Local server username
)

# --- Paths (edit if different) ---
$PublicHost   = 'YOUR_PUBLIC_IP_HERE'
$PublicUser   = 'ubuntu'
$PublicKeyPem = 'D:\ThermostatPublicServer\keys\LightsailDefaultKey-us-east-1.pem'   # Lightsail key for public server
$LocalKey     = 'D:\ThermostatPublicServer\keys\local-login'                         # OpenSSH private key reused for all locals

# Build ProxyCommand: reach the public server with Lightsail key, then forward stdio to 127.0.0.1:$Port
$Proxy = "ssh -i `"$PublicKeyPem`" -W %h:%p $PublicUser@$PublicHost"

# Main SSH: authenticate to the local server user with the shared local-login key
ssh -o "ProxyCommand=$Proxy" -i "$LocalKey" -p $Port $LocalUser@127.0.0.1
