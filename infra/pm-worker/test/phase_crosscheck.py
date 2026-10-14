#!/usr/bin/env python3
"""tools/pm/launch_issues.py の count_open_prs / phase_update を、固定 fixture で実行して結果を JSON で出す。

test/phase.test.ts から呼ばれる。GitHub へは行かず、phase.json は読まず・書かない (書き先は捨て先に差し替える)。
各ケースの prev (直前の review_only) を入れて、ヒステリシスの両側を確かめる。
usage: phase_crosscheck.py <fixture.json>
"""
import importlib.util
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MOD_PATH = os.path.join(HERE, "..", "..", "..", "tools", "pm", "launch_issues.py")


def main():
    spec = importlib.util.spec_from_file_location("launch_issues", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fx = json.load(open(sys.argv[1], encoding="utf-8"))
    mod.now = lambda: datetime.fromisoformat(fx["now"].replace("Z", "+00:00"))
    mod.PHASE = os.devnull

    results = []
    for c in fx["cases"]:
        prev = {"review_only": c["prev"]}
        mod.load_json = lambda p, default, _p=prev: dict(_p)
        open_excl, stuck = mod.count_open_prs(c["pulls"])
        st = mod.phase_update(open_excl)
        results.append({"open_prs_excl_stuck": open_excl, "stuck": stuck, "review_only": st["review_only"]})
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
