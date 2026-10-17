#!/usr/bin/env bash
# Regenerate every blog image from whatever real data exists, in one go (Git Bash on Windows, or any bash).
#
#   bash docs/regen_media.sh                 # everything
#   bash docs/regen_media.sh --no-shots      # (a)-(c) only: fixtures, visuals, charts
#   bash docs/regen_media.sh --shots-only    # (d) only
#
#  (a) agent.make_fixtures -> shared/fixtures/*.json, copied over web/public/fixtures/ (web-only files are kept)
#  (b) docs/visuals: build_data.py + render.py -> docs/images/*.png
#  (c) docs/charts/make_charts.py -> docs/charts/*.png (+ chart_data.json)
#  (d) starts Temporal dev server + worker + API (agent.dev), the web app on :3000 (built against the live API),
#      and a READ-ONLY copy of the label UI on :8790 (RECALLDESK_DATA = temp copy of data/), takes
#      docs/blog-shots/*.png incl. the Temporal Web UI, then stops everything it started.
#
# Safety: never spends SerpApi (SERPAPI_API_KEY is blanked for the stack), never trains or labels, never touches
# :8765 (the live labelling session). Services already listening on a port are reused and left running.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG="${TMPDIR:-/tmp}/recalldesk-regen"
mkdir -p "$LOG"
AGENT_PY="agent/.venv/Scripts/python.exe"; [ -x "$AGENT_PY" ] || AGENT_PY="agent/.venv/bin/python"
ML_PY="ml/.venv/Scripts/python.exe"; [ -x "$ML_PY" ] || ML_PY="ml/.venv/bin/python"
CH_PY="docs/charts/.venv/Scripts/python.exe"; [ -x "$CH_PY" ] || CH_PY="docs/charts/.venv/bin/python"
SYS_PY="$(command -v python || command -v python3)"
LABEL_PORT=8790
DO_PREP=1; DO_SHOTS=1
[ "${1:-}" = "--no-shots" ] && DO_SHOTS=0
[ "${1:-}" = "--shots-only" ] && DO_PREP=0
FAIL=0
step() { printf '\n=== %s ===\n' "$*"; }
warn() { printf '!!! %s\n' "$*"; FAIL=1; }

port_busy() {  # port_busy 8000 -> 0 if something listens
  if command -v netstat >/dev/null 2>&1; then
    # (Windows keeps a dead process's socket as "LISTENING ... pid 0" for a while: not busy)
    netstat -ano 2>/dev/null | grep -E "LISTENING|LISTEN " | grep -E "[:.]$1 " | awk '$NF != "0"' | grep -q . \
      && return 0 || return 1
  fi
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && return 0 || return 1
}
wait_http() {  # wait_http URL seconds
  local i=0
  while [ $i -lt "$2" ]; do
    curl -sf -o /dev/null "$1" && return 0
    sleep 1; i=$((i + 1))
  done
  return 1
}
PIDS=()
start_bg() {  # start_bg name cmd...  (records the Windows pid when available, for a tree kill)
  local name="$1"; shift
  "$@" >"$LOG/$name.log" 2>&1 &
  local pid=$!
  local wp="$pid"; [ -r "/proc/$pid/winpid" ] && wp="$(cat /proc/$pid/winpid)"
  PIDS+=("$name:$pid:$wp")
  echo "started $name (pid $pid, win $wp) -> $LOG/$name.log"
}
stop_all() {
  for e in "${PIDS[@]:-}"; do
    [ -z "$e" ] && continue
    IFS=: read -r name pid wp <<<"$e"
    if command -v taskkill >/dev/null 2>&1; then taskkill //F //T //PID "$wp" >/dev/null 2>&1 || true; fi
    kill "$pid" >/dev/null 2>&1 || true
    echo "stopped $name"
  done
  PIDS=()
  # anything we started that still holds one of our ports (e.g. temporal.exe re-parented): kill by port
  for p in "${OWNED_PORTS[@]:-}"; do
    [ -z "$p" ] && continue
    if command -v netstat >/dev/null 2>&1 && command -v taskkill >/dev/null 2>&1; then
      for wp in $(netstat -ano | grep LISTENING | grep -E "[:.]$p " | awk '{print $NF}' | sort -u); do
        [ "$wp" != "0" ] && taskkill //F //T //PID "$wp" >/dev/null 2>&1 && echo "killed leftover pid $wp on :$p"
      done
    fi
  done
}
OWNED_PORTS=()
trap stop_all EXIT

if [ $DO_PREP = 1 ]; then
  step "(a) fixtures from real runs + ml/results"
  if "$AGENT_PY" -m agent.make_fixtures; then
    mkdir -p web/public/fixtures
    cp -f shared/fixtures/*.json web/public/fixtures/ && echo "copied $(ls shared/fixtures/*.json | wc -l) fixture(s) -> web/public/fixtures/"
  else warn "agent.make_fixtures failed"; fi

  step "(b) docs/visuals -> docs/images"
  "$SYS_PY" docs/visuals/build_data.py && "$SYS_PY" docs/visuals/render.py || warn "visuals failed"

  step "(c) docs/charts"
  "$CH_PY" docs/charts/make_charts.py 2>&1 | grep -v "^findfont" || warn "charts failed"
fi

if [ $DO_SHOTS = 1 ]; then
  step "(d) live stack + screenshots"
  # The /check shot runs one real InventoryCheckWorkflow for the UI's demo shop, which the API aliases to
  # little-loop, so it would replace agent/cards/latest_little-loop.json (the post's card) with a 12-item
  # sample card. Snapshot the published cards and put them back afterwards. The shot's own run record stays.
  CARDS_BAK="$(mktemp -d "${TMPDIR:-/tmp}/rd-cards-XXXX")"
  cp -p agent/cards/latest_*.json agent/cards/card_*.json "$CARDS_BAK/" 2>/dev/null || true
  restore_cards() {
    [ -n "${CARDS_BAK:-}" ] && [ -d "$CARDS_BAK" ] || return 0
    cp -p "$CARDS_BAK"/*.json agent/cards/ 2>/dev/null && echo "restored published cards (latest_*, card_*)"
    rm -rf "$CARDS_BAK"; CARDS_BAK=""
  }
  trap 'stop_all; restore_cards' EXIT
  # 1) Temporal + worker + API
  if port_busy 8000; then echo ":8000 already in use - reusing that API"; else
    OWNED_PORTS+=(8000 7233 8233)
    SERPAPI_API_KEY="" PYTHONUNBUFFERED=1 start_bg agent-dev "$AGENT_PY" -m agent.dev
  fi
  wait_http "http://localhost:8000/api/health" 180 || warn "API did not come up (see $LOG/agent-dev.log)"
  wait_http "http://localhost:8233/" 60 || warn "Temporal UI did not come up"

  # 2) web, built against the live API
  if port_busy 3000; then echo ":3000 already in use - reusing that web server"; else
    OWNED_PORTS+=(3000)
    # The API base defaults to http://localhost:8000 in web/lib/api.ts, so an existing production build already
    # points at the live API. Rebuild only when asked (RD_WEB_BUILD=1) or when there is no build: rebuilding
    # web/.next under another running `next start` breaks that server's chunks.
    if [ "${RD_WEB_BUILD:-0}" = 1 ] || [ ! -f web/.next/BUILD_ID ]; then
      ( cd web && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run build >"$LOG/web-build.log" 2>&1 ) \
        || warn "web build failed (see $LOG/web-build.log)"
    else echo "reusing web/.next (RD_WEB_BUILD=1 to rebuild)"; fi
    pushd web >/dev/null
    NEXT_PUBLIC_API_BASE=http://localhost:8000 start_bg web npx next start -p 3000
    popd >/dev/null
  fi
  wait_http "http://localhost:3000/" 90 || warn "web did not come up"

  # 3) read-only label UI on a temp copy of data/ (never :8765, never the real data/gold)
  TMPD="$(mktemp -d "${TMPDIR:-/tmp}/rd-label-XXXX")"
  for d in recalls specs listings splits pairs gold; do [ -d "data/$d" ] && cp -r "data/$d" "$TMPD/"; done
  if [ -f "$TMPD/splits/test.jsonl" ]; then
    if port_busy $LABEL_PORT; then warn ":$LABEL_PORT busy - skipping label UI"; else
      OWNED_PORTS+=($LABEL_PORT)
      RECALLDESK_DATA="$TMPD" PYTHONUNBUFFERED=1 start_bg label-ui "$ML_PY" -m ml.label_ui --port $LABEL_PORT
      wait_http "http://localhost:$LABEL_PORT/" 60 || warn "label UI did not come up (see $LOG/label-ui.log)"
    fi
  else warn "no data/splits/test.jsonl yet - label UI shot skipped"; fi

  # 4) shots
  ( cd web && LABEL_BASE="http://localhost:$LABEL_PORT" node scripts/blog-shots.mjs ) || warn "blog-shots failed"

  step "stopping what this script started"
  stop_all
  OWNED_PORTS=()
  restore_cards
  rm -rf "$TMPD"
  for p in 3000 8000 7233 8233 $LABEL_PORT; do port_busy $p && echo "port :$p still listening" || echo "port :$p free"; done
fi
[ $FAIL = 0 ] && echo "regen_media: OK" || echo "regen_media: finished with warnings (see above)"
exit $FAIL
