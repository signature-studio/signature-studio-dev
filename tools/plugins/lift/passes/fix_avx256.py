#!/usr/bin/env python3
"""[P-A1] VEX (AVX) の i256 / store 形 __asm_v* helper を IR 命令へ lower する (#535)。

RetDec は ymm 演算を `call i256 @__asm_vaddps(i256, i256)` の疑似 helper で出す。 C 側 (m11_simd2) に i256 の ABI を決めて実装すると
wasm の sret / 4 分割引数の規約に依存するため、IR の `<8 x float>` 演算へ置換して helper 自体を消す。
変換:
  %r = call i256 @__asm_v{mov(aps|ups|dqa|dqu|apd|upd)}(i256 %x)           -> or i256 %x, 0                (load 形 = 恒等)
  %r = call i256 @__asm_v{add,sub,mul,div,min,max}ps(i256 %x, i256 %y)       -> bitcast <8 x float> + fadd/fsub/fmul/fdiv + bitcast
  %r = call i128 @__asm_vextractf128(i256 %x, i8 0|1)                       -> (lshr 128 +) trunc
  call void @__asm_vmov{aps...}(iW %old, iW %new) (W=128|256, %old = load iW, ptr %p)  -> store iW %new, ptr %p
      (RetDec は store の dst を「書込前の値の load」として渡す。 S1a が扱うのは非 VEX の movaps/movups/movdqa のみ)
min/max は x86 の「どちらかが NaN or 両方 0 なら第 2 operand」を select で再現する (a < b ? a : b)。
置換後に参照の無い declare を除く。 置換できなかった呼出は触らない (m11_simd2 が trap / unimpl として計上する = fail-closed)。
usage: fix_avx256.py IN.ll OUT.ll
"""
import re, sys

MOV = r'v(?:movaps|movups|movdqa|movdqu|movapd|movupd)'
CALL = re.compile(r'^(\s*)(%[\w.\-]+) = call (i256|i128) @(__asm_[\w.$-]+)\(([^()]*)\)\s*$')
STORE = re.compile(r'^(\s*)call void @(__asm_%s)(?:__\d+)?\((i256|i128) (%%[\w.\-]+), (i256|i128) (%%[\w.\-]+)\)\s*$' % MOV)
LOAD = re.compile(r'^\s*(%[\w.\-]+) = load (i256|i128), ptr (%[\w.\-]+)(, align \d+)?\s*$')
FOP = {'add': 'fadd', 'sub': 'fsub', 'mul': 'fmul', 'div': 'fdiv'}


def base_of(n):
    return re.sub(r'(__\d+)+$', '', n[len('__asm_'):])


def args_of(s):
    return [a.strip().split() for a in s.split(',') if a.strip()]


def fix_fn(lines, ctr):
    loads = {}
    out = []
    n = {'ymm': 0, 'store': 0}
    for l in lines:
        m = LOAD.match(l)
        if m:
            loads[m.group(1)] = (m.group(2), m.group(3), m.group(4) or '')
        m = STORE.match(l)
        if m:
            ind, _, w1, old, w2, new = m.groups()
            ent = loads.get(old)
            if w1 == w2 and ent and ent[0] == w1:
                out.append('%sstore %s %s, ptr %s%s' % (ind, w1, new, ent[1], ent[2]))
                n['store'] += 1
                continue
        m = CALL.match(l)
        if m:
            ind, dst, rt, fn, a = m.groups()
            base, A = base_of(fn), args_of(a)
            if rt == 'i256' and re.fullmatch(MOV, base) and len(A) == 1 and A[0][0] == 'i256':
                out.append('%s%s = or i256 %s, 0' % (ind, dst, A[0][1]))
                n['ymm'] += 1
                continue
            pm = re.fullmatch(r'v(add|sub|mul|div|min|max)ps', base)
            if rt == 'i256' and pm and len(A) == 2 and A[0][0] == A[1][0] == 'i256':
                ctr[0] += 1
                u = 'avx%d' % ctr[0]
                x, y, op = A[0][1], A[1][1], pm.group(1)
                out.append('%s%%%s_x = bitcast i256 %s to <8 x float>' % (ind, u, x))
                out.append('%s%%%s_y = bitcast i256 %s to <8 x float>' % (ind, u, y))
                if op in FOP:
                    out.append('%s%%%s_r = %s <8 x float> %%%s_x, %%%s_y' % (ind, u, FOP[op], u, u))
                else:
                    # x86: minps = (x < y) ? x : y, maxps = (x > y) ? x : y (NaN / 両 0 は第 2 operand)
                    cmp = 'olt' if op == 'min' else 'ogt'
                    out.append('%s%%%s_c = fcmp %s <8 x float> %%%s_x, %%%s_y' % (ind, u, cmp, u, u))
                    out.append('%s%%%s_r = select <8 x i1> %%%s_c, <8 x float> %%%s_x, <8 x float> %%%s_y' % (ind, u, u, u, u))
                out.append('%s%s = bitcast <8 x float> %%%s_r to i256' % (ind, dst, u))
                n['ymm'] += 1
                continue
            if rt == 'i128' and base == 'vextractf128' and len(A) == 2 and A[0][0] == 'i256' and A[1][0] == 'i8' and A[1][1] in ('0', '1'):
                if A[1][1] == '1':
                    ctr[0] += 1
                    u = 'avx%d' % ctr[0]
                    out.append('%s%%%s_h = lshr i256 %s, 128' % (ind, u, A[0][1]))
                    out.append('%s%s = trunc i256 %%%s_h to i128' % (ind, dst, u))
                else:
                    out.append('%s%s = trunc i256 %s to i128' % (ind, dst, A[0][1]))
                n['ymm'] += 1
                continue
        out.append(l)
    return out, n


def main():
    lines = open(sys.argv[1]).read().split('\n')
    ctr = [0]
    tot = {'ymm': 0, 'store': 0}
    out, start = [], None
    for l in lines:
        if l.startswith('define '):
            start = len(out)
        out.append(l)
        if l.startswith('}') and start is not None:
            seg, n = fix_fn(out[start:], ctr)
            out[start:] = seg
            for k in tot:
                tot[k] += n[k]
            start = None
    text = '\n'.join(out)
    # 参照の無くなった declare を除く
    dropped = 0
    keep = []
    for l in text.split('\n'):
        m = re.match(r'^declare \S+ @(__asm_v[\w.$-]+)\(', l)
        if m and not re.search(r'[@]' + re.escape(m.group(1)) + r'\(', text.replace(l, '')):
            dropped += 1
            continue
        keep.append(l)
    open(sys.argv[2], 'w').write('\n'.join(keep))
    sys.stderr.write('[P-A1] ymm 演算 lower %d 件 / VEX store 復元 %d 件 / 不要 declare 除去 %d 件\n' % (tot['ymm'], tot['store'], dropped))


if __name__ == '__main__':
    main()
