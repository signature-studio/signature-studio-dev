#!/usr/bin/env python3
"""win 版 Reverb.dll (x64 PE) から Process_* 実体の範囲を再特定し、メモリイメージを書き出す (依存: 標準ライブラリのみ)。
usage: locate.py <Reverb.dll> <outdir>
  <outdir>/image.bin   SizeOfImage 分の RVA 配置イメージ (native_ref.c が mmap して元の機械語を実行する)
  <outdir>/ranges.json {"fruity": {...}, "uf": {...}}  export stub -> 実体 -> .pdata 連鎖で求めた [begin,end) (RVA)
手順: export (Process_Fruity_32FM_32FS / Process_UF_32FM_32FS) の stub が `jmp rel32` (E9) か `call rel32` (E8) で実体へ飛ぶので
      そのターゲットを実体先頭とし、.pdata の RUNTIME_FUNCTION を begin==前の end かつ UNWIND_INFO.Flags に CHAININFO(0x4) が立つ限り連結して end を決める。"""
import json, struct, sys, os

def parse(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3c)[0]
    assert d[pe:pe + 4] == b"PE\0\0"
    nsec, = struct.unpack_from("<H", d, pe + 6)
    optsz, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    assert struct.unpack_from("<H", d, opt)[0] == 0x20b, "PE32+ only"
    image_base, = struct.unpack_from("<Q", d, opt + 24)
    size_img, = struct.unpack_from("<I", d, opt + 56)
    hdr_sz, = struct.unpack_from("<I", d, opt + 60)
    dd = opt + 112
    exp_rva, exp_sz = struct.unpack_from("<II", d, dd)
    exc_rva, exc_sz = struct.unpack_from("<II", d, dd + 3 * 8)
    secs = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode()
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        secs.append((name, va, vs, rp, rs))
    img = bytearray(size_img)
    img[:hdr_sz] = d[:hdr_sz]
    for name, va, vs, rp, rs in secs:
        n = min(rs, vs) if vs else rs
        img[va:va + n] = d[rp:rp + n]
    return bytes(img), image_base, exp_rva, exc_rva, exc_sz

def u32(b, o): return struct.unpack_from("<I", b, o)[0]

def exports(img, exp_rva):
    nfun, nnames, afun, anames, aord = struct.unpack_from("<IIIII", img, exp_rva + 20)
    out = {}
    for i in range(nnames):
        name_rva = u32(img, anames + 4 * i)
        end = img.index(b"\0", name_rva)
        nm = img[name_rva:end].decode()
        ordi = struct.unpack_from("<H", img, aord + 2 * i)[0]
        out[nm] = u32(img, afun + 4 * ordi)
    return out

def stub_target(img, rva, funcs):
    """export stub (先頭から最大 40B) をバイト走査し、E9/E8 rel32 のうち**ターゲットが .pdata の関数先頭に一致する**
    最初の候補を返す (命令長デコーダ無しの走査なので、オペランド中の偶然の E8/E9 は pdata 一致で弾く)。"""
    for i in range(rva, rva + 40):
        if img[i] in (0xE9, 0xE8):
            t = i + 5 + struct.unpack_from("<i", img, i + 1)[0]
            if t in funcs: return t, ("jmp" if img[i] == 0xE9 else "call")
    raise SystemExit(f"no rel32 jmp/call to a .pdata function start in export stub {rva:#x}")

def main():
    dll, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    img, base, exp_rva, exc_rva, exc_sz = parse(dll)
    ex = exports(img, exp_rva)
    rf = []
    for o in range(exc_rva, exc_rva + exc_sz - 11, 12):
        b, e, u = struct.unpack_from("<III", img, o)
        if b: rf.append((b, e, u))
    rf.sort()
    byb = {b: (e, u) for b, e, u in rf}
    res = {}
    for key, nm in (("fruity", "Process_Fruity_32FM_32FS"), ("uf", "Process_UF_32FM_32FS")):
        stub = ex[nm]
        tgt, kind = stub_target(img, stub, byb)
        e, u = byb[tgt]
        chain = [(tgt, e)]
        while e in byb:
            ne, nu = byb[e]
            flags = img[nu] >> 3
            if not (flags & 4): break
            chain.append((e, ne)); e = ne
        res[key] = {"export": nm, "stub_rva": stub, "stub_kind": kind, "begin": tgt, "end": e, "size": e - tgt, "pdata_chain": chain,
                    "range": f"{base + tgt:#x}-{base + e:#x}"}
    open(os.path.join(outdir, "image.bin"), "wb").write(img)
    json.dump({"image_base": base, **res, "create_rva": ex["CreateReverbInstance"]}, open(os.path.join(outdir, "ranges.json"), "w"), indent=1)
    for k, v in res.items():
        print(f"[locate] {k}: {v['export']} stub {v['stub_rva']:#x} --{v['stub_kind']}--> {v['begin']:#x}..{v['end']:#x} ({v['size']} B, pdata chain {len(v['pdata_chain'])})  select-range {v['range']}")

if __name__ == "__main__":
    main()
