import os, sys, struct
import pefile

# capstone の線形走査は .text 内のデータでずれ、実在する call を取りこぼす (0x41d8f0 ← 0x1376870 で確認)。
# そのため rel32 の E8 を全バイト走査する。アドレスの一致は 1 命令ごとに検証できないため、
# 候補の数は上限ではなく参考値として扱う。
PE = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block00031_PE.bin')
pe = pefile.PE(PE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
code = text.get_data()
start = base + text.VirtualAddress
targets = [int(a, 0) for a in sys.argv[1:]]
hits = {t: [] for t in targets}
for i in range(len(code) - 4):
    if code[i] == 0xE8:
        dest = start + i + 5 + struct.unpack_from('<i', code, i + 1)[0]
        if dest in hits:
            hits[dest].append(start + i)
for t in targets:
    print('0x%x <- %d 件 (E8 候補): %s' % (t, len(hits[t]), ' '.join('0x%x' % a for a in hits[t][:20]) or '-'))
