#!/usr/bin/env python3
"""fix_shx_t46.py — #5203 (SHX-T46, D23 段 1): function_448490 の count (+0x48 / IR 名 -32) を親 SSA から外し、object のメモリに置く (実験・既定 OFF)。

機械語では count は親フレーム object の +0x48 (= rbp-0x20) の 1 か所で、親のループ変数と callee function_4483f0 の `add [this+0x48], 1` が同じ場所を指す。
lift は count を reg2mem の 6 スロット (%stack_var_-32.*.reg2mem) に分けたため、call の副作用が親の次の読出しに届かない。
本 pass は 6 スロットへの全 store/load を、object 内の +0x48 を指す GEP (%fx46cnt) への store/load に置き換える。
これで各 call 後の読出しは機械語と同じく callee の書込みを見る。10 site の before/after 表は作らない (メモリの意味がそのまま残るため)。

object (%stack_var_-104) は callee が +0x4c (76)・+0x70 (112) も触るため、[15 x i64] (120 B) に拡幅する (fix_shx_t40.py と同じ)。
+0x70 の初期化は本 pass では行わない (#3234 の範囲)。
想定と違う入力は assert で止める (fail-closed)。

使い方: python3 fix_shx_t46.py IN.ll OUT.ll
"""
import re
import sys

FN = re.compile(r'^define [^\n]*@function_448490\(.*?\n}\n', re.M | re.S)
DEF_HEAD = 'define i64 @function_448490(i64 %arg1, '
ALLOCA_RE = re.compile(r'^  %stack_var_-104 = alloca (?:i64|\[6 x i64\]), align 8\n', re.M)
ALLOCA_NEW = '  %stack_var_-104 = alloca [15 x i64], align 8\n'
SLOT_RE = re.compile(r'%stack_var_-32\.[A-Za-z0-9.]+\.reg2mem')
SLOT_DEF_RE = re.compile(r'^  %stack_var_-32\.[A-Za-z0-9.]+\.reg2mem = alloca i32\n', re.M)
ENTRY_ANCHOR = '  store ptr null, ptr %stack_var_-48, align 8\n'
ENTRY_NEW = (ENTRY_ANCHOR +
             '  %fx46cnt = getelementptr i8, ptr %stack_var_-104, i64 72\n')
STORE_RE = re.compile(r'^(  store i32 [^,\n]+, ptr )(%stack_var_-32\.[A-Za-z0-9.]+\.reg2mem)(, align 4)?$', re.M)
LOAD_RE = re.compile(r'^(  %[^ ]+ = load i32, ptr )(%stack_var_-32\.[A-Za-z0-9.]+\.reg2mem)(, align 4)?$', re.M)


def patch(fn):
    assert fn.startswith(DEF_HEAD), 'function_448490 の仮引数が想定と違う'
    assert 'fx46' not in fn, '適用済み (二重適用)'
    assert len(ALLOCA_RE.findall(fn)) == 1, 'object の alloca 行が 1 件でない'
    assert fn.count(ENTRY_ANCHOR) == 1, 'entry の anchor 行が 1 件でない: %d' % fn.count(ENTRY_ANCHOR)
    slots = set(SLOT_RE.findall(fn))
    assert len(slots) == 6, 'count スロットが 6 件でない: %d' % len(slots)
    # 全出現が「store i32 / load i32 の対象」か「alloca 定義」のどちらかであること (それ以外の使い方は fail-closed)
    n_def = len(SLOT_DEF_RE.findall(fn))
    n_st = len(STORE_RE.findall(fn))
    n_ld = len(LOAD_RE.findall(fn))
    n_all = len(SLOT_RE.findall(fn))
    assert n_def == 6, 'count スロットの alloca 定義が 6 件でない: %d' % n_def
    assert n_st + n_ld + n_def == n_all, 'count スロットに想定外の使い方がある: store=%d load=%d def=%d all=%d' % (n_st, n_ld, n_def, n_all)
    assert n_st >= 1 and n_ld >= 1, 'count スロットの store/load が無い'
    fn = ALLOCA_RE.sub(ALLOCA_NEW, fn)
    fn = fn.replace(ENTRY_ANCHOR, ENTRY_NEW)
    fn = STORE_RE.sub(lambda m: m.group(1) + '%fx46cnt' + (m.group(3) or ''), fn)
    fn = LOAD_RE.sub(lambda m: m.group(1) + '%fx46cnt' + (m.group(3) or ''), fn)
    assert len(SLOT_RE.findall(fn)) == n_def, 'slot の置換が不完全'
    return fn


def main():
    src = open(sys.argv[1], errors='replace').read()
    fns = list(FN.finditer(src))
    assert len(fns) == 1, 'function_448490 の定義が 1 件でない: %d' % len(fns)
    f = fns[0].group(0)
    out = src[:fns[0].start()] + patch(f) + src[fns[0].end():]
    assert out != src
    open(sys.argv[2], 'w').write(out)
    print('[fix_shx_t46] function_448490: count (-32) の 6 スロットを object +0x48 のメモリに統合 (実験)')


if __name__ == '__main__':
    main()
