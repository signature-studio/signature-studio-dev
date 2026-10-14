#!/usr/bin/env python3
"""tools/pm/pm_needs.py の KEY を直接読み、固定 fixture の各本文で『一致した行の数』を JSON で出す。

test/needs.test.ts から呼ばれる。GitHub へは行かない (pm_needs.py の main は呼ばない)。
usage: needs_crosscheck.py <fixture.json>
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.join(HERE, "..", "..", "..", "tools", "pm", "pm_needs.py")


def main():
    spec = importlib.util.spec_from_file_location("pm_needs", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fx = json.load(open(sys.argv[1], encoding="utf-8"))
    out = []
    for c in fx["cases"]:
        hits = [l.strip() for l in c["body"].splitlines() if mod.KEY.search(l)]
        out.append({"hits": len(hits), "matches": len(hits) > 0})
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
