#!/usr/bin/env python3
"""cmp_entries.py — entry 比較 matrix の判定 + 差分表生成。

  cmp_entries.py NATIVE.json WASM.json [--cov COV.json] [--covdsp ref/cov_all.json] [--out SUMMARY.json] [--table TABLE.md]

判定 (scenario 毎):
  both_ok   : 全 call の (rax*, xmm0, buf, out_f, ckpt, out) と終端状態 (obj†, alog sizes, am) が一致
  nat_crash : native が CRT 未初期化等で crash (比較不能 → 到達確認)
  wasm_fail : wasm 側が fail-fast / crash (本チケットの要修復項目)
  (*) rax は scenario の eff/obj と同じ値ならアドレス差を吸って 'EFF'/'OBJ' に正規化
  (†) obj+0x08 (audioMaster fn ポインタ: native=実アドレス / wasm=trampoline VA) は比較除外
"""
import sys, os, json, struct, argparse

IMG = 0x180000000


def pdata_funcs(dll_path):
    """RVA → (start, end) 関数境界表 (.pdata)"""
    import pefile
    pe = pefile.PE(dll_path)
    sec = [s for s in pe.sections if s.Name.startswith(b'.pdata')][0]
    raw = sec.get_data()
    out = []
    for i in range(0, len(raw) // 12 * 12, 12):
        b, e, u = struct.unpack_from('<III', raw, i)
        if b == 0 and e == 0: break
        out.append((b, e))
    return sorted(out)


def fn_of(rva, pdata):
    lo, hi = 0, len(pdata) - 1
    while lo <= hi:
        m = (lo + hi) // 2
        s, e = pdata[m]
        if s <= rva < e: return s
        if rva < s: hi = m - 1
        else: lo = m + 1
    return None


def norm_img(v):
    """native image VA / wasm shift VA を RVA に正規化 (比較用)"""
    if IMG <= v < IMG + 0x308000: return v - IMG
    if 0x30000000 <= v < 0x30308000: return v - 0x30000000
    if 0x10000 <= v < 0x10000 + 0x308000: return v - 0x10000
    return v


def as_int(v):
    """JSON 由来の数値/文字列 (u64 安全表現) を int へ"""
    return int(v) if isinstance(v, str) else v


def norm_rax(v, eff, obj):
    v = as_int(v)
    if v == eff: return 'EFF'
    if obj and obj <= v < obj + 0x1000: return 'OBJ+%x' % (v - obj)
    return norm_img(v)


def norm_q(v):
    if IMG <= v < IMG + 0x308000: return v - IMG           # native image (0x180000000)
    if 0x30000000 <= v < 0x30308000: return v - 0x30000000  # direct ott wasm build (shift 後)
    if 0x10000 <= v < 0x10000 + 0x308000: return v - 0x10000  # lowbase (LB_BASE=0x10000)
    return v


# rax / xmm0 を比較する step 種 (それ以外は caller-saved 残値 = harness 差のため非比較)
RAX_CMP = {'vstmain', 'disp', 'editorctor'}
XMM_CMP = {'getp'}


def cmp_scenario(nat, was):
    """→ (ok, reasons[])"""
    if not nat.get('ok'): return None, ['native crash st=%s' % nat.get('status')]
    if not was.get('ok'): return False, ['wasm fail: %s' % was.get('err', was.get('status'))]
    reasons = []
    nc, wc = nat['calls'], was['calls']
    if len(nc) != len(wc): return False, ['call count %d vs %d' % (len(nc), len(wc))]
    eff_n, eff_w = nat.get('eff_ptr', 0), was.get('eff_ptr', 0)
    for i, (a, b) in enumerate(zip(nc, wc)):
        kind = a.get('kind', '')
        if kind in RAX_CMP or a.get('raxok'):
            if norm_rax(a['rax'], eff_n, nat.get('obj_ptr')) != norm_rax(as_int(b['rax']), eff_w, was.get('obj_ptr')):
                reasons.append('call%d rax %s vs %s' % (i, norm_rax(a['rax'], eff_n, 0), norm_rax(as_int(b['rax']), eff_w, 0)))
        if kind in XMM_CMP and as_int(a.get('xmm0', 0)) != as_int(b.get('xmm0', 0)):
            reasons.append('call%d xmm0 %s vs %s' % (i, a.get('xmm0'), b.get('xmm0')))
        for k in ('buf', 'out_f', 'ckpt', 'out', 'editor_null'):
            if a.get(k) != b.get(k):
                av, bv = a.get(k), b.get(k)
                if isinstance(av, str) and isinstance(bv, str) and len(av) > 48: av, bv = av[:24] + '..', bv[:24] + '..'
                reasons.append('call%d %s %s vs %s' % (i, k, av, bv))
        if 'eff' in a or 'eff' in b:
            if a.get('eff') != b.get('eff'):
                reasons.append('call%d eff fields differ' % i)
    # 終端状態 (qword は image VA を RVA 正規化して比較)
    if (nat.get('obj') is None) != (was.get('obj') is None):
        reasons.append('obj presence')
    elif nat.get('obj'):
        A, B = bytes.fromhex(nat['obj']), bytes.fromhex(was['obj'])
        if len(A) != len(B):
            reasons.append('obj size %d vs %d' % (len(A), len(B)))
        else:
            diffs = []
            for o in range(0, len(A), 8):
                if o == 8: continue  # +0x08 audioMaster fn ポインタ (native=実アドレス / wasm=trampoline VA)
                qa = norm_q(struct.unpack_from('<Q', A, o)[0])
                qb = norm_q(struct.unpack_from('<Q', B, o)[0])
                if qa != qb: diffs.append(o)
            if diffs: reasons.append('obj qword diffs @%s' % [hex(d) for d in diffs[:6]])
    sa = [s for p, s in nat.get('alog', [])]
    sb = [s for p, s in was.get('alog', [])]
    if sa != sb: reasons.append('alog sizes %s vs %s' % (sa[:8], sb[:8]))
    if nat.get('am') != was.get('am'): reasons.append('am counters')
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('native'); ap.add_argument('wasm')
    ap.add_argument('--cov', default=None)
    ap.add_argument('--covdsp', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--table', default=None)
    a = ap.parse_args()
    N = json.load(open(a.native))['scenarios']
    Wj = json.load(open(a.wasm))
    W = Wj['scenarios'] if 'scenarios' in Wj else Wj
    DLL = '/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll'
    pdata = pdata_funcs(DLL)

    rows, okn = [], 0
    for name in sorted(set(N) | set(W)):
        nat, was = N.get(name, {'ok': False, 'status': 'missing'}), W.get(name, {'ok': False, 'status': 'missing'})
        ok, reasons = cmp_scenario(nat, was)
        if ok is None:
            verdict = 'nat_crash(到達確認)'
        else:
            verdict = 'PASS' if ok else 'FAIL'
            okn += ok
        rows.append({'name': name, 'verdict': verdict, 'reasons': reasons})
    n_crash = sum(1 for r in rows if r['verdict'].startswith('nat_crash'))
    n_fail = sum(1 for r in rows if r['verdict'] == 'FAIL')
    print('[cmp_entries] scenarios %d: PASS %d / nat_crash(到達確認) %d / FAIL %d' % (len(rows), okn, n_crash, n_fail))
    for r in rows:
        if r['verdict'] != 'PASS':
            print('  %-16s %s %s' % (r['name'], r['verdict'], '; '.join(r['reasons'])[:120]))

    # --- 関数別 差分表 (native 照合済 / 到達確認のみ / 未実行) ---
    if a.cov:
        cov = json.load(open(a.cov))
        dsp = json.load(open(a.covdsp)) if a.covdsp else {'insn': []}
        pass_scen = set(r['name'] for r in rows if r['verdict'] == 'PASS')
        crash_scen = set(r['name'] for r in rows if r['verdict'].startswith('nat_crash'))
        per = cov.get('per_scen', {})
        exec_pass, exec_crash = set(), set()
        for sname, insns in per.items():
            fns = set(x for x in (fn_of(i, pdata) for i in insns) if x is not None)
            if sname in pass_scen: exec_pass |= fns
            elif sname in crash_scen: exec_crash |= fns
        dsp_fns = set(x for x in (fn_of(i, pdata) for i in dsp.get('insn', [])) if x is not None)
        entry_only_pass = exec_pass - dsp_fns
        summary = {
            'rows': rows,
            'fn_verified_dsp': sorted(dsp_fns - exec_crash),
            'fn_verified_entry_new': sorted(entry_only_pass),
            'fn_reach_only': sorted((exec_pass & exec_crash) | (exec_crash - exec_pass)),
            'counts': dict(scenarios=len(rows), ok=okn, nat_crash=n_crash, fail=n_fail,
                           dsp_fns=len(dsp_fns), entry_new_verified=len(entry_only_pass)),
        }
        if a.out:
            json.dump(summary, open(a.out, 'w'), indent=1)
        if a.table:
            with open(a.table, 'w') as f:
                f.write('| 関数 (RVA) | 区分 | 状態 | 根拠 |\n|---|---|---|---|\n')
                f.write('| DSP closure 計 %d 関数 | DSP (既存 matrix) | native 照合済 | tools/ott/ott_e2e.sh 89 scenario / 50,236 cell bit-exact |\n' % len(dsp_fns - exec_crash))
                for va in sorted(summary['fn_verified_entry_new']):
                    f.write('| 0x%x | 入口拡張 (新規) | native 照合済 | entry matrix PASS scenario で実行・出力/状態一致 |\n' % (IMG + va))
                for va in sorted(summary['fn_reach_only']):
                    f.write('| 0x%x | 入口拡張 (新規) | 到達確認のみ | native が CRT 未初期化で crash する経路 (比較不能) |\n' % (IMG + va))
        print('[cmp_entries] fn: dsp_verified %d / entry_new_verified %d / reach_only %d' % (
            len(summary['fn_verified_dsp']), len(summary['fn_verified_entry_new']), len(summary['fn_reach_only'])))
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
