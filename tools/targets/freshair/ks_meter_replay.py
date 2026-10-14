#!/usr/bin/env python3
"""Gain の meter (m1/m2) 更新式を、ks_semantic_gain の出力 (L/R 出力・state) から照合する。
   usage: ks_meter_replay.py <sc.txt> <kh.txt>
 meter 漸化式 m = (s*s - m)*c + m を float32 で L/R に適用し、各 case の state (0x88 = m1, 0x98 = m2) と一致するかを見る。
 出力: 1 行の JSON (meter 不一致の件数と、cur 一致 case との内訳)。
 入力 sc.txt/kh.txt は ks_semantic_gain.sh の出力 (L/R/state を含む)。
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


def main():
    sc, kh = load(sys.argv[1]), load(sys.argv[2])
    keys = sorted(set(sc) & set(kh))
    m1_diff = [k for k in keys if float(sc[k]["S"][9]) != float(kh[k]["S"][9])]
    m2_diff = [k for k in keys if float(sc[k]["S"][13]) != float(kh[k]["S"][13])]
    cur_same = [k for k in keys if float(sc[k]["S"][4]) == float(kh[k]["S"][4])]
    l_same = [k for k in keys if np.array_equal(sc[k]["L"], kh[k]["L"])]
    r_same = [k for k in keys if np.array_equal(sc[k]["R"], kh[k]["R"])]
    m_diff_cur_eq = [k for k in set(m1_diff) | set(m2_diff) if k in cur_same]
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
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
