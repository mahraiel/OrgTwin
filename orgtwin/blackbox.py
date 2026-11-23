"""Append-only, hash-chained event recorder (the 'black box'). Events come from humans, AI agents and systems alike."""
import hashlib, json

REQUIRED = ("id", "trace", "ts", "actor", "actor_type", "action", "resource")


class BlackBox:
    def __init__(self):
        self.events = []

    @staticmethod
    def _h(prev, core):
        return hashlib.sha256((prev + json.dumps(core, sort_keys=True, default=str)).encode()).hexdigest()

    def record(self, **e):
        miss = [k for k in REQUIRED if k not in e]
        if miss:
            raise ValueError(f"missing fields: {miss}")
        if any(x["id"] == e["id"] for x in self.events):
            raise ValueError("duplicate event id")
        for k, d in (("parent", None), ("permission", None), ("inputs", {}), ("outputs", {}), ("meta", {})):
            e.setdefault(k, d)
        prev = self.events[-1]["hash"] if self.events else "0" * 64
        e["seq"], e["prev"] = len(self.events), prev
        e["hash"] = self._h(prev, {k: v for k, v in e.items() if k not in ("hash", "prev")})
        self.events.append(e)
        return e

    def verify(self):
        prev = "0" * 64
        for e in self.events:
            core = {k: v for k, v in e.items() if k not in ("hash", "prev")}
            if e["prev"] != prev or e["hash"] != self._h(prev, core):
                return {"ok": False, "broken_at": e["id"], "events": len(self.events)}
            prev = e["hash"]
        return {"ok": True, "broken_at": None, "events": len(self.events), "head": prev[:16]}

    def trace(self, trace_id):
        return sorted((e for e in self.events if e["trace"] == trace_id), key=lambda e: e["ts"])

    def traces(self):
        return sorted({e["trace"] for e in self.events})
