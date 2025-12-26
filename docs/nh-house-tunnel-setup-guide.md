# 🔒 Add Local Server "nh-house" (Path A)

This guide connects your **Windows PC + WinSCP** to the **nh-house local server** via the **Public Aggregate Server (YOUR_PUBLIC_SERVER_IP)** using key-based authentication.

---

## 🧱 Step 1 – Generate keypair on the Public server

**Server:** Public (Aggregate)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/local-login-nh-house -N "" -C "aggregate->local nh-house"
```

Verify the files:

```bash
ls -l ~/.ssh/local-login-nh-house*
```

Show and copy the public part:

```bash
cat ~/.ssh/local-login-nh-house.pub
```

## 🔑 Step 2 – Send key to the Local "nh-house" server

**Server:** Public (Aggregate)

```bash
scp -P 2223 ~/.ssh/local-login-nh-house.pub tstat@127.0.0.1:/home/tstat/
```

Append it to authorized_keys and fix permissions:

```bash
ssh -p 2223 tstat@127.0.0.1 'mkdir -p ~/.ssh'
```

```bash
ssh -p 2223 tstat@127.0.0.1 'touch ~/.ssh/authorized_keys'
```

```bash
ssh -p 2223 tstat@127.0.0.1 'cat ~/local-login-nh-house.pub >> ~/.ssh/authorized_keys'
```

```bash
ssh -p 2223 tstat@127.0.0.1 'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && rm ~/local-login-nh-house.pub'
```

## 🧪 Step 3 – Test from the Public server

**Server:** Public (Aggregate)

```bash
ssh -p 2223 -i ~/.ssh/local-login-nh-house tstat@127.0.0.1
```

✅ If you see `tstat@nh-house:~$` — success.

## 📦 Step 4 – Prepare key for Windows

**Server:** Public (Aggregate)

```bash
cp ~/.ssh/local-login-nh-house /tmp/local-login-nh-house
chmod 600 /tmp/local-login-nh-house
```

## 💾 Step 5 – Download to Windows

**Server:** Windows PC (WinSCP GUI)

1. Connect to the Public server (`ubuntu@YOUR_PUBLIC_SERVER_IP`) using `LightsailDefaultKey-us-east-1.ppk`
2. Download the file `/tmp/local-login-nh-house` to:
   ```
   D:\ThermostatPublicServer\keys\local-login-nh-house
   ```

## 🔁 Step 6 – Convert the key to .ppk format

**Server:** Windows PC (PowerShell)

```powershell
$WinSCP = "${env:ProgramFiles}\WinSCP\WinSCP.com"
if (-not (Test-Path $WinSCP)) { $WinSCP = "${env:ProgramFiles(x86)}\WinSCP\WinSCP.com" }
& $WinSCP "/keygen" "D:\ThermostatPublicServer\keys\local-login-nh-house" "/output=D:\ThermostatPublicServer\keys\local-login-nh-house.ppk"
```

## ⚙️ Step 7 – Configure WinSCP GUI for nh-house

**Server:** Windows PC

Open WinSCP → New Site

**Basic Settings:**
- File protocol: `SFTP`
- Host name: `127.0.0.1`
- Port number: `2223`
- User name: `tstat`
- Private key file: `D:\ThermostatPublicServer\keys\local-login-nh-house.ppk`

**Advanced Settings:**

Go to **Advanced → Connection → Tunnel**

- ✓ Connect through SSH tunnel
- Host name: `YOUR_PUBLIC_SERVER_IP`
- Port number: `22`
- User name: `ubuntu`
- Private key file: `D:\ThermostatPublicServer\keys\LightsailDefaultKey-us-east-1.ppk`

**Save as:** `nh-house via Public`

Click **Login**

✅ You should see `/home/tstat` on nh-house.

## 🧹 Step 8 – Clean up temporary key on the Public server

**Server:** Public (Aggregate)

```bash
rm /tmp/local-login-nh-house
```

---

## ✅ Final Verification

**From Windows:**
1. Open WinSCP
2. Select `nh-house via Public`
3. Click Login

**From Public server:**

```bash
ssh -p 2223 -i ~/.ssh/local-login-nh-house tstat@127.0.0.1
```

You now have full SFTP access from **Windows → Public → nh-house** through the secure reverse SSH tunnel.
