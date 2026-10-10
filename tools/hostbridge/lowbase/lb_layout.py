#!/usr/bin/env python3
"""lb_layout.py — lowbase の linear memory レイアウト算出 (全ビルド/ハーネスが共有する唯一の定義).

  0 ──────────── NULL 領域 (LB_BASE 未満は未使用; 64KiB 以上を空ける = shimx GetProcAddress の序数誤認回避)
  LB_BASE ────── PE image (RVA 0 .. SizeOfImage)   ← V-shift 後の絶対 VA = LB_BASE + RVA
  ARENA ──────── harness/surrogate 用の固定アリーナ (obj / 入出力 buf / scratch / 呼び出し側 instance)
  GLOBAL_BASE ── emscripten 静的データ → STACK → malloc heap (→ memory.grow)
usage: lb_layout.py [--base HEX] [--image-size HEX] [--arena-size HEX] [--init-mib N] [--max-mib N] [--fmt sh|json]
"""
import argparse, json

def up(v, a): return (v + a - 1) // a * a

def layout(base=0x10000, image_size=0x308000, arena_size=0x100000, init_mib=16, max_mib=64, check=True):
    assert base % 0x10000 == 0 and base >= 0x10000, 'LB_BASE は 64KiB 境界かつ >= 0x10000 (序数誤認回避)'
    img_end = base + image_size
    arena = up(img_end, 0x10000)
    gb = up(arena + arena_size, 0x10000)
    L = dict(LB_BASE=base, LB_IMAGE_SIZE=image_size, LB_IMG_END=img_end, LB_ARENA=arena, LB_ARENA_SIZE=arena_size,
             LB_GLOBAL_BASE=gb, LB_INIT=init_mib << 20, LB_MAX=max_mib << 20)
    if check: assert gb < L['LB_INIT'], 'initial memory が GLOBAL_BASE を覆えない'
    return L

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='0x10000'); ap.add_argument('--image-size', default='0x308000')
    ap.add_argument('--arena-size', default='0x100000'); ap.add_argument('--init-mib', type=int, default=16); ap.add_argument('--max-mib', type=int, default=64)
    ap.add_argument('--fmt', default='sh'); ap.add_argument('--no-check', action='store_true')
    a = ap.parse_args()
    L = layout(int(a.base, 0), int(a.image_size, 0), int(a.arena_size, 0), a.init_mib, a.max_mib, not a.no_check)
    if a.fmt == 'json': print(json.dumps({k: hex(v) for k, v in L.items()}))
    else:
        for k, v in L.items(): print('%s=%d' % (k, v))
