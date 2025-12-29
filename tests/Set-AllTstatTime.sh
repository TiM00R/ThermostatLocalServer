#!/usr/bin/env bash
# Set-AllTstatTime.sh
#
# Bash conversion of the provided PowerShell script.
# Requires: bash, curl
#
# Usage examples:
#   ./Set-AllTstatTime.sh                    # defaults: 10.0.60.2..20, timeout 4s
#   ./Set-AllTstatTime.sh 2 20 4
#   ./Set-AllTstatTime.sh 10.0.60.2 10.0.60.20 6

set -u

START_IP="${1:-2}"     # accepts "2" or "10.0.60.2"
END_IP="${2:-20}"      # accepts "20" or "10.0.60.20"
TIMEOUT_SEC="${3:-4}"  # per-host HTTP timeout seconds

BASE="10.0.60"
DAY_NAMES=(Mon Tue Wed Thu Fri Sat Sun)
TZ_NAME="America/New_York"


get_host_octet() {
  # Input: "2" or "10.0.60.2"
  # Output: last octet as int
  local arg="$1"
  if [[ "$arg" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
    echo "${arg##*.}"
  else
    echo "$arg"
  fi
}

is_thermostat() {
  # Heuristic check:
  # - GET /tstat must return JSON containing: "time", plus "day","hour","minute"
  # - Validate ranges (best-effort with simple parsing)
  local ip="$1"
  local to="$2"

  local json
  json="$(curl -sS --max-time "$to" "http://$ip/tstat" 2>/dev/null || true)"
  [[ -n "$json" ]] || return 1

  # Must contain time + fields
  echo "$json" | grep -q '"time"'   || return 1
  echo "$json" | grep -q '"day"'    || return 1
  echo "$json" | grep -q '"hour"'   || return 1
  echo "$json" | grep -q '"minute"' || return 1

  # Extract numbers (best-effort). This assumes keys look like: "day":0 etc.
  local day hour minute tmode
  day="$(echo "$json" | sed -n 's/.*"day"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
  hour="$(echo "$json" | sed -n 's/.*"hour"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
  minute="$(echo "$json" | sed -n 's/.*"minute"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"

  [[ "$day" =~ ^[0-9]+$ ]]    || return 1
  [[ "$hour" =~ ^[0-9]+$ ]]   || return 1
  [[ "$minute" =~ ^[0-9]+$ ]] || return 1

  (( day >= 0 && day <= 6 ))     || return 1
  (( hour >= 0 && hour <= 23 ))  || return 1
  (( minute >= 0 && minute <= 59 )) || return 1

  # Optional: tmode 0..3 if present
  if echo "$json" | grep -q '"tmode"'; then
    tmode="$(echo "$json" | sed -n 's/.*"tmode"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
    if [[ "$tmode" =~ ^[0-9]+$ ]]; then
      (( tmode >= 0 && tmode <= 3 )) || return 1
    fi
  fi

  return 0
}

http_get() {
  local url="$1"
  local to="$2"
  curl -sS --max-time "$to" "$url" 2>/dev/null || true
}

http_post_json() {
  local url="$1"
  local to="$2"
  local body="$3"
  curl -sS --max-time "$to" -H "Content-Type: application/json" -X POST -d "$body" "$url" 2>/dev/null || true
}

# --- main -------------------------------------------------------------

start="$(get_host_octet "$START_IP")"
end="$(get_host_octet "$END_IP")"

# swap if needed
if (( end < start )); then
  tmp="$start"; start="$end"; end="$tmp"
fi

# Local time -> API day mapping (Mon=0..Sun=6)
# Linux date: %u gives 1..7 (Mon..Sun). Convert to 0..6 by -1.

now_ymd_hm="$(TZ=$TZ_NAME date '+%Y-%m-%d %H:%M')"
api_day="$(( $(TZ=$TZ_NAME date '+%u') - 1 ))"
hour="$(TZ=$TZ_NAME date '+%H')"
minute="$(TZ=$TZ_NAME date '+%M')"

body="{\"time\":{\"day\":$api_day,\"hour\":$((10#$hour)),\"minute\":$((10#$minute))}}"

printf "Setting time to %s (day=%s) on %s.%s..%s  timeout=%ss\n\n" \
  "$now_ymd_hm" "$api_day" "$BASE" "$start" "$end" "$TIMEOUT_SEC"

total=$(( end - start + 1 ))
i=0
ok=0

for ((oct=start; oct<=end; oct++)); do
  ip="$BASE.$oct"
  i=$((i+1))

  printf "[%2d/%d] %s ..." "$i" "$total" "$ip"

  if ! is_thermostat "$ip" "$TIMEOUT_SEC"; then
    printf "  skip (not a thermostat)\n"
    continue
  fi

  # Optional: read /sys/name (ignore errors)
  name_json="$(http_get "http://$ip/sys/name" "$TIMEOUT_SEC")"
  name="$(echo "$name_json" | sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"

  # Set time (discard response noise)
  http_post_json "http://$ip/tstat" "$TIMEOUT_SEC" "$body" >/dev/null

  # Verify actual time from device
  tstat_json="$(http_get "http://$ip/tstat" "$TIMEOUT_SEC")"

  d="$(echo "$tstat_json" | sed -n 's/.*"day"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
  h="$(echo "$tstat_json" | sed -n 's/.*"hour"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
  m="$(echo "$tstat_json" | sed -n 's/.*"minute"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"

  if [[ "$d" =~ ^[0-9]+$ && "$h" =~ ^[0-9]+$ && "$m" =~ ^[0-9]+$ ]]; then
    # 12h formatting
    h12=$(( h % 12 ))
    (( h12 == 0 )) && h12=12
    ampm="AM"
    (( h >= 12 )) && ampm="PM"

    # Print OK line
    if [[ -n "$name" ]]; then
      printf "  OK  %s -> %s %d:%02d (24h) / %d:%02d %s\n" \
        "$name" "${DAY_NAMES[$d]}" "$h" "$m" "$h12" "$m" "$ampm"
    else
      printf "  OK  -> %s %d:%02d (24h) / %d:%02d %s\n" \
        "${DAY_NAMES[$d]}" "$h" "$m" "$h12" "$m" "$ampm"
    fi
    ok=$((ok+1))
  else
    printf "  -\n"
  fi
done

printf "\nDone. Updated %d thermostat(s).\n" "$ok"
