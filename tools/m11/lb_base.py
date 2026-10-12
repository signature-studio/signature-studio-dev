"""M11 LB_BASE (LVA = RVA + LB_BASE) の単一定義 (#222). 環境変数 M11_LB_BASE (既定 0 = 従来の LVA=RVA).
LB_BASE >= 0x10000 かつ 64KiB 境界にすると全 guest ポインタが shimx の整数判定 (<0x10000) を避ける (lowbase/lb_layout.py と同規則)."""
import os

IMG_BASE = 0x400000      # PE preferred ImageBase (VA = RVA + IMG_BASE)
GLOBAL_BASE = 0x10000000  # m11_build.sh の -sGLOBAL_BASE


def lb_base():
    v = int(os.environ.get('M11_LB_BASE', '0'), 0)
    assert v % 0x10000 == 0, 'M11_LB_BASE は 64KiB 境界 (lb_layout.py と同規則): 0x%x' % v
    return v


LB = lb_base()
VA_TO_LVA = LB - IMG_BASE   # lva = va + VA_TO_LVA
