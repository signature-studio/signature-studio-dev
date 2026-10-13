#!/usr/bin/env python3
"""svc_check.py — 言語検索パス服務 (0x9de400 の [self+0xa8]->vtbl+0x30) の実体と、不在時挙動の静的根拠を FLEngine_x64.dll で機械照合する (#590)。

stdlib のみ。verify_refs.PE (関数境界 / 直接 call 辺) を再利用し、加えて次を PE から直接読む:
  - vtable スロット (.text 内 8 byte ポインタ) / 関数本体の機械語バイト列 / IAT 経由 thunk (jmp [rip+x]) → import 名
usage: svc_check.py <FLEngine_x64.dll> [--mutate]
  --mutate: 期待値を 1 つずつ壊して実行する。全件 FAIL を検出すれば exit 0 (ネガコン)。壊しても通る項目があれば exit 1。
  既定: 全件一致で exit 0、1 件でも不一致なら exit 1。
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_refs import PE  # noqa: E402

BASE = 0x400000

# 期待値 (すべて ImageBase 込みの絶対 VA)
VT_FACADE = 0x751150                       # 検索パス服務 (TPathManager 系) の vtable。+0x30 = 0x75b750
SLOTS = {0x30: 0x75b750, 0x38: 0x75b870}
CALLS = [                                  # (caller, callee) 直接 call 辺
    (0x75b750, 0x758330),                  # slot+0x30 → 探索本体 (owner = [this+8])
    (0x758330, 0x759320),                  # level 毎の候補パス生成
    (0x758330, 0x758200),                  # 存在確認
    (0x758200, 0x43ba70),                  # FileExists
    (0x43ba70, 0x43ba20),                  # GetFileAttributesW 失敗時の FindFirstFileW 再確認
    (0x9db5b0, 0x759c80),                  # 検索 level の登録 (0, 2, 1)
    (0x758b90, 0x75b9e0),                  # owner が自分を指す服務 (vtable 0x751150) を構築し [owner+0x28] に保存
    (0x13754b0, 0x75b3d0),                 # 言語初期化に渡す服務 = getter 0x75b3d0 ([this+0x28])
]
IMPORT_THUNKS = {0x4234f0: 'GetFileAttributesW', 0x423230: 'CreateFileW', 0x423380: 'FindFirstFileW', 0x423370: 'FindClose'}
CALL_THUNKS = [(0x43ba70, 0x4234f0), (0x43ba70, 0x423230), (0x43ba20, 0x423380), (0x43ba20, 0x423370)]
# (関数 VA, 先頭からの探索範囲, 含むべき機械語, 出現回数, 意味)
BYTES = [
    (0x9de400, 0x1a0, bytes.fromhex('41b80f040000'), 2, 'mov r8d, 0x40f (Languages 区分 id) を .moe / .mo の 2 回'),
    (0x9de400, 0x1a0, bytes.fromhex('ff5330'), 2, 'call [rbx+0x30] (vtbl+0x30) を 2 回'),
    (0x9de400, 0x1a0, bytes.fromhex('488b89a8000000'), 2, 'mov rcx, [rcx+0xa8] (self+0xa8 = 服務) を 2 回'),
    (0x9db5b0, 0x80, bytes.fromhex('33d2e8'), 1, 'level 0 の登録 (xor edx,edx; call 0x759c80)'),
    (0x9db5b0, 0x80, bytes.fromhex('b202'), 1, 'level 2 の登録 (mov dl,2)'),
    (0x9db5b0, 0x80, bytes.fromhex('b201'), 1, 'level 1 の登録 (mov dl,1)'),
    (0x75b3d0, 5, bytes.fromhex('488b4128c3'), 1, 'getter: mov rax,[rcx+0x28]; ret'),
    (0x43ba70, 0xd0, bytes.fromhex('83f802'), 1, 'GetLastError==2 (FILE_NOT_FOUND) は false を返す'),
    (0x43ba70, 0xd0, bytes.fromhex('83f803'), 1, 'GetLastError==3 (PATH_NOT_FOUND) は false を返す'),
    (0x43ba70, 0xd0, bytes.fromhex('83f87b'), 1, 'GetLastError==0x7b (INVALID_NAME) は false を返す'),
    (0x43ba70, 0x30, bytes.fromhex('83f8ff'), 1, 'GetFileAttributesW == INVALID_FILE_ATTRIBUTES (-1) の分岐'),
    (0x758200, 0x50, bytes.fromhex('8b80b8000000a904000000'), 1, '呼出元フレーム [rbp+0xb8] (0x758330 の第 6 引数 flags) の bit2 test (存在確認の省略)'),
]

# (説明, 書込命令 VA, opcode 長, 読出命令 VA, opcode 長): 0x9db5b0 が 4 番目に作る登録集合の id (mov [rip+x], eax) を、
# 0x9dc7af 付近で message id 0x40f と対応づける側 (mov r8d, [rip+x]) が読むこと
GLOBALS = [('0x40f に対応づける集合 id (0x9db73f 書込 / 0x9dc7b4 読出)', 0x9db73f, 2, 0x9dc7b4, 3)]


def load_imports(pe):
    d = pe.d
    pe_off = struct.unpack_from('<I', d, 0x3C)[0]
    opt = pe_off + 24
    imp_rva = struct.unpack_from('<I', d, opt + 112 + 8)[0]
    iat = {}
    o = pe.rva2off(imp_rva)
    while True:
        ol, _t, _f, nm, ft = struct.unpack_from('<IIIII', d, o)
        if not nm:
            break
        dll = d[pe.rva2off(nm):d.find(b'\0', pe.rva2off(nm))].decode()
        t, s = pe.rva2off(ol or ft), ft
        while True:
            v = struct.unpack_from('<Q', d, t)[0]
            if not v:
                break
            if not v >> 63:
                p = pe.rva2off(v & 0x7fffffff) + 2
                iat[BASE + s] = (dll.lower(), d[p:d.find(b'\0', p)].decode())
            t += 8
            s += 8
        o += 20
    return iat


def thunk_import(pe, iat, va):
    o = pe.rva2off(va - BASE)
    if o is None or pe.d[o:o + 2] != b'\xff\x25':
        return None
    return iat.get(va + 6 + struct.unpack_from('<i', pe.d, o + 2)[0])


def rip_target(pe, va, opc_len):
    """va の命令 (opcode 部 opc_len byte + disp32 + 末尾) の RIP 相対参照先 (命令長 = opc_len + 4 + tail は呼出側で渡す)"""
    o = pe.rva2off(va - BASE)
    return va + opc_len + 4 + struct.unpack_from('<i', pe.d, o + opc_len)[0]


def run(pe, spec):
    fails, ok = [], 0
    iat = load_imports(pe)
    strrefs, calls = pe.scan()
    starts = set(pe.starts)

    def chk(cond, msg):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fails.append(msg)

    for slot, want in spec['slots'].items():
        off = pe.rva2off(spec['vt'] + slot - BASE)
        got = struct.unpack_from('<Q', pe.d, off)[0]
        chk(got == want, f'vtable {spec["vt"]:#x}+{slot:#x}: {got:#x} != 期待 {want:#x}')
    for caller, callee in spec['calls']:
        chk(callee - BASE in calls.get(caller - BASE, set()), f'call 辺 {caller:#x}->{callee:#x} が無い')
    for caller, thunk in spec['call_thunks']:
        chk(thunk - BASE in calls.get(caller - BASE, set()), f'call 辺 {caller:#x}->thunk {thunk:#x} が無い')
    for thunk, name in spec['thunks'].items():
        got = thunk_import(pe, iat, thunk)
        chk(got is not None and got[0] == 'kernel32.dll' and got[1] == name, f'thunk {thunk:#x}: {got} != kernel32!{name}')
    for va, span, pat, n, what in spec['bytes']:
        chk(va - BASE in starts, f'{va:#x}: 関数先頭でない')
        o = pe.rva2off(va - BASE)
        cnt = pe.d[o:o + span].count(pat)
        chk(cnt == n, f'{va:#x} +0..{span:#x}: {what}: 出現 {cnt} != {n}')
    for what, store_va, store_len, load_va, load_len in spec['globals']:
        a, b = rip_target(pe, store_va, store_len), rip_target(pe, load_va, load_len)
        chk(a == b, f'{what}: 書込側 {a:#x} != 読出側 {b:#x}')
    return ok, fails


def main(argv):
    pe = PE(open(argv[1], 'rb').read())
    spec = {'vt': VT_FACADE, 'slots': dict(SLOTS), 'calls': list(CALLS), 'call_thunks': list(CALL_THUNKS),
            'thunks': dict(IMPORT_THUNKS), 'bytes': list(BYTES), 'globals': list(GLOBALS)}
    ok, fails = run(pe, spec)
    total = ok + len(fails)
    if '--mutate' not in argv:
        print(f'svc_check: {ok}/{total} 一致')
        for f in fails:
            print('FAIL', f)
        return 1 if fails else 0
    if fails:
        print('mutate 前に不一致あり', fails)
        return 1
    muts = []
    muts.append(('vtable スロット', {**spec, 'slots': {0x30: 0x75b751, 0x38: 0x75b870}}))
    muts.append(('call 辺', {**spec, 'calls': spec['calls'] + [(0x75b750, 0x758200)]}))
    muts.append(('import 名', {**spec, 'thunks': {**spec['thunks'], 0x4234f0: 'GetFileAttributesA'}}))
    muts.append(('機械語 (出現回数)', {**spec, 'bytes': [(0x9de400, 0x1a0, bytes.fromhex('ff5330'), 3, 'x')]}))
    muts.append(('グローバル対応', {**spec, 'globals': [('x', 0x9db66a, 2, 0x9dc7b4, 3)]}))
    muts.append(('機械語 (別 level)', {**spec, 'bytes': [(0x9db5b0, 0x80, bytes.fromhex('b203'), 1, 'x')]}))
    missed = 0
    for name, sp in muts:
        _ok, f = run(pe, sp)
        print(f'  NC {name}: {"検出 (" + str(len(f)) + " 件)" if f else "★検出されず"}')
        missed += 0 if f else 1
    return 1 if missed else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv))
