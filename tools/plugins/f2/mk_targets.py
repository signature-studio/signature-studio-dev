#!/usr/bin/env python3
"""PLG-F2-3 (#515): leaf.json の block ごとに tools/liftdiff 用の target JSON・wasm image・VA 一覧を作る。

  python3 tools/plugins/f2/mk_targets.py [--ir-suffix p.final.ll] [--tag eqf]

出力 (すべて tools/plugins/work/f2/ = gitignore):
  targets/<tag><block>.json   liftdiff の target 記述 (docs/FORMAT.md §1)。IR = work/batch/<block>/p.final.ll (RetDec + pass 鎖の出力そのまま)
  image/<block>.bin           wasm 線形メモリに載せる PE イメージ (offset 0 = RVA 0)。m11_image_gen.py と同じ規約:
                              .reloc を除く全 section を RVA に敷き、DIR64 reloc が指す image 内ポインタは VA→RVA (-ImageBase) 補正
  targets/<block>.vas         関数 VA 一覧 (liftdiff batch --set file:)
"""
import json, os, re, struct, sys
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGINS = os.path.abspath(os.path.join(HERE, '..'))
REPO = os.path.abspath(os.path.join(PLUGINS, '..', '..'))
sys.path.insert(0, os.path.join(PLUGINS, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
W = os.path.join(PLUGINS, 'work')


def build_image(path):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = pe.OPTIONAL_HEADER.SizeOfImage
    secs = [s for s in pe.sections if s.SizeOfRawData and s.Name.rstrip(b'\0') != b'.reloc']
    top = max(s.VirtualAddress + min(s.Misc_VirtualSize or s.SizeOfRawData, s.SizeOfRawData) for s in secs)
    img = bytearray(top)
    for s in secs:
        d = s.get_data()[:min(s.Misc_VirtualSize or s.SizeOfRawData, s.SizeOfRawData)]
        img[s.VirtualAddress:s.VirtualAddress + len(d)] = d
    rd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
    relocs = []
    if rd.VirtualAddress and rd.Size:
        data = pe.get_data(rd.VirtualAddress, rd.Size)
        i = 0
        while i + 8 <= len(data):
            page, blk = struct.unpack_from('<II', data, i)
            if blk < 8 or page == 0:
                break
            for k in range((blk - 8) // 2):
                e = struct.unpack_from('<H', data, i + 8 + k * 2)[0]
                if (e >> 12) == 10:
                    relocs.append(page + (e & 0xfff))
            i += blk
    fixed = 0
    for r in relocs:
        if r + 8 <= top:
            v = struct.unpack_from('<Q', img, r)[0]
            if base < v < base + size:
                struct.pack_into('<Q', img, r, v - base)
                fixed += 1
    return bytes(img), {'base': base, 'size': size, 'top': top, 'reloc_dir64': len(relocs), 'fixed': fixed}


def ret_kind(pe, base, va, size):
    """i128 を返す IR 関数の実戻り型: 機械語で ret 前に最後に xmm0 へ書く命令から float/double を決める (決まらなければ None)"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86 import X86_OP_REG, X86_REG_XMM0
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    kind = None
    for i in md.disasm(pe.get_data(va - base, size), va):
        o = i.operands
        if o and o[0].type == X86_OP_REG and o[0].reg == X86_REG_XMM0 and not i.mnemonic.startswith('ucomis') and not i.mnemonic.startswith('comis'):
            m = i.mnemonic
            kind = 'float' if (m.endswith('ss') or m == 'cvtsd2ss') and m != 'cvtss2sd' else 'double' if (m.endswith('sd') or m == 'cvtss2sd') else None
    return kind


def wrap_i128(src, dst, fns):
    """fns: {va: 'float'|'double'}。 `define i128 @function_<va>(P)` を `@function_<va>.i128` に改名 (呼出し側も) し、
    同名で float/double を返す ABI アダプタ (trunc + bitcast のみ) を追加する。 liftdiff の JS ランナは i128 戻りの wasm export を呼べないため。
    戻り: 実際に包んだ {va: kind}"""
    txt = open(src, errors='replace').read()
    done, extra = {}, []
    for va, kind in fns.items():
        name = 'function_%x' % va
        m = re.search(r'^define i128 @%s\((.*?)\)(.*)\{$' % name, txt, re.M)
        if not m:
            continue
        params = m.group(1)
        args = params   # 仮引数は `ty %name` 形式なのでそのまま実引数に使える
        txt = re.sub(r'@%s\b(?=\()' % name, '@%s.i128' % name, txt)
        ity, fty = ('i32', 'float') if kind == 'float' else ('i64', 'double')
        extra.append('define %s @%s(%s) {\nentry:\n  %%r = call i128 @%s.i128(%s)\n  %%t = trunc i128 %%r to %s\n  %%f = bitcast %s %%t to %s\n  ret %s %%f\n}\n' % (
            fty, name, params, name, args, ity, ity, fty, fty))
        done[va] = kind
    open(dst, 'w').write(txt + '\n' + '\n'.join(extra))
    return done


def main():
    a = sys.argv[1:]
    tag = 'eqf'
    ir_name = 'p.final.ll'
    while a:
        if a[0] == '--tag':
            tag, a = a[1], a[2:]
        elif a[0] == '--ir-suffix':
            ir_name, a = a[1], a[2:]
        else:
            raise SystemExit('unknown arg ' + a[0])
    rows = json.load(open(os.path.join(W, 'f2', 'leaf.json')))
    blocks = sorted({r['block'] for r in rows})
    os.makedirs(os.path.join(W, 'f2', 'targets'), exist_ok=True)
    os.makedirs(os.path.join(W, 'f2', 'image'), exist_ok=True)
    rel = lambda p: os.path.relpath(p, REPO)
    for b in blocks:
        pe_path = os.path.join(FL_WIN64_DIR, 'extracted', 'block%05d_PE.bin' % b)
        img, info = build_image(pe_path)
        ip = os.path.join(W, 'f2', 'image', '%d.bin' % b)
        open(ip, 'wb').write(img)
        bd = os.path.join(W, 'batch', str(b))
        pe = pefile.PE(pe_path, fast_load=True)
        i128 = {}
        for r in [r for r in rows if r['block'] == b]:
            va = int(r['va'], 16)
            if re.search(r'^define i128 @function_%x\(' % va, open(os.path.join(bd, ir_name), errors='replace').read(), re.M):
                k = ret_kind(pe, pe.OPTIONAL_HEADER.ImageBase, va, r['bytes'])
                if k:
                    i128[va] = k
        ir_path = os.path.join(bd, ir_name)
        if i128:
            os.makedirs(os.path.join(W, 'f2', 'wrap'), exist_ok=True)
            ir_path = os.path.join(W, 'f2', 'wrap', '%d.ll' % b)
            print('block %d: i128 戻りを ABI アダプタで包む: %s' % (b, {hex(k): v for k, v in wrap_i128(os.path.join(bd, ir_name), ir_path, i128).items()}))
        t = {
            'name': '%s%d' % (tag, b),
            'desc': 'PLG-F2-3 (#515) eq-filter block %d: RetDec + pass 鎖 (batch_lift.sh) の p.final.ll を関数単位で native 機械語と差分' % b,
            'pe': '${FL_WIN64_DIR}/extracted/block%05d_PE.bin' % b,
            'ir': rel(ir_path),
            'image': rel(ip),
            'wasm_origin': '0x0',
            'fn_prefix': 'function_',
            'initial_memory': 671088640,   # ld_wasm.c の g_inbuf 192MB + g_heap 96MB + image が収まる最小級 (m11.json と同値)
            'simd': {'gen': 'cat %s' % rel(os.path.join(bd, 'p_simd.c')), 'ir': rel(ir_path),
                     'include': ['tools/plugins/lift/passes']},
        }
        json.dump(t, open(os.path.join(W, 'f2', 'targets', '%s%d.json' % (tag, b)), 'w'), indent=1)
        vas = [r['va'] for r in rows if r['block'] == b]
        open(os.path.join(W, 'f2', 'targets', '%d.vas' % b), 'w').write('\n'.join(v[2:] for v in vas) + '\n')
        print('block %d: image %d B (RVA 0..0x%x) reloc_dir64=%d fixed=%d, %d 関数' % (
            b, len(img), info['top'], info['reloc_dir64'], info['fixed'], len(vas)))


if __name__ == '__main__':
    main()
