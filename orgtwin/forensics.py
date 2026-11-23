"""Incident reconstruction + replay. reconstruct() answers: who started it, what data, which permissions, where did it go wrong,
which decisions/barriers let it through. replay() re-runs a recorded trace with candidate controls to test prevention.
Replay is counterfactual on the RECORDED events: it does not simulate what humans or agents would have done instead."""
from datetime import datetime, timezone
from .controls import amount, ancestors, check


def _t(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def divergences(events):
    by, out = {e["id"]: e for e in events}, []
    for e in events:
        m, src = e["meta"], by.get(e["meta"].get("source_event"))
        if src:
            got, exp = e["outputs"].get(m["output_field"]), src["outputs"].get(m["source_field"])
            if got is not None and exp is not None and got != exp:
                out.append({"event": e["id"], "source_event": src["id"], "got": got, "expected": exp,
                            "why": f"{e['actor']} produced {got:,.2f} but the source document says {exp:,.2f}"})
    return out


def reconstruct(bb, trace_id, controls, candidates, graph, memory):
    ev = bb.trace(trace_id)
    if not ev:
        raise KeyError(trace_id)
    by = {e["id"]: e for e in ev}
    div = divergences(ev)
    viol = [x for e in ev for c in controls if (x := check(c, e, by))]
    skipped = [{"event": e["id"], "what": e["action"], "reason": e["outputs"].get("reason")} for e in ev
               if e["outputs"].get("skipped") or str(e["outputs"].get("reason", "")).startswith("auto_approve")]
    root = None
    if div:
        d = div[0]
        root = {"event": d["event"], "kind": "data_divergence", "why": d["why"], "evidence": [d["source_event"], d["event"]]}
    elif viol:
        v = viol[0]
        root = {"event": v["event"], "kind": "control_violation", "why": v["why"], "evidence": [v["event"]]}
    loss = 0
    for t in (e for e in ev if e["action"] == "transfer"):
        anc = {a["id"] for a in ancestors(by, t)}
        d = next((x for x in div if x["event"] in anc), None)
        if d:
            loss += (amount(t) or 0) - d["expected"]
    alert = next((e for e in ev if e["action"] == "mismatch_alert"), None)
    tr = next((e for e in ev if e["action"] == "transfer"), None)
    nodes = {e["actor"] for e in ev} | {e["resource"] for e in ev}
    rep = {
        "trace": trace_id, "chain": bb.verify(),
        "originator": {"actor": ev[0]["actor"], "type": ev[0]["actor_type"], "event": ev[0]["id"], "at": _t(ev[0]["ts"])},
        "timeline": [{"id": e["id"], "at": _t(e["ts"]), "actor": e["actor"], "type": e["actor_type"], "action": e["action"],
                      "resource": e["resource"], "parent": e["parent"], "permission": e["permission"], "inputs": e["inputs"],
                      "outputs": e["outputs"]} for e in ev],
        "permissions_used": [{"event": e["id"], "actor": e["actor"], "permission": e["permission"]} for e in ev if e["permission"]],
        "divergences": div, "violations": viol, "skipped_barriers": skipped, "root_cause": root,
        "loss": loss, "detection_lag_hours": round((alert["ts"] - tr["ts"]) / 3600, 1) if alert and tr else None,
        "decisions": [{"id": d["id"], "title": d["title"], "date": d["date"], "nodes": sorted(set(d["nodes"]) & nodes)}
                      for d in memory.for_nodes(nodes)] if root else [],
        "blast_radius": [],
    }
    if root:
        re_ = by[root["event"]]
        node = next((n for n in (re_["actor"], re_["resource"]) if n in graph.nodes), None)
        rep["blast_radius"] = graph.impact(node, "degrade")[:5] if node else []
    rep["recommendations"] = rank_candidates(bb, trace_id, candidates) if root else []
    return rep


def replay(bb, trace_id, candidates):
    ev, by, status, first = bb.trace(trace_id), {e["id"]: e for e in bb.trace(trace_id)}, {}, None
    for e in ev:
        if status.get(e["parent"]) in ("blocked", "not_executed"):
            status[e["id"]] = "not_executed"
            continue
        hit = next((x for c in candidates if (x := check(c, e, by))), None)
        status[e["id"]] = "blocked" if hit else "executed"
        first = first or hit
    irreversible = [e for e in ev if e["action"] == "transfer"]
    prevented = bool(first) and all(status[e["id"]] != "executed" for e in irreversible)
    full = divergences(ev)
    loss = sum((amount(t) or 0) - full[0]["expected"] for t in irreversible) if full and irreversible else 0
    return {"controls": [c["id"] for c in candidates], "status": status, "blocked_by": first, "prevented": prevented,
            "loss_avoided": loss if prevented else 0}


def rank_candidates(bb, trace_id, candidates):
    rows = []
    for c in candidates:
        r = replay(bb, trace_id, [c])
        rows.append({"control": c["id"], "name": c["name"], "prevented": r["prevented"],
                     "blocks_at": r["blocked_by"]["event"] if r["blocked_by"] else None, "loss_avoided": r["loss_avoided"]})
    rows.sort(key=lambda r: (not r["prevented"], r["blocks_at"] or "~"))
    n = sum(r["prevented"] for r in rows)
    for r in rows:
        r["independent_barriers"] = n
    return rows
