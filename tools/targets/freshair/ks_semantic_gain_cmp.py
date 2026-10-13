#!/usr/bin/env python3
"""ks_semantic_gain の SC/KH 出力を突き合わせる (意味同一性の判定)。
   usage: ks_semantic_gain_cmp.py <sc.txt> <kh.txt>
 判定対象 = L 出力・R 出力・self state (0x38 B)。通知 vector は両者で表現が違うため件数のみ一致確認。
 出力: 1 行の JSON (cases / bit_exact / field_mismatch / notify_count_mismatch) と不一致 case の先頭。
"""
import json, sys


def parse(path):
    rows = {}
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p or not p[0].startswith("C"):
                continue
            idx = int(p[0][1:])
            kv = dict(x.split("=") for x in p[1:6])
            n = int(kv["n"])
            # 形式: C<i> n= mode= first= dl= dr= <notify...> <L hex> <R hex> <state hex>
            L, R, S = p[-3], p[-2], p[-1]
            notify = p[6:-3]
            rows[idx] = {"n": n, "kv": kv, "L": L, "R": R, "S": S, "notify": notify}
    return rows


def main():
    sc, kh = parse(sys.argv[1]), parse(sys.argv[2])
    keys = sorted(set(sc) & set(kh))
    mism = {"L": [], "R": [], "S": []}
    notify_bad = []
    exact = 0
    for k in keys:
        a, b = sc[k], kh[k]
        bad = False
        for fld in ("L", "R", "S"):
            if a[fld] != b[fld]:
                mism[fld].append(k)
                bad = True
        # 通知件数: SC は end-begin のバイト数 (要素 4 B)、KH は要素数。件数に揃えて比べる
        na = int(a["notify"][0]) // 4 if a["notify"] else 0
        nb = int(b["notify"][0]) if b["notify"] else 0
        if na != nb:
            notify_bad.append(k)
        if not bad:
            exact += 1
    out = {
        "cases": len(keys),
        "bit_exact_LRS": exact,
        "mismatch_L": len(mism["L"]),
        "mismatch_R": len(mism["R"]),
        "mismatch_S": len(mism["S"]),
        "first_mismatch_cases": {f: v[:5] for f, v in mism.items() if v},
        "notify_count_mismatch": len(notify_bad),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
