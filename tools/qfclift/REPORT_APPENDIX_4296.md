# tools/qfclift REPORT 付録 #4296 — T-SH-113: FontCache_GetStats / FontCache_CleanUp の直接呼出し

REPORT.md §7.9 の全文 (分割移動)。

## 7.9 FontCache_GetStats / FontCache_CleanUp の直接呼出し (T-SH-113 / #4296)

測定 commit = `c36a9b817` (`qfc_direct.mjs` を追加した commit)。lift・rt・boot 経路は無改変。DllMain を通さず、`fle_data_install` → `fle_init` の後に 2 関数を直接呼んだ。
引数仕様は REPORT に無いため、逆アセンブルから推定した (推定呼出し)。GetStats = `rcx=buf` (buf に 0x50 byte を書く)、CleanUp = `ecx, edx` の 2 int。

| 版 | 関数 | 引数 (推定) | 結果 | 停止点・根拠 |
|---|---|---|---|---|
| strict | FontCache_GetStats (VA `0x57faf0`) | buf (malloc 0x1000) | **trap** (`Aborted`) | 関数先頭の `call qword ptr [rax]` (`0x57fb07`)。`rax = [0x5cae18] = 0x5d8b48` (`.data`)、呼出先 `[0x5d8b48]` は `.bss` (raw 0) で **0 のまま**。`[fle] call to UNLIFTED function 0 ret=0x57fb09` が出て abort |
| strict | FontCache_CleanUp (VA `0x57f980`) | 0, 0 | ok・rax = `0x0` | 間接呼出しなし。戻り値は引数 (0,0) 依存の可能性あり (未検証) |
| soft | FontCache_GetStats | buf | **trap** (同じ停止点) | soft 呼出し 0 件 (abort は stub に入る前) |
| soft | FontCache_CleanUp | 0, 0 | ok・rax = `0x0` | soft 呼出し 0 件 |

- 実行: `QFC_CJS=<work/boot/lift/qfcl.cjs> QFC_OUT=<json> node tools/qfclift/qfc_direct.mjs` (lift は `qfc_boot.sh` の `work/boot/lift/` を使う)。`CleanUp` は `GetStats` の trap 後に別 instance で実行 (trap 後の wasm 状態は信用しないため)。
- 結論: **`FontCache_GetStats` は DllMain の init を経ないと実行できない**。`0x5d8b48` (`.bss`) の関数ポインタは DllMain 側で設定される前提 (推定。設定箇所は未特定。lifted code に `0x5cae18`/`0x5d8b48` への store は無い)。
  これは §7.4 の停止点 (DllMain が `0x59c210` の longjmp 継続で完走しない) と同じ前提の欠落で、直接呼出しでは回避できない。
- `FontCache_CleanUp` の rax = 0 は、引数 (0,0) での単発の値で、実物との一致は未確認。受入の「結果 (rc・戻り値・停止点) を実測で書く」は満たすが、PASS 判定ではない。
- 受入条件の未達: GetStats は wasm で完走しない。DllMain の完走 (#3411 の rt 実装・#4262 の偽の停止の確定・#4263 の longjmp 条件) が前提。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x5d8b48` (.bss 関数ポインタ) を設定する箇所の特定と、DllMain 完走後の値の確認 | GetStats が実行できない | #3411 (T-SH-78) / #4262 (T-SH-106) |
| CleanUp の rax = 0 が引数 (0,0) 依存か、実物と一致するか | CleanUp の PASS 判定 | #4296 (T-SH-113・継続) |
| GetStats・CleanUp の引数仕様 (逆アセンブルの推定のみ) | 呼出しの正しさ | #4296 (T-SH-113・継続) |

## 付録 2: FT 解決 (0x563000) の直接呼出し (T-SH-113 / #4296・再測定)

測定 HEAD = `1a81452eb` (origin/main 取り込み後)。`qfc_ft_resolve.mjs` (新規・計測専用) で、FT 解決 `0x563000` を GetStats より前に直接呼び、`[0x5d8b48]` の変化を見た。`qfc_boot.sh` の lift (`work/boot/lift/`、gitignore 対象) を使用。

| 版 | 項目 | 結果 |
|---|---|---|
| strict | 初期値 `[0x5d8b48]` / `[0x5cae18]` / `[0x5d9f20]` | `0x0` / `0x5d8b48` / `0x0` |
| strict | `0x563000` を直接呼出し | **trap** `RuntimeError: memory access out of bounds` ([fle] 出力なし) |
| strict | 呼出し後 `[0x5d8b48]` | `0x0` (未設定のまま) |
| strict | GetStats | trap `[fle] call to UNLIFTED function 0 ret=0x57fb09` |
| soft | 同上 | 同じ (resolve は OOB trap・GetStats は UNLIFTED function 0) |

- `0x563000` は `0x522d20` と `0x41d760` (GetProcAddress 相当と推定・逆アセンブルのみ) を呼ぶ。OOB の発生箇所は**未特定** (トレース未取得)。引数 0・前提状態なしで呼んだため、trap は「直接呼出しでは実行できない」ことの証拠であり、FT 解決そのものの失敗の証拠ではない。
- 結論: 直接呼出しでは `0x563000` を正しく実行できない (引数・前提状態が不明)。`[0x5d8b48]` を埋める経路は DllMain 内の本来の呼出し文脈が要る。
- 未解決: `0x563000` の正しい呼出し文脈 (DllMain 内での呼出し元と前提状態) の特定。起票先は OPEN の #3411 (T-SH-78)。新規の子は起票しない (重複回避)。
- 再現: `QFC_CJS=<work/boot/lift/qfcl_soft.cjs> QFC_OUT=<json> node tools/qfclift/qfc_ft_resolve.mjs`。

### 付録 2.1 qfc_boot.sh の再実行 (測定 HEAD `3d9b1188e`・n=1)

`QFC_BOOT_REBUILD=1 bash tools/qfclift/qfc_boot.sh` (lift + emcc ×2 + 実行 ×2 を含む)。素材 `fl-win64` を展開し、emsdk 6.0.12 と FreeType 2.7 wasm32 (`tools/shared/oss/freetype/build.sh`) を用意してから実行した。

| 版 | 停止段 | 停止点・根拠 |
|---|---|---|
| strict | DllMain(PROCESS_ATTACH) = trap | `[fle] MISSING IMPORT LocalAlloc` (rt 未実装 import。DllMain 完走せず) |
| soft | FontCache_GetStats = trap | `[fle] call to UNLIFTED function 0 ret=0x57fb09`。soft 呼出し 0 件 (DllMain は ok・rax=0x1) |

- 判定: strict / soft とも **FAIL** (PASS 条件を満たさない)。soft の停止点は §7.4 と同じ GetStats。strict の停止点は `LocalAlloc` で、soft と異なる。
- 所要: real 50 s・load `1.88 1.02 0.43 → 1.43 1.03 0.47` (nproc 4)。`qfc_boot.sh` の終了コード 1 (FAIL)。

### 付録 2.2 FT 解決 (0x563000) の再測定 (同 HEAD・n=1)

`qfc_ft_resolve.mjs` を上記 lift の `qfcl.cjs` / `qfcl_soft.cjs` に対して実行。

| 版 | 初期 `[0x5d8b48]` | `0x563000` 直接呼出し後 | GetStats |
|---|---|---|---|
| strict | `0x0` | trap `memory access out of bounds` (`[0x5d8b48]` = `0x0` のまま) | trap `[fle] call to UNLIFTED function 0 ret=0x57fb09` |
| soft | `0x0` | 同上 | 同上 |

