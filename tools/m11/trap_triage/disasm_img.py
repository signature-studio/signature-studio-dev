import sys, os, capstone
# disasm_img.py VA [bytes] [all]: work/m11_image.bin (PE 不要) の逆アセンブル。第3引数なしなら最初の ret で止まる (#419)
img=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','work','m11_image.bin'),'rb').read()
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
va=int(sys.argv[1],16); n=int(sys.argv[2],0) if len(sys.argv)>2 else 400
rva=va-0x400000
for i in cs.disasm(img[rva:rva+n],va):
    print('%x: %s %s'%(i.address,i.mnemonic,i.op_str))
    if i.mnemonic=='ret' and len(sys.argv)<=3: break
