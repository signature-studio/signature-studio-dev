#!/usr/bin/env python3
"""tools/pm/launch_issues.py の classify を、固定 fixture で実行して rows を JSON で出す。

test/classify.test.ts から呼ばれる。GitHub へは行かず、時刻・状態ファイル・
live blocker・bot 本文は fixture から注入する (launch_issues.py 本体は変更しない)。
usage: classify_crosscheck.py <fixture.json>
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
    fixed_now = datetime.fromisoformat(fx["now"].replace("Z", "+00:00"))
    mod.now = lambda: fixed_now

    files = {
        "launched.json": fx["launched"],
        "relaunch.json": fx["relaunch"],
        "manual_deps.json": fx["manualDeps"],
    }

    def fake_load_json(p, default):
        return files.get(os.path.basename(p), default)

    mod.load_json = fake_load_json
    mod.LAUNCHED = "launched.json"
    mod.RELAUNCH = "relaunch.json"

    for k, v in fx["liveBlockers"].items():
        mod._live_cache[int(k)] = {int(x) for x in v}
    for k, v in fx["fullBotBody"].items():
        mod._full_cache[int(k)] = v

    _, _, _, rows = mod.classify(fx["snapshot"])
    print(json.dumps(rows, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
