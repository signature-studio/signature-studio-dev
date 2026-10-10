import random, struct, sys
rnd = random.Random(0xF0E1); N = int(sys.argv[2]); out = []
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
bf = lambda b: struct.unpack('<f', struct.pack('<I', b))[0]
for k in range(N):
    r = rnd.random()
    if r < 0.5:   # Compressor 実使用域: pow(2.0, y), y = -x/(sr*t) など
        x = 2.0; y = -10 ** rnd.uniform(-6, 2) * rnd.choice([1, 1, 1, -1])
    elif r < 0.75:  # 一般 pow(正, 実数)
        x = 10 ** rnd.uniform(-3, 3); y = rnd.uniform(-8, 8)
    elif r < 0.9:  # 全域ランダムビット列 (特殊値含む)
        x = bf(rnd.getrandbits(32)); y = bf(rnd.getrandbits(32))
    else:  # 特殊値
        sp = [0.0, -0.0, 1.0, -1.0, 2.0, 0.5, float('inf'), float('-inf'), float('nan'), 1e-45, 3.4e38, -2.0, 1e-30, 1e30]
        x = rnd.choice(sp); y = rnd.choice(sp + [3.0, -3.0, 0.5, 1e-5])
    for f in (0, 1):
        out.append('%x %x %x' % (fb(x) if not isinstance(x, int) else x, fb(y), f))
open(sys.argv[1], 'w').write('\n'.join(out) + '\n')
print('wrote', len(out))
