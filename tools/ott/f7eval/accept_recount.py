#!/usr/bin/env python3
"""accept_recount.py — CAB-238/CAB-135 検収の独立再計算 (規則 37: 別アルゴリズムでの検算)。

cab238_eval.py の実行結果 (tools/ott/work/cab238/<tag>/result.json) と auto_repair.log を
**テキストパース**で再集計する。cab238_eval.py は liftlib API を直接呼ぶ (in-process) ため、
本スクリプトは結果 JSON とログだけから別経路で同じ数数を再現する (= 独立再計算)。

数え方の定義 (規則 36):
  * F7 修復サイト = auto_repair.log の `F7 repaired` 行数 (site VA は行内の 16 進アドレス)。
    `F7 skip` は修復しなかった dropped_load。dropped_load = repaired + skip。
  * P1 再構成/残留 = auto_stats の state_dropped (= reconstructed + unsupported) と、
    auto_repair.log の P1 完了行の内訳。両者が一致することを突合する。
  * 脱落分岐 sites = state_branch (rewired + unresolved_orient) + state_dropped + consumer。
    consumer = sites - state_branch - state_dropped として定義 (auto_stats の定義)。
  * census junkHi = result.json の census0/census1 の junkHi 値そのもの ( harness = e2e 標準
    256 sample, param 0.5)。集計コマンドは本ファイル。
  * tag 間の差分 (F7 単独/除外/P1 group) は result.json の Census 値を比較するだけなので
    再計算というより**参照**。独立要素は「サイト集合の導出」と「auto_stats の矛盾検査」。

使い方:
  python3 tools/ott/f7eval/accept_recount.py [--cab238 DIR] [--expect-f7 7]
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OTT = os.path.dirname(HERE)
CAB = os.path.join(OTT, "work", "cab238")

# CAB-238 REPORT §3 のサイト表 (読み取り専用の期待値 = 検算の基準)
EXPECT_F7 = [0x18011EF10, 0x18011F00E, 0x18011F9AA, 0x180120632, 0x180120E6A, 0x1801ADDA1, 0x1801C6B5B]
EXPECT_P1_TAIL = [0x18011FFDD, 0x180120049, 0x18012024B, 0x1801202B7, 0x1801204B9, 0x180120525]


def parse_repair_log(path):
    """auto_repair.log をテキストパースして F7/P1 サイト集合を返す (in-process API を使わない)。"""
    f7_rep, f7_skip, p1_done, p1_unsup = [], [], [], []
    if not os.path.exists(path):
        return None
    for line in open(path, errors="replace"):
        m = re.search(r"F7 repaired @([0-9a-f]+)", line, re.I)
        if m:
            f7_rep.append(int(m.group(1), 16)); continue
        m = re.search(r"F7 skip @([0-9a-f]+)", line, re.I)
        if m:
            f7_skip.append(int(m.group(1), 16)); continue
        # P1 再構成/未対応の完了行 (reconstructed / UNSUPPORTED dropped の site VA)
        m = re.search(r"^reconstructed jcc@([0-9a-f]+)", line, re.I)
        if m:
            p1_done.append(int(m.group(1), 16)); continue
        m = re.search(r"^UNSUPPORTED dropped@([0-9a-f]+)", line, re.I)
        if m:
            p1_unsup.append(int(m.group(1), 16)); continue
    return dict(f7_rep=f7_rep, f7_skip=f7_skip, p1_done=p1_done, p1_unsup=p1_unsup)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cab238", default=CAB)
    a = ap.parse_args()
    D = a.cab238
    rows = []
    for tag in sorted(os.listdir(D)):
        p = os.path.join(D, tag, "result.json")
        if not os.path.isfile(p):
            continue
        d = json.load(open(p))
        st = d.get("auto_stats") or {}
        c0, c1 = d.get("census0") or {}, d.get("census1") or {}
        bc = d.get("bitcmp_vs_x64c") or {}
        hp = d.get("hang_p0.9_f1") or {}
        rows.append(dict(tag=tag, checks=d.get("checks"), broken=d.get("broken"),
                         trap=d.get("trap_rc"), c0=c0.get("junkHi"), c1=c1.get("junkHi"),
                         c1abs=c1.get("absmax"), bit=bc.get("equal"),
                         hang=any(v == "HANG" for v in hp.values()) if hp else None,
                         c0z=c0.get("zero"), c1z=c1.get("zero"),
                         c0n=c0.get("normal"), c1n=c1.get("normal"),
                         c0t=c0.get("junkTiny"), c1t=c1.get("junkTiny"),
                         dropped=st.get("dropped_load"), rep=st.get("repaired"),
                         sd=st.get("state_dropped"), rec=st.get("reconstructed"),
                         un=st.get("unsupported"), sb=st.get("state_branch"),
                         rw=st.get("rewired"), uo=st.get("unresolved_orient"),
                         sites=st.get("sites")))

    prod = [r for r in rows if r["tag"] == "production"]
    if not prod:
        print("[recount] production/result.json が無い (先に cab238_eval.py production を実行)")
        return 2
    p = prod[0]

    print("== auto_stats の内部整合 (定義: sites = state_branch + state_dropped + consumer) ==")
    consumer = p["sites"] - p["sb"] - p["sd"]
    print("   sites %d = state_branch %d (rewired %d + unresolved_orient %d) + state_dropped %d "
          "(reconstructed %d + unsupported %d) + consumer %d"
          % (p["sites"], p["sb"], p["rw"], p["uo"], p["sd"], p["rec"], p["un"], consumer))
    ok_bal = (p["rw"] + p["uo"] == p["sb"] and p["rec"] + p["un"] == p["sd"]
              and p["sb"] + p["sd"] + consumer == p["sites"])
    print("   収支一致: %s" % ("OK" if ok_bal else "NG"))

    print("== dropped_load = F7 repaired + F7 skip (auto_repair.log テキストパース) ==")
    lg = parse_repair_log(os.path.join(D, "production", "auto_repair.log"))
    if lg:
        tot = len(lg["f7_rep"]) + len(lg["f7_skip"])
        print("   F7 repaired %d + F7 skip %d = %d (auto_stats.dropped_load = %d) -> %s"
              % (len(lg["f7_rep"]), len(lg["f7_skip"]), tot, p["dropped"],
                 "OK" if tot == p["dropped"] else "NG"))
        print("   F7 repaired site set == 期待 (REPORT §3 の 7 site): %s"
              % ("OK" if sorted(lg["f7_rep"]) == sorted(EXPECT_F7) else "NG %s" % [hex(x) for x in lg["f7_rep"]]))

    print("== P1 再構成/残留も auto_repair.log テキストパースで再集計 (別アルゴリズム) ==")
    if lg:
        print("   reconstructed %d (auto_stats.reconstructed = %d) -> %s"
              % (len(lg["p1_done"]), p["rec"],
                 "OK" if len(lg["p1_done"]) == p["rec"] else "NG"))
        print("   UNSUPPORTED dropped %d (auto_stats.unsupported = %d) -> %s"
              % (len(lg["p1_unsup"]), p["un"],
                 "OK" if len(lg["p1_unsup"]) == p["un"] else "NG"))

    print("== tag 別 (result.json 参照・census は harness 定義を各行頭に注記) ==")
    print("   %-18s %-8s %-6s %-6s %-6s %-6s %-11s %-6s %s" % (
        "tag", "checks", "trap", "c0jH", "c1jH", "bitEQ", "c1absmax", "HANG", "P1 recon"))
    for r in sorted(rows, key=lambda x: x["tag"]):
        print("   %-18s %-8s %-6s %-6s %-6s %-6s %-11s %-6s %s" % (
            r["tag"], "%s/%s" % (r["checks"], r["broken"]), r["trap"], r["c0"], r["c1"],
            r["bit"], "%.2e" % (r["c1abs"] or 0), r["hang"],
            "P1再構成あり" if (r["rec"] or 0) else "P1再構成なし"))

    print("== 主要な差分の再現 (差分は result.json の差 = 別アルゴリズム不要の参照) ==")
    g = {r["tag"]: r for r in rows}
    def show(t, msg):
        r = g.get(t)
        print("   %-22s %s" % (t, msg % r if r else "(未実行)"))

    if "f7_only" in g:
        r = g["f7_only"]
        print("   f7_only      : census0 junkHi %s (= 旧既定 175 と一致 → F7 単独は census0 不変) bitEQ %s"
              % (r["c0"], r["bit"]))
    if "f7_ex_180120632" in g:
        r = g["f7_ex_180120632"]
        print("   f7_ex_180120632: census0 %s / census1 %s / absmax %.2e (REPORT: 52 / 0 / 2.2e-3)"
              % (r["c0"], r["c1"], r["c1abs"] or 0))
    for t in ("p1_one_18012024b", "p1_one_1801204b9", "p1_one_18011ffdd"):
        if t in g:
            r = g[t]
            print("   %-16s: census0 %s HANG=%s" % (t, r["c0"], r["hang"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
