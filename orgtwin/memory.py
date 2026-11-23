"""Decision & policy memory: BM25 retrieval over past decisions, each linked to graph nodes and to the assumptions it relied on."""
import math, re
from collections import Counter

_AR = str.maketrans("أإآى", "ااای")


def toks(s):
    s = re.sub(r"[\u064B-\u0652\u0640]", "", s.lower()).translate(_AR)
    return re.findall(r"\w+", s)


class Memory:
    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}
        self.tf = {i: Counter(toks(d["title"] + " " + d["title"] + " " + d["text"])) for i, d in self.docs.items()}
        self.len = {i: sum(c.values()) for i, c in self.tf.items()}
        self.avg = sum(self.len.values()) / max(1, len(self.len))
        self.df = Counter(t for c in self.tf.values() for t in c)

    def search(self, q, k=3, boost_nodes=()):
        N, out = len(self.docs), []
        for i, d in self.docs.items():
            s = 0.0
            for t in set(toks(q)):
                f = self.tf[i].get(t, 0)
                if f:
                    idf = math.log(1 + (N - self.df[t] + .5) / (self.df[t] + .5))
                    s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.len[i] / self.avg))
            if s > 0 and set(d["nodes"]) & set(boost_nodes):
                s += 1.0
            if s > 0:
                out.append({**d, "score": round(s, 3)})
        return sorted(out, key=lambda x: -x["score"])[:k]

    def for_nodes(self, nodes):
        nodes = set(nodes)
        return [d for d in self.docs.values() if nodes & set(d["nodes"])]

    def assumptions_hit(self, node):
        """Past decisions that explicitly relied on `node` staying as it is."""
        return [d for d in self.docs.values() if node in d.get("assumes", [])]
