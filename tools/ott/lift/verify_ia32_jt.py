# verify_ia32_jt.py: ia32 jump table (Slayer_Engine.dll 0x10001310) の lift 出力 case 集合を PE の表データと突き合わせる (#1117)。
# 使い方: FL_PE=<block22434_PE.bin> python3 verify_ia32_jt.py <ott_lifted.c> [neg]
import pefile, re, sys, struct
import os
P=os.environ['FL_PE']
C=sys.argv[1]; NEG=len(sys.argv)>2
pe=pefile.PE(P); IMG=pe.OPTIONAL_HEADER.ImageBase
def rva_bytes(va,n):
    rva=va-IMG
    for s in pe.sections:
        if s.VirtualAddress<=rva<s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData):
            off=s.PointerToRawData+(rva-s.VirtualAddress)
            return pe.__data__[off:off+n]
    raise SystemExit('no section')
TBL=0x100014a4; N=25  # cmp eax,0x18 (ja 0x1000149c) → 有効 index 0..24
raw=[struct.unpack('<I',rva_bytes(TBL+4*k,4))[0] for k in range(N)]
if NEG: raw[7]^=0x10   # ネガコン: 表の 1 エントリを故意に壊す
src=open(C).read()
m=re.search(r'switch \(LD32\(\(R\[0\]\*4 \+ 0x100014a4ULL\)\)\) \{ (.*?) default', src, re.S)
if m is None: raise SystemExit('[jt] FAIL: switch not found')
cases=re.findall(r'case (0x[0-9a-f]+)ULL: goto (L_[0-9a-f]+);', m.group(1))
case_vals={int(c,16):l for c,l in cases}
# 各 case の遷移先ラベルが実在し、そのラベルの VA が case 値と一致する
label_ok=all(re.search(r'\n%s:;' % l, src) and int(l[2:],16)==v for v,l in case_vals.items())
tbl_set=set(raw)
print('[jt] switch cases %d, PE table entries %d (idx 0..%d @ 0x%x)' % (len(case_vals), N, N-1, TBL))
if not label_ok or set(case_vals)!=tbl_set:
    print('[jt] FAIL: only-in-C %s, only-in-PE %s' % (sorted(hex(x) for x in set(case_vals)-tbl_set), sorted(hex(x) for x in tbl_set-set(case_vals))))
    sys.exit(1)
print('[jt] OK: case 値集合 == PE jump table 実データ (%d B)' % (4*N))
