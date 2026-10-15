# REPORT_APPENDIX_3434 — guest imp_GetProcAddress の結線 (T-SH-83 / #3434)

REPORT.md §11 の全文 (行数上限 250 のため分割移動。内容は削除していない)。


既知類型との関係 (DEFECTS.md): 該当なし。測定 commit = `ddafc3602` (コードを変えた最後の commit)。`git diff ddafc3602 HEAD -- tools/flelift tools/qfclift/qfc_imp.c tools/qfclift/qfc_lift.sh tools/qfclift/env.sh tools/shared/oss/freetype` の出力は空 (差分 0)。HEAD 側の新規 commit は本節の REPORT 追記のみ。

**前提**: `qfc_lift.sh` の `wasm_build` (`qfc_e2e.sh` / `qfc_boot.sh` を含む全 QFC ビルド) は FreeType wasm32 の成果物 `FT_WASM32_LIB` (`tools/shared/oss/freetype/build.sh` の出力) を必ず link するため、ビルド前にそれを用意する (`env.sh` 参照)。

**結論 (部分達成)**: 受入条件 1 (`imp_GetProcAddress` → `qfc_gpa` の結線) を実装した。受入条件 2 (`FontCache_GetStats` / `FontCache_CleanUp` の wasm 実行) は未達 (DllMain が `0x59c210` の longjmp 継続で止まり、`0x563000` の FT 解決に届かない)。受入条件 2 は子 issue #4296 (`[T-SH-113]`) に移した。

### 11.1 結線の形
- `tools/flelift/rt/fle_cpu.c` の `imp_GetProcAddress` は、既定 NULL の `fle_gpa_hook (h, nm)` を呼ぶ (hook 未設定 = 従来どおり 0)。FLEngine の既定挙動は変えない。
- `tools/qfclift/qfc_imp.c` が constructor で `fle_gpa_hook = qfc_gpa_hook` と `fle_ff_hook = qfc_ff` を設定する。`qfc_gpa_hook` は `qfc_gpa(name)` を返す。`qfc_ff` は `unlifted` の VA がトークンなら `qfc_gpa_call` で実行し、Win64 の第 5 引数を `[RSP+0x28]` から読む。トークン以外は従来どおり abort する。
- 2 つの擬似値の範囲: トークン `0x7F200000+` と IAT pseudo-VA 基準 `IMP_VA_BASE = 0x1D80000` は重ならない。

### 11.2 検証 (実測。e2e `qfc_import_e2e.sh`、DejaVuSans.ttf)
| 検査 | 結果 |
|---|---|
| 既存: 表経由 / トークン経由 (native・wasm32・wasm64) | PASS (TOTAL `6e3c628e7e4a12df` / `d77adc88f7ca92a4`) |
| 新規: `test_qfc_gpa_hook.c` (imp_GetProcAddress → hook → token → ott_unlifted → qfc_gpa_call → FT_Get_Char_Index) | PASS。`FT_Get_Char_Index('A')` hook=36 = direct=36。表外 `FT_Alloc` は 0 |
| rt の compile (`fle_cpu.c` / `fle_glue.c`) | OK (gcc -std=gnu11) |

### 11.3 boot (受入条件 2 の前段。`qfc_boot.sh`、HEAD `ddafc3602`・n=1)
- lift: functions 6,347 / unsup 0 / unlifted 0 / imports 222 (前回と同じ)。
- strict: `DllMain(PROCESS_ATTACH)` = trap (`[fle] MISSING IMPORT LocalAlloc`)。soft: `[fle] call to UNLIFTED function 0x59c210`。判定 FAIL (前回 §7 と同じ停止点)。
- strict の `LocalAlloc` 欠落の理由: strict のビルド (`wasm_build` の `lift/qfcl.cjs`) は `qfc_imp.c` を link しない。`imp_LocalAlloc` は `qfc_imp.c` にあり、soft ビルド (`qfcl_soft.cjs`) だけが link する。よって欠落は rt の未実装ではなく、link 対象の差である。soft 側は `qfc_imp.c` で `LocalAlloc` を実装済みのため、§11.4 の「LocalAlloc は qfc_imp.c で実装済み」と一致する。
- boot 全体 real 50 s、load 開始 0.29 0.55 0.31。

### 11.4 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `FontCache_GetStats` / `FontCache_CleanUp` の wasm 実行 (受入条件 2) | 結線の実行確認が未到達。`0x563000` の FT 解決まで DllMain が届かない | #3410 / #3411 の後に再起票 |
| 戻り先 `0x59c210` (setjmp 継続) | DllMain 完走の前提 | #3410 (T-SH-77) |
| rt 未実装の import (LocalAlloc は qfc_imp.c で実装済み。残りは soft stub) | strict の停止 | #3411 (T-SH-78) |
