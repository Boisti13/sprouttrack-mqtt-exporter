#!/usr/bin/env bash
set -euo pipefail

# Interactive setup helper for the exporter.
# Writes ./config.yaml and ./.secrets.env
# Optionally installs as a systemd service under /opt

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing required command: $1" >&2
    exit 1
  }
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

is_root() { [[ "${EUID:-$(id -u)}" -eq 0 ]]; }

run_root() {
  # Run a command that requires root.
  # - If already root: run directly
  # - Else: use sudo if available
  if is_root; then
    "$@"
  else
    if have_cmd sudo; then
      sudo "$@"
    else
      echo "ERROR: Need root privileges to run: $* (sudo not available)." >&2
      exit 1
    fi
  fi
}

detect_py_ver() {
  python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true
}

detect_venv_pkgs() {
  # Return package candidates in best-first order for Debian/Ubuntu.
  # Example output: "python3.12-venv python3-venv"
  local pyver
  pyver="$(detect_py_ver)"
  if [[ -n "$pyver" ]]; then
    echo "python3.${pyver}-venv python3-venv"
  else
    echo "python3-venv"
  fi
}

ensure_venv_support() {
  # If venv is usable, do nothing. Else install the distro package providing ensurepip/venv.
  if python3 -c 'import venv' >/dev/null 2>&1; then
    return 0
  fi

  echo
  echo "Python venv support not available (ensurepip/venv missing). Installing venv package..."

  if have_cmd apt-get; then
    run_root apt-get update -y

    local pkgs p
    pkgs="$(detect_venv_pkgs)"
    for p in $pkgs; do
      if run_root apt-get install -y "$p"; then
        echo "Installed: $p"
        return 0
      fi
    done

    echo "ERROR: Could not install python venv support. Tried: $pkgs" >&2
    exit 1
  fi

  echo "ERROR: Unsupported package manager; install python3-venv manually." >&2
  exit 1
}

prompt() {
  local var="$1"; shift
  local text="$1"; shift
  local def="${1:-}"

  if [[ -n "$def" ]]; then
    read -r -p "$text [$def]: " "$var" || true
    if [[ -z "${!var}" ]]; then
      printf -v "$var" '%s' "$def"
    fi
  else
    read -r -p "$text: " "$var" || true
  fi
}

prompt_secret() {
  local var="$1"; shift
  local text="$1"; shift
  read -r -s -p "$text: " "$var" || true
  echo
}

slugify() {
  # Lowercase, replace non-alnum with underscore, collapse repeats
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//; s/_+/_/g'
}

find_db_candidates() {
  local cands=()
  local p
  for p in \
    "/root/sprout-track/db/baby-tracker.db" \
    "/opt/sprout-track/db/baby-tracker.db" \
    "$(pwd)/baby-tracker.db" \
    "$(pwd)/db/baby-tracker.db" \
    ; do
    [[ -f "$p" ]] && cands+=("$p")
  done
  printf '%s\n' "${cands[@]:-}"
}

select_db() {
  mapfile -t CANDS < <(find_db_candidates || true)

  echo "Detected DB candidates:"
  if [[ ${#CANDS[@]} -eq 0 ]]; then
    echo "  (none found)"
  else
    local i
    for i in "${!CANDS[@]}"; do
      echo "  [$((i+1))] ${CANDS[$i]}"
    done
  fi
  echo "  [0] Enter custom path"

  local choice
  read -r -p "Choose DB path: " choice
  if [[ "$choice" == "0" || ${#CANDS[@]} -eq 0 ]]; then
    prompt DB_PATH "Enter full path to baby-tracker.db"
  else
    local idx=$((choice-1))
    DB_PATH="${CANDS[$idx]}"
  fi

  if [[ ! -f "$DB_PATH" ]]; then
    echo "ERROR: DB not found at: $DB_PATH" >&2
    exit 1
  fi

  # Light sanity check
  if ! sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('Baby','FeedLog','DiaperLog','SleepLog');" | grep -q Baby; then
    echo "ERROR: This does not look like a Sprout Track DB (missing expected tables)." >&2
    exit 1
  fi
}

select_baby() {
  echo
  echo "Babies found in DB:"

  # Detect actual column names in Baby table
  local cols
  cols="$(sqlite3 "$DB_PATH" "PRAGMA table_info(Baby);" 2>/dev/null | cut -d'|' -f2 | tr '\n' ' ' || true)"

  if [[ -z "$cols" ]]; then
    echo "ERROR: Could not inspect Baby table schema (PRAGMA failed)." >&2
    exit 1
  fi

  # Pick best-guess column names
  local col_id="id"
  local col_name=""
  local col_created=""
  local col_deleted=""

  # name can be: name, firstName, fullName (we prefer 'name')
  if echo " $cols " | grep -q " name "; then col_name="name"; fi
  if [[ -z "$col_name" ]] && echo " $cols " | grep -q " firstName "; then col_name="firstName"; fi
  if [[ -z "$col_name" ]] && echo " $cols " | grep -q " fullName "; then col_name="fullName"; fi

  # createdAt can be: createdAt, created_at
  if echo " $cols " | grep -q " createdAt "; then col_created="createdAt"; fi
  if [[ -z "$col_created" ]] && echo " $cols " | grep -q " created_at "; then col_created="created_at"; fi

  # deletedAt can be: deletedAt, deleted_at
  if echo " $cols " | grep -q " deletedAt "; then col_deleted="deletedAt"; fi
  if [[ -z "$col_deleted" ]] && echo " $cols " | grep -q " deleted_at "; then col_deleted="deleted_at"; fi

  if [[ -z "$col_name" ]]; then
    echo "ERROR: Could not find a baby name column in Baby table. Columns: $cols" >&2
    exit 1
  fi

  # Build query dynamically (avoid failing on missing columns)
  local sql="SELECT $col_id, $col_name FROM Baby"
  if [[ -n "$col_deleted" ]]; then
    sql="$sql WHERE $col_deleted IS NULL"
  fi
  if [[ -n "$col_created" ]]; then
    sql="$sql ORDER BY $col_created DESC"
  else
    sql="$sql ORDER BY rowid DESC"
  fi
  sql="$sql;"

  local rows
  rows="$(sqlite3 -separator $'\t' "$DB_PATH" "$sql" 2>/dev/null || true)"

  if [[ -z "$rows" ]]; then
    echo "ERROR: Could not list babies from DB (query returned no rows)." >&2
    echo "Tried SQL: $sql" >&2
    exit 1
  fi

  mapfile -t BABY_ROWS < <(printf '%s\n' "$rows")

  local i
  for i in "${!BABY_ROWS[@]}"; do
    local id name
    id="$(printf '%s' "${BABY_ROWS[$i]}" | cut -f1)"
    name="$(printf '%s' "${BABY_ROWS[$i]}" | cut -f2)"
    echo "  [$((i+1))] $name ($id)"
  done

  local choice
  read -r -p "Choose baby: " choice
  local idx=$((choice-1))
  BABY_ID="$(printf '%s' "${BABY_ROWS[$idx]}" | cut -f1)"
  BABY_NAME="$(printf '%s' "${BABY_ROWS[$idx]}" | cut -f2)"

  if [[ -z "$BABY_ID" || -z "$BABY_NAME" ]]; then
    echo "ERROR: invalid selection." >&2
    exit 1
  fi
}

main() {
  need_cmd sqlite3
  need_cmd sed
  need_cmd tr
  need_cmd awk

  echo "Sprout Track -> HA MQTT Exporter setup"
  echo "Project: $PROJECT_ROOT"

  echo
  echo "Environment:"
  echo "  [1] Proxmox / LXC (no sudo assumed; typically running as root)"
  echo "  [2] Bare metal / VM (sudo may be used if not root)"
  local env_choice
  read -r -p "Choose [1/2] (default 1): " env_choice || true
  env_choice="${env_choice:-1}"
  # Note: behavior is auto-detected via is_root/sudo; this prompt is UX-only.

  select_db
  select_baby

  echo
  prompt MQTT_HOST "MQTT host / IP"
  prompt MQTT_PORT "MQTT port" "1883"
  prompt MQTT_USER "MQTT username (leave empty if none)" ""
  prompt_secret MQTT_PASS "MQTT password (leave empty if none)"
  prompt POLL_SEC "Poll interval (seconds)" "300"

  echo
  echo "Install options:"
  echo "  [1] Dev setup only (write config.yaml + .secrets.env in this folder)"
  echo "  [2] Install as a systemd service (copies to /opt, creates venv, enables service)"
  local install_choice
  read -r -p "Choose [1/2] (default 1): " install_choice || true
  install_choice="${install_choice:-1}"

  local INSTALL_ROOT=""
  if [[ "$install_choice" == "2" ]]; then
    if ! is_root; then
      echo "ERROR: systemd install requires root. Re-run as root (or choose option 1)." >&2
      exit 1
    fi
    prompt INSTALL_ROOT "Install directory" "/opt/sprouttrack-ha-exporter"
  fi

  cat > config.yaml <<CFG
# Generated by scripts/setup.sh

db_path: ${DB_PATH}
baby_id: "${BABY_ID}"
baby_name: "${BABY_NAME}"

baby_slug: "$(slugify "$BABY_NAME")"

poll_sec: ${POLL_SEC}

mqtt:
  host: ${MQTT_HOST}
  port: ${MQTT_PORT}

base_topic: sprouttrack
ha_discovery_prefix: homeassistant
timezone: Europe/Berlin
CFG

  cat > .secrets.env <<SECRETS
# Generated by scripts/setup.sh
MQTT_USER=${MQTT_USER}
MQTT_PASS=${MQTT_PASS}
SECRETS

  chmod 600 .secrets.env

  if [[ "$install_choice" == "1" ]]; then
    echo
    echo "Wrote: $(pwd)/config.yaml"
    echo "Wrote: $(pwd)/.secrets.env (mode 600)"
    echo

    local run_now="n"
    read -r -p "Run exporter now (create venv + install deps)? [y/N]: " run_now || true
    run_now="${run_now:-n}"

    if [[ "$run_now" =~ ^[Yy]$ ]]; then
      need_cmd python3
      ensure_venv_support

      if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
      fi

      .venv/bin/pip install --upgrade pip
      .venv/bin/pip install -r requirements.txt

      echo
      echo "Starting exporter (Ctrl+C to stop)..."
      exec .venv/bin/python -m sprouttrack_exporter --config config.yaml --secrets .secrets.env
    fi

    echo "Next (manual):"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo "  python -m sprouttrack_exporter --config config.yaml --secrets .secrets.env"
    return 0
  fi

  # Option 2: Install as systemd service
  echo
  echo "Installing to: $INSTALL_ROOT"
  mkdir -p "$INSTALL_ROOT"

  # Copy project (excluding venv/cache)
  # Use tar to preserve permissions and keep this dependency-light.
  (cd "$PROJECT_ROOT" && tar --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' -cf - .) \
    | (cd "$INSTALL_ROOT" && tar -xf -)

  # Ensure secrets are protected in install location
  chmod 600 "$INSTALL_ROOT/.secrets.env" || true

  # Create venv + install requirements
  need_cmd python3
  ensure_venv_support
  python3 -m venv "$INSTALL_ROOT/.venv"
  "$INSTALL_ROOT/.venv/bin/pip" install --upgrade pip
  "$INSTALL_ROOT/.venv/bin/pip" install -r "$INSTALL_ROOT/requirements.txt"

  # Install systemd unit
  local SERVICE_NAME="sprouttrack-ha-exporter.service"
  local UNIT_SRC="$INSTALL_ROOT/systemd/sprouttrack-ha-exporter.service.template"
  local UNIT_DST="/etc/systemd/system/$SERVICE_NAME"

  if [[ ! -f "$UNIT_SRC" ]]; then
    echo "ERROR: missing systemd unit template at $UNIT_SRC" >&2
    exit 1
  fi

  # Patch WorkingDirectory/ExecStart paths if user changed install dir
  awk -v root="$INSTALL_ROOT" '
    /^WorkingDirectory=/ {print "WorkingDirectory=" root; next}
    /^EnvironmentFile=/ {print "EnvironmentFile=" root "/.secrets.env"; next}
    /^ExecStart=/ {print "ExecStart=" root "/.venv/bin/python -m sprouttrack_exporter --config " root "/config.yaml --secrets " root "/.secrets.env"; next}
    {print}
  ' "$UNIT_SRC" > "$UNIT_DST"

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"

  echo
  echo "Installed and started: $SERVICE_NAME"
  echo "Check status: systemctl status $SERVICE_NAME --no-pager"
}

main "$@"
