"""lb_layout.py — lowbase の linear memory レイアウト算出 (全 recipe が共有する唯一の定義)。

tools/hostbridge/lowbase/lb_layout.py (CAB-90 産) を liftlib へ取り込んだもの (CAB-220)。
**正本は lowbase 側**。両者は同一関数であることを tests/test_unit.py T8 が検査する
(変更は両方に反映すること)。

  0 ──────────── NULL 領域 (LB_BASE 未満は未使用; 64KiB 以上を空ける = shimx GetProcAddress の序数誤認回避)
  LB_BASE ────── PE image (RVA 0 .. SizeOfImage)   ← V-shift 後の絶対 VA = LB_BASE + RVA
  ARENA ──────── harness/surrogate 用の固定アリーナ (obj / 入出力 buf / scratch / 呼び出し側 instance)
  GLOBAL_BASE ── emscripten 静的データ → STACK → malloc heap (→ memory.grow)

emcc へは -sINITIAL_MEMORY/-sMAXIMUM_MEMORY を使う (-Wl,--initial-memory だと
emscripten の initial-heap 既定 16MiB が加算されて "initial memory too small" になる)。
"""


def up(v: int, a: int) -> int:
    return (v + a - 1) // a * a


def layout(base: int = 0x10000, image_size: int = 0x308000, arena_size: int = 0x100000,
           init_mib: int = 16, max_mib: int = 64, check: bool = True) -> dict[str, int]:
    assert base % 0x10000 == 0 and base >= 0x10000, 'LB_BASE は 64KiB 境界かつ >= 0x10000 (序数誤認回避)'
    img_end = base + image_size
    arena = up(img_end, 0x10000)
    gb = up(arena + arena_size, 0x10000)
    L = dict(LB_BASE=base, LB_IMAGE_SIZE=image_size, LB_IMG_END=img_end, LB_ARENA=arena, LB_ARENA_SIZE=arena_size,
             LB_GLOBAL_BASE=gb, LB_INIT=init_mib << 20, LB_MAX=max_mib << 20)
    if check:
        assert gb < L['LB_INIT'], 'initial memory が GLOBAL_BASE を覆えない'
    return L
