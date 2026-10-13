"""lift_determinism_check.py — RetDec raw .drc.ll の非決定性を liftlib base 段の出力で判定する (LIFTLIB-9 / #668)。

  python3 lift_determinism_check.py <outdir> <runs>

<outdir>/r<i>/ott.drc.ll (同一入力で RetDec を実行した raw) を liftlib.passes.base.run_base に通し
(A7 で uselistorder 行を除去する段を含む)、<outdir>/r<i>/base.ll を書く。
全 run の base.ll の sha256 が一致すれば PASS。raw の sha256 は表示のみで判定には使わない
(raw は uselistorder の順序が実行ごとに変わるため)。

ネガコン 1: r1 の base.ll に 1 行を足した複製が、同じ比較関数で「不一致」と判定されること。
ネガコン 2: DET_NEGCTRL_NO_BASE=1 で run_base (A7) を外し raw をそのまま比較する (検出力の実測用)。
ネガコン 3 (LIFTLIB-11): r1 の raw の alloca 並びを逆順にした複製で、canon_alloca_order 後は一致し
canon 無し (A7 のみ) では不一致になること (canon-same/nocanon-DIFF) を確認する。判定に含める。
raw の全 run が偶然一致すれば PASS (exit 0)、不一致なら FAIL (exit 1) になる。
PASS かつネガコン 1 検出のときのみ exit 0。それ以外は exit 1。runs < 2 は比較 0 組のため exit 2。
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from liftlib.passes import base as B  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def same(a, b):
    return sha(a) == sha(b)


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def permute_alloca_reversed(text):
    """各関数の連続した alloca 行の並びを逆順にし、%N 参照を付け替えた複製を返す (ネガコン 3 用)。
    スロット番号の付け替えのみで意味は変わらない。alloca が 2 本未満なら None。"""
    lines = text.split("\n")
    n = len(lines)
    changed = False
    i = 0
    while i < n:
        if not lines[i].startswith("define "):
            i += 1
            continue
        j = i + 1
        while j < n and not lines[j].startswith("}"):
            j += 1
        k = i + 1
        while k < j:
            if not B._ALLOCA_LINE.match(lines[k]):
                k += 1
                continue
            run = []
            while k < j and B._ALLOCA_LINE.match(lines[k]):
                run.append(k)
                k += 1
            if len(run) < 2:
                continue
            ms = [B._ALLOCA_LINE.match(lines[x]) for x in run]
            names = [m.group(2) for m in ms]
            rev = list(reversed(range(len(run))))
            swap = {names[p]: names[q] for p, q in enumerate(rev)}
            for p, q in enumerate(rev):
                m = ms[q]
                lines[run[p]] = f"{m.group(1)}%{names[p]} = alloca {m.group(3)}{m.group(4)}"
            for x in range(i + 1, j):
                if x not in run:
                    lines[x] = B._LOCAL_REF.sub(lambda mo: "%" + swap.get(mo.group(1), mo.group(1)), lines[x])
            changed = True
        i = j + 1
    return "\n".join(lines) if changed else None


def main():
    out, runs = sys.argv[1], int(sys.argv[2])
    if runs < 2:
        print("runs は 2 以上が必要 (比較 0 組で PASS させない): %d" % runs, file=sys.stderr)
        return 2
    no_base = os.environ.get("DET_NEGCTRL_NO_BASE") == "1"
    rows = []
    for i in range(1, runs + 1):
        d = os.path.join(out, "r%d" % i)
        raw = os.path.join(d, "ott.drc.ll")
        base = os.path.join(d, "base.ll")
        t0 = time.time()
        if no_base:
            text = open(raw).read()
        else:
            text, _ = B.run_base(open(raw).read(), B.make_args())
            text = B.canon_alloca_order(text)
        with open(base, "w") as f:
            f.write(text)
        rows.append({
            "run": i,
            "raw_sha256_12": sha(raw)[:12],
            "base_sha256_12": sha(base)[:12],
            "base_lines": text.count("\n"),
            "base_sec": round(time.time() - t0, 1),
        })

    print("run  raw_sha256(情報)  base_sha256(判定)  base_lines  base_sec")
    for r in rows:
        print("r%-3d %-18s %-18s %-11d %s" % (r["run"], r["raw_sha256_12"], r["base_sha256_12"], r["base_lines"], r["base_sec"]))

    r1 = os.path.join(out, "r1", "base.ll")
    r1_raw = os.path.join(out, "r1", "ott.drc.ll")
    det_pass = all(same(r1, os.path.join(out, "r%d" % i, "base.ll")) for i in range(2, runs + 1))

    neg = os.path.join(out, "r1", "base.negctrl.ll")
    with open(r1) as f:
        body = f.read()
    with open(neg, "w") as f:
        f.write(body + "; NEG-CONTROL (LIFTLIB-9): one appended line must be detected as a mismatch\n")
    nc_detected = not same(r1, neg)

    # ネガコン 3 (LIFTLIB-11): r1 の raw の alloca 並びを反転した複製を、canon ありで比較する。
    # 反転は内容を変えない (スロット番号の付け替えのみ) ため、canon 後は r1 と一致しなければならない。
    # canon を外す (A7 のみ) と一致しないことも同時に見る (正規化が並びの差を吸収していることの確認)。
    raw_text = open(r1_raw).read()
    rev_raw = permute_alloca_reversed(raw_text)
    if rev_raw is None:
        nc3 = "no-alloca-pair"
    else:
        base_nc, _ = B.run_base(raw_text, B.make_args())
        rev_nc, _ = B.run_base(rev_raw, B.make_args())
        canon_same = sha_text(B.canon_alloca_order(base_nc)) == sha_text(B.canon_alloca_order(rev_nc))
        nocanon_same = sha_text(base_nc) == sha_text(rev_nc)
        nc3 = ("canon-same" if canon_same else "canon-DIFF") + "/" + ("nocanon-same" if nocanon_same else "nocanon-DIFF")

    nc3_ok = nc3 == "canon-same/nocanon-DIFF"
    verdict = {
        "runs": runs,
        "rows": rows,
        "determinism": "PASS" if det_pass else "FAIL",
        "negctrl_detected": nc_detected,
        "negctrl_alloca_reverse": nc3,
        "negctrl_alloca_reverse_ok": nc3_ok,
    }
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=1)
    print("determinism(base.ll 全 run 一致): %s" % verdict["determinism"])
    print("negctrl(1 行追加を不一致と検出): %s" % ("detected" if nc_detected else "NOT detected"))
    print("negctrl 3(alloca 逆順: canon で吸収・canon 無しで差): %s (%s)" % ("OK" if nc3_ok else "NG", nc3))
    return 0 if (det_pass and nc_detected and nc3_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
