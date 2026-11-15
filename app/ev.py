"""Evidence layer. data/evidence.json is the ONLY place a number can come from.
Every number rendered in the UI goes through num()/stat()/chip(), so it always carries a status badge
and a source link. An id with no source raises, so an unsourced number cannot reach the screen."""
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
_RAW = json.loads((ROOT / "data/evidence.json").read_text())
EV = {e["id"]: e for e in _RAW}
IV = json.loads((ROOT / "data/interventions.json").read_text())

_ORDER = {"sourced": 0, "preliminary": 1, "assumption": 2, "synthetic": 3}
LABEL = {"sourced": "Sourced", "preliminary": "Preliminary", "assumption": "Assumption", "synthetic": "Synthetic"}


def _derive(e):
    d = e.get("derive")
    if not d or "value" in e:
        return
    if d["op"] == "sub":
        e["value"] = get(d["a"])["value"] - get(d["b"])["value"]
    elif d["op"] == "remainder":
        e["value"] = get(d["total"])["value"] - sum(get(i)["value"] for i in d["minus"])


def get(eid):
    e = EV[eid]
    _derive(e)
    return e


for _e in EV.values():
    _derive(_e)
    if not _e.get("source"):
        raise ValueError(f"evidence {_e['id']} has no source")


def public():
    """Entries safe to cite as real-world evidence (excludes synthetic prototype numbers)."""
    return [e for e in EV.values() if e["status"] != "synthetic"]


def v(eid):
    return get(eid)["value"]


def rng(eid):
    return get(eid)["range"]


def fmt(eid, plus=False):
    e = get(eid)
    if "cost_label" in e:
        return e["cost_label"]
    x = e["value"]
    x = int(x) if float(x).is_integer() else x
    u = e.get("unit", "")
    s = {"days": f"{x} d", "%": f"{x}%", "pp": f"{x} pp", "": f"{x}"}.get(u, f"{x} {u}")
    return ("+" if plus and e["value"] > 0 else "") + s


def chip(eid):
    """Small status badge + source link (HTML)."""
    e = get(eid)
    st = e["status"]
    name = html.escape(e.get("short") or e["source"][:40])
    label = LABEL.get(st, st)
    inner = f'<span class="st">{label}</span>{name}'
    if e.get("url"):
        return f'<a class="src s-{st}" href="{html.escape(e["url"])}" target="_blank" rel="noopener" title="{html.escape(e["source"])}">{inner}</a>'
    return f'<span class="src s-{st}" title="{html.escape(e["source"])}">{inner}</span>'


def chips(*eids):
    seen, out = set(), []
    for i in eids:
        e = get(i)
        key = (e.get("short") or e["source"], e["status"], e.get("url", ""))
        if key not in seen:  # one chip per distinct source + status
            seen.add(key)
            out.append(chip(i))
    return '<span class="chips">' + "".join(out) + "</span>"


def worst(*eids):
    return max((get(i)["status"] for i in eids), key=lambda s: _ORDER[s])


def num(eid, plus=False):
    """Inline number + its badge."""
    return f'<b class="n">{fmt(eid, plus)}</b> {chip(eid)}'


def stat(label, big, eids, note="", tone=""):
    """Stat card. `big` is an evidence id (formatted) or literal text with no digits."""
    eids = [eids] if isinstance(eids, str) else list(eids)
    value = fmt(big) if big in EV else html.escape(big)
    cls = f"card {tone}".strip()
    note_html = f'<span class="note">{html.escape(note)}</span>' if note else ""
    return (f'<div class="{cls}"><span class="big">{value}</span><span class="lab">{html.escape(label)}</span>'
            f'{note_html}{chips(*eids)}</div>')


def sources_text(eid):
    e = get(eid)
    return f"[{e['source']}]({e['url']})" if e.get("url") else e["source"]
