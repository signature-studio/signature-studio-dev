> **正本**: `tools/plugins/dynamics/REPORT.md`。本書は REPORT の付録 (250 行上限のため分割移動。内容は無変更)。

# tools/plugins/dynamics/REPORT_APPENDIX.md — #1412 脱落の原因 (付録)

## A. `.pdata` define 脱落の原因 (#1412)

REPORT §4 の「脱落の原因」の全文。 本付録は本体から分割移動した。

- 既定の RetDec 呼出し (`--disable-static-code-detection` 無し) が、定数 libc 系の関数を
  「statically linked function」として除去する (`e.retdec.log` の `Running phase: removing functions from standard libraries`)。
  19048 の欠落 210 件のうち **208 件** は dsm の `statically linked function` 行の開始 VA と一致 (`e.drc.dsm`)。 残る 2 件は
  `CreateEngine` (0x18000b1a0) / `entry_point` (0x18000bb98) で、RetDec は名前付きの `function:` として出力しており、
  `define @CreateEngine` / `define @entry_point` は final.ll に存在する。 `engine_defs.py` は `function_<VA>` 形式しか見ないため、この 2 件は偽陽性。
- ネガティブ/切替の実測: `PLUG_NO_STATIC_DETECT=1 bash tools/plugins/dynamics/engine_lift.sh 19048` で `missing_define` 210 → **2** (97 B)、`missing_ref` 67 → **0**、`define` 1,504 → 1,712。
- 残りの 2 件 (19252 の 165 B / 19048 の 97 B) は、いずれも dsm で `function: <名前> at <VA>` として出る `CreateEngine` / `entry_point` で、`final.ll` に `define @CreateEngine` / `define @entry_point` が存在する。 `engine_defs.py` の偽陽性だったため、本 run で名前付き define を計上するように修正した (commit db4fe1f0)。 これで両 engine の実在の欠落は 0 件。
- 既定値 (`lift_ranges.sh` の `PLUG_NO_STATIC_DETECT:-1`) は commit 0d51d876 (#1536) で切替済み。 本 run は既定のまま測定した。
- `engine_fixcmp.py` の `%penv` 修正は commit 5457975c (#1163) で入っており、切替後の 19048 は fixcmp 後 `emcc -c` rc 0。 raw の `final.ll` は `%arg2` i32/i64 の型不整合で rc 1 のまま (既存の修正対象。 `engine_fixcmp.py` で吸収)。

## B. fixcmp の call 引数拡張による 19048 の `emcc -c` 解消 (#1163 run)

- 原因: `engine_fixcmp.py` は `icmp ptr` の被演算子しか扱わず、`call` の `ptr` 引数に i64 仮引数を渡す箇所 (`call i1 @FreeEnvironmentStringsW(ptr %penv)`、`%penv` は i64) が残っていた。 `emcc -c` は最初の型エラーで止まる。
- 修正: `engine_fixcmp.py` に、`call` の `ptr` 引数で i64 値の箇所へ `inttoptr` を挿入する処理を追加 (engine 局所。共有 lift 鎖には入れない)。
- 測定 (`engine_lift.sh` 単独実行、HEAD = 本 PR の commit):

| engine | unimpl | emcc_c_rc (final.ll) | fixcmp patched | emcc_c_rc_after_fixcmp | missing_define | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|
| 19252 Transient | 5 | 0 | 0 | 0 | 2 | 16 |
| 19048 Multiband | 5 | 1 | 2 | 0 | 97 B / 2 件 | 63 |

- 変更前 (main) の 19048 は `emcc_c_rc_after_fixcmp` = 1 (`%penv` の型)。 変更後は 0。
- 生成 helper C (`tools/plugins/work/dynamics/simdchk<B>/m11_simd.c`、`msimd11_core.h` を親 dir に置いて `emcc -c`): 19252 rc 0 / 19048 rc 0。
- 未実装 helper の残件は両 engine とも 5 件 (`movntps`・`vmovsd` store・`vcomisd`・`vucomisd`・`vucomiss`。19048 は `vcomisd__22` を含む)。 #1408 の範囲。
- 共有鎖 (`lift/passes/`・`lift_ranges.sh`) への影響なし (本変更は `dynamics/engine_fixcmp.py` のみ)。
