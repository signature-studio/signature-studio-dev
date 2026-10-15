"""p1_legacy.py — [vendored] tools/m6/ir6_pass.py [P1] (insn.addr 不要の旧鎖; IR 完全一致の参照実装)。
新規 P1 (p1.py) は機械語を正本にするが, addr の無い IR (ott_lift.ll 等) 向けに旧鎖を保持する。
"""
import sys, re
from collections import Counter


COMIS_RE = re.compile(
    r"^(\s*)call void @__asm_(v)?(u)?(comis)(s|d)(?:__(\d+))?\(({?[^)]*})\)(,?.*)$")
ARG2_RE = re.compile(r"i128 (%[\w.\-]+), (i128 %[\w.\-]+|i64 (?:%[\w.\-]+|-?\d+))")


def parse_call(l):
    m = re.match(r"^(\s*)call void @__asm_(v)?(u)?(comis)(s|d)(?:__(\d+))?\((.*?)\)(,?.*)$", l)
    if not m:
        return None
    mm = ARG2_RE.match(m.group(7))
    if not mm:
        return None
    a1 = mm.group(1)
    a2raw = mm.group(2)
    a2 = a2raw[len('i128 '):] if a2raw.startswith('i128') else a2raw[len('i64 '):]
    a2_is_i128 = a2raw.startswith('i128')
    a2_is_const = re.fullmatch(r'-?\d+', a2) is not None
    return (m.keras if False else None,
            m.group(2), m.group(4), a1, a2, a2_is_i128, a2_is_const)


def legacy_p1(text, quiet=True):
    lines = text.split('\n')
    sites = [i for i, l in enumerate(lines) if 'void @__asm_' in l and 'comis' in l]
    stats = {}
    stats['sites'] = len(sites)
    inserts = {}
    hits = Counter()
    for idx in sites:
        pc = parse_call(lines[idx])
        if pc is None:
            continue
        (mk, iss, kind, a1, a2, a2_is_i128, a2_is_const) = pc
        ty = 'double' if kind == 'd' else 'float'
        opx = []
        tag = 'pc%d' % idx
        opx.append(f"  %{tag}fs1 = trunc i128 {a1} to {'i64' if kind=='d' else 'i32'}")
        opx.append(f"  %{tag}f1 = bitcast {'i64' if kind=='d' else 'i32'} %{tag}fs1 to {ty}")
        if a2_is_const:
            opx.append(f"  %{tag}f2 = bitcast {'i32' if ty=='float' else 'i64'} {a2} to {ty}")
        else:
            opx.append(f"  %{tag}fs2 = trunc i128 {a2} to {'i64' if kind=='d' else 'i32'}")
            opx.append(f"  %{tag}f2 = bitcast {'i64' if kind=='d' else 'i32'} %{tag}fs2 to {ty}")
        opx.append(f"  %{tag}lt = fcmp ult {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}eq = fcmp ueq {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}uord = fcmp uno {ty} %{tag}f1, %{tag}f2")
        opx.append(f"  %{tag}cf = or i1 %{tag}lt, %{tag}uord")
        opx.append(f"  %{tag}zf = or i1 %{tag}eq, %{tag}uord")
        opx.append(f"  %{tag}pf = and i1 %{tag}uord, %{tag}uord")
        # (a) 直後の br
        repl = []
        j = idx + 1
        while j < min(idx + 13, len(lines)):
            l2 = lines[j]
            if re.match(r"^  br i1 %", l2):
                m2 = re.match(r"^  br i1 (i1 )?%([\w.\-]+), label", l2) or re.match(r"^  br i1 %([\w.\-]+), label", l2)
                if m2:
                    if m2.group(2).startswith('cf.'):
                        repl.append((j, m2.group(2), f"%{tag}cf"))
                        hits['br_cf'] += 1
                    elif m2.group(2).startswith('zf.'):
                        repl.append((j, m2.group(2), f"%{tag}zf"))
                        hits['br_zf'] += 1
                    elif m2.group(2).startswith('pf.'):
                        repl.append((j, m2.group(2), f"%{tag}pf"))
                        hits['br_pf'] += 1
                    elif re.search(r'cf\.|zf\.|pf\.', m2.group(2)):
                        repl.append((j, m2.group(2), f"%{tag}cf"))
                        hits['br_?'] += 1
                    else:
                        hits['br_other'] += 1
                break
            if re.match(r"^  %[\w.\-]+ = or i1 %[\w.\.-]+, %[\w.\.-]+$", l2):
                mm = re.match(r"^  %([\w.\-]+) = or i1 %([\w.\-]+), %([\w.\-]+)(.*)$", l2)
                a, b = mm.group(2), mm.group(3)
                if 'cf.' in a and 'zf.' in b:
                    repl.append((j, a, f"%{tag}cf"))
                    repl.append((j, b, f"%{tag}zf"))
                    hits['or_cfzf'] += 1
                    break
                elif 'zf.' in a and 'cf.' in b:
                    repl.append((j, a, f"%{tag}zf"))
                    repl.append((j, b, f"%{tag}cf"))
                    hits['or_zfcf'] += 1
                    break
            if re.match(r"^  call void @__asm_", l2):
                break
            j += 1
        if not repl:
            hits['no_branch'] += 1
            continue
        inserts[idx] = (opx, repl)
    stats['inserted'] = len(inserts)
    stats['hits'] = dict(hits)
    # repmap は挿入前の行番号 j で登録されているため, 挿入前の原行 lines[j] に適用してから挿入する (#3067)。
    # 旧名は % 無し (cf.N)・新名は % 付き (%pcNcf) なので, 旧名は % 付き・後続文字の境界付きで置換する。
    repmap = {}
    for (idx, repl) in inserts.values():
        for (j, old, new) in repl:
            repmap.setdefault(j, []).append((old, new))
    for j, repls in sorted(repmap.items()):
        ln = lines[j]
        for (old, new) in repls:
            ln = re.sub(r'%' + re.escape(old) + r'(?![\w.\-])', lambda _m, n=new: n, ln, count=1)
        lines[j] = ln
    out = []
    for i, l in enumerate(lines):
        if i in inserts:
            opx, repl = inserts[i]
            out += opx
            out.append(l)
        else:
            out.append(l)
    return '\n'.join(out), stats


PC_TAG_RE = re.compile(r"%pc(\d+)([a-z]+\d*)\b")


def canon_tags(text):
    """legacy_p1 の一時名 `%pc<入力行 index><接尾>` を出現順の番号 `%pc<k><接尾>` へ改名する (全単射の α 変換)。

    行 index は入力の空行数に依るため、#1664 (A7 の空行除去) で名前だけが変わる (分岐・命令の内容は不変)。
    IR 一致ゲート (ott.same) はこの改名だけを無視する。検査は tests/test_unit.py T26。
    """
    seen = {}

    def rep(m):
        k = seen.setdefault(m.group(1), len(seen))
        return "%%pc%d%s" % (k, m.group(2))

    return PC_TAG_RE.sub(rep, text)
