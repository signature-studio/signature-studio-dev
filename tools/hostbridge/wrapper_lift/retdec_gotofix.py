"""RetDec 分割 lift 出力 C の「loop 外の break」を、RetDec の飛び先への goto に直す (#1679)。

使い方 (cwd=リポジトリルート):
  EM_CONFIG=<emsdk>/.emscripten PATH=<emsdk>/upstream/emscripten:$PATH \
    python3 tools/hostbridge/wrapper_lift/retdec_gotofix.py <in_dir> <out_dir>

対象: emcc が `'break' statement not in loop or switch statement` と報告した行だけ。
  - 飛び先: その直前 3 行以内の `// break -> 0x<VA>` 注釈 (RetDec の制御フロー復元が示す飛び先)。
  - 飛び先の証拠: 同じ関数内に、行頭の `// 0x<VA>` 注釈 (RetDec が機械語アドレスを付けた文) があること。
    無ければ直さない (飛び先が C 上に存在しない)。
  - 変換: `break;` → `goto lab_0x<VA>;`、注釈行の直前に `lab_0x<VA>:;` を置く (同一関数で未定義のときだけ)。
loop 内の `break` (emcc が正当と判定する) は触らない。制御構造の再設計はせず、飛び先が同じ goto に限る。
"""
import collections
import os
import re
import subprocess
import sys

BRK_CMT = re.compile(r"^\s*// break(?: \(via goto\))? -> (0x[0-9a-f]+)\s*$")
ADDR_CMT = re.compile(r"^(\s*)// (0x[0-9a-f]+)\s*$")
FUNC_HDR = re.compile(r"^// Address range: ")
NOTLOOP_RE = re.compile(r"^[^:\n]+:(\d+):\d+: error: 'break' statement not in loop", re.M)


def notloop_lines(path):
    p = subprocess.run(
        ["emcc", "-c", "-fsyntax-only", "-w", "-ferror-limit=0", path],
        capture_output=True, text=True,
    )
    return {int(m.group(1)) for m in NOTLOOP_RE.finditer(p.stderr + p.stdout)}


def fix_file(path, dst, cnt):
    with open(path, errors="replace") as fh:
        lines = fh.read().split("\n")
    targets = notloop_lines(path)
    cnt["notloop"] += len(targets)
    func_of = []
    cur = -1
    for i, x in enumerate(lines):
        if FUNC_HDR.match(x):
            cur = i
        func_of.append(cur)
    end_of = {}
    hdrs = [i for i, x in enumerate(lines) if FUNC_HDR.match(x)]
    for k, h in enumerate(hdrs):
        end_of[h] = hdrs[k + 1] if k + 1 < len(hdrs) else len(lines)
    labels = {}
    for ln in sorted(targets):
        i = ln - 1
        f = func_of[i]
        if f < 0 or "break;" not in lines[i]:
            cnt["skip_no_break_text"] += 1
            continue
        addr = None
        for k in range(i - 1, max(i - 4, -1), -1):
            m = BRK_CMT.match(lines[k])
            if m:
                addr = m.group(1)
                break
        if addr is None:
            cnt["skip_no_target_comment"] += 1
            continue
        j = None
        for k in range(f + 1, end_of[f]):
            m = ADDR_CMT.match(lines[k])
            if m and m.group(2) == addr:
                j = k
                break
        if j is None:
            cnt["skip_no_addr_in_func"] += 1
            continue
        lines[i] = lines[i].replace("break;", "goto lab_%s;" % addr, 1)
        cnt["goto_replaced"] += 1
        labels.setdefault((f, addr), j)
    inserts = []
    for (f, addr), j in labels.items():
        exists = any(re.search(r"\blab_%s:" % addr, lines[k]) for k in range(f, end_of[f]))
        if exists:
            cnt["label_already"] += 1
            continue
        indent = ADDR_CMT.match(lines[j]).group(1)
        inserts.append((j, indent + "lab_%s:;" % addr))
    for j, s in sorted(inserts, reverse=True):
        lines.insert(j, s)
    cnt["label_inserted"] += len(inserts)
    with open(dst, "w") as fh:
        fh.write("\n".join(lines))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    cnt = collections.Counter()
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        fix_file(os.path.join(src, f), os.path.join(dst, f), cnt)
    print(dict(cnt))


if __name__ == "__main__":
    main()
