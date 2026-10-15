import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PE = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
pe = pefile.PE(PE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
code = text.get_data()
start = base + text.VirtualAddress
md = Cs(CS_ARCH_X86, CS_MODE_64)
targets = [int(a, 0) for a in sys.argv[1:]]
want = set(targets)
hits = {}
for ins in md.disasm(code, start):
    if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
        t = int(ins.op_str, 16)
        if t in want:
            hits.setdefault(t, []).append(ins.address)
for t in targets:
    print('0x%x <- %s' % (t, ' '.join('0x%x' % a for a in hits.get(t, [])) or '-'))
