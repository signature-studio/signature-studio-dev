#!/usr/bin/env python3
# lea_index_scan.py — ICALL-86 (#3136): SlateCore.core_64 の全命令から、基底を lea [rip+...] で作った添字参照
#   [B+I*sc+disp] を列挙し、既知 5 件 (0x1813068d0〜0x181306910) に届く添字 n を求める。
#   基底 B の値 X は lea-rip の定数。n = (slot − X − disp) / sc が整数のものだけを候補にする。
#   X の求め方: (a) 線形走査 (分岐先・ret/jmp/int3/ud2 の直後で状態を破棄) と
#               (b) 関数内の全定義が lea-rip の場合 (流れ非依存・全定義が X の集合)。
#               (b) は入口由来の値を排除できないため、判定は必ず「届き得る」(届かないとは言わない)。
#   添字 I の値域: 線形区間での最後の定義 (区間は分岐先で切れるので到達定義と一致する) から分類する。
#     const (xor/mov の即値)・movzx byte/word・movsx byte/word・and imm (0..imm)・shr (上限)。それ以外は未確定。
#     分岐先は objdump の先頭トークンを読む (0x 有りの形式・無しの形式 `4020 <sym+0x..>` の両方)。間接分岐の先は未解析。
#   用法: python3 tools/icall/diff/lea_index_scan.py <objdump -d -M intel の出力> <SlateCore.core_64 | ->
#   exe に '-' を渡すと pdata を使わない (負の対照用の合成入力)。結果は標準出力へ。
import bisect
import re
import sys
from collections import defaultdict

IMAGE_BASE = 0x180000000
SLOTS = [0x1813068D0, 0x1813068F8, 0x181306900, 0x181306908, 0x181306910]
INS = re.compile(r"\s*([0-9a-f]+):\t(?:[0-9a-f]{2} )+\s*\t?(.*)$")
COMMENT = re.compile(r"#\s*(?:0x)?([0-9a-f]+)")
PREFIX = {"lock", "rep", "repz", "repnz", "rex", "rex.W", "rex.WB", "rex.R", "rex.B", "rex.X",
          "data16", "cs", "ds", "es", "ss", "notrack", "bnd", "addr32", "xacquire", "xrelease"}
CALLER_SAVED = ["rax", "rcx", "rdx", "r8", "r9", "r10", "r11"]
NO_WRITE = {"cmp", "test", "bt", "ucomiss", "ucomisd", "comiss", "comisd", "nop", "push", "ret", "int3",
            "ud2", "hlt", "prefetcht0", "prefetchnta", "clflush"}
BOUNDARY_PREV = {"ret", "jmp", "int3", "ud2", "hlt"}
JT_OP = re.compile(r"(?:0x)?[0-9a-f]+(?: |$)")

REG64 = {}
for _b, _names in [("rax", "eax ax al ah"), ("rbx", "ebx bx bl bh"), ("rcx", "ecx cx cl ch"),
                   ("rdx", "edx dx dl dh"), ("rsi", "esi si sil"), ("rdi", "edi di dil"),
                   ("rbp", "ebp bp bpl"), ("rsp", "esp sp spl")]:
    REG64[_b] = _b
    for _n in _names.split():
        REG64[_n] = _b
for _i in range(8, 16):
    for _suf in ("", "d", "w", "b"):
        REG64["r%d%s" % (_i, _suf)] = "r%d" % _i
FULL_NAMES = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"} | {"r%d" % i for i in range(8, 16)}


def canon(tok):
    return REG64.get(tok)


def is_full32_64(tok):
    # 64bit 名・32bit 名 (ecx 等・r8d 等) は上位ビットを 0 にする (部分書込みではない)
    return tok in FULL_NAMES or re.fullmatch(r"e(ax|bx|cx|dx|si|di|bp|sp)|r\d+d", tok) is not None


def reg_width(tok):
    if re.fullmatch(r"[a-d][lh]|[sd]il|[sb]pl|r\d+b", tok):
        return 8
    if re.fullmatch(r"[a-d]x|[sd]i|[sb]p|r\d+w", tok):
        return 16
    return 32 if re.fullmatch(r"e(ax|bx|cx|dx|si|di|bp|sp)|r\d+d", tok) else 64


def split_ins(text):
    parts = text.split()
    while parts and parts[0] in PREFIX:
        parts = parts[1:]
    if not parts:
        return "", []
    mnem = parts[0]
    rest = " ".join(parts[1:])
    ops = [o.strip() for o in rest.split(",")] if rest else []
    return mnem, ops


def mem_parts(op):
    m = re.search(r"\[([^\]]*)\]", op)
    if not m:
        return None
    U, S, disp, rip = [], [], 0, False
    for sign, body in re.findall(r"([+-]?)([^+-]+)", m.group(1)):
        if "*" in body:
            r, s = body.split("*")
            c = canon(r)
            if c is None or sign == "-":
                return None
            S.append((c, int(s)))
        elif body == "rip":
            rip = True
        elif body.startswith("0x"):
            disp += (-1 if sign == "-" else 1) * int(body, 16)
        else:
            c = canon(body)
            if c is None or sign == "-":
                return None
            U.append(c)
    return {"U": U, "S": S, "disp": disp, "rip": rip}


def writes(mnem, ops):
    if mnem in NO_WRITE or mnem.startswith("j"):
        return []
    if mnem == "call":
        return CALLER_SAVED
    if mnem in ("cqo", "cdq", "cwd"):
        return ["rdx"]
    if mnem in ("mul", "div", "idiv") or (mnem == "imul" and len(ops) == 1):
        return ["rax", "rdx"]
    if mnem in ("cpuid", "rdtsc"):
        return ["rax", "rbx", "rcx", "rdx"]
    if mnem == "cmpxchg":
        return ["rax"] + ([canon(ops[0])] if ops and canon(ops[0]) else [])
    if mnem.startswith("stos") or mnem.startswith("movs"):
        return ["rdi", "rsi", "rcx"]
    if mnem == "syscall":
        return ["rax", "rcx", "r11"]
    if mnem == "xchg":
        return [canon(o) for o in ops if canon(o)]
    if mnem == "leave":
        return ["rbp", "rsp"]
    if ops and canon(ops[0]):
        return [canon(ops[0])]
    return []


def load_pdata(exe):
    if exe == "-":
        return []
    import pefile
    pe = pefile.PE(exe, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    return sorted((IMAGE_BASE + e.struct.BeginAddress, IMAGE_BASE + e.struct.EndAddress)
                  for e in pe.DIRECTORY_ENTRY_EXCEPTION)


def classify_index(d):
    """d = 線形区間の最後の定義 (va, mnem, ops, text)。戻り値 (kind, value)。kind は const / range / unknown。"""
    if d is None:
        return ("unknown", "線形区間に定義なし (分岐先・関数入口由来・64bit 未確定)")
    _, mnem, ops, _ = d
    dst = ops[0] if ops else ""
    if not is_full32_64(dst):
        return ("unknown", "部分レジスタへの書込み (%s %s)" % (mnem, dst))
    if mnem == "xor" and len(ops) == 2 and ops[0] == ops[1]:
        return ("const", 0)
    if mnem == "mov" and len(ops) == 2 and re.fullmatch(r"0x[0-9a-f]+|[0-9]+", ops[1]):
        return ("const", int(ops[1], 0))
    if mnem == "movzx" and len(ops) == 2:
        src = ops[1]
        if src.startswith("BYTE") or (canon(src) and reg_width(src) == 8):
            return ("range", (0, 255, "movzx byte"))
        if src.startswith("WORD") or (canon(src) and reg_width(src) == 16):
            return ("range", (0, 65535, "movzx word"))
    if mnem in ("movsx", "movsxd") and len(ops) == 2 and ops[1].startswith("BYTE"):
        return ("range", (-128, 127, "movsx byte"))
    if mnem in ("movsx", "movsxd") and len(ops) == 2 and ops[1].startswith("WORD"):
        return ("range", (-32768, 32767, "movsx word"))
    if mnem == "and" and len(ops) == 2 and re.fullmatch(r"0x[0-9a-f]+", ops[1]):
        imm = int(ops[1], 16)
        if imm < 2 ** 63:
            return ("range", (0, imm, "and imm"))
    if mnem == "shr" and len(ops) == 2 and re.fullmatch(r"0x[0-9a-f]+|[0-9]+", ops[1]):
        k = int(ops[1], 0)
        bits = 64 if reg_width(dst) == 64 else 32
        if 0 < k < bits:
            return ("range", (0, 2 ** (bits - k) - 1, "shr %d" % k))
    if reg_width(dst) == 32:
        return ("unknown", "%s (32bit 零拡張: [0,2^32))" % mnem)
    return ("unknown", "%s (64bit・値域未確定)" % mnem)


def scan(dis_path, exe):
    lines = []
    for line in open(dis_path, errors="replace"):
        m = INS.match(line)
        if m and m.group(2).strip():
            lines.append((int(m.group(1), 16), m.group(2).strip()))
    parsed = [split_ins(t) for _, t in lines]
    funcs = load_pdata(exe)
    starts = [a for a, _ in funcs]
    pstart = set(starts)
    jt = set()
    for mnem, ops in parsed:
        if (mnem.startswith("j") or mnem in ("call", "loop")) and ops and JT_OP.match(ops[0]):
            jt.add(int(ops[0].split()[0], 16))
    # 線形区間の境界: pdata 開始・分岐先・直前が ret/jmp/int3/ud2/hlt
    bound, key_of = [], []
    chunk, prev_int3 = None, True
    for idx, (va, text) in enumerate(lines):
        prev = parsed[idx - 1][0] if idx > 0 else "ret"
        bound.append(va in pstart or va in jt or prev in BOUNDARY_PREV)
        # 関数キー: pdata 内はその開始 / pdata 外は int3 の後の最初の命令 (推定)
        i = bisect.bisect_right(starts, va) - 1
        if i >= 0 and funcs[i][0] <= va < funcs[i][1]:
            key_of.append(("p", funcs[i][0]))
            prev_int3 = False
            continue
        if parsed[idx][0] == "int3":
            prev_int3 = True
            key_of.append(("c", None))
            continue
        if prev_int3:
            chunk, prev_int3 = va, False
        key_of.append(("c", chunk))
    # 流れ非依存: 関数キーごとに、各レジスタの全定義が lea-rip なら X の集合
    defs_all = defaultdict(lambda: defaultdict(list))
    for idx, (va, text) in enumerate(lines):
        mnem, ops = parsed[idx]
        xv = None
        if mnem == "lea" and len(ops) == 2:
            mp = mem_parts(ops[1])
            cm = COMMENT.search(text)
            if mp and mp["rip"] and cm:
                xv = int(cm.group(1), 16)
        for r in writes(mnem, ops):
            defs_all[key_of[idx]][r].append(xv if (xv is not None and canon(ops[0]) == r) else None)
    flow_x = {}
    for k, regs in defs_all.items():
        flow_x[k] = {r: sorted(set(v)) for r, v in regs.items() if all(x is not None for x in v)}
    # 線形走査
    state_x, last_def, cands, seen = {}, {}, [], set()
    stats = {"idx_ops": 0, "base_pairs": 0, "x_pairs": 0}
    for idx, (va, text) in enumerate(lines):
        if bound[idx]:
            state_x.clear()
            last_def.clear()
        mnem, ops = parsed[idx]
        key = key_of[idx]
        for op in ops:
            mp = mem_parts(op)
            if not mp or mp["rip"]:
                continue
            pairs = []
            if mp["S"] or len(mp["U"]) == 2:
                stats["idx_ops"] += 1
            if mp["S"]:
                if len(mp["S"]) == 1 and len(mp["U"]) == 1:
                    pairs.append((mp["U"][0], mp["S"][0][0], mp["S"][0][1]))
            elif len(mp["U"]) == 2:
                pairs.append((mp["U"][0], mp["U"][1], 1))
                pairs.append((mp["U"][1], mp["U"][0], 1))
            for base, idx_reg, sc in pairs:
                if base == idx_reg:
                    continue
                stats["base_pairs"] += 1
                srcs = []
                if base in state_x:
                    srcs.append(("線形", state_x[base]))
                srcs.extend(("流れ非依存", x) for x in flow_x.get(key, {}).get(base, []))
                if srcs:
                    stats["x_pairs"] += 1
                for method, X in srcs:
                    nS = {}
                    for s in SLOTS:
                        d = s - X - mp["disp"]
                        nS[s] = d // sc if d % sc == 0 else None
                    if all(v is None for v in nS.values()):
                        continue
                    if (va, op, X) in seen:
                        continue
                    seen.add((va, op, X))
                    cands.append({"va": va, "key": key, "mnem": mnem, "text": text, "method": method, "X": X,
                                  "disp": mp["disp"], "sc": sc, "base": base, "idx": idx_reg, "nS": nS,
                                  "def": last_def.get(idx_reg), "op": op,
                                  "acc": access(mnem, ops, op)})
        # 状態更新
        if mnem == "call":
            for r in CALLER_SAVED:
                state_x.pop(r, None)
                last_def.pop(r, None)
            continue
        for r in writes(mnem, ops):
            if mnem == "lea" and len(ops) == 2 and canon(ops[0]) == r:
                mp = mem_parts(ops[1])
                cm = COMMENT.search(text)
                if mp and mp["rip"] and cm and not mp["U"] and not mp["S"]:
                    state_x[r] = int(cm.group(1), 16)
                    last_def[r] = (va, mnem, ops, text)
                    continue
            if mnem == "mov" and len(ops) == 2 and canon(ops[0]) == r and canon(ops[1]) in state_x \
                    and is_full32_64(ops[0]) and is_full32_64(ops[1]):
                state_x[r] = state_x[canon(ops[1])]
            else:
                state_x.pop(r, None)
            last_def[r] = (va, mnem, ops, text)
    return lines, cands, stats


def access(mnem, ops, op):
    if mnem == "lea":
        return "アドレス生成"
    if ops and ops[0] == op:
        if mnem in ("xchg", "add", "sub", "and", "or", "xor", "inc", "dec", "adc", "sbb", "neg", "not", "xadd",
                    "cmpxchg", "bts", "btr", "btc"):
            return "RW"
        return "W"
    return "R"


def index_desc(kind, val):
    if kind == "const":
        return "定数 %d" % val
    if kind == "range":
        return "%s の値域 [%d,%d]" % (val[2], val[0], val[1])
    return "値域未確定: %s" % val


def verdict(c):
    kind, val = classify_index(c["def"])
    ns = [n for n in c["nS"].values() if n is not None]
    if c["method"] == "流れ非依存":
        return "届き得る", "基底が流れ非依存 (入口由来を排除できず)", index_desc(kind, val)
    if kind == "const":
        if any(n == val for n in ns):
            return "届く", "定数一致", "定数 %d" % val
        return "届かない", "定数不一致", "定数 %d (届く n=%s)" % (val, ",".join(str(n) for n in ns))
    if kind == "range":
        lo, hi, label = val
        if any(lo <= n <= hi for n in ns):
            return "届き得る", "値域内", "%s の値域 [%d,%d] 内" % (label, lo, hi)
        return "届かない", "値域外", "%s の値域 [%d,%d] の外 (届く n=%s)" % (label, lo, hi, ",".join(str(n) for n in ns))
    m = min(abs(n) for n in ns)
    if m < 2 ** 16:
        return "届き得る", "値域未確定 |n|<2^16", "値域未確定: %s" % val
    return "届き得る", "値域未確定 |n|>=2^16", "値域未確定: %s" % val


def main():
    lines, cands, stats = scan(sys.argv[1], sys.argv[2])
    print("# lea_index_scan: 命令 %d 件・添字付きメモリ式 %d 件・評価した基底・添字の組 %d 件・うち基底が lea-rip の X を持つ組 %d 件・候補 %d 件 (n が整数になる組。同一 (VA,式,X) は 1 件)"
          % (len(lines), stats["idx_ops"], stats["base_pairs"], stats["x_pairs"], len(cands)))
    tally = defaultdict(int)
    mtally = defaultdict(int)
    for c in cands:
        v, cat, why = verdict(c)
        tally[(v, cat, c["acc"])] += 1
        mtally[(c["method"], v)] += 1
        nstr = " ".join("%x:%d" % (s, c["nS"][s]) for s in SLOTS if c["nS"][s] is not None)
        idef = c["def"][3] if c["def"] else "-"
        print("%x\t%s\t%s\tX=%x\tdisp=0x%x\tsc=%d\tbase=%s\tidx=%s\t%s\t%s\t%s\t%s\tn[%s]\tidxdef=%s\tacc=%s" % (
            c["va"], c["key"][0] + ("%x" % c["key"][1] if c["key"][1] else ""), c["method"], c["X"],
            c["disp"], c["sc"], c["base"], c["idx"], c["text"], v, cat, why, nstr, idef, c["acc"]))
    print("# 集計 (判定・理由の種別・アクセス)")
    for k, v in sorted(tally.items()):
        print("# %s\t%s\t%s\t%d" % (k[0], k[1], k[2], v))
    print("# 方式別 (基底 X の求め方・判定)")
    for k, v in sorted(mtally.items()):
        print("# %s\t%s\t%d" % (k[0], k[1], v))


if __name__ == "__main__":
    main()
