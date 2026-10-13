"""stdbuild.py — lift→wasm 標準ビルド設定 (PERF-P1 / #155) と出力 bit 署名ガード。標準ライブラリのみ (単体でも実行できる)。

設定の正本は data/std_build.json。標準 profile `std` = `-O3 -flto` + `-Wl,--gc-sections` + 最小 export。
  - -O2 以上は必須 / LTO は無害 (bit-exact OTT で O2 比 1.15×) / `-msimd128`・追加 wasm-opt 段は入れない (tools/perf/REPORT.md §2.1)
  - 最小 export は呼び出し側 (cfg の exports) が渡す。gc-sections が不要関数を落とす
署名ガード: 同一入力に対する出力の署名 (probe の出力) が全変種で一致しなければ SignatureMismatch (CLI は exit 1)。

shell から:
  python3 stdbuild.py flags std                     # emcc に渡す最適化・FP フラグを 1 行で出力
  python3 stdbuild.py check std -- <flags...>       # enforce profile に禁止フラグが混ざっていないか (違反で exit 1)
  python3 stdbuild.py guard --probe 'node p.mjs {cjs}' --regex '"sig":"(\\w+)"' [--expect SIG] a.cjs b.cjs ...
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "..", "data", "std_build.json")


class StdBuildError(RuntimeError):
    pass


class SignatureMismatch(StdBuildError):
    pass


# 署名が取れなかったことを表す番兵。同じ失敗が全変種で起きても「一致」にしてはいけない (fail-closed)
SENTINEL_SIGS = ("TIMEOUT", "NO-RESULT")


def is_sentinel(sig):
    return not sig or sig in SENTINEL_SIGS or sig.startswith("PROBE-FAIL")


def load():
    return json.load(open(CFG_PATH))


def profile_names():
    return list(load()["profiles"])


def flags(profile, rounding_math=False):
    """最適化 + FP + link の emcc フラグ (export / メモリ配置は呼び出し側)。"""
    c = load()
    if profile not in c["profiles"]:
        raise StdBuildError("unknown profile %r (有効: %s)" % (profile, ", ".join(c["profiles"])))
    p = c["profiles"][profile]
    return list(p["opt"]) + list(c["fp_rounding" if rounding_math else "fp"]) + list(p["link"])


def violations(profile, cmd):
    """enforce profile (std/o2/o3) の最終コマンドに禁止フラグがあれば列挙する。他 profile は常に []。"""
    c = load()
    if not c["profiles"][profile].get("enforce"):
        return []
    forb = set(c["forbidden_in_enforced"])
    mine = set(c["profiles"][profile]["opt"]) | set(c["profiles"][profile]["link"])
    return [t for t in cmd if t in forb and t not in mine]


def emcc_cmd(profile, srcs, out, exports=(), link_extra=(), cflags_extra=(), rounding_math=False):
    """C/LL ソース群 → emcc コマンド。標準フラグ + 最小 export (`_` は自動付与)。enforce profile では禁止フラグ混入で StdBuildError。"""
    cmd = ["emcc"] + flags(profile, rounding_math) + list(cflags_extra) + list(srcs) + list(link_extra)
    if exports:
        cmd.append("-sEXPORTED_FUNCTIONS=" + ",".join(e if e.startswith("_") else "_" + e for e in exports))
    cmd += ["-o", out]
    bad = violations(profile, cmd)
    if bad:
        raise StdBuildError("profile %s に禁止フラグ: %s" % (profile, " ".join(bad)))
    return cmd


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def canon_digest(out_text, spec):
    """wasm_runner の出力 (R/D/E 行) を、diff.py の比較規則と同じ正規化 (compare_ret / ret_from_xmm0 / ignore_buffers /
    mask_ranges / ポインタトークン) で署名化する。malloc 配置に依存する値 (生ポインタの rax 等) は署名に入れない。
    R 行が 1 件も無い出力 (runner が何も出さなかった) は署名化せず StdBuildError (空文字の sha256 が全変種で一致してしまうため)。"""
    cmp_ret = spec.get("compare_ret", False) or spec.get("ret_from_xmm0", False)
    ign = set(spec.get("ignore_buffers", []))
    masks = spec.get("mask_ranges", {})
    lines = []
    for ln in out_text.split("\n"):
        w = ln.rstrip().split(" ")
        if w[0] == "R" and len(w) >= 5:
            lines.append("R %s %s %s %s" % (w[1], w[2], w[3], w[4] if (cmp_ret and w[3] == "0") else "-"))
        elif w[0] == "D" and len(w) >= 3:
            if w[1] in ign:
                continue
            hx = w[2]
            for (o, n) in masks.get(w[1], []):
                hx = hx[:2 * o] + "00" * n + hx[2 * (o + n):]
            lines.append("D %s %s %s" % (w[1], hx, w[3] if len(w) > 3 else "-"))
        elif w[0] == "E":
            lines.append(ln.rstrip())
    if not any(ln.startswith("R ") for ln in lines):
        raise StdBuildError("出力に R 行が 0 件 (wasm_runner が結果を出していない): 署名化しない")
    return digest("\n".join(lines))


def guard(sigs, expect=None):
    """sigs: {variant: signature}。全一致 (+ expect 一致) で report、不一致なら SignatureMismatch。
    署名が取れていない変種 (番兵 TIMEOUT / PROBE-FAIL* / NO-RESULT / 空) が 1 つでもあれば、全変種が同じ失敗でも SignatureMismatch。"""
    if not sigs:
        raise StdBuildError("署名が空 (変種が 0)")
    bad = {k: v for k, v in sigs.items() if is_sentinel(v)}
    if bad:
        raise SignatureMismatch("署名が取得できていない変種 (失敗は一致とみなさない): " + ", ".join("%s=%s" % (k, v or "<空>") for k, v in bad.items()))
    uniq = sorted(set(sigs.values()))
    rep = dict(sigs=dict(sigs), unique=uniq, expect=expect, ok=True)
    if len(uniq) != 1:
        raise SignatureMismatch("署名不一致: " + ", ".join("%s=%s" % (k, v) for k, v in sigs.items()))
    if expect is not None and uniq[0] != expect:
        raise SignatureMismatch("期待署名 %s と不一致: %s" % (expect, uniq[0]))
    return rep


def probe_cmd(template, regex, cjs, env_extra=None, timeout=600):
    """外部 probe (例 `node bench.mjs {cjs}`) を走らせ、出力から regex 第 1 群で署名を得る。"""
    cmd = [t.replace("{cjs}", cjs) for t in template]
    e = dict(os.environ, **(env_extra or {}))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    m = re.search(regex, r.stdout + "\n" + r.stderr)
    if r.returncode or not m:
        return "PROBE-FAIL(rc=%d)" % r.returncode
    return m.group(1)


def _main(argv):
    ap = argparse.ArgumentParser(prog="stdbuild")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("flags")
    p.add_argument("profile", nargs="?", default=load()["default_profile"]); p.add_argument("--rounding-math", action="store_true")
    p = sp.add_parser("check")
    p.add_argument("profile"); p.add_argument("flags", nargs="*")
    p = sp.add_parser("guard")
    p.add_argument("--probe", required=True, help="shlex 分割される probe コマンド。{cjs} を各ファイルに置換")
    p.add_argument("--regex", required=True); p.add_argument("--expect"); p.add_argument("--env", action="append", default=[])
    p.add_argument("--timeout", type=int, default=600); p.add_argument("cjs", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "flags":
        print(" ".join(flags(a.profile, a.rounding_math)))
        return 0
    if a.cmd == "check":
        bad = violations(a.profile, a.flags)
        if bad:
            print("[stdbuild] FAIL: profile %s に禁止フラグ: %s" % (a.profile, " ".join(bad)), file=sys.stderr)
            return 1
        print("[stdbuild] ok: profile %s 禁止フラグなし" % a.profile)
        return 0
    import shlex
    real = [os.path.realpath(f) for f in a.cjs]
    if len(a.cjs) < 2 or len(set(real)) != len(real):
        print("[sigguard] FAIL: 比較には異なるファイルが 2 件以上必要 (重複・1 件のみは拒否): %s" % " ".join(a.cjs), file=sys.stderr)
        return 1
    envx = dict(kv.split("=", 1) for kv in a.env)
    sigs = {f: probe_cmd(shlex.split(a.probe), a.regex, os.path.abspath(f), envx, a.timeout) for f in a.cjs}
    for k, v in sigs.items():
        print("[sigguard] %s  %s" % (k, v))
    try:
        guard(sigs, a.expect)
    except SignatureMismatch as e:
        print("[sigguard] FAIL: %s" % e, file=sys.stderr)
        return 1
    print("[sigguard] PASS: %d 変種で署名一致 (%s)" % (len(sigs), next(iter(sigs.values()))))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main(sys.argv[1:]))
    except StdBuildError as e:
        print("[stdbuild] ERROR: %s" % e, file=sys.stderr)
        sys.exit(2)
