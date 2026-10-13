#!/usr/bin/env python3
"""PLG-F2 (#514): lift 後 IR の間接 call が機械語の間接 call site を全て覆っているかの回帰ゲート。 `emcc -c` 通過は gate にならない
((icall §4) D1 = RetDec が間接 call を decoder 段で捨てる) ので、機械語側の site 集合と IR 側の site 集合を突合して不足があれば exit 1。

  機械語側 (rewriter/audit_icall とは別算法): 閉包 ranges を capstone の線形 sweep で逆アセンブルし、オペランドが即値でない `call` のうち
      PE の IAT 呼出し (`call [rip+IAT]`) を除いたものの VA 集合。
  IR 側: lift 後 IR (p.final.ll) の
      dispatch   = `call void @__icall_dispatch(i64 <site VA>)` (tools/icall の復元 pass が元 site VA 付きで戻したもの)
      native_ind = callee が `@name` でない call (RetDec が自力で残した間接 call; 通常 0)

  FAIL 条件 (どれか 1 つで exit 1):
    F1 機械語の site VA のうち IR の dispatch site 集合に無いものがある (missing > 0)。 ただし waiver (icall_gate_waivers.json: block, site, reason) が
       あり、かつ **復元直後の raw IR (p.drc.restored.ll) に、その site VA を insn.addr に持つ命令が 1 つも無い** ときだけ「waived」として許す
       (= RetDec が site を含む基本ブロックごと到達不能として除去した場合。 call だけ落ちたなら site の BLK store 列が元 VA 付きで残るので waiver は無効 → F4)
    F2 IR の間接 call 総数 (dispatch + native_ind) + waived < 機械語の site 数      ← 「IR の間接 call 数が機械語より少ない」
    F3 site VA を持たない dispatch (`i64 0`) がある (復元の帰属失敗)
    F4 waiver があるのに raw IR が site VA の命令を持つ (または raw IR が読めない) = waiver 無効
  参考表示のみ: extra = 機械語の間接 call でない site の dispatch (tail jmp / jump table / CFG thunk を stub 化したもの。 mnemonic を併記)

使い方 (dynamics #506 の閉包にもそのまま使える: ranges/IR の置き場が batch_lift.sh と同じ):
  python3 tools/plugins/f2/icall_gate.py <block> ...                    work/closure/block<NNNNN>.ranges.txt と work/batch/<block>/p.final.ll を読む
  python3 tools/plugins/f2/icall_gate.py --pe PE --ranges R.txt --ir X.ll [--raw-ir RAW.ll] [--label L]   任意の PE / 閉包 / IR
  オプション: --json OUT (block ごとの結果), --ir-name p.final.ll (batch の IR ファイル名), --raw-name p.drc.restored.ll,
              --waivers FILE (既定: このスクリプトと同じ dir の icall_gate_waivers.json; 無ければ waiver なし)
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

W = os.path.join(HERE, '..', 'work')
DISPATCH = re.compile(r'\bcall\s+void\s+@__icall_dispatch\(i64\s+(-?\d+)\)')
CALL = re.compile(r'\bcall\b[^\n]*?(?<![\w.])(@[\w.$"-]+|%[\w.]+)\s*\(')


def parse_ranges(path):
    return [tuple(int(x, 16) for x in r.split('-')) for r in open(path).read().replace(',', '\n').split() if r]


def machine_sites(pe_path, ranges):
    """{VA: mnemonic} — 閉包 ranges 内の非 IAT 間接 call (線形 sweep)。 同時に range 内の全 jmp 間接の VA も返す"""
    pe = pefile.PE(pe_path, fast_load=True)
    pe.parse_data_directories()
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {i.address for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) for i in d.imports if i.address}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    calls, jmps = {}, {}
    for lo, hi in ranges:
        for i in md.disasm(pe.get_data(lo - base, hi - lo + 1), lo):
            if i.mnemonic not in ('call', 'jmp') or i.operands[0].type == X86_OP_IMM:
                continue
            o = i.operands[0]
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and (i.address + i.size + o.mem.disp) in iat:
                continue
            (calls if i.mnemonic == 'call' else jmps)[i.address] = i.op_str
    return calls, jmps


def ir_sites(ir_path):
    """(dispatch site VA のリスト (出現ごと), native_ind 件数)"""
    text = open(ir_path, errors='replace').read()
    disp = [int(m.group(1)) for m in DISPATCH.finditer(text)]
    native = 0
    for line in text.split('\n'):
        s = line.strip()
        if 'call ' not in s or s.startswith(('declare', 'define', ';')):
            continue
        m = CALL.search(s)
        if m and m.group(1).startswith('%'):
            native += 1
    return disp, native


def attributed(raw_ir_path, vas):
    """raw IR (復元直後, !insn.addr 付き) で insn.addr が vas のいずれかに等しい命令を持つ VA の集合"""
    text = open(raw_ir_path, errors='replace').read()
    ids = {}
    for m in re.finditer(r'^!(\d+) = !\{i64 (\d+)\}$', text, re.M):
        if int(m.group(2)) in vas:
            ids[m.group(1)] = int(m.group(2))
    hit = set()
    if ids:
        for m in re.finditer(r'!insn\.addr !(\d+)', text):
            if m.group(1) in ids:
                hit.add(ids[m.group(1)])
    return hit


def gate(label, pe_path, ranges_path, ir_path, raw_ir_path=None, waivers=()):
    calls, jmps = machine_sites(pe_path, parse_ranges(ranges_path))
    disp, native = ir_sites(ir_path)
    dset = set(disp)
    missing_all = sorted(set(calls) - dset)
    wv = {int(w['site'], 16): w for w in waivers if str(w['block']) == str(label)}
    waived, invalid, missing = [], [], []
    hit = set()
    for v in missing_all:
        if v not in wv:
            missing.append(v)
            continue
        if raw_ir_path is None or not os.path.exists(raw_ir_path):
            invalid.append(v)
            continue
        if v in attributed(raw_ir_path, {v}):
            invalid.append(v)
        else:
            waived.append(v)
    extra = sorted(v for v in dset if v not in calls and v != 0)
    r = {'label': label, 'machine_call_sites': len(calls), 'ir_dispatch_calls': len(disp), 'ir_dispatch_sites': len(dset - {0}),
         'ir_native_indirect': native, 'ir_indirect_total': len(disp) + native,
         'missing': [hex(v) for v in missing], 'n_missing': len(missing),
         'waived': [[hex(v), wv[v]['reason']] for v in waived], 'n_waived': len(waived),
         'waiver_invalid': [hex(v) for v in invalid], 'n_waiver_invalid': len(invalid),
         'unattributed': disp.count(0), 'extra': [[hex(v), 'jmp' if v in jmps else '?'] for v in extra], 'n_extra': len(extra),
         'extra_are_machine_jmp': sum(1 for v in extra if v in jmps)}
    fails = []
    if missing:
        fails.append('F1 missing=%d' % len(missing))
    if r['ir_indirect_total'] + len(waived) < len(calls):
        fails.append('F2 ir_total=%d + waived=%d < machine=%d' % (r['ir_indirect_total'], len(waived), len(calls)))
    if r['unattributed']:
        fails.append('F3 unattributed=%d' % r['unattributed'])
    if invalid:
        fails.append('F4 waiver 無効=%d (%s)' % (len(invalid), ','.join(hex(v) for v in invalid)))
    r['fails'] = fails
    r['pass'] = not fails
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('blocks', nargs='*', type=int)
    ap.add_argument('--pe')
    ap.add_argument('--ranges')
    ap.add_argument('--ir')
    ap.add_argument('--label', default='')
    ap.add_argument('--raw-ir')
    ap.add_argument('--ir-name', default='p.final.ll')
    ap.add_argument('--raw-name', default='p.drc.restored.ll')
    ap.add_argument('--waivers', default=os.path.join(HERE, 'icall_gate_waivers.json'))
    ap.add_argument('--json')
    a = ap.parse_args()
    waivers = json.load(open(a.waivers)) if os.path.exists(a.waivers) else []
    jobs = []
    if a.pe:
        jobs.append((a.label or os.path.basename(a.ir), a.pe, a.ranges, a.ir, a.raw_ir))
    for b in a.blocks:
        jobs.append((str(b), os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b),
                     os.path.join(W, 'closure', 'block%05d.ranges.txt' % b), os.path.join(W, 'batch', str(b), a.ir_name),
                     os.path.join(W, 'batch', str(b), a.raw_name)))
    if not jobs:
        ap.error('block か --pe/--ranges/--ir が必要')
    res = []
    print('| block | 機械語 間接 call site | IR dispatch 呼出し | IR dispatch 異 site | IR native 間接 call | IR 間接 call 計 | waived (到達不能で除去) | 未被覆 (F1) | site 不明 (F3) | 参考: 非 call の dispatch (うち機械語 jmp) | 判定 |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|')
    tot = [0, 0, 0, 0, 0]
    for lab, pe, rg, ir, raw in jobs:
        r = gate(lab, pe, rg, ir, raw, waivers)
        res.append(r)
        tot[0] += r['machine_call_sites']; tot[1] += r['ir_dispatch_calls']; tot[2] += r['ir_indirect_total']; tot[3] += r['n_missing']; tot[4] += r['n_waived']
        print('| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d (%d) | %s |' % (
            lab, r['machine_call_sites'], r['ir_dispatch_calls'], r['ir_dispatch_sites'], r['ir_native_indirect'], r['ir_indirect_total'],
            r['n_waived'], r['n_missing'], r['unattributed'], r['n_extra'], r['extra_are_machine_jmp'], 'PASS' if r['pass'] else 'FAIL ' + '; '.join(r['fails'])))
    print('| 合計 | %d | %d | | | %d | %d | %d | | | %s |' % (tot[0], tot[1], tot[2], tot[4], tot[3], 'PASS' if all(r['pass'] for r in res) else 'FAIL'))
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)
    sys.exit(0 if all(r['pass'] for r in res) else 1)


if __name__ == '__main__':
    main()
