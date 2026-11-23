"""OrgTwin: one facade over graph (what depends on what), memory (why things are the way they are),
black box (what actually happened) and controls (what should have stopped it)."""
import json, os, re, urllib.request
from .forensics import reconstruct, replay, rank_candidates

CHANGE_WORDS = [("delay", r"delay|slow|late|postpone|تأخير|اتأخر"), ("remove", r"remove|delete|shut|stop|retire|إلغاء|الغاء|شيل|وقف"),
                ("relax", r"raise|increase|loosen|relax|disable|skip|ارفع|زود|خفف|عطل"), ("degrade", r"degrade|change|upgrade|modify|غير|عدل")]


class OrgTwin:
    def __init__(self, graph, memory, bb, controls, candidates):
        self.g, self.mem, self.bb, self.controls, self.candidates = graph, memory, bb, controls, candidates

    def simulate(self, node, change):
        if self.g.nodes[node]["type"] == "policy" and change == "remove":
            change = "relax"
        impacted = self.g.impact(node, change)
        ids = [node] + [i["id"] for i in impacted[:5]]
        past = [t for t in self.bb.traces() if any(e["actor"] == node or e["resource"] == node for e in self.bb.trace(t))]
        return {"node": node, "name": self.g.nodes[node]["name"], "change": change, "impacted": impacted,
                "relied_on_by": [{"id": d["id"], "title": d["title"], "date": d["date"]} for d in self.mem.assumptions_hit(node)],
                "related_decisions": [{"id": d["id"], "title": d["title"], "date": d["date"]} for d in self.mem.for_nodes(ids)],
                "seen_in_incidents": past}

    def report(self, trace):
        return reconstruct(self.bb, trace, self.controls, self.candidates, self.g, self.mem)

    def replay(self, trace, control_ids):
        cs = [c for c in self.candidates if c["id"] in control_ids]
        if not cs:
            raise ValueError("choose at least one known candidate control")
        return replay(self.bb, trace, cs)

    def incidents(self):
        out = []
        for t in self.bb.traces():
            r = self.report(t)
            out.append({"trace": t, "root_cause": bool(r["root_cause"]), "loss": r["loss"], "events": len(r["timeline"])})
        return out

    def ask(self, q):
        if re.search(r"what if|what happens|simulate|لو |ماذا لو|لو\b", q, re.I):
            node = self.g.find(q)
            if not node:
                return {"type": "clarify", "answer": "I could not tell which part of the organisation you mean. Name a system, process or policy."}
            change = next((c for c, rx in CHANGE_WORDS if re.search(rx, q, re.I)), "degrade")
            return {"type": "simulation", **self.simulate(node, change)}
        if re.search(r"what happened|root cause|incident|why did .*(fail|wrong)|حصل|فشل|غلط", q, re.I):
            t = next((i["trace"] for i in self.incidents() if i["root_cause"]), None)
            return {"type": "incident", "report": self.report(t)} if t else {"type": "clarify", "answer": "No failed run is recorded."}
        hits = self.mem.search(q, 3)
        return {"type": "memory", "answer": hits[0]["text"] + f" [{hits[0]['id']}]" if hits else "Nothing in the decision memory matches.",
                "sources": [{"id": h["id"], "title": h["title"], "date": h["date"], "score": h["score"]} for h in hits]}

    @staticmethod
    def summary(r):
        rc = r["root_cause"]
        if not rc:
            return f"Run {r['trace']} completed without divergence or control violations."
        bar = ", ".join(f"{v['control']} at {v['event'].split('-')[-1]}" for v in r["violations"]) or "none"
        sk = ", ".join(f"{s['what']} ({s['reason']})" for s in r["skipped_barriers"]) or "none"
        return (f"Run {r['trace']} started with {r['originator']['actor']}. The error began at {rc['event']}: {rc['why']}. "
                f"Barriers that failed: {bar}. Barriers skipped by exception: {sk}. Loss: EGP {r['loss']:,.0f}, "
                f"detected {r['detection_lag_hours']} h after the transfer.")

    def narrate(self, r):
        key = os.getenv("ANTHROPIC_API_KEY")
        text = self.summary(r)
        if not key:
            return {"text": text, "source": "deterministic"}
        try:
            body = {"model": os.getenv("LLM_MODEL", "claude-sonnet-5-5"), "max_tokens": 500, "messages": [{"role": "user", "content":
                    "Write a 5-sentence incident explanation for a CFO. Use ONLY the JSON evidence. Cite event ids like [INC-2026-001-E2]. "
                    "Do not invent numbers.\n" + json.dumps(r, default=str)}]}
            rq = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
                                        {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
            out = json.loads(urllib.request.urlopen(rq, timeout=30).read())["content"][0]["text"]
        except Exception:
            return {"text": text, "source": "deterministic (LLM unavailable)"}
        ev_json = json.dumps(r, default=str).replace(",", "")
        ids_ok = all(i in {e["id"] for e in r["timeline"]} for i in re.findall(r"\[(INC-[\w-]+|TRX-[\w-]+)\]", out))
        nums_ok = all(n in ev_json for n in re.findall(r"\d[\d,]*\.?\d*", out.replace(",", "")) if len(n) > 2)
        return {"text": out, "source": "llm (grounded)"} if ids_ok and nums_ok else {"text": text, "source": "deterministic (LLM output failed grounding check)"}
