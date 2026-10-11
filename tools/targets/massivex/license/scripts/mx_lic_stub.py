#!/usr/bin/env python3
"""mx_lic_stub.py — MX-2 ライセンス stub IR pass (Massive X 1.7.1 VST3 win64)。

RetDec raw .ll (!insn.addr メタデータ付き) に対し、CAB-46 REPORT §6 N1-N3 の
中性化 (常時 activated / serial 常時 OK / subscription 常時通過) を適用する。
KH-9 lic_stub.py (VA 鍵による IR 後処理) + SR-2b authstub_irpass.py
(!insn.addr 鍵 + --check CFG 到達性機械検証) のパターンを踏襲。

差し替え点 (machine VA / 実測は license/work/zone_*.txt と REPORT §11):
  N1 evaluateRAS2ActivationState 0x18115de60 (Product::, this=arg1, 状態 this+0x31c)
    N1a 0x18115e038 br_force e056 : SystemID/AuthKey 未設定の早期 return を抑制
    N1b 0x18115e142 br_force e6d5 : SystemID 比較経路をskip ('SystemID OK' へ直行)
    N1c 0x18115e88d br_force e893 : 判定を必ず activated 側へ ('Activated RAS2 product'
                                    + this+0x31c = 3 @0x18115ea5c が無条件に実行される)
  N2 productCheckSerialNumber 0x1805b3510 (tError 返し, bool& = arg4)
    N2a 0x1805b36d6 br_force 36dc : engine 未初期化 error 3 を抑制
    N2b 0x1805b36e9 br_force 36ef : engine flag error 7 を抑制
    N2c 0x1805b37d5 br_force 3843 : serial 比較結果経路に固定 (serial 追加経路を到達不能化)
    N2d 0x1805b3843 store_const 1 : *bool& = 1 (matched) — 比較結果 %96 を 1 に置換
    N2e 0x1805b3819 store_const 1 : serial 追加経路の *bool& store も 1 に (防御)
  N3 productGetSubscription 0x1805b3ad0 (tError 返し, Subscription& = arg3)
    N3a 0x1805b3c99 br_force 3c9f : error 3 抑制
    N3b 0x1805b3cac br_force 3cb2 : error 7 抑制
    N3c 0x1805b3cd7 br_force cf7  : error 0xb (arg4=false) 抑制
    N3d 0x1805b3d88 br_force 3d8a : subscription 無し error 0x12 を抑制
                                    (常時 tError=0 経路: 文字列 copy + type + 成功)

--check は適用後の CFG 到達性を機械検証する:
  - evaluateRAS2: 'SystemID or AuthKey not set' (0x18115e222) / SystemID 比較 (0x18115e148)
    / 非 activated フォールバック (0x18115ea68) が到達不能、activated block (0x18115e893)
    と state=3 store (0x18115ea5c, [arg1+796]) が到達可能
  - checkSerial: serial 追加経路 (0x1805b37dc) と overflow (0x1805b3890/389a) が到達不能、
    *arg4 store 2 箇所が全て定数 1
  - getSubscription: error 0x12 block (0x1805b3dc4) が到達不能、成功 tail (0x1805b3e0a) と
    epilogue (0x1805b3dad) が到達可能、r15=0 store が到達 block に存在

usage:
  python3 mx_lic_stub.py in.ll out.ll --report report.json [--check]
"""
import argparse
import collections
import json
import re
import sys

# ---- 差し替え点テーブル (machine VA。zone_*.txt / REPORT §11 実測) ----
RULES = [
    # id, fn, at(VA), kind, target(label)/const, why
    dict(id='N1a', fn=0x18115de60, at=0x18115e038, kind='br_force', target='dec_label_pc_18115e056',
         why='SystemID/AuthKey 未設定早期return を抑制 (常に RAS 評価へ)'),
    dict(id='N1b', fn=0x18115de60, at=0x18115e142, kind='br_force', target='dec_label_pc_18115e6d5',
         why='SystemID 比較経路をskip、SystemID OK ログへ直行'),
    dict(id='N1c', fn=0x18115de60, at=0x18115e88d, kind='br_force', target='dec_label_pc_18115e893',
         why='最終判定を必ず activated 側へ (Activated RAS2 product + state=3)'),
    dict(id='N2a', fn=0x1805b3510, at=0x1805b36d6, kind='br_force', target='dec_label_pc_1805b36dc',
         why='engine 未初期化 error 3 を抑制'),
    dict(id='N2b', fn=0x1805b3510, at=0x1805b36e9, kind='br_force', target='dec_label_pc_1805b36ef',
         why='engine flag error 7 を抑制'),
    dict(id='N2c', fn=0x1805b3510, at=0x1805b37d5, kind='br_force', target='dec_label_pc_1805b3843',
         why='serial 比較結果経路に固定 (serial 追加経路を到達不能化)'),
    dict(id='N2d', fn=0x1805b3510, at=0x1805b3843, kind='store_const', const=1,
         why='*bool& = 1 (serial matched 常時 true)'),
    dict(id='N2e', fn=0x1805b3510, at=0x1805b3819, kind='store_const', const=1,
         why='serial 追加経路の *bool& store も 1 (防御・N2c 後は到達不能)'),
    dict(id='N3a', fn=0x1805b3ad0, at=0x1805b3c99, kind='br_force', target='dec_label_pc_1805b3c9f',
         why='error 3 抑制'),
    dict(id='N3b', fn=0x1805b3ad0, at=0x1805b3cac, kind='br_force', target='dec_label_pc_1805b3cb2',
         why='error 7 抑制'),
    dict(id='N3c', fn=0x1805b3ad0, at=0x1805b3cd7, kind='br_force', target='dec_label_pc_1805b3cf7.preheader',
         why='error 0xb (arg4=false) 抑制'),
    dict(id='N3d', fn=0x1805b3ad0, at=0x1805b3d88, kind='br_force', target='dec_label_pc_1805b3d8a',
         why='subscription 無し error 0x12 を抑制 (常時成功経路)'),
]

# ---- 適用後検証 (到達性) ----
CHECKS = dict(
    unreachable={  # fn VA -> [block 先頭 VA ...] (存在する場合のみ到達不能を要求)
        0x18115de60: [0x18115e03a, 0x18115e148, 0x18115e222, 0x18115ea68],
        # 37dc = serial 追加経路。3890/389a はログ文字列 dealloc の共有 fail-fast
        # 経路 (0x1805b3667 jae) からも到達するため到達不能要件から除外 (実測)
        0x1805b3510: [0x1805b37dc],
        0x1805b3ad0: [0x1805b3dc4],
    },
    reachable={
        0x18115de60: [0x18115e893, 0x18115eaa9],
        0x1805b3510: [0x1805b3843, 0x1805b382c],
        0x1805b3ad0: [0x1805b3d8a, 0x1805b3e0a, 0x1805b3dad],
    },
    const_stores=[  # (fn VA, insn VA, type, const) — store が定数であること
        (0x1805b3510, 0x1805b3843, 'i8', 1),
        (0x1805b3510, 0x1805b3819, 'i8', 1),
        (0x18115de60, 0x18115ea5c, 'i32', 3),
    ],
    reachable_stores={  # fn VA -> [insn VA ...] store が到達可能 block にあること
        0x18115de60: [0x18115ea5c],
        0x1805b3510: [0x1805b3843],
        0x1805b3ad0: [],
    },
    r15_zero={0x1805b3ad0: True},  # getSubscription: 到達 block に store i64 0 (%r15) があること
)

BR_RE = re.compile(r'^(\s*)br i1 (.*?), label %([A-Za-z0-9_.]+), label %([A-Za-z0-9_.]+)(,\s*!insn\.addr\s+!\d+)?\s*$')
BRL_RE = re.compile(r'^(\s*)br label %([A-Za-z0-9_.]+)')
LABEL_RE = re.compile(r'^([A-Za-z0-9_.]+):\s*(?:;.*)?$')
META_DEF_RE = re.compile(r'^!(\d+)\s*=\s*!\{i64 (\d+)\}')
INSN_META_RE = re.compile(r'!insn\.addr\s+!(\d+)\s*(?:,.*)?$')


def parse_meta(lines):
    meta = {}
    for l in lines:
        m = META_DEF_RE.match(l.strip())
        if m:
            meta[int(m.group(1))] = int(m.group(2))
    inv = collections.defaultdict(list)
    for n, va in meta.items():
        inv[va].append(str(n))   # line_meta_name が返すのは文字列
    return meta, inv


def fn_ranges(lines):
    out, cur = [], None
    for i, l in enumerate(lines):
        if l.startswith('define'):
            m = re.search(r'@function_([0-9a-f]+)\(', l)
            cur = (int(m.group(1), 16), i) if m else None
        elif l.startswith('}') and cur:
            out.append((cur[0], cur[1], i))
            cur = None
    return out


def line_meta_name(l):
    m = INSN_META_RE.search(l)
    return m.group(1) if m else None


def apply_rules(lines, report):
    meta, inv = parse_meta(lines)
    ranges = fn_ranges(lines)
    present = {fva for (fva, _s, _e) in ranges}
    changed, skipped = [], []
    rules = [r for r in RULES if r['fn'] in present]
    for r in RULES:
        if r['fn'] not in present:
            skipped.append(r['id'])
    report['skipped_fn_absent'] = skipped
    for rule in rules:
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
                    tgt = rule['target']
                    if m.group(3) != tgt and m.group(4) != tgt:
                        continue
                    new = f"{m.group(1)}br label %{tgt}{m.group(5) or ''}"
                    report.setdefault('before', {})[rule['id']] = ln.strip()
                    lines[i] = new
                    report.setdefault('after', {})[rule['id']] = new.strip()
                    hits += 1
                elif kind == 'store_const':
                    m = re.match(r'^(\s*)store\s+(\S+)\s+(\S+),\s*(.+)$', ln)
                    if not m:
                        continue
                    val = m.group(3)
                    if val.lstrip('-').isdigit() and int(val) == rule['const']:
                        continue
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


# ---------------- CFG 到達性検証 ----------------
def split_blocks(lines, s, e):
    blocks = collections.OrderedDict()
    cur = None
    for i in range(s + 1, e):
        l = lines[i]
        m = LABEL_RE.match(l)
        if m:   # ラベルは必ず column 0 (RetDec 出力)
            cur = m.group(1)
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(i)
    return blocks


def block_succ(lines, idxs):
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
    return succ


def reach_analysis(lines, s, e):
    blocks = split_blocks(lines, s, e)
    order = list(blocks.keys())
    if not order:
        return blocks, set()
    seen = set()
    dq = collections.deque([order[0]])
    while dq:
        b = dq.popleft()
        if b in seen or b not in blocks:
            continue
        seen.add(b)
        for t in block_succ(lines, blocks[b]):
            dq.append(t)
    return blocks, seen


def block_of_va(blocks, va):
    """block 先頭 VA に対応する label (完全一致 or .suffix 付き)"""
    base = 'dec_label_pc_%x' % va
    if base in blocks:
        return base
    for k in blocks:
        if k.split('.')[0] == base:
            return k
    return None


def run_check(lines, report):
    ranges = {fva: (s, e) for (fva, s, e) in fn_ranges(lines)}
    present = set(ranges)
    ok = {}
    for fnva, blk_vas in CHECKS['unreachable'].items():
        if fnva not in present:
            continue
        s, e = ranges[fnva]
        blocks, reach = reach_analysis(lines, s, e)
        for bv in blk_vas:
            lab = block_of_va(blocks, bv)
            if lab and lab in reach:
                raise SystemExit(f"check fail: {fnva:#x} block {bv:#x} ({lab}) が到達可能のまま")
        ok[f'unreachable@{fnva:#x}'] = [hex(b) for b in blk_vas]
    reach_store = {}
    for fnva, blk_vas in CHECKS['reachable'].items():
        if fnva not in present:
            continue
        s, e = ranges[fnva]
        blocks, reach = reach_analysis(lines, s, e)
        for bv in blk_vas:
            lab = block_of_va(blocks, bv)
            if not lab or lab not in reach:
                raise SystemExit(f"check fail: {fnva:#x} block {bv:#x} ({lab}) が到達不能")
        ok[f'reachable@{fnva:#x}'] = [hex(b) for b in blk_vas]
        # 到達 block 内の insn.addr VA 集合 (store 到達性チェック用)
        vas = set()
        meta, _ = parse_meta(lines)
        for b in reach:
            for i in blocks[b]:
                mn = line_meta_name(lines[i])
                if mn:
                    vas.add(meta.get(int(mn)))
        reach_store[fnva] = vas
    for (fnva, at, ty, const) in CHECKS['const_stores']:
        if fnva not in present:
            continue
        s, e = ranges[fnva]
        meta, inv = parse_meta(lines)
        mr = inv.get(at)
        found = None
        for i in range(s + 1, e):
            mn = line_meta_name(lines[i])
            if mn in mr:
                m = re.match(r'^\s*store\s+' + re.escape(ty) + r'\s+(\S+),', lines[i])
                if m:
                    found = m.group(1)
        if found is None:
            raise SystemExit(f"check fail: store {ty} @{at:#x} が見つからない")
        if not (re.fullmatch(r'-?\d+', found) and int(found) == const):
            raise SystemExit(f"check fail: store @{at:#x} が定数 {const} でない: {found}")
        ok[f'const_store@{at:#x}'] = f'{ty} {const}'
    for fnva, ats in CHECKS['reachable_stores'].items():
        if fnva not in present:
            continue
        for at in ats:
            if at not in reach_store[fnva]:
                raise SystemExit(f"check fail: store @{at:#x} が到達可能 block に無い")
        ok[f'reachable_stores@{fnva:#x}'] = [hex(a) for a in ats]
    for fnva, want in CHECKS['r15_zero'].items():
        if not want or fnva not in present:
            continue
        s, e = ranges[fnva]
        blocks, reach = reach_analysis(lines, s, e)
        n = 0
        for b in reach:
            for i in blocks[b]:
                if re.match(r'\s*store i64 0, i64\* %r15', lines[i]):
                    n += 1
        if n < 1:
            raise SystemExit(f"check fail: {fnva:#x} 到達 block に r15=0 store 無し (成功 return が消滅?)")
        ok[f'r15_zero@{fnva:#x}'] = n
    report['check'] = ok
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--report', default=None)
    ap.add_argument('--check', action='store_true', help='適用後の到達性検証も実施')
    ap.add_argument('--harness-fix', action='store_true',
                    help='wasm ハーネス用: 0x18115debb の movups load (repack 異常バイト由来の '
                         'below-image 絶対アドレス 5536445154) を mock global @mx_harness_str0 へ置換')
    ap.add_argument('--no-rules', action='store_true', help='N1-N3 ルールを適用せず harness-fix のみ')
    a = ap.parse_args()
    lines = open(a.src).read().splitlines()
    report = {}
    n_before = len(lines)
    if not a.no_rules:
        lines = apply_rules(lines, report)
    if a.harness_fix:
        n = 0
        for i, l in enumerate(lines):
            if 'inttoptr (i64 5536445154 to i128*)' in l:
                lines[i] = re.sub(r'load i128, i128\* inttoptr \(i64 5536445154 to i128\*\)',
                                  'load i128, i128* @mx_harness_str0', l)
                n += 1
            elif 'inttoptr i64 5536445154 to ptr' in l:
                # liftlib base 後の形: hoist された定数ポインタ行
                lines[i] = l.replace('inttoptr i64 5536445154 to ptr',
                                     'inttoptr i64 ptrtoint (ptr @mx_harness_str0 to i64) to ptr')
                n += 1
        if n != 1:
            raise SystemExit(f'harness-fix: sites={n} (expect 1)')
        # 宣言を追加 (datalayout 行の後)
        ins = next(i for i, l in enumerate(lines) if l.startswith('target datalayout'))
        lines.insert(ins + 1, '@mx_harness_str0 = external global i128 ; MX-2 harness mock (16B 文字列)')
        report['harness_fix'] = n
    if a.check:
        run_check(lines, report)
    report['lines'] = {'src': n_before, 'dst': len(lines)}
    open(a.dst, 'w').write('\n'.join(lines) + '\n')
    if a.report:
        json.dump(report, open(a.report, 'w'), ensure_ascii=False, indent=1)
    print('mx_lic_stub: applied=%s check=%s -> %s' % (
        report.get('applied'), bool(a.check), a.dst))


if __name__ == '__main__':
    main()
