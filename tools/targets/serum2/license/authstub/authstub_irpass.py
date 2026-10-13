#!/usr/bin/env python3
"""SR-2b authstub IR pass — Serum2 認可機構の中性化 (N1–N3) を RetDec raw .ll に適用する。

対象: CAB-71 REPORT §7 のうち本体 3 点 (N1–N3) + 0x800010 host 通知経路 (N2b)。
方式: !insn.addr メタデータ (機械語 VA) を鍵にした構造的差し替え。
  - br_force    : 条件分岐を指定 target への無条件 br に置換 (デモ経路への辺を除去)
  - store_const : 指定 store の値オペランドを定数に置換 (demo bit +0x22792 の常時 0 化)
全ルールは --check で適用後の到達性 (CFG BFS) を機械検証する:
  - 0x1800c2b50: demo bit への store が全て定数 0 / 0x800010 通知ブロックが到達不能
  - 0x1800c6090: demo マーカ書込ブロックが到達不能
  - 0x18004fad0: demo ダイアログ (復元打ち切り) ブロックが到達不能 / 復元本体が到達可能
  - 0x180056670: 1 行も変更しない (音声経路 N4 の無変更保証)

usage:
  python3 authstub_irpass.py in.ll out.ll --report patch_report.json [--check]
"""
import argparse, json, os, re, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'liftlib'))
from liftlib.passes.fp_bind import replace_lines, replace_at, site_at, bind_load_at, insert_after, fn_span

# ---- 差し替え点テーブル (実測座標。machine 側対応は mpatch.py と対) ----
# at      : 分岐 / store の機械語 VA
# fn      : 所属関数 VA
# kind    : br_force | store_const
# target  : br_force の跳び先 (licensed 経路)
# why     : REPORT 対応
RULES = [
    dict(id="N1",      fn=0x18004fad0, at=0x18004fbdd, kind="br_force",    target=0x18004fe1c,
         why="DSP setState: demoVersion キー検出→ダイアログ+復元打ち切り を 不検出扱い (復元続行)"),
    dict(id="N2a-1",   fn=0x1800c2b50, at=0x1800c2cfe, kind="store_const", const=0,
         why="Controller setState: demo bit (+0x22792) = ¬marker の store を常時 0 に"),
    dict(id="N2a-2",   fn=0x1800c2b50, at=0x1800c2d42, kind="store_const", const=0,
         why="Controller setState: productVersion<2.0.20 時の demo bit=1 store を常時 0 に"),
    dict(id="N2b-1",   fn=0x1800c2b50, at=0x1800c2d04, kind="br_force",    target=0x1800c2d06,
         why="Controller setState: marker¬=true→0x800010 通知経路 への辺を除去 (version 比較へ直行)"),
    dict(id="N2b-2",   fn=0x1800c2b50, at=0x1800c2d59, kind="br_force",    target=0x1800c2f08,
         why="Controller setState: bit 再読出し後の通知分岐を licensed 側 (skip) に固定"),
    dict(id="N3",      fn=0x1800c6090, at=0x1800c687b, kind="br_force",    target=0x1800c68ba,
         why="Controller getState: demo bit==1 時の demo マーカ書込 (key 0xfc8950, 値 false) を常時 skip"),
]
# 到達性検証 (適用後で成立すべき性質)
CHECKS = dict(
    unreachable={  # fn VA -> [ブロック先頭 VA ...] 適用後 到達不能であるべき
        0x1800c2b50: [0x1800c2d5f, 0x1800c2d6f],   # 0x800010 通知 (deferred OR 経路)
        0x1800c6090: [0x1800c687d],                # demo マーカ書込
        0x18004fad0: [0x18004fbe3],                # demo ダイアログ + 復元打ち切り
    },
    reachable={  # fn VA -> [ブロック先頭 VA ...] 適用後 到達可能であるべき
        0x18004fad0: [0x18004fe1c],                # 正常復元経路
        0x1800c2b50: [0x1800c2ce4, 0x1800c2f08],   # demo bit block 入口 / 合流
    },
    demo_bit_stores={0x1800c2b50: 2},              # +0x22792 への store 数 (全て const 0 であること)
    untouched_fns=[0x180056670],                   # N4: 音声経路は 1 行も変更しない
)

BR_RE = re.compile(r'^(\s*)br i1 (.*?), label %([A-Za-z0-9_.]+), label %([A-Za-z0-9_.]+)(,\s*!insn\.addr\s+!\d+)?\s*$')
BRL_RE = re.compile(r'^(\s*)br label %([A-Za-z0-9_.]+)')
STORE_RE = re.compile(r'^(\s*)store\s+(\S+)\s+(%[A-Za-z0-9_.]+|true|false|null|\-?\d+),\s*(.+)$')
LABEL_RE = re.compile(r'^([A-Za-z0-9_.]+):\s*(?:;.*)?$')
META_RE = re.compile(r'!\{i64 (\d+)\}')


def parse_meta(lines):
    """メタデータテーブル: '!N = !{i64 VA}' → {N: VA}"""
    meta = {}
    for l in lines:
        m = re.match(r'^!(\d+)\s*=\s*!\{i64 (\d+)\}', l.strip())
        if m:
            meta[m.group(1)] = int(m.group(2))
    inv = {}
    for k, v in meta.items():
        inv.setdefault(v, []).append(k)
    return meta, inv


def fn_ranges(lines):
    """define 行 → (name, start, end) の列挙"""
    out = []
    cur = None
    for i, l in enumerate(lines):
        if l.startswith('define'):
            m = re.search(r'@function_([0-9a-f]+)', l)
            cur = (m.group(1), i) if m else None
        elif l.startswith('}') and cur:
            out.append((int(cur[0], 16), cur[1], i))
            cur = None
    return out


def line_meta_name(l):
    m = re.search(r'!insn\.addr\s+!(\d+)', l)
    return m.group(1) if m else None


def apply_rules(lines, report):
    meta, inv = parse_meta(lines)
    ranges = fn_ranges(lines)
    changed = []
    for rule in RULES:
        at, fnva, kind = rule['at'], rule['fn'], rule['kind']
        mr = inv.get(at)
        if not mr:
            raise SystemExit(f"rule {rule['id']}: insn.addr VA {at:#x} がメタデータに無い (lift 差異?)")
        hits = 0
        for (fva, s, e) in ranges:
            if fva != fnva:
                continue
            for i in range(s + 1, e):
                ln = lines[i]
                mn = line_meta_name(ln)
                if mn not in mr:
                    continue
                if kind == 'br_force':
                    m = BR_RE.match(ln)
                    if not m:
                        continue
                    tgt_lab = 'dec_label_pc_%x' % rule['target']
                    if m.group(3) == tgt_lab or m.group(4) == tgt_lab:
                        new = f"{m.group(1)}br label %{tgt_lab}{m.group(5) or ''}"
                        report.setdefault('before', {})[rule['id']] = ln.strip()
                        lines[i] = new
                        report.setdefault('after', {})[rule['id']] = new.strip()
                        hits += 1
                elif kind == 'store_const':
                    m = STORE_RE.match(ln)
                    if not m:
                        continue
                    val = m.group(3)
                    if val.lstrip('-').isdigit() and int(val) == rule['const']:
                        continue  # 既に定数
                    new = f"{m.group(1)}store {m.group(2)} {rule['const']}, {m.group(4)}"
                    report.setdefault('before', {})[rule['id']] = ln.strip()
                    lines[i] = new
                    report.setdefault('after', {})[rule['id']] = new.strip()
                    hits += 1
        if hits != 1:
            raise SystemExit(f"rule {rule['id']} @{at:#x}: apply count = {hits} (expect 1)")
        changed.append(rule['id'])
    report['applied'] = changed
    return lines


def cfg_of(lines, s, e):
    """fn [s,e] のブロック隣接 + store 情報を抽出"""
    blocks = collections.OrderedDict()   # label -> [line idx...]
    order = []
    cur = None
    for i in range(s + 1, e):
        l = lines[i]
        m = LABEL_RE.match(l.strip())
        if m and not l.startswith('  '):
            cur = m.group(1)
            blocks[cur] = []
            order.append(cur)
        elif cur is not None:
            blocks[cur].append(i)
    entry = order[0] if order else None
    # ブロック先頭行の位置 (label 行自身) も保持
    label_line = {}
    cur = None
    for i in range(s + 1, e):
        l = lines[i]
        m = LABEL_RE.match(l.strip())
        if m and not l.startswith('  '):
            cur = m.group(1)
            label_line[cur] = i
    return blocks, entry, label_line


def block_succ(lines, idxs):
    """ブロック内終端器の successors (label 名)"""
    succ = []
    for i in idxs:
        l = lines[i]
        m = BR_RE.match(l)
        if m:
            succ += [m.group(3), m.group(4)]
            continue
        m = BRL_RE.match(l)
        if m:
            succ.append(m.group(2))
            continue
        m = re.match(r'\s*br i1 .*?, label %([A-Za-z0-9_.]+), label %([A-Za-z0-9_.]+)', l)
        if m:
            succ += [m.group(1), m.group(2)]
            continue
        m = re.match(r'\s*br label %([A-Za-z0-9_.]+)', l)
        if m:
            succ.append(m.group(1))
    return succ


def reachable_set(lines, s, e):
    blocks, entry, _ = cfg_of(lines, s, e)
    seen = set()
    dq = collections.deque([entry])
    while dq:
        b = dq.popleft()
        if b in seen or b not in blocks:
            continue
        seen.add(b)
        for t in block_succ(lines, blocks[b]):
            dq.append(t)
    return blocks, seen


def run_check(lines, report):
    """適用後の到達性・store 形状を検証 (失敗は SystemExit)"""
    ranges = {fva: (s, e) for (fva, s, e) in fn_ranges(lines)}
    ok = {}
    for fnva, blk_vas in CHECKS['unreachable'].items():
        s, e = ranges[fnva]
        blocks, reach = reachable_set(lines, s, e)
        for bv in blk_vas:
            lab = 'dec_label_pc_%x' % bv
            if lab in blocks and lab in reach:
                raise SystemExit(f"check fail: {fnva:#x} block {bv:#x} ({lab}) が到達可能のまま")
        ok[f'unreachable@{fnva:#x}'] = [hex(b) for b in blk_vas]
    for fnva, blk_vas in CHECKS['reachable'].items():
        s, e = ranges[fnva]
        blocks, reach = reachable_set(lines, s, e)
        for bv in blk_vas:
            lab = 'dec_label_pc_%x' % bv
            if lab not in blocks or lab not in reach:
                raise SystemExit(f"check fail: {fnva:#x} block {bv:#x} ({lab}) が到達不能")
        ok[f'reachable@{fnva:#x}'] = [hex(b) for b in blk_vas]
    # demo bit (+0x22792 = 141202) store: 全て const 0 かつ個数一致
    for fnva, expect_n in CHECKS['demo_bit_stores'].items():
        s, e = ranges[fnva]
        # ptr 名を収集 (%x = add i64 %arg1, 141202 → %y = inttoptr i64 %x to i8*)
        ptrs = set()
        for i in range(s + 1, e):
            m = re.match(r'\s*%(\S+) = add i64 %arg1, 141202\b', lines[i])
            if not m:
                continue
            base = m.group(1)
            for j in range(i + 1, min(i + 4, e)):
                m2 = re.match(r'\s*%(\S+) = inttoptr i64 %' + re.escape(base) + r' to i8\*', lines[j])
                if m2:
                    ptrs.add('%' + m2.group(1))
        n = 0
        for i in range(s + 1, e):
            for p in ptrs:
                mk = re.match(r'\s*store i8 (\S+), i8\* ' + re.escape(p) + r'\b', lines[i])
                if mk:
                    if mk.group(1) != '0':
                        raise SystemExit(f"check fail: demo bit store @{fnva:#x} L{i+1} が定数 0 でない: {lines[i].strip()}")
                    n += 1
        if n != expect_n:
            raise SystemExit(f"check fail: demo bit store 数 {n} (expect {expect_n}) @{fnva:#x}")
        ok[f'demo_bit_stores@{fnva:#x}'] = f'{n}/{expect_n} all const-0 (ptrs={",".join(sorted(ptrs))})'
    # 0x800010 即値が到達コードに残っていないか (0x1800c2b50)
    s, e = ranges[0x1800c2b50]
    blocks, reach = reachable_set(lines, s, e)
    for b, idxs in blocks.items():
        if b in reach:
            for i in idxs:
                if '8388624' in lines[i]:
                    raise SystemExit(f"check fail: 0x800010 が到達ブロック {b} に残存 L{i+1}")
    ok['imm_0x800010_reachable'] = 'none'
    report['check'] = ok
    return report


# ハーネス用 liftfix (本体 diff とは分離。RetDec が callee の caller-stack 書込み / FP 戻り値を
# 未定義 alloca 読みに落とした箇所を実行可能にする束縛 — lift fidelity gap L2/L3 の回避)。
# 適用対象は base 修復後の IR。各ルール: (fn, パターン) → 置換。
LIFTFIX_DECL = [
    "@__authstub_dbl_ret0 = external global i128 ; LF2: DSP setState の version double 戻り (harness C で定義)",
]

def apply_liftfix(lines, report):
    """base 後 IR に対する束縛。全ルール exactly-1 でなければ失敗。"""
    applied = []
    C = 0x1800c2b50  # controller setState
    D = 0x18004fad0  # DSP setState

    # LF1: tag 文字列 len (base が undef alloca 読みを xor 0 に fold。
    # machine は call 後に [rbp-0x28] を読む → 呼出後に mock が書く global から読む)
    replace_at(lines, C, 0x1800c2c1f, r'\s*%\S+ = trunc i128 %\S+ to i64, ',
               ['  %36 = load i64, ptr @__authstub_str_len0, !insn.addr !2583 '
                '; LIFTFIX LF1 (旧: trunc of undef-fold)'])
    applied.append('LF1')

    # LF5/LF6: DOM root ポインタ (alloca 配置が machine と異なるため global に束縛)
    bind_load_at(lines, C, 0x1800c2c94, '-72', '__authstub_doc_root', 'LF5')
    bind_load_at(lines, C, 0x1800c2ca4, '-72', '__authstub_doc_root', 'LF5')
    applied.append('LF5')
    bind_load_at(lines, D, 0x18004fbc6, '-80', '__authstub_doc_root', 'LF6')
    bind_load_at(lines, D, 0x18004fbd6, '-80', '__authstub_doc_root', 'LF6')
    applied.append('LF6')

    # LF7: tag 文字列 len (ctrl LF1 の DSP 版: alloca 配置差を global 束縛で吸収)
    bind_load_at(lines, D, 0x18004fb74, '-152', '__authstub_str_len0', 'LF7')
    applied.append('LF7')

    # LF2: `%3 = xor i128 0, 0` (base が入口 undef 読みを fold したもの。
    # ucomisd の version double 値) → global から読む (mock が callee 戻りを書込)
    replace_lines(lines, D, r'\s*%3 = xor i128 0, 0',
                  lambda m, l: ['  %3 = load i128, ptr @__authstub_dbl_ret0, !insn.addr !0 '
                                '; LIFTFIX LF2 (旧: xor i128 0,0)'], 1, 'LF2')
    applied.append('LF2')

    # LF3: ucomisd(0, v) 後の stale flag 再読出し (or cf,zf) を実 fcmp に置換
    # (machine: ucomisd xmm1=0, xmm0=v; ja → out。IR は entry 時の整数 flag を再利用するため誤分岐)
    # version 値は mock が呼出中に書く global から「比较時に」読む (entry hoist を避ける)
    i3 = site_at(lines, D, 0x18004fe46, r'\s*%\S+ = or i1 %cf\.0\.reload, %zf\.0\.reload')
    var = re.match(r'\s*(%\S+) = or i1', lines[i3]).group(1)
    lines[i3:i3 + 1] = [
        '  %lf3t = load i64, ptr @__authstub_dbl_ret0 ; LIFTFIX LF3 (stale flag → 実比較, 呼出後の値)',
        '  %lf3d = bitcast i64 %lf3t to double ; LIFTFIX LF3',
        f'  {var} = fcmp uge double %lf3d, 0.0 ; LIFTFIX LF3',
    ]
    applied.append('LF3')

    # LF4: 2 つ目の ucomisd (v <= 11.00001) の分岐が脱落しているため挿入
    # (machine: ucomisd xmm0, [11.00001]; ja 0x18004ff26)
    i = site_at(lines, D, 0x18004fe4c, r'\s*call void @__asm_ucomisd__1\(')
    cst = re.search(r'i128 %3, (i64 )?(\d+)\)', lines[i]).group(2)
    insert_after(lines, i, [
        '  %lf4t = load i64, ptr @__authstub_dbl_ret0 ; LIFTFIX LF4 (脱落分岐の復元, 呼出後の値)',
        '  %lf4d = bitcast i64 %lf4t to double ; LIFTFIX LF4',
        f'  %lf4c = bitcast i64 {cst} to double ; LIFTFIX LF4',
        '  %lf4 = fcmp ugt double %lf4d, %lf4c ; LIFTFIX LF4',
        '  br i1 %lf4, label %dec_label_pc_18004ff26, label %lf4_cont ; LIFTFIX LF4',
        '',
        'lf4_cont: ; LIFTFIX LF4',
    ])
    applied.append('LF4')

    # 宣言を先頭 (target triple 行の後) に足す
    ins = next(i for i, l in enumerate(lines) if l.startswith('target datalayout'))
    for k, d in enumerate(LIFTFIX_DECL):
        lines.insert(ins + 1 + k, d)
    report['liftfix'] = applied
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report', default=None)
    ap.add_argument('--check', action='store_true', help='適用後の到達性検証も実施')
    ap.add_argument('--liftfix', action='store_true', help='base 後 IR へのハーネス用束縛 (LF1/LF2) のみ適用')
    ap.add_argument('--with-rules', action='store_true', help='--liftfix と併用でルールも適用')
    ap.add_argument('--dry', action='store_true', help='適用せず現状での check のみ (before 記録)')
    a = ap.parse_args()
    lines = open(a.src).read().splitlines()
    report = {}
    n_before = len(lines)
    if a.liftfix:
        if a.with_rules:
            lines = apply_rules(lines, report)
    else:
        lines = apply_rules(lines, report)
    if a.liftfix:
        lines = apply_liftfix(lines, report)
    if a.check:
        run_check(lines, report)
    report['lines'] = {'src': n_before, 'dst': len(lines)}
    open(a.dst, 'w').write('\n'.join(lines) + '\n')
    if a.report:
        json.dump(report, open(a.report, 'w'), ensure_ascii=False, indent=1)
    print('authstub_irpass: applied=%s liftfix=%s check=%s -> %s' % (
        report.get('applied'), report.get('liftfix'), bool(a.check), a.dst))


if __name__ == '__main__':
    main()
