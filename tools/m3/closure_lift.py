#!/usr/bin/env python3
# M3-1: RetDec bin2llvmir selective lift の declare 閉包 (closure) を
#       固定点に達するまで反復で伸ばす。
#
#   python3 closure_lift.py --input <binary> --seed "0x412d60-0x412da0,0x409440-0x409660" \
#       --out <out.ll> --workdir <workdir> [--name <tag>] [--max-rounds 12] [--window 0x600]
#
# 動作:
#   round 0    : seed ranges で `--select-ranges --select-decode-only` を実行 (bin2llvmir 一発通過)
#   round 1..N : 出力 .ll の `declare <ty> @function_XXXX` (内部関数アドレス, 未定義) を収集し
#                [addr, addr+window) 区間を追加して再リフト。declare の内部関数が
#                消えなくなる (固定点) まで反復。
#   出力: <out>.ll (固定点 IR) / <out>.closure.json (ラウンド毎の追加分, 未解決 declare 一覧)
#
# 固定点でも残る declare (= リフト対象外アドレス・外部 import) は closure.json に記録し
# 後段 (gen_imports.py) の stub 自動生成へ渡す。未実装 stub は実行時に fail-fast throw。

import argparse
import json
import os
import re
import subprocess
import sys


def die(msg):
    print(f"[closure_lift] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


DECL_RE = re.compile(r"^declare \S+ @function_([0-9a-f]+)\(", re.M)
DEF_RE = re.compile(r"^define \S+ @function_([0-9a-f]+)\(", re.M)


def lift_once(retdec, binpath, ranges, outbase, workdir, logname):
    cmd = [retdec, binpath, "-o", os.path.join(workdir, outbase + ".drc.c"),
           "--select-ranges", ranges, "--select-decode-only", "--timeout", "900"]
    with open(os.path.join(workdir, logname), "w") as lf:
        p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
    ll = os.path.join(workdir, outbase + ".drc.ll")
    if p.returncode != 0 or not os.path.exists(ll):
        die(f"RetDec リフト失敗 ({logname}, rc={p.returncode})")
    return ll


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True, help="固定点 IR の出力パス (.ll)")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--name", default="closure")
    ap.add_argument("--max-rounds", type=int, default=12)
    ap.add_argument("--window", default="0x600")
    ap.add_argument("--retdec", default="/opt/retdec/bin/retdec-decompiler")
    ap.add_argument("--max-declares", type=int, default=400,
                    help="declare 数がこの値を超えたら打ち切り (爆発防止)")
    args = ap.parse_args()

    os.makedirs(args.workdir or ".", exist_ok=True)
    wd = args.workdir
    ranges = [r.strip() for r in args.seed.split(",") if r.strip()]
    log = {"input": args.input, "seed_ranges": ranges, "rounds": []}
    win = int(args.window, 0)
    prev_added = None

    for r in range(args.max_rounds + 1):
        ll = lift_once(args.retdec, args.input, ",".join(ranges),
                       args.name, wd, f"{args.name}.r{r}.log")
        text = open(ll).read()
        declared = set(DECL_RE.findall(text))
        defined = set(DEF_RE.findall(text))
        missing = sorted(int(a, 16) for a in declared if a not in defined)
        log["rounds"].append({
            "round": r, "ranges": len(ranges), "defines": len(defined),
            "declares_internal": len(missing),
            "added": list(prev_added or []),
        })
        if not missing or len(missing) > args.max_declares:
            break
        prev_added = [f"0x{a:x}-0x{a + win:x}" for a in missing]
        ranges.extend(prev_added)

    out_ll = args.out
    with open(out_ll, "w") as f:
        f.write(text)
    ext_declares = []
    seen = set()
    for m in re.finditer(r"^declare \S+ @([^\s(]+)\(", text, re.M):
        n = m.group(1)
        if n in seen or n.startswith("llvm.") or n.startswith("__asm_"):
            continue
        seen.add(n)
        ext_declares.append(n)
    log["final_internal_declares"] = sorted(f"0x{a}" for a in declared - defined)
    log["external_declares"] = sorted(ext_declares)
    log["ranges_final"] = len(ranges)
    cj = os.path.splitext(out_ll)[0] + ".closure.json"
    with open(cj, "w") as f:
        json.dump(log, f, indent=1)
    print(f"[closure_lift] {out_ll}: rounds={len(log['rounds'])} "
          f"ranges={log['ranges_final']} defines={len(defined)} "
          f"internal_declares={len(log['final_internal_declares'])} "
          f"external_declares={len(ext_declares)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
