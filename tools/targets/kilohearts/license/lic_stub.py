#!/usr/bin/env python3
"""lic_stub.py — KH-9 ライセンス stub: kh_lower + ir_normalize 後の .ll (n1.ll 形式) に対する IR 後処理 pass。

lic_config.json の stub 表に従い、@function_<VA> (ms_abi 入口 wrapper) と @kh_<VA> (lift 本体) の
両方を定数返し・短絡の本体に置換する。wrapper/本体の両面で置換する理由:
  - 外部 (wasm export) からは @function_<VA> 経由で呼ばれる
  - lift 済み関数同士の内部呼出は @kh_<VA> へ直接 call する (kh_lower の呼出規約)
の両経路で同じ定数を返すため。

対応 kind:
  ret        本体を `ret i64 <value>` に置換 (引数は @rcx/@rdx/@r8/@r9 に store するのみ = deref なし)
  store2     [rcx+0]=values[0], [rcx+4]=values[1] を i32 store し rax=rcx を返す (getStatusAndDaysLeft)
  apply_key  [rcx+0]=0x1a (unlocked) を i32 store し 1 を返す
  key_init   実 0x180021490 の初期化を再現: state=0x17, found=1, std::string SSO リセット (cap=0xf)

usage: lic_stub.py IN.ll OUT.ll --config lic_config.json [--module A|B] [--report OUT.json]
"""
import argparse
import json
import re
import sys

REGS = ['rcx', 'rdx', 'r8', 'r9']
DEF_FN = re.compile(r'^define (\S+) @function_([0-9a-f]+)\(([^)]*)\) \{$')
DEF_KH = re.compile(r'^define (\S+) @kh_([0-9a-f]+)\(\) \{$')


def body(kind, cfg):
    """@kh_<VA> の置換本体 (登録グローバル @rcx 等は kh_lower 出力の宣言を流用)。
    注意: % 指定を行う行は %% エスケープ、行そのものを返す行は単一 % (LLVM 識別子) """
    if kind == 'ret':
        return ['  ret i64 %d' % int(cfg['value'])]
    if kind == 'store2':
        v0, v1 = (int(x) for x in cfg['values'])
        return [
            '  %p = load i64, ptr @rcx',
            '  %q = inttoptr i64 %p to ptr',
            '  store i32 %d, ptr %%q' % v0,
            '  %q4 = getelementptr i8, ptr %q, i64 4',
            '  store i32 %d, ptr %%q4' % v1,
            '  store i64 %p, ptr @rax',
            '  ret i64 %p',
        ]
    if kind == 'apply_key':
        return [
            '  %p = load i64, ptr @rcx',
            '  %q = inttoptr i64 %p to ptr',
            '  store i32 26, ptr %q',
            '  store i64 1, ptr @rax',
            '  ret i64 1',
        ]
    if kind == 'key_init':
        return [
            '  %p = load i64, ptr @rcx',
            '  %q = inttoptr i64 %p to ptr',
            '  store i32 23, ptr %q',
            '  %q4 = getelementptr i8, ptr %q, i64 4',
            '  store i8 1, ptr %q4',
            '  %q8 = getelementptr i8, ptr %q, i64 8',
            '  store i64 0, ptr %q8',
            '  %q16 = getelementptr i8, ptr %q, i64 16',
            '  store i64 0, ptr %q16',
            '  %q24 = getelementptr i8, ptr %q, i64 24',
            '  store i64 0, ptr %q24',
            '  %q32 = getelementptr i8, ptr %q, i64 32',
            '  store i64 15, ptr %q32',
            '  store i64 %p, ptr @rax',
            '  ret i64 %p',
        ]
    raise SystemExit('unknown stub kind: %s' % kind)


def wrapper_fn(retty, params, va):
    """@function_<VA> の置換本体: 引数をレジスタグローバルへ store して @kh_<VA> を呼び rax 系を返す"""
    out = ['define %s @function_%s(%s) {' % (retty, va, params), 'entry:']
    for i, pm in enumerate([p.strip() for p in params.split(',') if p.strip()]):
        if i >= len(REGS):
            break   # 5+ 引数 (スタック引数) は本 pass の対象外 (stub 対象は全て 4 引数以内)
        pname = pm.split()[-1].lstrip('%')
        out.append('  store %s %%%s, ptr @%s' % (pm.split()[0], pname, REGS[i]))
    khret = 'i64'   # kh_ は常に i64 (rax) を返す
    if retty == 'void':
        out += ['  call i64 @kh_%s()' % va, '  ret void']
    elif retty == 'i64':
        out += ['  %%r = call i64 @kh_%s()' % va, '  ret i64 %r']
    else:
        out += ['  %%r = call i64 @kh_%s()' % va, '  %%rt = trunc i64 %%r to %s' % retty, '  ret %s %%rt' % retty]
    out.append('}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--config', required=True)
    ap.add_argument('--module', default=None, help='A/B: モジュール構成に応じて stub 適用対象を絞る')
    ap.add_argument('--report', default=None)
    a = ap.parse_args()

    cfg = json.load(open(a.config))
    want = {s['va']: s for s in cfg['stubs']}
    if a.module:
        mod = cfg['modules'][a.module]
        if mod.get('stub_all'):
            pass
        else:
            only = set(mod.get('stub_only', []))
            want = {k: v for k, v in want.items() if k in only}

    lines = open(a.src).read().split('\n')
    out, rep, i = [], {k: {'wrapper': False, 'body': False, 'sig': None, 'kind': want[k]['kind']} for k in want}, 0
    while i < len(lines):
        l = lines[i]
        mfn = DEF_FN.match(l)
        mkh = DEF_KH.match(l)
        if mfn and mfn.group(2) in want:
            va, retty, params = mfn.group(2), mfn.group(1), mfn.group(3)
            rep[va]['sig'] = '%s (%s)' % (retty, params)
            nparam = len([p for p in params.split(',') if p.strip()])
            assert nparam <= 4, 'stub target %s has stack args (unsupported): %s' % (va, params)
            out.extend(wrapper_fn(retty, params, va))
            rep[va]['wrapper'] = True
            i += 1
            while i < len(lines) and lines[i] != '}':
                i += 1
            i += 1
            continue
        if mkh and mkh.group(2) in want:
            va, retty = mkh.group(2), mkh.group(1)
            assert retty == 'i64', 'kh_ body must return i64: kh_%s returns %s' % (va, retty)
            out.append('define i64 @kh_%s() {' % va)
            out.append('entry:')
            out.extend(body(want[va]['kind'], want[va]))
            out.append('}')
            rep[va]['body'] = True
            i += 1
            while i < len(lines) and lines[i] != '}':
                i += 1
            i += 1
            continue
        out.append(l)
        i += 1
    # lift 範囲に存在しない対象 (例: 名前付き export の KHSUnlock は stage-0 で @function_<VA> にならない)
    # は定型 define を生成して補完する (レジスタグローバル宣言は kh_lower 出力の preamble を流用)
    synth = []
    for va, s in want.items():
        if rep[va]['wrapper'] and rep[va]['body']:
            continue
        synth.append(va)
        out.append('define i64 @kh_%s() {' % va)
        out.append('entry:')
        out.extend(body(s['kind'], s))
        out.append('}')
        out.append('')
        out.extend(wrapper_fn('i64', 'i64 %p0, i64 %p1, i64 %p2, i64 %p3', va))
        out.append('')
        rep[va]['wrapper'] = rep[va]['body'] = True
        rep[va]['synth'] = True
    open(a.dst, 'w').write('\n'.join(out))
    n_ok = sum(1 for v in rep.values() if v['wrapper'] and v['body'])
    n_want = len(want)
    n_missing = [k for k, v in rep.items() if not (v['wrapper'] and v['body'])]
    print('[lic_stub] stubbed %d/%d (synth: %s, missing: %s)' % (n_ok, n_want, synth or '-', n_missing or '-'))
    if a.report:
        json.dump({'stubbed': n_ok, 'wanted': n_want, 'synth': synth, 'missing': n_missing, 'detail': rep}, open(a.report, 'w'), indent=1)
    if n_missing:
        # 対象関数が lift 範囲に無い (DSP モードでは通常 = ライセンス層非通過の証拠)。エラーにはしない。
        pass


if __name__ == '__main__':
    main()
