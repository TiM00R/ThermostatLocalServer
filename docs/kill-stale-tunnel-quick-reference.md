# Quick Reference: Kill Stale Reverse SSH Tunnel

## Step 1: Check Which Tunnels Are Active

```bash
sudo ss -tlnp | grep "127.0.0.1:222"
```

**Shows active tunnel ports (2222, 2223, 2224, etc.)**

---

## Step 2: Find Stale tunneluser Processes

```bash
ps aux | grep "tunneluser"
```

**Look for old dates in the START column**

---

## Step 3: Get Details of Suspicious Process

```bash
sudo lsof -i -a -p <PID>
```

**Replace `<PID>` with the process ID from step 2**

**Look for old ESTABLISHED connections or processes not showing a LISTEN port**

---

## Step 4: Kill the Stale Connection

```bash
sudo kill <PID1> <PID2>
```

**Kill both the parent and child process (usually two PIDs per tunnel)**

**Example:**
```bash
sudo kill 105895 105952
```

---

## Step 5: Verify Tunnel Reconnects

Wait 10-30 seconds, then check:

```bash
sudo ss -tlnp | grep "127.0.0.1:222"
```

**The missing port should reappear if the remote service is running**

---

## Quick One-Liner to See All Active Tunnels

```bash
sudo ss -tlnp | grep "127.0.0.1:222" && echo "---" && ps aux | grep "tunneluser" | grep -v grep
```

**Shows both listening ports and processes**

---

## Port Reference

| Server | Port |
|--------|------|
| Cape | 2222 |
| NH-house | 2223 |
| Fram | 2224 |
| Next | 2225 |
