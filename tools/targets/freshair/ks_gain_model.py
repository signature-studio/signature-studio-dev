"""Gain の丸め形だけを差し替えたモデルで、SC/KH の native 出力 (L・R・state 0x38 B) を再現できるかを見る (#52 / #1264 受入 2)。

   usage: ks_gain_model.py <sc.txt> <kh.txt> <sc_in.txt> <kh_in.txt>

   sc.txt/kh.txt: ks_semantic_gain の stdout (native 実行結果)。
   sc_in.txt/kh_in.txt: IN_DUMP=1 の stderr (X<i> = 実行前 state 0x38 B・入力 L・入力 R, hex)。

   モデル (float32 を各演算で丸める。式は ks_cur_trace.py と同じ機械語読み):
     ramp の丸め形 form:
       SC: t = pos*coef; cur = (1-t)*A + t*B
       KH: t = pos*inc;  cur = a + (b-a)*t
     係数は両側で bit 一致する入力 (inc=coef, a=A, b=B) を使う。pos は各 case 先頭で 0 から +1 する (ks_cur_trace と同じ)。
     L = inL*cur, R = inR*cur。m1 は L に c1 を、m2 は R に c2 を順に適用 (m = (s*s-m)*c+m)。
   検証: SC 形 × SC 入力 → SC native、KH 形 × KH 入力 → KH native (モデルの妥当性)。
   反実仮想: KH 形 × SC 入力 → KH native (丸め形だけが差なら一致する)。
   負例: SC 形 × SC 入力 → KH native (丸め形を変えなければ不一致が残ることを示す)。
"""
import json
import struct
import sys

import numpy as np

f32 = np.float32


def fl(h):
    return np.frombuffer(bytes.fromhex(h), dtype="<f4").copy()


def parse_native(path):
    rows = {}
    for line in open(path, encoding="ascii"):
        t = line.split()
        if not t or not t[0].startswith("C"):
            continue
        idx = int(t[0][1:])
        n = int(t[1][2:])
        L = fl(t[8]) if t[8] != "-" else np.zeros(0, f32)
        R = fl(t[9]) if t[9] != "-" else np.zeros(0, f32)
        rows[idx] = {"n": n, "first": int(t[3][6:]), "L": L, "R": R, "S": bytes.fromhex(t[10])}
    return rows


def parse_pre(path):
    rows = {}
    for line in open(path, encoding="ascii"):
        t = line.split()
        if not t or not t[0].startswith("X"):
            continue
        idx = int(t[0][1:])
        st = bytes.fromhex(t[1])
        lh = t[2] if len(t) > 2 else ""
        rh = t[3] if len(t) > 3 else ""
        rows[idx] = {"S": st, "L": fl(lh) if lh else np.zeros(0, f32), "R": fl(rh) if rh else np.zeros(0, f32)}
    return rows


def sf(st, off):
    return f32(struct.unpack("<f", st[off:off + 4])[0])


def ramp(form, n, p0, inc, a, b, cur0, first):
    """first=0 は ramp (pos から +1 ずつ)。first=1 は cur0 を一定で使う (native の first=1 経路と一致するか検証)。"""
    out = np.empty(n, f32)
    if first:
        out[:] = cur0
        return out
    pos = f32(0)
    one = f32(1.0)
    for k in range(n):
        pos = f32(pos + one)
        if form == "sc":
            t = f32(pos * inc)
            out[k] = f32(f32(f32(one - t) * a) + f32(t * b))
        else:
            t = f32(pos * inc)
            out[k] = f32(a + f32(f32(b - a) * t))
    return out


def meter(m, c, xs):
    for s in xs:
        m = f32(f32(f32(s * s - m) * c) + m)
    return m


def model(form, pre, end):
    """pre: 実行前 (入力 L/R・meter 初期値・first)。end: 端点の源となる native の実行後 state (coef/A/B/cur)。"""
    st = pre["S"]
    first = st[20]
    c1, m1 = sf(st, 32), sf(st, 36)
    c2, m2 = sf(st, 48), sf(st, 52)
    coef, A, B, curp = sf(end, 4), sf(end, 8), sf(end, 12), sf(end, 16)
    n = len(pre["L"])
    if first:
        cur = np.full(n, curp, dtype=f32)
    else:
        cur = ramp(form, n, f32(0), coef, A, B, curp, 0)
    L = np.array([f32(pre["L"][i] * cur[i]) for i in range(n)], dtype=f32)
    R = np.array([f32(pre["R"][i] * cur[i]) for i in range(n)], dtype=f32)
    return {"cur": cur, "L": L, "R": R, "m1": meter(m1, c1, L), "m2": meter(m2, c2, R)}


def compare(form, pre_rows, end_rows, nat_rows):
    keys = sorted(k for k in pre_rows if nat_rows[k]["n"] > 0)
    res = {"n": len(keys), "L_eq": 0, "R_eq": 0, "m1_eq": 0, "m2_eq": 0, "LRS_eq": 0, "bad": []}
    for k in keys:
        nat = nat_rows[k]
        m = model(form, pre_rows[k], end_rows[k]["S"])
        eqL = np.array_equal(m["L"].view(np.uint32), nat["L"].view(np.uint32))
        eqR = np.array_equal(m["R"].view(np.uint32), nat["R"].view(np.uint32))
        eqm1 = m["m1"].tobytes() == nat["S"][36:40]
        eqm2 = m["m2"].tobytes() == nat["S"][52:56]
        res["L_eq"] += eqL
        res["R_eq"] += eqR
        res["m1_eq"] += eqm1
        res["m2_eq"] += eqm2
        if eqL and eqR and eqm1 and eqm2:
            res["LRS_eq"] += 1
        else:
            res["bad"].append(k)
    res["bad"] = res["bad"][:20]
    return res


def full_state(form, pre_rows, end_rows, nat_rows):
    """LRS 全体 (L・R・実行後 state 0x38 B) を 200 case 全てで比べる。state は端点側の実行後 state に、
    モデルの終端 cur・m1・m2 を入れたものを使う (n=0 は L/R・cur・m を変えない)。"""
    res = {"n": 0, "LRS_eq": 0, "bad": []}
    for k in sorted(pre_rows):
        nat = nat_rows[k]
        res["n"] += 1
        st = bytearray(end_rows[k]["S"])
        if nat["n"] > 0:
            m = model(form, pre_rows[k], end_rows[k]["S"])
            st[16:20] = m["cur"][-1].tobytes()
            st[36:40] = m["m1"].tobytes()
            st[52:56] = m["m2"].tobytes()
            ok = (np.array_equal(m["L"].view(np.uint32), nat["L"].view(np.uint32))
                  and np.array_equal(m["R"].view(np.uint32), nat["R"].view(np.uint32)))
        else:
            ok = True
        ok = ok and bytes(st) == nat["S"]
        if ok:
            res["LRS_eq"] += 1
        else:
            res["bad"].append(k)
    res["bad"] = res["bad"][:20]
    return res


def native_nonform_fields(sc_nat, kh_nat):
    """SC と KH の実行後 state を、ramp 形で決まらない領域 (cur・m1・m2 の 3 箇所以外) で比べる。"""
    eq = 0
    bad = []
    for k in sorted(sc_nat):
        a, b = sc_nat[k]["S"], kh_nat[k]["S"]
        diff = [i for i in range(0x38) if a[i] != b[i] and not (16 <= i < 20 or 36 <= i < 40 or 52 <= i < 56)]
        if not diff:
            eq += 1
        else:
            bad.append(k)
    return {"n": len(sc_nat), "equal": eq, "bad": bad[:20]}


def main():
    sc_nat, kh_nat = parse_native(sys.argv[1]), parse_native(sys.argv[2])
    sc_pre, kh_pre = parse_pre(sys.argv[3]), parse_pre(sys.argv[4])
    same_in = 0
    for k in sc_pre:
        s, h = sc_pre[k]["S"], kh_pre[k]["S"]
        if s[4:16] == h[4:16] and sc_pre[k]["L"].tobytes() == kh_pre[k]["L"].tobytes() and sc_pre[k]["R"].tobytes() == kh_pre[k]["R"].tobytes():
            same_in += 1
    out = {
        "input_same_sc_kh_cases": same_in,
        "validate_sc_form_on_sc_inputs_vs_sc_native": compare("sc", sc_pre, sc_nat, sc_nat),
        "validate_kh_form_on_kh_inputs_vs_kh_native": compare("kh", kh_pre, kh_nat, kh_nat),
        "counterfactual_kh_form_on_sc_inputs_vs_kh_native": compare("kh", sc_pre, sc_nat, kh_nat),
        "counterfactual_sc_form_on_kh_inputs_vs_sc_native": compare("sc", kh_pre, kh_nat, sc_nat),
        "full_state_validate_sc": full_state("sc", sc_pre, sc_nat, sc_nat),
        "full_state_validate_kh": full_state("kh", kh_pre, kh_nat, kh_nat),
        "full_state_counterfactual_kh_form_on_sc_inputs": full_state("kh", sc_pre, sc_nat, kh_nat),
        "nonform_state_fields_sc_vs_kh": native_nonform_fields(sc_nat, kh_nat),
        "negative_control_sc_form_on_sc_inputs_vs_kh_native": compare("sc", sc_pre, sc_nat, kh_nat),
        "negative_control_full_state_sc_form_on_sc_inputs_vs_kh_native": full_state("sc", sc_pre, sc_nat, kh_nat),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
