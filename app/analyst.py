"""AI analyst: answers ONLY from data/evidence.json and cites ids.
Uses the shared llm() chain (Nemotron, then Featherless). With no LLM reachable it falls back to keyword
retrieval (no generation), so the demo never breaks."""
from app import ev, llm

EVID = ev.public()  # real evidence only; synthetic prototype numbers are never cited

SYSTEM = ("You are a cancer-pathway policy analyst for a Finnish wellbeing services county. "
          "Answer ONLY using the EVIDENCE list. Cite every claim as [id]. If the evidence does not "
          "cover something, say so plainly. Mark 'preliminary' or 'assumption' items as such. "
          "End with up to 3 concrete actions for the county (owner, KPI). Max 150 words. Plain language "
          "for a non-technical decision-maker. Never give clinical advice.")


def retrieve(q: str, k: int = 8):
    words = {w.strip("?.,").lower() for w in q.split() if len(w) > 3}
    scored = sorted(EVID, key=lambda e: -sum(w in e["claim"].lower() for w in words))
    return scored[:k]


def ask(q: str):
    """Return (answer, evidence used, engine)."""
    ctx = retrieve(q)
    evidence = "\n".join(f"[{e['id']}] ({e['status']}) {e['claim']} — {e['source']}" for e in EVID)
    text, engine = llm.llm(f"EVIDENCE:\n{evidence}\n\nQUESTION: {q}", system=SYSTEM, max_tokens=500)
    if not text:
        return ("No AI model reachable, so here is the most relevant evidence.\n\n"
                + "\n".join(f"- {e['claim']} [{e['id']}, {e['status']}]" for e in ctx[:5]), ctx, "offline")
    return text, ctx, engine
