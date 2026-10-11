#!/usr/bin/env python3
"""fw_ovpass.py — C override 対象関数 (_StartLib/_InitLib) の lifted define 本体を C 呼出しに差し替える.

dispatch 経由は fw_table.py の OVERRIDES で接続するが, RetDec が直接 call 再接続した呼出し元
(entry → _StartLib の 1 引数 call など) は IR の define 本体を直接呼ぶため, 本体自体を
`call @fw_ov_<name>` に差し替える (ABI spill 済みの BLK を C 側で読む)。

  python3 fw_ovpass.py IN.ll OUT.ll
"""
import re, sys

OVERRIDES = {0x4189c0: 'fw_ov_startlib', 0x40db20: 'fw_ov_initlib', 0x40e0b0: 'fw_ov_restorectx_run'}
INT_RE = re.compile(r'^i(\d+)$')


def ret_of(rt, r):
    """戻り型 rt の `%r` (i64) からの変換命令を返す。

    S4 (CAB-269): 旧実装は i64 以外をすべて `trunc i64 %r to <rt>` にしていたため,
    i128 を返す function_40e0b0 (= RestoreContext 実行本体) で
    clang `invalid cast opcode for cast from 'i64' to 'i128'` になっていた。
    64 bit より広い整数は `zext` (拡張) が必要。
    """
    if rt == 'i64':
        return ['  ret i64 %s' % r]
    if rt == 'void':
        return ['  ret void']
    if rt == 'ptr' or rt.endswith('*'):
        return ['  %%t = inttoptr i64 %s to %s' % (r, rt), '  ret %s %%t' % rt]
    m = INT_RE.match(rt)
    if m and int(m.group(1)) > 64:
        return ['  %%t = zext i64 %s to %s' % (r, rt), '  ret %s %%t' % rt]
    if m:
        return ['  %%t = trunc i64 %s to %s' % (r, rt), '  ret %s %%t' % rt]
    raise SystemExit('[fw_ovpass] FATAL: 戻り型 %s は未対応 (i64/void/ptr/iN のみ)' % rt)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, errors='replace').read().split('\n')
    n = 0
    out = []
    i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r'define (.+?) @function_([0-9a-f]+)\(([^)]*)\)', l)
        if m and int(m.group(2), 16) in OVERRIDES:
            va = int(m.group(2), 16)
            cname = OVERRIDES[va]
            params = m.group(3)
            # 本体を C override 呼出しに差し替え (引数は捨てる: C 側は BLK から読む)
            pl = [p.strip() for p in params.split(',') if p.strip()]
            call_args = ', '.join('%s 0' % p.split(' ')[0] if not p.split(' ')[0].endswith('*') else 'ptr null' for p in pl) or 'void'
            out.append('define %s @function_%x(%s) {' % (m.group(1), va, params))
            out.append('  %%r = call i64 @%s()' % cname)
            out.extend(ret_of(m.group(1), '%r'))
            out.append('}')
            # declare 追加 (先頭の define の前に入れられないのでマーカー)
            out.append('; FWOV-DECLARE declare i64 @%s() local_unnamed_addr' % cname)
            i += 1
            while i < len(lines) and not lines[i].startswith('}'):
                i += 1
            i += 1
            n += 1
            continue
        out.append(l)
        i += 1
    # マーカー declare を移動 (重複除去)
    seen_d = set()
    decls = []
    for l in out:
        if l.startswith('; FWOV-DECLARE '):
            d = l.replace('; FWOV-DECLARE ', '')
            if d not in seen_d:
                seen_d.add(d)
                decls.append(d)
    out = [l for l in out if not l.startswith('; FWOV-DECLARE')]
    for i2, l in enumerate(out):
        if l.startswith('define '):
            out[i2:i2] = decls
            break
    open(dst, 'w').write('\n'.join(out))
    print('[ovpass] replaced defines: %d' % n)


if __name__ == '__main__':
    main()
