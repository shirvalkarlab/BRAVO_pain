"""Compare two proof files field by field: every leaf value, its path, and how many differ."""
import json, sys, collections
def leaves(o, p=""):
    if isinstance(o, dict):
        for k in sorted(o): yield from leaves(o[k], f"{p}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from leaves(v, f"{p}[{i}]")
    else:
        yield p, o
a, b = (json.load(open(f)) for f in sys.argv[1:3])
assert [r["body"] for r in a] == [r["body"] for r in b]
tot = 0; diff = collections.Counter(); ex = {}
import re
for ra, rb in zip(a, b):
    la, lb = dict(leaves(ra["out"])), dict(leaves(rb["out"]))
    keys = set(la) | set(lb); tot += len(keys)
    for k in keys:
        va, vb = la.get(k, "<absent>"), lb.get(k, "<absent>")
        if va != vb and not (isinstance(va, float) and isinstance(vb, float) and va != va and vb != vb):
            g = ra["kind"] + " " + re.sub(r"\[\d+\]", "[]", k)
            diff[g] += 1; ex.setdefault(g, (la.get(k, "<absent>"), lb.get(k, "<absent>")))
print("fields", tot, "differ", sum(diff.values()))
for g, c in diff.most_common(): print(c, g, "|", str(ex[g][0])[:60], "->", str(ex[g][1])[:60])
