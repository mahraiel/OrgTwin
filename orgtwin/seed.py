"""Demo organisation: finance operations. One bad incident (INC-2026-001: an AI agent overpays an invoice 10x) and one clean run."""
from datetime import datetime, timezone
from .blackbox import BlackBox
from .graph import Graph
from .memory import Memory

T0 = datetime(2026, 11, 19, 9, 12, 3, tzinfo=timezone.utc).timestamp()


def graph():
    g = Graph()
    for i, t, n, c in [("sys:ocr", "system", "Invoice OCR service", .7), ("sys:erp", "system", "ERP", .8), ("sys:bank", "system", "Bank API", .9),
                       ("agent:paybot", "agent", "PayBot payment agent", .8), ("proc:vendor_pay", "process", "Vendor payment", .9),
                       ("proc:ap", "process", "Accounts payable", .8), ("proc:recon", "process", "Bank reconciliation", .7),
                       ("proc:treasury", "process", "Treasury cash management", .9), ("proc:close", "process", "Monthly close reporting", .8),
                       ("data:invoices", "data", "Invoice documents", .6), ("data:po", "data", "Purchase orders", .6),
                       ("data:vendors", "data", "Vendor master data", .6), ("pol:approval", "policy", "Payment approval policy", .9),
                       ("pol:po_match", "policy", "PO matching policy", .7), ("human:ap_clerk", "human", "AP clerk", .3)]:
        g.add_node(i, t, n, c)
    for s, d, w, why in [("sys:ocr", "data:invoices", .9, "reads invoices"), ("agent:paybot", "sys:ocr", .9, "uses extracted amounts"),
                         ("agent:paybot", "sys:bank", .95, "executes transfers"), ("agent:paybot", "data:po", .6, "matches POs"),
                         ("agent:paybot", "data:vendors", .5, "trusted-vendor flag"), ("proc:vendor_pay", "agent:paybot", .9, "runs the payments"),
                         ("proc:vendor_pay", "pol:approval", .7, "governed by"), ("proc:vendor_pay", "pol:po_match", .6, "governed by"),
                         ("proc:ap", "proc:vendor_pay", .8, "AP closes via payments"), ("proc:ap", "sys:erp", .8, "posts to ERP"),
                         ("proc:recon", "sys:bank", .8, "reads bank statements"), ("proc:recon", "proc:vendor_pay", .6, "matches payments"),
                         ("proc:treasury", "proc:vendor_pay", .7, "forecasts cash from payments"),
                         ("proc:close", "proc:recon", .7, "needs reconciled books"), ("proc:close", "proc:treasury", .6, "needs cash position")]:
        g.add_dep(s, d, w, why)
    return g


DOCS = [
    {"id": "DEC-009", "date": "2026-03-04", "kind": "decision", "title": "Skip PO matching for trusted vendors",
     "text": "To speed up payments, PayBot skips purchase order matching when the vendor is flagged trusted in vendor master data.",
     "nodes": ["pol:po_match", "agent:paybot", "data:vendors"], "assumes": ["pol:approval", "sys:ocr"]},
    {"id": "DEC-014", "date": "2026-09-22", "kind": "decision", "title": "Upgrade invoice OCR to locale-aware parser v3",
     "text": "OCR v3 reads European and Egyptian number formats. Rolled out without a regression set for amounts.",
     "nodes": ["sys:ocr", "data:invoices"], "assumes": []},
    {"id": "DEC-017", "date": "2026-01-15", "kind": "policy", "title": "Payments above EGP 100,000 need human approval",
     "text": "Any vendor payment above EGP 100,000 requires approval from a human finance approver before the transfer.",
     "nodes": ["pol:approval", "proc:vendor_pay"], "assumes": []},
    {"id": "CHG-022", "date": "2026-06-30", "kind": "change", "title": "Grant PayBot treasury transfer permission up to EGP 200,000",
     "text": "PayBot gets the treasury.transfer permission with a per-payment limit of EGP 200,000 to reduce clerk workload.",
     "nodes": ["agent:paybot", "sys:bank"], "assumes": ["pol:approval"]},
    {"id": "POL-031", "date": "2025-11-01", "kind": "policy", "title": "Daily bank reconciliation",
     "text": "Bank statements are reconciled against ERP payments every business day; mismatches are escalated to treasury.",
     "nodes": ["proc:recon", "sys:bank"], "assumes": []},
]
CONTROLS = [
    {"id": "CTL-1", "kind": "approval_required", "name": "Payments over EGP 100,000 need human approval", "params": {"over": 100000}},
    {"id": "CTL-2", "kind": "po_match_required", "name": "PO match before transfer (trusted vendors exempt, DEC-009)", "params": {"exempt_flag": "trusted_vendor"}},
]
CANDIDATES = [
    {"id": "K1", "kind": "amount_crosscheck", "name": "Cross-check extracted amount against the source document", "params": {"tolerance": 0.005}},
    {"id": "K2", "kind": "po_match_required", "name": "PO matching with no trusted-vendor exemption", "params": {"exempt_flag": None}},
    {"id": "K3", "kind": "agent_cap", "name": "Agents cannot transfer above EGP 50,000 without a human", "params": {"cap": 50000}},
    {"id": "K4", "kind": "approval_required", "name": "Enforce the EGP 100,000 approval gate in the executor (no auto-approve)", "params": {"over": 100000}},
]


def _flow(bb, trace, base, true_total, parsed_total, trusted):
    p, ok = f"{trace}-", true_total == parsed_total
    bb.record(id=p + "E1", trace=trace, ts=base, actor="human:ap_clerk", actor_type="human", action="upload_invoice", resource="data:invoices",
              outputs={"doc": "INV-8841" if not ok else "INV-8702", "total": true_total, "total_text": f"{true_total:,.2f}", "currency": "EGP"})
    bb.record(id=p + "E2", trace=trace, ts=base + 4, actor="sys:ocr", actor_type="system", action="extract", resource="data:invoices", parent=p + "E1",
              inputs={"parser": "v3-locale"}, outputs={"amount": parsed_total},
              meta={"source_event": p + "E1", "source_field": "total", "output_field": "amount"})
    bb.record(id=p + "E3", trace=trace, ts=base + 9, actor="agent:paybot", actor_type="agent", action="vendor_lookup", resource="data:vendors", parent=p + "E2",
              inputs={"vendor": "Delta Supplies"}, outputs={"trusted_vendor": trusted})
    bb.record(id=p + "E4", trace=trace, ts=base + 11, actor="agent:paybot", actor_type="agent", action="po_match", resource="data:po", parent=p + "E3",
              inputs={"amount": parsed_total}, outputs={"skipped": True, "reason": "trusted_vendor"} if trusted else {"matched": True, "skipped": False})
    bb.record(id=p + "E5", trace=trace, ts=base + 12, actor="agent:paybot", actor_type="agent", action="approval_check", resource="pol:approval", parent=p + "E4",
              inputs={"amount": parsed_total}, outputs={"required": parsed_total > 100000 and not trusted, "reason": "auto_approve_trusted_vendor" if trusted else "threshold"})
    bb.record(id=p + "E6", trace=trace, ts=base + 15, actor="agent:paybot", actor_type="agent", action="transfer", resource="sys:bank", parent=p + "E5",
              permission="treasury.transfer<=200000", inputs={"amount": parsed_total}, outputs={"bank_ref": "BNK-" + trace[-3:] + "7731", "settled": True},
              meta={"irreversible": True})
    bb.record(id=p + "E7", trace=trace, ts=base + 40, actor="sys:bank", actor_type="system", action="settle", resource="proc:recon", parent=p + "E6",
              outputs={"settled_amount": parsed_total})
    if not ok:
        bb.record(id=p + "E8", trace=trace, ts=base + 2 * 86400 + 3600, actor="proc:recon", actor_type="system", action="mismatch_alert", resource="proc:treasury",
                  parent=p + "E7", outputs={"delta": parsed_total - true_total})


def black_box():
    bb = BlackBox()
    _flow(bb, "INC-2026-001", T0, 12500.00, 125000.00, True)
    _flow(bb, "TRX-2026-114", T0 + 3 * 86400, 8400.00, 8400.00, False)
    return bb


def build():
    from .twin import OrgTwin
    return OrgTwin(graph(), Memory(DOCS), black_box(), CONTROLS, CANDIDATES)
