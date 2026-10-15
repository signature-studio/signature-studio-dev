#!/usr/bin/env python3
"""diff_entry.py: Slayer_Engine.dll (block22434) の関数 1 本以上を native (実 ia32 機械語) と wasm (ia32 x64c lift) で実行し、
戻り値 (eax) と書込み先メモリ (OBJ 領域 128 B) を bit 単位で突合する (#1223 PLG-G2-11)。

  python3 diff_entry.py                 突合 (不一致・件数不足は exit 1)
  python3 diff_entry.py --nega          ネガコン: wasm 側の 1 bit を壊した出力を判定器に通し、FAIL することを確かめる (FAIL 検出で exit 0)

入力: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。 出力: work/entry/ (gitignore)。
入口: ENTRIES 7 本 (下の表)。 leaf 関数 4 本 (#1223: OBJ 領域への store だけ) と、 #3127 の 3 本 (export main の callback 0 経路 (KERNEL32 import は通らない)・
  heap 系 (HeapAlloc/VirtualAlloc/HeapReAlloc を通る)・stdcall の pop (LeaveCriticalSection を通る))。 出力は eax・OBJ 領域 128 B・heap 先頭 64 B (VA 0x10800000)。
native: native_entry.c (freestanding i386 ELF。 image を VA 0x10000000 に敷設し、 PE import directory から IAT を ia32 model の stub に書き換えて call)。
wasm  : lift_text.py の出力 ott_lifted.c + rt32_glue.c (ia32 規約の imp_*) + rt/ott_cpu.c を emcc で wasm 化し entry_wasm.mjs で実行。
        ott_cpu.c の x64 規約の imp_* は --allow-multiple-definition で rt32_glue.c が上書きする。
"""
import os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
RT = os.path.join(ROOT, 'tools', 'ott', 'rt')
WORK = os.path.join(HERE, 'work', 'entry')
LIFT = os.path.join(HERE, 'work', 'lift_text', 'ott_lifted.c')
IMG_BASE = 0x10000000
OBJ = 0x10F80000
OBJ_LEN = 0x80
N_PER_ENTRY = 64
SEED = 1223

# 入口 VA, 引数の形 (thiscall: ecx=OBJ), 引数生成の種類
ENTRIES = {
    0x10001b40: 'thiscall_two_stores',   # mov [ecx+0x1c],a0 / mov [ecx+4],a1
    0x10009300: 'thiscall_byte_store',   # mov [ecx+0x15],al (al = a0)
    0x1000d77e: 'ptr_obj_stores',        # mov [a0+0x50],imm32 / mov [a0+0x14],1
    0x10008630: 'ptr_byte_zero',         # mov byte [a1],0
    0x10007ca0: 'export_main_callback',  # export main: cdecl。 a0 = callback (6 引数で呼ぶ)。 callback が 0 を返す経路のみ (#3127)。 KERNEL32 import は 1 回も呼ばない
    0x1000e1b7: 'heap_pool_alloc',       # cdecl・引数なし。 HeapAlloc/VirtualAlloc/HeapReAlloc を通る (HeapFree は通らない。 fs: を使わない。 状態は image の .data に持つ) (#3127)
    0x1000ea7d: 'stdcall_leave_cs',      # cdecl・a0 = table index (0..63)。 LeaveCriticalSection(table[a0]) を 1 回呼ぶ (stdcall の pop を確認) (#3127)
}
# export main の callback 候補 (cdecl・返り値 0 の ret のみの関数)。 stdcall の `ret N` は main の esp 規約と合わないため使わない。
# 返り値が非 0 の経路 (main が定数 0x8298d8 を host オブジェクトとして f_10009f64 に渡す) は未モデル化のため使わない (REPORT_APPENDIX_3127.md)
MAIN_CB = [0x10001b10, 0x10001b70]   # xor eax,eax; ret / xor al,al; ret


def pe_image():
    import pefile
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    p = os.path.join(d, 'extracted', 'block22434_PE.bin')
    if not os.path.isfile(p):
        sys.exit('[diff_entry] FAIL: %s が無い (素材 fl-win64 を展開すること)' % p)
    pe = pefile.PE(p)
    if pe.OPTIONAL_HEADER.ImageBase != IMG_BASE:
        sys.exit('[diff_entry] FAIL: ImageBase 0x%x != 0x%x' % (pe.OPTIONAL_HEADER.ImageBase, IMG_BASE))
    img = bytearray(pe.OPTIONAL_HEADER.SizeOfImage)
    for s in pe.sections:
        raw = s.get_data()[:s.Misc_VirtualSize or len(s.get_data())]
        img[s.VirtualAddress:s.VirtualAddress + len(raw)] = raw
    hdr = open(p, 'rb').read(pe.OPTIONAL_HEADER.SizeOfHeaders)
    img[:len(hdr)] = hdr   # PE ヘッダも VA 0 に敷く (native_entry.c の patch_iat が import directory を読む)
    return bytes(img)


def gen_scen(seed, n):
    rng = random.Random(seed)
    rows = []
    for va, kind in ENTRIES.items():
        for _ in range(n):
            init = bytes(rng.randrange(256) for _ in range(OBJ_LEN))
            a = [rng.getrandbits(32) for _ in range(4)]
            if kind == 'ptr_obj_stores':
                a[0] = OBJ
            if kind == 'ptr_byte_zero':
                a[1] = OBJ + rng.randrange(OBJ_LEN)
            if kind == 'export_main_callback':
                a[0] = MAIN_CB[rng.randrange(len(MAIN_CB))]
            if kind == 'stdcall_leave_cs':
                a[0] = rng.randrange(64)
            rows.append('%08x %08x %08x %08x %08x %08x %s' % (va, OBJ, a[0], a[1], a[2], a[3], init.hex()))
    return rows


def run(cmd, what, timeout=600):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-1500:] + r.stderr[-1500:])
        sys.exit('[diff_entry] FAIL: %s rc %d' % (what, r.returncode))
    return time.time() - t0


def compare(exp_path, act_path, n_expected):
    exp = open(exp_path).read().splitlines()
    act = open(act_path).read().splitlines()
    if len(exp) != n_expected or len(act) != n_expected:
        print('[compare] FAIL: 件数 native %d / wasm %d / 期待 %d' % (len(exp), len(act), n_expected))
        return 1
    bad = [i for i, (x, y) in enumerate(zip(exp, act)) if x != y]
    for i in bad[:3]:
        print('[compare] mismatch #%d\n  native %s\n  wasm   %s' % (i, exp[i], act[i]))
    print('[compare] %s: %d / %d 件が bit 一致、不一致 %d 件' % ('PASS' if not bad else 'FAIL', n_expected - len(bad), n_expected, len(bad)))
    return 1 if bad else 0


def effect_count(exp_path, scen_rows):
    changed = 0
    for row, line in zip(scen_rows, open(exp_path).read().splitlines()):
        init = row.split()[6]
        mem = line.split(' mem=')[1].split(' heap=')[0]
        changed += (init != mem)
    return changed


def main():
    nega = '--nega' in sys.argv
    os.makedirs(WORK, exist_ok=True)
    img = pe_image()
    open(os.path.join(WORK, 'image.bin'), 'wb').write(img)
    rows = gen_scen(SEED, N_PER_ENTRY)
    scen = os.path.join(WORK, 'scen.txt')
    open(scen, 'w').write('\n'.join(rows) + '\n')
    print('[scen] entries %d x %d = %d 行 (seed %d)' % (len(ENTRIES), N_PER_ENTRY, len(rows), SEED))
    if not os.path.isfile(LIFT):
        sys.exit('[diff_entry] FAIL: %s が無い (lift_text.py を先に実行)' % LIFT)
    nat = os.path.join(WORK, 'native_entry')
    t_nat_build = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                       '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                       '-o', nat, os.path.join(HERE, 'native_entry.c')], 'native build')
    mjs = os.path.join(WORK, 'wasm_entry.cjs')
    t_wasm_build = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', RT, '-I', HERE,
                        os.path.join(HERE, 'rt32_glue.c'), LIFT, os.path.join(RT, 'ott_cpu.c'),
                        '-Wl,--allow-multiple-definition',   # ott_cpu.c の x64 規約の imp_* を rt32_glue.c (ia32 規約) が先勝ちで上書き
                        '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                        '-sEXPORTED_FUNCTIONS=_ott_call32', '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                        '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                        '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 'wasm build (emcc)', timeout=900)
    nat_out = os.path.join(WORK, 'native_out.txt')
    wasm_out = os.path.join(WORK, 'wasm_out.txt')
    load = os.getloadavg()[0]
    t_nat = run([nat, os.path.join(WORK, 'image.bin'), scen, nat_out], 'native run')
    t_wasm = run(['node', os.path.join(HERE, 'entry_wasm.mjs'), mjs, os.path.join(WORK, 'image.bin'), scen, wasm_out], 'wasm run (node)', timeout=900)
    print('[build] native %.2f s, wasm emcc %.2f s; [run] native %.3f s, wasm(node) %.3f s; load1 before run %.2f' % (
        t_nat_build, t_wasm_build, t_nat, t_wasm, load))
    changed = effect_count(nat_out, rows)
    print('[effect] native 実行で OBJ 領域が変わった行 %d / %d (入力の非自明性)' % (changed, len(rows)))
    if not nega:
        rc = compare(nat_out, wasm_out, len(rows))
        if rc == 0:
            print('[diff_entry] PASS')
        sys.exit(rc)
    # ネガコン: wasm 出力の 1 行目の eax の 1 bit を壊し、判定器が FAIL することを確かめる
    lines = open(wasm_out).read().splitlines()
    head, rest = lines[0].split(' mem=')
    eax_part = head.split(' eax=')
    v = int(eax_part[1], 16) ^ 0x1
    lines[0] = eax_part[0] + ' eax=%08x mem=' % v + rest
    nega_out = os.path.join(WORK, 'nega_out.txt')
    open(nega_out, 'w').write('\n'.join(lines) + '\n')
    rc = compare(nat_out, nega_out, len(rows))
    if rc == 0:
        print('[nega] FAIL: 1 bit 壊した出力が PASS した (判定器が効いていない)')
        sys.exit(1)
    print('[nega] 1 bit 壊した出力を検出 (FAIL, exit %d)。 ネガコン OK' % rc)
    sys.exit(0)


if __name__ == '__main__':
    main()
