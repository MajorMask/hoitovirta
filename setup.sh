#!/usr/bin/env bash
# One-time setup for Hoitovirta. Run from this folder:  bash setup.sh
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Paste your keys into it, save, then run: bash setup.sh"
  open -e .env 2>/dev/null || true
  exit 0
fi

missing=$(grep -E '^(VERDA_INFERENCE_KEY|FEATHERLESS_API_KEY|GEMINI_API_KEY|ELEVENLABS_API_KEY|VOICE_TOOL_SECRET|ELEVENLABS_WEBHOOK_SECRET|OPENAI_API_KEY|DATABASE_URL)=$' .env | cut -d= -f1 || true)
if [ -n "$missing" ]; then
  echo "Still empty in .env (fine for now, the app falls back offline):"
  echo "$missing"
fi

echo "1/3 Installing Python packages"
python3 -m pip install -q --upgrade modal -r requirements.txt

echo "2/3 Linking this Mac to Modal (opens a browser tab once)"
python3 -m modal token info >/dev/null 2>&1 || python3 -m modal setup

echo "3/3 Saving .env as the Modal secret 'hoitovirta'"
tmp=$(mktemp); grep -E '^[A-Z_]+=.+' .env > "$tmp"
# GEMINI_API_KEY and the protected voice secrets are included by the same dotenv export.
python3 -m modal secret create hoitovirta --from-dotenv "$tmp" --force
rm -f "$tmp"

echo "Done. Next: python3 -m modal deploy modal_app.py"
