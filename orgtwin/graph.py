"""Organisation graph: nodes (systems, agents, processes, data, policies, humans) and weighted dependencies.
impact() walks the *reverse* edges: who depends on the thing I change, and how exposed are they?"""
import re
from collections import deque

SEVERITY = {"remove": 1.0, "degrade": 0.6, "relax": 0.5, "delay": 0.3}


class Graph:
    def __init__(self):
        self.nodes, self.dep, self.rdep = {}, {}, {}

    def add_node(self, id, type, name, crit=0.5):
        self.nodes[id] = {"id": id, "type": type, "name": name, "criticality": crit}

    def add_dep(self, src, dst, weight, why=""):
        """src depends on dst with strength weight (0..1)."""
        assert src in self.nodes and dst in self.nodes, (src, dst)
        self.dep.setdefault(src, []).append((dst, weight, why))
        self.rdep.setdefault(dst, []).append((src, weight, why))

    def impact(self, node, change="degrade", min_risk=0.05):
        if node not in self.nodes:
            raise KeyError(f"unknown node {node}")
        if change not in SEVERITY:
            raise ValueError(f"change must be one of {sorted(SEVERITY)}")
        best, q = {}, deque([(node, SEVERITY[change], [node])])
        while q:
            n, risk, path = q.popleft()
            for src, w, why in self.rdep.get(n, []):
                r = risk * w
                if r < min_risk or src in path:
                    continue
                if r > best.get(src, {}).get("risk", 0):
                    best[src] = {"id": src, "risk": round(r, 3), "path": path + [src], "why": why}
                    q.append((src, r, path + [src]))
        for b in best.values():
            nd = self.nodes[b["id"]]
            b.update(name=nd["name"], type=nd["type"], exposure=round(b["risk"] * (0.5 + nd["criticality"]), 3))
        return sorted(best.values(), key=lambda x: -x["exposure"])

    def to_json(self):
        edges = [{"from": s, "to": d, "weight": w} for s, L in self.dep.items() for d, w, _ in L]
        return {"nodes": list(self.nodes.values()), "edges": edges}

    def find(self, text):
        """Best node for a free-text mention (token overlap on name/id)."""
        toks = set(re.findall(r"\w+", text.lower()))
        score = lambda n: len(toks & set(re.findall(r"\w+", (n["name"] + " " + n["id"].replace(":", " ")).lower())))
        best = max(self.nodes.values(), key=score)
        return best["id"] if score(best) else None
