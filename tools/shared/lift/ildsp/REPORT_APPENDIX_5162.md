# ildsp REPORT 付録: PSOLA 差分の HeapAlloc 13 件目の呼出元 (#5162 / T-SH-139)

> **正本**: 本付録。親 #5138・前提 REPORT_APPENDIX_4302.md §7・§8・§9。
> 本付録の結論は、§1 の 13 件目の確保位置と、差分の入力 (dispatch 値) の特定まで。サイズ式 (0x500) の完全な導出は未達 (§5)。

## 1. 結論

- 1 case 目の HeapAlloc 要求列の **13 件目 (通し番号 n=12・slot 1 の呼出し中)** で、native `sz=71368`・wasm `sz=70088` (差 1280 = 0x500) を確認した。
- 13 件目の確保位置: `0x161561` (`call 0x1b6ea0` → `0x1b9c1c` の retry wrapper 経由で HeapAlloc)。要求サイズは `N + 0x48` の形。`N` は `0x10a0`・`0x10d0` の jump table (index = global `[0x3f5b80]`) から来る。
- 差分の入力: global `[0x3f5b80]` が native で `4`、wasm で `0`。書込みは `0x161506` (`mov %edx, [0x3f5b80]`)、`edx` は `0x161780` の戻り値 (CPU 機能ビットから決まる level)。
- 仮説 (確定は未): wasm 側の `cpuid_model()` (`tools/flelift/rt/fle_cpu.c`) は leaf 1 ECX = `0x1`・leaf 7 無し。実機 (AMD EPYC・AVX2/BMI2/SSE4) は leaf 1 ECX = `0xfeda3203`・leaf 7 EBX = `0x219c07a9`。CPU モデルの差が level の差を生む。
- 実験 (不採用): wasm の `cpuid` を実機値に差し替えると level は 0→3 になったが、native は 4 のまま、13 件目は 70088 のまま。よって CPU モデルは寄与するが、差 0x500 の全部ではない。実験のコードは戻し、コミットしていない。

## 2. 13 件目の確保 (受入 1 の根拠)

測定 commit: `b2f7cee49` (診断コードを含む)。`c552566e3` からの差分は本診断 (`wc_glue.c`・`wc_native_ref.c`・`wc_run_wasm.mjs`・`lift_wc.sh`) のみ。`c552566e3` は診断追加前のため、13 件目の診断値はこの commit でしか得られない。

| 項目 | native | wasm |
|---|---|---|
| 13 件目 (tag=3 = slot 1・n=12) の要求サイズ | 71368 | 70088 |
| 差 | | 1280 (0x500) |
| 直前の確保 (n=11) | 16384 | 16384 |
| `[0x3f5b80]` (13 件目の時点) | 4 | 0 |

- 呼出し連鎖 (stack 走査・native 側・`[stk]` 行): `0x1b9c60` (retry wrapper) → `0x161561` → `0x17fbf9` (`call 0x10a0`)。
- `0x17fbc0` の関数で `0x17fbf4 call 0x10a0` の後に確保の要求を組み立てる。

## 3. 再現

診断は `WC_HEAP_LOG=1` を付けたときだけ動く (既定は従来どおり)。

```
WC_HEAP_LOG=1 WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola-s8 WC_INIT_RVA=0x1b7d80 WC_ARENA_SZ=0x400000 \
WC_ROOTS="0x1ab540 0x1ab590 0x1ab690 0x1ab6b0 0x1ab800 0x17f700 0x180830 0x1b7d80 0x1ab680 0x1ab6a0 0x112de0 0x115f00" \
WC_CALL_IDX="0 1 2 3 4 5" WC_RET_IDX="0 2 4 5" \
WC_CALL_ARGS="IN OUT 16 0;IN OUT 16 0;IN OUT 16 0;0 16 IN OUT;IN OUT 16 0;IN OUT 16 0" WC_LOG_FD=1 \
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/lift_wc.sh ok
```

- native 側は `[heap] tag=... n=... sz=... ret=... g3f5b80=...` を stderr に出す。wasm 側は `wc_glue.c` (`WC_HEAP_LOG` 定義時) で同形式を `fd_write` 経由で出す。
- 測定値 (測定 commit `b2f7cee49`): 差分 harness rc 1・elapsed 42.0 s・load 0.57→0.80。PASS=0 FAIL=64 (§1 の前回値と一致)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[0x3f5b80]` の level を決める `0x161780` の入力 (`R12` の機能ビット) の、native と wasm の差の確定 | 13 件目のサイズ差 0x500 の式が未確定。PASS 0 のまま | #5162 (残件・Refs) |
| wasm の `cpuid_model()` を実機値に合わせる範囲の決定 | 本物の CPU を模倣すると、他の slot の分岐も変わりうる。`cpuid` は runtime 共有のため、影響範囲の確認が要る | #5162 (残件) |

## 5. 受入判定

受入 1 (13 件目の呼出元 RVA・呼出し slot・init の区間の特定と、サイズ式 0x500 の REPORT 記載): **部分達成**。呼出元 RVA・slot・区間と、差の入力 (`[0x3f5b80]` の 4 対 0) は特定した。式の完全な導出 (level 決定の差を 1280 バイトへ変換する式) は未達。
