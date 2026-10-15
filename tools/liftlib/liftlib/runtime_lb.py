"""runtime_lb.py — C ランタイム固定値の `#ifndef LB_IMG_BASE` マクロ化 (CAB-220 / lowbase integration.md §A)。

tools/m6,m8,m10 の C ランタイム (読取のみ) を work へマクロ化コピーして返す。
`#ifndef` の既定値は元ソースの固定値と同一なので, -D 無しでも旧ビルドと等価。
emcc に `-DLB_IMG_BASE=<newbase>` `-DLB_MAX_MEM=<max>` を渡すと低位 base で動く。

  m6_rt.c        `#define M6base 0x30000000ul`            → LB_IMG_BASE 既定付きマクロ化
  m8_rt.c        `#define M8BASE 0x30000000ul` + 上限 `0x36000000ull` → LB_IMG_BASE / LB_MAX_MEM
  m6_stubs_hand.c `0x30000000ull + RVA` 直書き 4 箇所       → ((unsigned long long)LB_IMG_BASE) + RVA
  m10_boot.c     `#define MSCR ((volatile uint32_t *)0x35e00000)` → 静的配列化
                 (lowbase retdec/lb_reloc.py が行う置換と同じ)

置換は exact 文字列一致 + 出現数の assert (監査可能。元ソースが変わったら気づける)。
"""
import os
from typing import Any

# LB_IMG_BASE の既定 (= 元ソースの固定値 0x30000000)。prologue として #ifndef 付きで差し込む。
PROLOGUE = "#ifndef LB_IMG_BASE\n#define LB_IMG_BASE 0x30000000ul\n#endif\n"

RULES: dict[str, list[tuple[str, str, int]]] = {
    "m6_rt.c": [
        ("#define M6base 0x30000000ul",
         PROLOGUE + "#define M6base LB_IMG_BASE", 1),
        ("""long long function_1801d2750(long long dst, long long src, long long n, long long opt) {
    if (n > 0 && n < 0x4000000LL && dst > 0) {""",
         """#ifndef LB_MAX_MEM
#define LB_MAX_MEM 0x36000000ull
#endif
long long function_1801d2750(long long dst, long long src, long long n, long long opt) {
    /* CAB-220: linear memory は LB_MAX_MEM まで (lowbase では 64MiB 級)。旧実装に dst/src の
     * 上限が無く, 864MiB 前提の legacy 配置では「fail-fast abort が先行して到達しない」
     * junk 経路 (c38c8 family 系, dst=0xffffffff/src=-1 を実測) が小 memory で
     * OOB trap した。範囲外は no-op (m10 検収 trap10 の要求は「OOB 不発」)。 */
    if (n > 0 && n < 0x4000000LL && dst > 0 &&
        (unsigned long long)dst + (unsigned long long)n <= LB_MAX_MEM &&
        (unsigned long long)src + (unsigned long long)n <= LB_MAX_MEM) {""", 1),
    ],
    "m8_rt.c": [
        ("#define M8BASE 0x30000000ul",
         PROLOGUE + "#define M8BASE LB_IMG_BASE", 1),
        ("return a >= M8BASE && a < 0x36000000ull;",
         "#ifndef LB_MAX_MEM\n#define LB_MAX_MEM 0x36000000ull\n#endif\n    return a >= M8BASE && a < LB_MAX_MEM;", 1),
    ],
    "m6_stubs_hand.c": [
        ("0x30000000ull + 0x260ce0", "((unsigned long long)LB_IMG_BASE) + 0x260ce0", 2),
        ("0x30000000ull + 0x26cb88", "((unsigned long long)LB_IMG_BASE) + 0x26cb88", 2),
    ],
    "m10_boot.c": [
        ("#define MSCR ((volatile uint32_t *)0x35e00000)",
         "static volatile uint32_t lb_mscr[4096];\n#define MSCR (lb_mscr)", 1),
    ],
}


def emit(srcs: dict[str, str], outdir: str) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    """srcs: {basename: path} → outdir へマクロ化コピー。返値: ({basename: outpath}, report)。

    ルール未定義のファイルは無改変コピー (m6_stubs_hand2.c 等の同梱用)。
    """
    os.makedirs(outdir, exist_ok=True)
    outs: dict[str, str] = {}
    report: dict[str, list[dict[str, Any]]] = {}
    for name, path in srcs.items():
        text = open(path).read()
        rep: list[dict[str, Any]] = []
        for old, new, expect in RULES.get(name, []):
            c = text.count(old)
            if c != expect:
                raise AssertionError("%s: '%s' の出現数 %d (期待 %d) — 元ソースが変わった可能性" % (name, old[:60], c, expect))
            text = text.replace(old, new)
            rep.append(dict(old=old[:70], n=c))
        # ルール置換で LB_IMG_BASE を参照するようになったファイルに既定定義が無ければ prologue を補う
        if "LB_IMG_BASE" in text and "define LB_IMG_BASE" not in text:
            text = PROLOGUE + text
        out = os.path.join(outdir, name)
        open(out, "w").write(text)
        outs[name] = out
        report[name] = rep
    return outs, report


def emcc_defs(lb_base: int, lb_max: int) -> list[str]:
    """低位 base ビルド用の -D フラグ。既定値 (0x30000000) は #ifndef 既定と同値。"""
    return ["-DLB_IMG_BASE=0x%xul" % lb_base, "-DLB_MAX_MEM=0x%xull" % lb_max]


def audit_summary(report: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {k: sum(r["n"] for r in v) for k, v in report.items() if v}


if __name__ == "__main__":                     # 手動監査用: python3 -m liftlib.runtime_lb
    import json
    T = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    srcs = {"m6_rt.c": os.path.join(T, "m6/m6_rt.c"), "m8_rt.c": os.path.join(T, "m8/m8_rt.c"),
            "m10_boot.c": os.path.join(T, "m10/m10_boot.c"),
            "m6_stubs_hand.c": os.path.join(T, "m6/work/m6_stubs_hand.c"),
            "m6_stubs_hand2.c": os.path.join(T, "m6/work/m6_stubs_hand2.c")}
    outs, rep = emit(srcs, "/tmp/opencode/lb_rt_audit")
    print(json.dumps(dict(audit=audit_summary(rep), detail=rep), indent=1, ensure_ascii=False))
