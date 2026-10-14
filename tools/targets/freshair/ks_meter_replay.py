#!/usr/bin/env python3
"""Gain の meter (m1/m2) 更新式を、ks_semantic_gain の出力から照合する。
   usage: ks_meter_replay.py <sc.txt> <kh.txt> <sc_m.txt> <kh_m.txt>
  sc.txt/kh.txt: ks_semantic_gain の stdout (L/R 出力・実行後 state を含む)。
  sc_m.txt/kh_m.txt: METER_DUMP=1 の stderr (M<i> m1 c1 m2 c2 = 実行前の値)。
  meter 漸化式 m = (s*s - m)*c + m を float32 で、出力 L (m1・c1) と R (m2・c2) の各サンプルに順に適用し、
  再計算値が実行後 state (m1 = 0x88 相当、m2 = 0x98 相当) とビット一致するかを SC/KH それぞれで見る。
  出力: 1 行の JSON。
"""
import json, struct, sys

import numpy as np

F32 = np.float32


def fl(h):
    return np.array([struct.unpack("<f", bytes.fromhex(h[i:i + 8]))[0] for i in range(0, len(h), 8)], dtype=F32)


def load(path):
    rows = {}
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t or not t[0].startswith("C") or t[1] == "n=0":
                continue
            rows[int(t[0][1:])] = {"L": fl(t[-3]), "R": fl(t[-2]), "S": fl(t[-1])}
    return rows


def load_pre(path):
    pre = {}
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t or not t[0].startswith("M"):
                continue
            pre[int(t[0][1:])] = [F32(float(x)) for x in t[1:5]]
    return pre


def recalc(row, pre):
    m1, c1, m2, c2 = pre
    for s in row["L"]:
        m1 = (s * s - m1) * c1 + m1
    for s in row["R"]:
        m2 = (s * s - m2) * c2 + m2
    return m1, m2


def replay(rows, pre):
    keys = [k for k in sorted(rows) if k in pre]
    ok, bad = [], []
    for k in keys:
        m1, m2 = recalc(rows[k], pre[k])
        same = m1.tobytes() == rows[k]["S"][9].tobytes() and m2.tobytes() == rows[k]["S"][13].tobytes()
        (ok if same else bad).append(k)
    return {"n": len(keys), "ok": len(ok), "bad_cases": bad[:20]}


def main():
    sc, kh = load(sys.argv[1]), load(sys.argv[2])
    keys = sorted(set(sc) & set(kh))
    m1_diff = [k for k in keys if float(sc[k]["S"][9]) != float(kh[k]["S"][9])]
    m2_diff = [k for k in keys if float(sc[k]["S"][13]) != float(kh[k]["S"][13])]
    cur_same = [k for k in keys if float(sc[k]["S"][4]) == float(kh[k]["S"][4])]
    l_same = [k for k in keys if np.array_equal(sc[k]["L"], kh[k]["L"])]
    r_same = [k for k in keys if np.array_equal(sc[k]["R"], kh[k]["R"])]
    m_diff_cur_eq = [k for k in set(m1_diff) | set(m2_diff) if k in cur_same]
    rc_sc = replay(sc, load_pre(sys.argv[3]))
    rc_kh = replay(kh, load_pre(sys.argv[4]))
    out = {
        "cases_n_gt0": len(keys),
        "m1_mismatch": len(m1_diff),
        "m2_mismatch": len(m2_diff),
        "cur_equal": len(cur_same),
        "meter_mismatch_with_cur_equal": len(m_diff_cur_eq),
        "m1_mismatch_with_L_identical": len([k for k in m1_diff if k in l_same]),
        "m2_mismatch_with_R_identical": len([k for k in m2_diff if k in r_same]),
        "L_identical": len(l_same),
        "R_identical": len(r_same),
        "recalc_SC": rc_sc,
        "recalc_KH": rc_kh,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
