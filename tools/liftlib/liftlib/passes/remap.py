"""remap.py — VA remap / グローバル data 敷設 / extern global の実体化。

- gdata(mod, img, mode): `@global_var_<va>` を PE の実バイトで定義する。
    mode="external": external 宣言のみ (FA/KH 型: シンボルとして参照される .rdata 定数)
    mode="all"     : 既存定義も PE バイトで置換 (OTT ir6_gdata 型。RetDec の定義は 0 初期化が混ざる)
  shift_base が指定されると VA を (VA - base + newbase) に読み替えた名前で出力 (OTT: 0x30000000 系)。
- shift_va(text, base, newbase, maxv): IR 内の VA 直値 / @global_var_ 名を新ベースへ平行移動 (ir6_shift 互換)
"""
import re

TYPE_BYTES = {"i8": 1, "i16": 2, "i32": 4, "i64": 8, "i128": 16, "i256": 32, "float": 4, "double": 8, "ptr": 8}


def _esc(b):
    out = []
    for v in b:
        if 32 <= v < 127 and v not in (0x22, 0x5C):
            out.append(chr(v))
        else:
            out.append("\\%02X" % v)
    return "".join(out)


def gdata(mod, img, mode="external", min_size=8, base=None, newbase=None, log=None):
    """module item の `@global_var_*` 定義行を書換える。返値: {"replaced": n, "added": n}"""
    log = log if log is not None else []
    base = img.base if base is None else base
    n_rep = n_add = 0
    have = set()
    for idx, it in enumerate(mod.items):
        if not isinstance(it, str):
            continue
        m = re.match(r"^(@global_var_([0-9a-f]+)) = (.*)$", it)
        if not m:
            continue
        name, hexva, rest = m.group(1), m.group(2), m.group(3)
        va = int(hexva, 16)
        have.add(name)
        is_ext = " external " in (" " + rest + " ") or rest.startswith("external")
        if mode == "external" and not is_ext:
            continue
        sz = _decl_size(rest, min_size)
        rd_va = va if newbase is None else va - newbase + base
        b = img.read(rd_va, sz)
        quals = "constant" if re.search(r"\bconstant\b", rest) else "global"
        mod.items[idx] = '%s = local_unnamed_addr %s [%d x i8] c"%s", align 16' % (name, quals, sz, _esc(b))
        n_rep += 1
    # 参照のみで定義の無い global (declare 忘れ) を補う
    refs = set()
    for it in mod.items:
        if hasattr(it, "render"):
            for ln in it.render():
                for mm in re.finditer(r"@global_var_([0-9a-f]+)\b", ln):
                    refs.add("@global_var_" + mm.group(1))
    for name in sorted(refs - have):
        va = int(name[len("@global_var_"):], 16)
        rd_va = va if newbase is None else va - newbase + base
        b = img.read(rd_va, min_size)
        mod.add_global('%s = local_unnamed_addr constant [%d x i8] c"%s", align 16' % (name, min_size, _esc(b)))
        n_add += 1
    return {"replaced": n_rep, "added": n_add}


def _decl_size(rest, min_size):
    m = re.search(r"\[(\d+) x (i8|i16|i32|i64|i128|float|double)\]", rest)
    if m:
        return max(int(m.group(1)) * TYPE_BYTES[m.group(2)], min_size)
    m = re.search(r"(?:constant|global)\s+(i\d+|float|double|ptr)\b", rest)
    if m:
        return max(TYPE_BYTES.get(m.group(1), min_size), min_size)
    return min_size


def shift_va(text, base=0x180000000, newbase=0x30000000, maxv=0x1803FFFFF):
    """ir6_shift.py 互換: @global_var_ 名と i64 VA 直値を平行移動。返値 (text, n_numeric)"""
    shift = base - newbase

    def rename_sym(m):
        v = int(m.group(1), 16)
        if base <= v <= maxv:
            return "@global_var_%x" % (v - shift)
        return m.group(0)
    text = re.sub(r"@global_var_(18[0-9a-fA-F]{6,10})\b", rename_sym, text)
    n = [0]

    def rep_num(m):
        if m.group(1) == "0":
            return m.group(0)
        v = int(m.group(1), 0)
        if base <= v <= maxv:
            n[0] += 1
            return "i64 " + str(v - shift)
        return m.group(0)
    text = re.sub(r"i64 (0x1[0-9a-fA-F]{8,12}|[0-9]{9,11})", rep_num, text)
    return text, n[0]


def gdata_legacy(text, img, datab=0x30000000):
    """[vendored] tools/m6/ir6_gdata.py 互換: 全 @global_var_* 定義を PE 実データ (VA shift 済み) の
    `constant [N x i8] c"..."` に置換し, 参照のみのものを `global [8 x i8]` で追加。IR テキスト完全一致用。"""
    def to_llvm(b):
        esc = ''
        for v in b:
            esc += chr(v) if 32 <= v < 127 and v not in (34, 92) else '\\%02x' % v
        return '"' + esc + '"'

    def read_bytes(rva, sz):
        b = img.read(img.base + rva, sz)
        return b

    names = sorted(set(re.findall(r"@global_var_([0-9a-f]+)\b", text)))
    ln = text.split('\n')
    out = []
    replaced = 0
    for l in ln:
        m = re.match(r"^(@global_var_([0-9a-f]+)) = .*$", l)
        if m:
            va = int(m.group(2), 16)
            rva = va - datab
            tm = re.match(r"@[\w.$-]+ = (local_unnamed_addr )?(?:\w+ )?(\w+) ", l)
            t = tm.group(2) if tm else 'i8'
            sz = 8
            msz = re.search(r"\[(\d+) x (i8|i16|i32|i64|i128)\]", l)
            if msz:
                mul = dict(i8=1, i16=2, i32=4, i64=8, i128=16)[msz.group(2)]
                sz = int(msz.group(1)) * mul
            else:
                sz = {'i8': 1, 'i16': 2, 'i32': 4, 'i64': 8, 'i128': 16, 'i256': 32}.get(t, 8)
            b = read_bytes(rva, sz)
            out.append('%s = constant [%d x i8] c%s' % (m.group(1), sz, to_llvm(b)))
            replaced += 1
            continue
        out.append(l)
    text2 = '\n'.join(out)
    have = set(re.findall(r"(?m)^@global_var_([0-9a-f]+) = ", text2))
    add = []
    for nm in names:
        if nm in have:
            continue
        va = int(nm, 16)
        add.append('@global_var_%s = global [8 x i8] c%s' % (nm, to_llvm(read_bytes(va - datab, 8))))
    text2 = text2.rstrip() + '\n' + '\n'.join(add) + '\n'
    return text2, dict(replaced=replaced, added=len(add))
