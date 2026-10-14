"""Gain ramp の逐次 cur を SC/KH で照合し、L 差の起点サンプルを特定する (#1617 / FA-23)。

   usage: ks_cur_trace.py <default_sc.txt> <default_kh.txt> <probe_sc.txt> <probe_kh.txt> <probe_sc.err> <probe_kh.err>

   default_*.txt: ks_semantic_gain の既定実行 (stdout)。L 差の case を取る。
   probe_*.txt:   CUR_PROBE=1 の stdout。L 出力 = 逐次 cur (入力 L は 1.0)。
   probe_*.err:   I<idx> (入力 L の hex)・S<idx>/K<idx> (ramp の係数・端点・pos)。

   式 (機械語から読んだ形。float32 の各演算を丸める):
     SC: pos = pos + 1; t = pos * coef; cur = (1 - t) * A + t * B      (A = +0xa4, B = +0xa8, coef = +0xa0)
     KH: pos = pos + 1; t = pos * inc;  cur = a + (b - a) * t          (a = +0x6c, b = +0x70, inc = +0x68)
   pos は両側とも case 開始時 0 (SC は毎回 0 に初期化、KH は first=0 でも 0x64 を 0 にする)。
"""
import json
import sys

import numpy as np

f32 = np.float32


def parse_stdout(path):
    rows = {}
    for line in open(path, encoding="ascii"):
        tok = line.split()
        if not tok or not tok[0].startswith("C"):
            continue
        idx = int(tok[0][1:])
        n = int(tok[1][2:])
        first = int(tok[3][6:])
        assert len(tok) == 11, (path, idx, len(tok))
        notify = tok[6]
        L = bytes.fromhex(tok[8]) if tok[8] != "-" else b""
        R = bytes.fromhex(tok[9]) if tok[9] != "-" else b""
        rows[idx] = {"n": n, "first": first, "notify": notify,
                     "L": np.frombuffer(L, dtype="<f4").copy(),
                     "R": np.frombuffer(R, dtype="<f4").copy(),
                     "state": bytes.fromhex(tok[10])}
    return rows


def parse_err(path):
    rows = {}
    for line in open(path, encoding="ascii"):
        tok = line.split()
        if not tok:
            continue
        kind, idx = tok[0][0], int(tok[0][1:])
        rows.setdefault(idx, {})
        if kind == "I":
            rows[idx]["I"] = bytes.fromhex(tok[1]) if len(tok) > 1 else b""
        else:
            for kv in tok[1:]:
                k, v = kv.split("=")
                rows[idx][k] = int(v, 16)
            rows[idx]["kind"] = kind
    return rows


def f(u):
    return np.array([u], dtype="<u4").view(f32)[0]


def ramp_sc(n, coef, A, B):
    out = np.empty(n, f32)
    pos = f32(0)
    one = f32(1.0)
    for k in range(n):
        pos = f32(pos + one)
        t = f32(pos * coef)
        out[k] = f32(f32(f32(one - t) * A) + f32(t * B))
    return out


def ramp_kh(n, inc, a, b):
    out = np.empty(n, f32)
    pos = f32(0)
    one = f32(1.0)
    for k in range(n):
        pos = f32(pos + one)
        t = f32(pos * inc)
        out[k] = f32(a + f32(f32(b - a) * t))
    return out


def main():
    dsc, dkh, psc, pkh, esc, ekh = sys.argv[1:7]
    D_sc, D_kh = parse_stdout(dsc), parse_stdout(dkh)
    P_sc, P_kh = parse_stdout(psc), parse_stdout(pkh)
    E_sc, E_kh = parse_err(esc), parse_err(ekh)

    cases = []
    for idx in sorted(D_sc):
        s, k = D_sc[idx], D_kh[idx]
        if s["n"] == 0:
            continue
        l_diff = not np.array_equal(s["L"].view(np.uint32), k["L"].view(np.uint32))
        if not l_diff:
            continue
        cur_s = P_sc[idx]["L"]
        cur_k = P_kh[idx]["L"]
        Lin = np.frombuffer(E_sc[idx]["I"], dtype="<f4").copy()
        if not np.array_equal((Lin * cur_s).view(np.uint32), s["L"].view(np.uint32)):
            raise SystemExit(f"probe cur (SC) is not the multiplier of default L at case {idx}")
        if not np.array_equal((Lin * cur_k).view(np.uint32), k["L"].view(np.uint32)):
            raise SystemExit(f"probe cur (KH) is not the multiplier of default L at case {idx}")
        first_cur_diff = None
        for i in range(s["n"]):
            if cur_s[i].view(np.uint32) != cur_k[i].view(np.uint32):
                first_cur_diff = i
                break
        ent = {"idx": idx, "n": s["n"], "first": s["first"], "L_diff_default": True,
               "cur_identical_all": first_cur_diff is None, "first_cur_diff_sample": first_cur_diff}
        first_L_diff = int(np.nonzero(s["L"].view(np.uint32) != k["L"].view(np.uint32))[0][0])
        ent["first_L_diff_sample"] = first_L_diff
        if s["first"] == 0 and s["n"] > 0:
            sc_e = E_sc[idx]
            kh_e = E_kh[idx]
            coef, A, B = f(sc_e["coef"]), f(sc_e["A"]), f(sc_e["B"])
            inc, a, b = f(kh_e["inc"]), f(kh_e["a"]), f(kh_e["b"])
            rs = ramp_sc(s["n"], coef, A, B)
            rk = ramp_kh(s["n"], inc, a, b)
            ent["recalc_sc_match_probe"] = bool(np.array_equal(rs.view(np.uint32), cur_s.view(np.uint32)))
            ent["recalc_kh_match_probe"] = bool(np.array_equal(rk.view(np.uint32), cur_k.view(np.uint32)))
            # 反実仮想: SC の入力 (coef, A, B) に KH の丸め形 a+(b-a)*t を当てはめる。
            # 入力は両側で bit 一致 (下の coef_inc / A_a / B_b) なので、これが KH の cur と一致すれば丸め形だけが差。
            cf = ramp_kh(s["n"], coef, A, B)
            ent["counterfactual_kh_form_on_sc_inputs_eq_kh_cur"] = bool(np.array_equal(cf.view(np.uint32), cur_k.view(np.uint32)))
            ent["counterfactual_L_eq_kh"] = bool(np.array_equal((Lin * cf).view(np.uint32), k["L"].view(np.uint32)))
            d = first_L_diff
            ent["at_first_L_diff"] = {"sc_form": f"{int(rs[d:d+1].view(np.uint32)[0]):08x}",
                                      "kh_form": f"{int(rk[d:d+1].view(np.uint32)[0]):08x}",
                                      "probe_sc_cur": f"{int(cur_s[d:d+1].view(np.uint32)[0]):08x}",
                                      "probe_kh_cur": f"{int(cur_k[d:d+1].view(np.uint32)[0]):08x}"}
            ent["coef_inc_bits"] = [f"{sc_e['coef']:08x}", f"{kh_e['inc']:08x}"]
            ent["A_a_bits"] = [f"{sc_e['A']:08x}", f"{kh_e['a']:08x}"]
            ent["B_b_bits"] = [f"{sc_e['B']:08x}", f"{kh_e['b']:08x}"]
        cases.append(ent)

    table = {"first0": {}, "first1": {}}
    for idx in sorted(D_sc):
        s, k = D_sc[idx], D_kh[idx]
        if s["n"] == 0:
            continue
        grp = "first0" if s["first"] == 0 else "first1"
        Lsame = np.array_equal(s["L"].view(np.uint32), k["L"].view(np.uint32))
        csame = np.array_equal(P_sc[idx]["L"].view(np.uint32), P_kh[idx]["L"].view(np.uint32))
        key = ("L_same" if Lsame else "L_differs") + "_cur_" + ("same" if csame else "differs")
        table[grp][key] = table[grp].get(key, 0) + 1

    cf_all = {"first0_cases": 0, "kh_form_on_sc_inputs_eq_probe_cur": 0, "kh_form_on_sc_inputs_eq_default_L": 0,
              "sc_form_eq_kh_form": 0}
    for idx in sorted(D_sc):
        s, k = D_sc[idx], D_kh[idx]
        if s["n"] == 0 or s["first"] != 0:
            continue
        cf_all["first0_cases"] += 1
        e = E_sc[idx]
        coef, A, B = f(e["coef"]), f(e["A"]), f(e["B"])
        cf = ramp_kh(s["n"], coef, A, B)
        Lin = np.frombuffer(E_sc[idx]["I"], dtype="<f4").copy()
        cf_all["kh_form_on_sc_inputs_eq_probe_cur"] += bool(np.array_equal(cf.view(np.uint32), P_kh[idx]["L"].view(np.uint32)))
        cf_all["kh_form_on_sc_inputs_eq_default_L"] += bool(np.array_equal((Lin * cf).view(np.uint32), k["L"].view(np.uint32)))
        cf_all["sc_form_eq_kh_form"] += bool(np.array_equal(ramp_sc(s["n"], coef, A, B).view(np.uint32), cf.view(np.uint32)))

    # 負例: case 3 の SC cur の 1 ulp を下げると KH 形と一致し、未変更の SC 形は一致しない (判定の感度)
    neg = {}
    e3 = E_sc[3]
    c3, A3, B3 = f(e3["coef"]), f(e3["A"]), f(e3["B"])
    rs3 = ramp_sc(81, c3, A3, B3)
    rk3 = ramp_kh(81, c3, A3, B3)
    lowered = rs3.copy().view(np.uint32)
    lowered[2] -= 1
    neg["unperturbed_sc_eq_kh_all"] = bool(np.array_equal(rs3.view(np.uint32), rk3.view(np.uint32)))
    neg["sc_minus_1ulp_at_sample2_eq_kh"] = bool(lowered[2] == rk3[2:3].view(np.uint32)[0])

    summary = {
        "negative_control": neg,
        "first0_counterfactual": cf_all,
        "cur_L_table": table,
        "L_diff_cases": len(cases),
        "first0_cases": sum(1 for c in cases if c["first"] == 0),
        "cur_identical_all": sum(1 for c in cases if c["cur_identical_all"]),
        "cur_differs": sum(1 for c in cases if not c["cur_identical_all"]),
        "recalc_sc_ok": sum(1 for c in cases if c.get("recalc_sc_match_probe") is True),
        "recalc_kh_ok": sum(1 for c in cases if c.get("recalc_kh_match_probe") is True),
        "counterfactual_kh_form_cur_eq_kh": sum(1 for c in cases if c.get("counterfactual_kh_form_on_sc_inputs_eq_kh_cur") is True),
        "counterfactual_L_eq_kh": sum(1 for c in cases if c.get("counterfactual_L_eq_kh") is True),
        "first_L_diff_sample_hist": {},
    }
    for c in cases:
        key = str(min(c["first_L_diff_sample"], 9))
        summary["first_L_diff_sample_hist"][key] = summary["first_L_diff_sample_hist"].get(key, 0) + 1
    print(json.dumps({"summary": summary, "cases": cases}, ensure_ascii=False))


if __name__ == "__main__":
    main()
