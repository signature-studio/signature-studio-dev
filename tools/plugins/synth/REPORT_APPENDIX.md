# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` 実測

- 本書は REPORT.md (250 行上限) の付録。結論は REPORT.md §0-4 と §5 を見る。
- 測定 HEAD: **604e900f** (origin/main。本 commit はコードを変えていない)。素材 `fl-win64` / `toolchain-emsdk` (emcc 6.0.12) / `toolchain-retdec` を `$HOME/artifacts` から展開して使用。
- 測定コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/plugins/synth/cpp_lift.sh <block> 2400` (9 本を `xargs -P 3`。既定の `HLL_CAP=300` のまま)。
- 測定の総経過: 472 s (9 本、終了コード 0 が 9 本)。 load (測定後): `1.35 1.85 1.09`。
- 出力: `tools/plugins/work/synth/cpp<block>/` (gitignore。`summary.csv` / `emcc.log` / `e.final.ll`)。

## A. 実測 (604e900f)

`summary.csv` 各列の値 (列名は `cpp_lift.sh` の先頭コメント参照)。`emcc_c_rc` 0 = `emcc -c` 通過。

| block | DLL | `.pdata` 関数 | defines | 欠落 define | 未実装 helper | i256 trap | f80 関数 | `emcc_c_rc` | lift 秒 | hll_killed_s | 最初のエラー |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| 21202 | BooBass_Eng | 1,579 | 1,393 | 211 | 15 | 3 | 0 | **1** | 54 | 0 | `'%arg2' defined with type 'i32' but expected 'i64'` (E3) |
| 23914 | Kepler engine | 3,194 | 3,697 | 2 | 103 | 3 | 0 | **0** | 159 | 0 | — |
| 23916 | Kepler Exo engine | 3,193 | 3,694 | 2 | 104 | 3 | 1 | **1** | 138 | 0 | `no libcall available for fp_round with type f80` |
| 23944 | Morphine | 3,050 | 3,321 | 1 | 121 | 24 | 0 | **0** | 407 | 354 | — |
| 24159 | PoiZone engine | 1,638 | 1,790 | 1 | 101 | 3 | 0 | **0** | 54 | 0 | — |
| 24163 | Sakura engine | 1,644 | 1,707 | 1 | 84 | 3 | 1 | **1** | 57 | 0 | `do not know how to soften fp_extend` |
| 24167 | Sawer engine | 1,676 | 1,833 | 1 | 83 | 3 | 1 | **1** | 57 | 0 | `do not know how to soften fp_extend` |
| 24216 | Toxic Biohazard | 1,841 | 1,927 | 1 | 94 | 3 | 1 | **1** | 93 | 0 | `do not know how to soften fp_extend` |
| 24298 | Transistor Bass engine | 3,257 | 3,741 | 2 | 87 | 3 | 0 | **0** | 108 | 0 | — |

- `emcc -c` 通過: **4/9** (23914 / 23944 / 24159 / 24298)。不通過 5 本: BooBass_Eng (E3 1 件)、f80 libcall 4 本 (23916 / 24163 / 24167 / 24216)。
- E1 (`fix_icmp_ptr.py`): `fixcmp_patched` は 9 本とも 0 (`engine_fixcmp.py` の適用なし)。共有鎖で解消済みのため、修復前後の rc は不変。
- Morphine (23944): `hll_killed_s` 354 — RetDec の HLL 段を kill して `.ll` から再開した経路。通常経路 (HLL 段を含む) の最後までの実測は無い。
- `known.json`: 通過 4 本の `emcc_c_rc` を除去。残りの fails (`declares_unimpl` / `i256_trap` / `missing_define` と不通過 5 本の `emcc_c_rc`) は未解決。
- judge (C++ 9 本の行のみ、`mk_status.py` 相当の列で作成): KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0 / exit 0。`synth_e2e.sh` 全体 (shell 12 本) は未実行。

## B. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round`) | 不通過 4 本 (23916 / 24163 / 24167 / 24216) | #534 (本 issue)。f80→f64 は精度が変わるため既定外。扱いは判断が要る |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 不通過 1 本 | #1301 (PLG-G2-13) |
| define 欠落 (BooBass_Eng 211 件) | 1 本 (他 8 本は 1〜2 件) | #1301 (PLG-G2-13) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | 未実測 (再開経路のみ) | #1301 (PLG-G2-13) |
| VEX helper 未実装 (未実装 helper 件数 83〜121) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) | 今回の最初のエラーには出ず未再現。 網羅の確認は未実施 | #534 (本 issue) |

## C. #1486: BooBass_Eng (21202) の define 欠落 211 件の原因分類

- 測定 commit: **0b233323** (コードを変えた最後の commit。`git diff 0b233323 HEAD -- tools/plugins/lift tools/plugins/synth` は 0 行)。 測定 HEAD も 0b233323。
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-liftlib` / `work-fw-stage1` / `plugins-ott` を `$HOME/artifacts` から展開して使用。
- 測定: `bash tools/plugins/synth/cpp_lift.sh 21202 1500` (既定) = 40 s、 load (測定前後) `0.20 0.35 0.25` → `0.59 0.43 0.29`。
  `summary.csv` = `21202,1579,0,1393,0,3,3,1,0,1,39,211,25828,67,23,1391,0` (欠落 211 / 25,828 B / 参照 67 は #1301 の実測と一致)。
- 分類コマンド: `python3 tools/plugins/synth/missing_define_classify.py tools/plugins/work/synth/cpp21202` (新規)。

### C-1. 原因の分類 (件数)

| 原因 | 件数 | 参照あり (`missing_ref`) | 長さ合計 (B) | 切り分けの根拠 |
|---|--:|--:|--:|---|
| (a) RetDec の静的コード検出で `statically linked function` 扱い | **209** | 67 | 25,411 | `e.drc.dsm` が `; statically linked function: ... at <VA>` と label。 `define` が出ない |
| (b) RetDec が関数名で `define` を出す (`function_<VA>` でない) | **2** | 0 | 417 | `CreatePlugInstance` (0x1800029a0) と `entry_point` (0x180005a50)。 `e.drc.ll` に `@CreatePlugInstance` / `@entry_point` として定義あり |
| (c) 未分類 | 0 | 0 | 0 | — |

- 209 件の内訳 (長さ): 64 B 以下 137 件 / 65〜256 B 60 件 / 257 B 以上 12 件。
- 「pass 鎖で消える」は **0 件**。 `e.drc.ll` の define 数 (1391) は、正規化 → `ir5_patch` → … → `e.final.ll` の全段で変わらない (`for f in e.*.ll` の計数で確認)。 欠落は RetDec 段で生じる。
- 別名化 (`function_<VA>` が無く、範囲の内側に別の define がある) は 0 件。 23 件の余分な define (range 開始 VA でない) は既存で、欠落とは別。

### C-2. 代表例と再現コマンド

- (a) 代表 `0x180002bf0-0x180002c1a` (len 43, 参照なし):
  `RetDec` を単独 range で実行すると `; statically linked function: ??_G?$codecvt@DDU_Mbstatet@@@std@@MEAAPEAXI@Z at 0x180002bf0` と出て `define` が無い。
  再現: `/opt/retdec/bin/retdec-decompiler $RUNNER_TEMP/fl-win64/extracted/block21202_PE.bin -o x.c --select-ranges 0x180002bf0-0x180002c1a --select-decode-only` → `grep -c ^define x.ll` = 0。
  同じ range に `--disable-static-code-detection` を付けると `define i64 @function_180002bf0(i64, i64)` が出る。
  参照ありの代表 `0x180005a98-0x180005acb` (len 52) も同じ経路 (`__raise_securityfailure`)。
- (b) 代表 `0x1800029a0-0x180002b03` (`CreatePlugInstance`, len 356):
  `grep -n '^define .*@CreatePlugInstance' work/synth/cpp21202/e.drc.ll` でヒット。 `function_1800029a0` は無い。 `missing_define` 判定 (開始 VA の `function_<VA>` 有無) では欠落扱いになるが、関数としては出力されている。

### C-3. 修復 (opt-in)

- `tools/plugins/lift/lift_ranges.sh` に `PLUG_NO_STATIC_DETECT=1` を追加 (既定 0 = 挙動不変)。 RetDec に `--disable-static-code-detection` を渡す。 pass 鎖 (`lift/passes/`) は触らない (原因は RetDec 段のため)。
- 実測 (0b233323、 `PLUG_NO_STATIC_DETECT=1 bash tools/plugins/synth/cpp_lift.sh 21202 1500`): 40 s、 `summary.csv` = `21202,1579,0,1602,0,21,3,1,0,1,39,2,417,0,23,1600,0`。
  欠落 **211 → 2** (B 25,828 → 417)、参照欠落 **67 → 0**。 未実装 helper 3 → 21 (`__asm_vroundsd` / `__asm_vucomisd` 等。 新規に見えた関数の VEX 命令。 今回は未対処)。
- `emcc -c` は既定と同じく **rc 1** (最初のエラーは既存の E3 `'%arg2' defined with type 'i32' but expected 'i64'`)。 emcc は最初のエラーで止まるため、回復した 209 関数に後段の型エラーがあるかは未確認。
- 既定にしない理由: 既定化は `lift_ranges.sh` を使う全 lift の出力を変える。 8 本の他 C++ DLL は `static_labels=0` で出力不変 (下記) だが、 他の batch への影響を未確認のため opt-in に留める。
- 他 8 本 (`PLUG_NO_STATIC_DETECT=1` と既定の両方で測定、 HEAD 0b233323): `summary.csv` は 8 本とも両者で同一。 `emcc_c_rc` は 604e900f の表 (§A) と同一 (23914=0 / 23916=1 / 23944=0 / 24159=0 / 24163=1 / 24167=1 / 24216=1 / 24298=0)。 `static_labels` は 8 本とも 0。

### C-4. 未解決 (起票先)

| 未解決 | 件数 | 起票先 |
|---|--:|---|
| 静的検出の既定化 (`PLUG_NO_STATIC_DETECT` を既定 1 にする) と他 batch への影響確認 | 209 件 (BooBass_Eng) | 子 issue (本 run で起票) |
| 関数名で出る 2 件 (`CreatePlugInstance` / `entry_point`) の `function_<VA>` への正規化 | 2 件 | 子 issue (本 run で起票) |
| 回復 209 関数の後段 (emcc 型エラー) の確認。 E3 が先に止めるため未確認 | 209 件 | #1301 (PLG-G2-13) |
