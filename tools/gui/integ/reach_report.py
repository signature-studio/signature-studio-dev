#!/usr/bin/env python3
"""reach_report.py — 到達 API ログ (GUI-REACH 行) から優先度見直し表を作る (CAB-173 で実到達 API の P 分類を更新する用)。

入力: console / ファイルの `GUI-REACH <order> <name> <calls> <IMPL|STUB> <P0..P3|P->` 行 (e2e は build/e2e/reach.log に保存)。
      host 側の取得: console 行、または wasm export `gui_reach_json(buf, cap)` ({"Name":calls,...} 到達順)。
出力: markdown (stdout)。
  - 到達 STUB: 実装必須 (到達した時点で fail-fast するため P に関わらず最優先)
  - 到達済みだが P2/P3 分類 (= 昇格候補)、FL が import しない名前 (P-)
  - 未到達の P0 (= この実行では使われなかった起動/描画必須 API)
usage: reach_report.py <log|-> [--json]
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "..", "build", "gui_reach_tab.json")


def parse(text):
    rows = []
    for l in text.splitlines():
        m = re.search(r"GUI-REACH (\d+) (\w+) (\d+) (IMPL|STUB) P([0-3-])", l)
        if m: rows.append((int(m.group(1)), m.group(2), int(m.group(3)), m.group(4), m.group(5)))
    if not rows:
        try:
            j = json.loads(text.strip())
            rows = [(i + 1, n, c, "?", "?") for i, (n, c) in enumerate(j.items())]
        except Exception:
            pass
    return rows


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    text = sys.stdin.read() if src == "-" else open(src).read()
    rows = parse(text)
    tab = json.load(open(TAB)) if os.path.exists(TAB) else None
    prio = tab["prio"] if tab else {}
    stub = set(tab["stub"]) if tab else set()
    out = ["# 到達 API レポート", "", "到達 %d 名 (総呼出 %d)。" % (len(rows), sum(r[2] for r in rows)), ""]
    def sec(title, sel, extra=""):
        sub = [r for r in rows if sel(r)]
        out.append("## %s (%d)\n" % (title, len(sub)))
        if sub:
            out.append("| 到達順 | API | 呼出 | shim | P |\n|---|---|---|---|---|")
            for r in sub: out.append("| %d | %s | %d | %s | P%s |" % r)
        else: out.append("なし")
        out.append("")
    sec("到達した fail-fast stub (実装必須)", lambda r: r[3] == "STUB")
    sec("到達したが P2/P3 分類 (昇格候補)", lambda r: r[4] in "23" and r[3] != "STUB")
    sec("到達したが FL の GUI import に無い名前 (P-)", lambda r: r[4] == "-")
    if prio:
        reached = {r[1] for r in rows}
        p0 = sorted(n for n, p in prio.items() if p == 0 and n not in reached)
        out.append("## 未到達の P0 (%d)\n\n%s\n" % (len(p0), ", ".join(p0) if p0 else "なし"))
        p1s = sorted(n for n, p in prio.items() if p == 1 and n in stub and n not in reached)
        out.append("## 未到達かつ未実装の P1 (%d)\n\n%s\n" % (len(p1s), ", ".join(p1s) if p1s else "なし (P1 全実装)"))
    print("\n".join(out))


if __name__ == "__main__":
    main()
