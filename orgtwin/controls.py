"""Controls = machine-checkable rules. Historical controls say what *should* have stopped an incident;
candidate controls are what-if fixes tested by replay. Same engine for both."""


def amount(e):
    return e["inputs"].get("amount", e["outputs"].get("amount"))


def ancestors(by_id, e):
    out = []
    while e.get("parent") in by_id:
        e = by_id[e["parent"]]
        out.append(e)
    return out


def check(c, e, by_id):
    """None if the event passes, else {control, event, why, bypass?}."""
    k, p, anc = c["kind"], c.get("params", {}), ancestors(by_id, e)
    v = lambda why, **x: {"control": c["id"], "name": c["name"], "event": e["id"], "why": why, **x}
    human_ok = any(a["action"] == "human_approval" and a["outputs"].get("approved") for a in anc)
    if k == "approval_required" and e["action"] == "transfer" and (amount(e) or 0) > p["over"] and not human_ok:
        skip = next((a["id"] for a in anc if a["action"] == "approval_check" and not a["outputs"].get("required", True)), None)
        return v(f"transfer of {amount(e):,.0f} exceeds {p['over']:,} with no human approval", bypass=skip)
    if k == "agent_cap" and e["action"] == "transfer" and e["actor_type"] == "agent" and (amount(e) or 0) > p["cap"] and not human_ok:
        return v(f"agent transfer of {amount(e):,.0f} exceeds the agent cap {p['cap']:,} without human approval")
    if k == "po_match_required" and e["action"] == "transfer":
        m = next((a for a in anc if a["action"] == "po_match"), None)
        ok = m and m["outputs"].get("matched") and not m["outputs"].get("skipped")
        exempt = m and m["outputs"].get("skipped") and m["outputs"].get("reason") == p.get("exempt_flag")
        if not ok and not exempt:
            return v("no successful PO match before the transfer", bypass=m["id"] if m else None)
    if k == "amount_crosscheck" and e["action"] == "extract":
        src = by_id.get(e["meta"].get("source_event"))
        a = e["outputs"].get(e["meta"].get("output_field"))
        b = src and src["outputs"].get(e["meta"].get("source_field"))
        if a is not None and b and abs(a - b) / abs(b) > p.get("tolerance", 0.005):
            return v(f"extracted {a:,.2f} differs from the source document {b:,.2f}")
    return None
