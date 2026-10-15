"""#4393: RetDec 分割 lift C の `statement not in loop` (飛び先の注釈 `// 0x<VA>` が無い break) の原因を切り分ける。

使い方 (cwd=リポジトリルート):
  RETDEC=<retdec>/bin/retdec-decompiler EM_CONFIG=<emsdk>/.emscripten PATH=<emsdk>/upstream/emscripten:$PATH \
    FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/notloop_probe.py <c_dir>
<c_dir> は retdec_batch.py の KEEP_DIR (関数単位の出力 C)。
判定 (各 notloop の飛び先 VA ごと):
  - 飛び先の注釈が同じ関数内に有る → resolvable (gotofix が直せる)。
  - 無い → 機械語上の位置を確認 (命令境界か・直接 jump の有無)。
  - 同じ関数を --backend-no-opts で再 lift し、注釈が出るかを確認 (出れば backend 最適化段で落ちた)。
"""
import collections
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "liftlib"))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from liftlib.pe import Image  # noqa: E402

BRK_CMT = re.compile(r"^\s*// break(?: \(via goto\))? -> (0x[0-9a-f]+)\s*$")
ADDR_CMT = re.compile(r"^\s*// (0x[0-9a-f]+)\s*$")
FUNC_HDR = re.compile(r"^// Address range: 0x([0-9a-f]+) - 0x([0-9a-f]+)")
NOTLOOP_RE = re.compile(r"^[^:\n]+:(\d+):\d+: error: 'break' statement not in loop", re.M)
RETDEC = os.environ["RETDEC"]
PE = os.path.join(os.environ["FL_WIN64_DIR"], "block19091_PE.bin")


def notloop(path):
    p = subprocess.run(["emcc", "-c", "-fsyntax-only", "-w", "-ferror-limit=0", path],
                       capture_output=True, text=True)
    return sorted({int(m.group(1)) for m in NOTLOOP_RE.finditer(p.stderr + p.stdout)})


def funcs_of(lines):
    hdrs = [(i, FUNC_HDR.match(x)) for i, x in enumerate(lines)]
    hdrs = [(i, m) for i, m in hdrs if m]
    out = []
    for k, (i, m) in enumerate(hdrs):
        end = hdrs[k + 1][0] if k + 1 < len(hdrs) else len(lines)
        out.append((i, end, int(m.group(1), 16), int(m.group(2), 16)))
    return out


def annotated(lines, s, e):
    return {int(ADDR_CMT.match(lines[j]).group(1), 16) for j in range(s, e) if ADDR_CMT.match(lines[j])}


def noopt_has(lo, hi, target):
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "f.c")
        subprocess.run([RETDEC, "-s", "-o", out, "--select-ranges", "0x%x-0x%x" % (lo, hi),
                        "--select-decode-only", "--backend-no-opts", PE],
                       capture_output=True, text=True, timeout=280)
        if not os.path.exists(out):
            return None
        txt = open(out, errors="replace").read()
    return re.search(r"^\s*// 0x%x\s*$" % target, txt, re.M) is not None


def main():
    src = sys.argv[1]
    img = Image(PE)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    cnt = collections.Counter()
    unresolved = collections.OrderedDict()
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".c"):
            continue
        path = os.path.join(src, fn)
        lines = open(path, errors="replace").read().split("\n")
        funcs = funcs_of(lines)
        for ln in notloop(path):
            i = ln - 1
            f = next(((s, e, lo, hi) for (s, e, lo, hi) in funcs if s <= i < e), None)
            tgt = None
            for k in range(i - 1, max(i - 4, -1), -1):
                m = BRK_CMT.match(lines[k])
                if m:
                    tgt = int(m.group(1), 16)
                    break
            cnt["notloop"] += 1
            if f is None or tgt is None:
                cnt["no_func_or_target"] += 1
                continue
            s, e, lo, hi = f
            if tgt in annotated(lines, s, e):
                cnt["resolvable"] += 1
                continue
            key = (lo, hi, tgt)
            unresolved.setdefault(key, fn)
    cnt["unresolved_pairs"] = len(unresolved)
    for (lo, hi, tgt), fn in unresolved.items():
        ins = list(md.disasm(img.read(lo, hi - lo), lo))
        at = next((x for x in ins if x.address == tgt), None)
        cnt["boundary" if at else "not_boundary"] += 1
        ok = noopt_has(lo, hi, tgt)
        cnt["noopt_annotated" if ok else ("noopt_missing" if ok is not None else "noopt_fail")] += 1
        print(json.dumps({"file": fn, "func": "0x%x-0x%x" % (lo, hi), "target": "0x%x" % tgt,
                          "insn": ("%s %s" % (at.mnemonic, at.op_str)) if at else None,
                          "noopt_annotated": ok}, ensure_ascii=False))
    print(json.dumps(dict(cnt), ensure_ascii=False))


if __name__ == "__main__":
    main()
