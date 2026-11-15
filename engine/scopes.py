"""Server-enforced demo personas. HMAC tokens are a UI scope mechanism, not real authentication."""
import base64
import hashlib
import hmac
import json
import os
import re
import time

TOKEN_TTL_SECONDS = 3600
ROLES = {"all", "patient", "family", "triage", "coordinator", "admin", "diagnostics", "specialist", "screening", "county", "national", "steward"}

# Shared route categories keep the persona boundaries centralized and reviewable.
RULES = {
    "all": {"*"},
    "patient": {"public", "patient_path", "patient_notes", "patient_sensitive", "patient_guide", "patient_write", "patient_pulse"},
    "family": {"public", "patient_path", "patient_notes"},
    "triage": {"public", "triage_calls", "fasttrack", "slots", "triage_work", "role_metrics"},
    "coordinator": {"public", "pathways", "pathway_search", "worklist", "fasttrack", "triage_calls", "reports", "slots", "messages", "handover", "tasks", "patient_path", "patient_guide", "patient_write", "role_metrics"},
    "admin": {"public", "worklist", "slots"},
    "diagnostics": {"public", "reports", "pathway_search", "evidence", "role_metrics"},
    "specialist": {"public", "worklist", "pathways"},
    "screening": {"public", "outreach", "role_metrics"},
    "county": {"public", "county_aggregate", "national_aggregate", "board", "evidence", "role_metrics"},
    "national": {"public", "county_aggregate", "national_aggregate", "evidence", "role_metrics"},
    "steward": {"public", "reports", "pathway_search", "evidence", "quality", "role_metrics"},
}

PATHWAY_ID = re.compile(r"^/api/mypath/([^/]+)(?:/|$)")


def _secret():
    return os.getenv("HV_PERSONA_TOKEN_SECRET") or os.getenv("VOICE_TOOL_SECRET") or ""


def issue_token(role, pathway_id=None, secret=None, now=None):
    if role not in ROLES:
        raise ValueError("unknown persona")
    if role in ("patient", "family") and not pathway_id:
        raise ValueError("patient and family tokens require pathway_id")
    key = secret if secret is not None else _secret()
    if not key:
        raise RuntimeError("persona signing secret is not configured")
    issued = int(time.time() if now is None else now)
    payload = {"role": role, "iat": issued, "exp": issued + TOKEN_TTL_SECONDS}
    if role in ("patient", "family"):
        payload["pathway_id"] = str(pathway_id)
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    sig = hmac.new(key.encode(), body, hashlib.sha256).digest()
    return body.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def verify_token(token, secret=None, now=None):
    key = secret if secret is not None else _secret()
    if not token or not key or "." not in token:
        return None
    body, signature = token.split(".", 1)
    expected = base64.urlsafe_b64encode(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        current = int(time.time() if now is None else now)
        if payload.get("role") not in ROLES or not isinstance(payload.get("exp"), int) or payload["exp"] <= current:
            return None
        if payload.get("iat", current + 1) > current or payload["exp"] - payload.get("iat", 0) > TOKEN_TTL_SECONDS:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def category(path, method="GET"):
    if path in ("/api/health", "/api/meta", "/api/persona-token") or path.startswith("/api/i18n/") or path == "/api/benchmarks":
        return "public"
    if path.startswith("/api/mypath/"):
        if path.endswith("/companion/confirm"):
            return "patient_write"
        if path.endswith("/notes"):
            return "patient_notes" if method == "GET" else "patient_write"
        if path.endswith("/journey-guide"):
            return "patient_guide"
        if path.endswith("/companion") or path.endswith("/companion/confirm") or path.endswith("/question") or path.endswith("/slip"):
            return "patient_write"
        if path.endswith("/thread") or path.endswith("/audio"):
            return "patient_sensitive"
        if PATHWAY_ID.match(path):
            return "patient_path"
    if path == "/api/patients": return "patient_path"
    if path == "/api/pulse" or path == "/api/pulse/voice": return "patient_pulse"
    if path == "/api/calls": return "triage_calls"
    if path == "/api/pathways/search": return "pathway_search"
    if path.startswith("/api/pathways") or (path == "/api/events" and method != "POST"): return "pathways"
    if path == "/api/events" and method == "POST": return "patient_write"
    if path.startswith("/api/worklist"): return "worklist"
    if path == "/api/activity": return "county_aggregate"
    if path.startswith("/api/fasttrack"): return "fasttrack"
    if path.startswith("/api/slots"): return "slots"
    if path.startswith("/api/messages"): return "messages"
    if path.startswith("/api/handover"): return "handover"
    if path.startswith("/api/tasks/"): return "tasks"
    if path.startswith("/api/reports"): return "reports"
    if path.startswith("/api/evidence/"): return "evidence"
    if path.startswith("/api/outreach"): return "outreach"
    if path == "/api/rolemetrics": return "role_metrics"
    if path in ("/api/kpis", "/api/controltower"): return "county_aggregate"
    if path.startswith("/api/national") or path.startswith("/api/board"): return "national_aggregate" if path.startswith("/api/national") else "board"
    if path in ("/api/sim", "/api/demo/reset"): return "demo_admin"
    return "unknown"


def allowed(role, scope):
    if role == "all":
        return True
    return scope in RULES.get(role, set())


def pathway_matches(payload, path):
    match = PATHWAY_ID.match(path)
    return not match or payload.get("pathway_id") == match.group(1)


def _trim_family(data):
    if not isinstance(data, dict):
        return data
    allowed_fields = {"pathway_id", "first_name", "language", "place", "nurse", "next", "synthetic"}
    return {k: v for k, v in data.items() if k in allowed_fields}


ADMIN_BOOKING_FIELDS = {"id", "name", "language", "language_name", "interpreter", "coordinator", "booking", "next_label", "slot", "owner"}


def trim_response(data, role, path, pathway_id=None):
    """Drop fields outside a persona's minimum dataset after the endpoint executes."""
    if role == "all":
        return suppress_small_cells(data) if path.startswith(("/api/kpis", "/api/controltower", "/api/national")) else data
    if role == "family" and path.endswith("/notes") and isinstance(data, dict):
        return {"notes": data.get("notes", []), "synthetic": data.get("synthetic", True)}
    if role == "family" and PATHWAY_ID.match(path) and not path.endswith(("/thread", "/audio", "/journey-guide", "/notes")):
        return _trim_family(data)
    if role == "patient" and path == "/api/patients" and isinstance(data, dict):
        return {**data, "patients": [p for p in data.get("patients", []) if p.get("id") == pathway_id]}
    if role == "family" and path == "/api/patients" and isinstance(data, dict):
        return {"patients": [{k: v for k, v in p.items() if k in {"id", "name", "language"}} for p in data.get("patients", []) if p.get("id") == pathway_id]}
    if role == "admin" and path.startswith("/api/worklist") and isinstance(data, dict):
        rows = data.get("rows", [])
        trimmed = []
        for row in rows:
            item = {k: v for k, v in row.items() if k in ADMIN_BOOKING_FIELDS}
            if item.get("name"):
                item["name"] = " ".join(part[0] + "." for part in str(item["name"]).split() if part)
            if isinstance(item.get("booking"), dict):
                item["booking"] = {k: v for k, v in item["booking"].items() if k in {"due", "slot", "when", "reserved"}}
            trimmed.append(item)
        return {"rows": trimmed, "synthetic": data.get("synthetic", True)}
    if role in ("county", "national"):
        return suppress_small_cells(data)
    if role == "specialist" and isinstance(data, dict) and path.startswith(("/api/worklist", "/api/pathways")):
        if "rows" in data:
            fields = {"id", "name", "age", "language", "language_name", "county", "cancer", "step", "step_label", "next_label", "coordinator", "booking", "slipped", "steps", "referral", "history", "last_event_id", "synthetic"}
            rows = [{k: v for k, v in r.items() if k in fields} for r in data["rows"] if r.get("step") in ("T2", "T3", "T4", "T5")]
            return {"rows": rows, "total": len(rows), "synthetic": data.get("synthetic", True)}
        return {k: v for k, v in data.items() if k not in {"pulse", "questions", "messages", "flag", "risk", "vulnerability", "alerts"}}
    return data


def suppress_small_cells(data):
    """Suppress subgroup counts/values at n<5 recursively on county/national responses."""
    if isinstance(data, list):
        return [suppress_small_cells(x) for x in data]
    if not isinstance(data, dict):
        return data
    out = {k: suppress_small_cells(v) for k, v in data.items()}
    n = out.get("n")
    if isinstance(n, int) and n < 5:
        for key in list(out):
            if key not in {"language", "name", "county", "cancer", "suppressed", "synthetic"}:
                out[key] = None
        out["suppressed"] = True
    for key, value in list(out.items()):
        if (key.startswith("n_") or key == "n_pathways") and isinstance(value, int) and value < 5:
            out[key] = None
    return out
