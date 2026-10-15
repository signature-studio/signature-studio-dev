#!/usr/bin/env python3
"""ci_restore_stores.py IN.ll OUT.ll [--drop-one] — RetDec の SSE ストア命令を IR の store に戻す (T-SH-103 #4229)。

RetDec は x86 の `movups [m], xmm` / `movntps [m], xmm` を `call void @__asm_movups(i128 LOAD(m), i128 xmm)` に変え、
書き込み先への store を出さない。`movaps [m], xmm` / `movapd [m], xmm` は
`%r = call i64 @__asm_movaps(i128 xmm)`・`%s = sext i64 %r to i128`・`store i128 %s, m` になる。
sext は下位 64bit の符号で上位を決めるため、xmm 全体の書き込みを表さない。

本 pass は次を行う。対象は同じ関数内で形が一致するものだけ。それ以外は exit 1 で止める。
  - movups/movntps: call を `store i128 xmm, m` に置き換える。m は load のアドレス。
    ただし m が「汎用レジスタの保存先 (alloca) を bitcast したもの」の場合は、保存先ではなく
    レジスタの値 (アドレス) が要るため、この pass では扱えない (exit 1)。
  - movaps/movapd: call と sext を消し、store の値を xmm (call の引数) にする。
  - 呼び出しが残らなくなった `declare @__asm_<op>` を削る。
件数は x86 から数えた期待値 (movups 3・movntps 8・movaps 7・movapd 1) と一致しなければ exit 1。
--drop-one : ネガティブコントロール用。movups/movntps の最後の 1 箇所を復元せず、件数検査で必ず FAIL させる。"""
import re, sys

args = sys.argv[1:]
drop_one = "--drop-one" in args
if drop_one:
    args.remove("--drop-one")

EXPECT = {"movups": 3, "movntps": 8, "movaps": 7, "movapd": 1}
LOAD = re.compile(r"^\s*(%[\w.\-]+) = load i128, i128\* (%[\w.\-]+),")
BITCAST = re.compile(r"^\s*(%[\w.\-]+) = bitcast i64\* (%[\w.\-]+) to i128\*")
STORE_CALL = re.compile(r"^(\s*)call void @__asm_(movups|movntps)\(i128 (%[\w.\-]+), i128 (%[\w.\-]+)\)(.*)$")
RET_CALL = re.compile(r"^(\s*)(%[\w.\-]+) = call i64 @__asm_(movaps|movapd)\(i128 (%[\w.\-]+)\)(.*)$")
SEXT = re.compile(r"^\s*(%[\w.\-]+) = sext i64 (%[\w.\-]+) to i128")
STORE_VAL = re.compile(r"^(\s*)store i128 (%[\w.\-]+), i128\* (%[\w.\-]+), (.*)$")


def is_block_start(line):
    return line.startswith("define ") or re.match(r"^[\w.\-]+:", line) is not None


def fn_bounds(lines, i):
    s = i
    while s > 0 and not lines[s].startswith("define "):
        s -= 1
    e = i
    while e < len(lines) - 1 and lines[e] != "}":
        e += 1
    return s, e


def count_refs(lines, i, name):
    s, e = fn_bounds(lines, i)
    return sum(len(re.findall(re.escape(name) + r"(?![\w.\-])", lines[x])) for x in range(s, e + 1))


def fail(msg):
    print(f"[restore] {msg}", file=sys.stderr)
    sys.exit(1)


src = open(args[0]).read().split("\n")
out = list(src)
done = {k: 0 for k in EXPECT}
drop_left = drop_one

for i, line in enumerate(src):
    m = STORE_CALL.match(line)
    if m:
        ind, op, val, xmm, rest = m.groups()
        ptr = None
        for j in range(i - 1, -1, -1):
            if is_block_start(src[j]):
                break
            lm = LOAD.match(src[j])
            if lm and lm.group(1) == val:
                ptr = lm.group(2)
                break
        if ptr is None:
            fail(f"{op} の値の load が同じ BB に無い: line {i + 1}")
        if drop_left and op in ("movups", "movntps") and done[op] == EXPECT[op] - 1:
            drop_left = False
            continue
        pd = next((x for x in range(i - 1, -1, -1) if re.match(r"^\s*" + re.escape(ptr) + r" = ", src[x])), None)
        if pd is not None and BITCAST.match(src[pd]):
            # 書き込み先が保存レジスタ (alloca) の bitcast。アドレスは alloca の中身 (レジスタの値) で、
            # 関数内で alloca へ入る store が書き込み直前まで 1 回だけ (入口の store) のときだけ解く。
            slot = BITCAST.match(src[pd]).group(2)
            s0, _ = fn_bounds(src, i)
            stores = [x for x in range(s0, i) if re.match(r"^\s*store i64 \S+, i64\* " + re.escape(slot) + r",", src[x])]
            if len(stores) != 1:
                fail(f"{op} の保存レジスタ {slot} の値を一意に決められない: line {i + 1}")
            addr = re.match(r"^\s*store i64 (\S+),", src[stores[0]]).group(1)
            tmp = f"%ci_wp{i}"
            out[i] = f"{ind}{tmp} = inttoptr i64 {addr} to i128*\n{ind}store i128 {xmm}, i128* {tmp}, align 1{rest}"
            done[op] += 1
            continue
        out[i] = f"{ind}store i128 {xmm}, i128* {ptr}, align 1{rest}"
        done[op] += 1
        continue

    m = RET_CALL.match(line)
    if m:
        ind, res, op, xmm, rest = m.groups()
        s_idx = next((x for x in range(i + 1, len(src))
                      if (sm := SEXT.match(src[x])) and sm.group(2) == res), None)
        if s_idx is None:
            fail(f"{op} の結果を sext する行が無い: line {i + 1}")
        sval = SEXT.match(src[s_idx]).group(1)
        k = next((x for x in range(s_idx + 1, len(src))
                  if (vm := STORE_VAL.match(src[x])) and vm.group(2) == sval), None)
        if k is None or count_refs(src, i, res) != 2 or count_refs(src, i, sval) != 2:
            fail(f"{op} の結果の使われ方が想定外: line {i + 1}")
        vm = STORE_VAL.match(src[k])
        out[i] = ""
        out[s_idx] = ""
        out[k] = f"{vm.group(1)}store i128 {xmm}, i128* {vm.group(3)}, {vm.group(4)}"
        done[op] += 1

for op in EXPECT:
    if done[op] != EXPECT[op]:
        fail(f"{op}: {done[op]} 件 (期待 {EXPECT[op]})")

text = "\n".join(out)
for op in EXPECT:
    if not re.search(r"call [^\n]*@__asm_" + op + r"\(", text):
        text = re.sub(r"^declare [^\n]*@__asm_" + op + r"\([^\n]*\n", "", text, flags=re.M)
open(args[1], "w").write(text)
print(f"[restore] stores restored: movups {done['movups']} movntps {done['movntps']} "
      f"movaps {done['movaps']} movapd {done['movapd']} -> {args[1]}")
