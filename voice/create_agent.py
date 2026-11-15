"""Safely prepare or explicitly apply the Hoitovirta ElevenLabs agent config.

Dry-run compares the desired config with the sanitized repo snapshot. Network writes
require --yes; dry-run never makes an API request.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from . import agent_config
except ImportError:  # direct script execution
    import agent_config

SNAPSHOT = Path(__file__).with_name("agent_live_snapshot.json")


def snapshot_view(snapshot):
    presets = snapshot.get("language_presets", {})
    return {
        "name": snapshot.get("name"),
        "language": snapshot.get("language"),
        "language_presets": presets,
        "llm": snapshot.get("llm"),
        "prompt": snapshot.get("prompt"),
        "tools": snapshot.get("tools", []),
        "built_in_tools_enabled": snapshot.get("built_in_tools_enabled", []),
        "turn": {k: (snapshot.get("turn") or {}).get(k) for k in ("turn_timeout", "silence_end_call_timeout")},
        "conversation": {"max_duration_seconds": (snapshot.get("conversation") or {}).get("max_duration_seconds")},
        "tts": snapshot.get("tts", {}),
        "data_collection": snapshot.get("data_collection", []),
        "widget": {k: (snapshot.get("widget") or {}).get(k) for k in agent_config.WIDGET},
        "overrides": (snapshot.get("overrides") or {}).get("conversation_config_override", {}),
    }


def config_view(cfg):
    cc = cfg["conversation_config"]
    agent = cc["agent"]
    prompt = agent["prompt"]
    preset_messages = {}
    for code, preset in cc["language_presets"].items():
        preset_messages[code] = preset.get("overrides", {}).get("agent", {}).get("first_message")
    return {
        "name": cfg["name"],
        "language": agent["language"],
        "language_presets": preset_messages,
        "llm": prompt["llm"],
        "prompt": prompt["prompt"],
        "tools": [t["name"] for t in prompt["tools"]],
        "built_in_tools_enabled": sorted(prompt["built_in_tools"]),
        "turn": cc["turn"],
        "conversation": cc["conversation"],
        "tts": cc["tts"],
        "data_collection": list(cfg["platform_settings"]["data_collection"]),
        "widget": cfg["platform_settings"]["widget"],
        "overrides": cfg["platform_settings"]["overrides"]["conversation_config_override"],
    }


def _safe(value, secrets_):
    if isinstance(value, str):
        for secret in secrets_:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_safe(v, secrets_) for v in value]
    if isinstance(value, dict):
        return {k: _safe(v, secrets_) for k, v in value.items()}
    return value


def render_diff(before, after, secrets_=()):
    before, after = _safe(before, secrets_), _safe(after, secrets_)
    rows = []
    for key in before.keys() | after.keys():
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if key == "prompt" and isinstance(old, str) and isinstance(new, str) and new.startswith(old):
            added = new[len(old):].strip()
            rows.append(f"~ prompt: append {added!r}")
        else:
            rows.append(f"~ {key}: {json.dumps(old, ensure_ascii=False, sort_keys=True)} -> {json.dumps(new, ensure_ascii=False, sort_keys=True)}")
    return "No changes against the sanitized snapshot." if not rows else "\n".join(sorted(rows))


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True, help="public URL where voice/service.py is served, no trailing slash")
    ap.add_argument("--language", default="en")
    ap.add_argument("--voice-id", default=None)
    ap.add_argument("--update", default=None, help="existing agent id to PATCH; defaults to ELEVENLABS_AGENT_ID at runtime")
    ap.add_argument("--dry-run", action="store_true", help="print a redacted diff only; never call the API")
    ap.add_argument("--yes", action="store_true", help="confirm the external agent write (required for POST/PATCH)")
    return ap


def main(argv=None, *, environ=None, urlopen=None, stdout=None):
    env = os.environ if environ is None else environ
    out = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    if environ is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        env = os.environ
    update_id = args.update or env.get("ELEVENLABS_AGENT_ID")
    key = env.get("ELEVENLABS_API_KEY", "")
    tool_secret = env.get("VOICE_TOOL_SECRET", "")
    cfg = agent_config.build(args.base_url.rstrip("/"), tool_secret, args.language, args.voice_id)
    try:
        baseline = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot read sanitized live snapshot: {type(exc).__name__}", file=out)
        return 2
    print(render_diff(snapshot_view(baseline), config_view(cfg), (key, tool_secret)), file=out)
    if args.dry_run or not args.yes:
        if not args.yes and not args.dry_run:
            print("\nNo API write made. Re-run with --yes only after reviewing the diff.", file=out)
        return 0
    if not key:
        print("Cannot apply: ELEVENLABS_API_KEY is not configured.", file=out)
        return 2
    endpoint = "https://api.elevenlabs.io/v1/convai/agents/" + (update_id if update_id else "create")
    request = urllib.request.Request(endpoint, data=json.dumps(cfg).encode(), method="PATCH" if update_id else "POST",
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(request, timeout=60) as response:
            body = json.load(response)
        print("API write completed for agent id:", body.get("agent_id", update_id or "created"), file=out)
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        detail = _safe(detail, (key, tool_secret))
        print("API write failed:", exc.code, detail[:1000], file=out)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
