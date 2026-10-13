# REPORT_912 — ClassCreate ON の ok 退行 4 件 (101 190 291 296) の oob 経路の切り分け (#912, 親 #704)

結論: unit 101 / 291 / 296 の oob は、`function_4fb090` の `4fa070` 呼出し第 2 引数 `dl` の IR 取り違え (機械語 `mov dl,1` を、IR がスタック番地の下位 byte にしていた) を直すと ok に戻る (実測。§6・§7)。修復 pass `fix912/m11_fix912.py` は既定 OFF (`M11_FIX_912=1` で有効化)。既定を OFF にした理由: 測定 commit `c05c11e4` (M2q 込み IR) では ON/OFF の survey 差が 0 (942 unit 全一致、§10)。101 / 291 / 296 の oob 解消は**旧 IR (測定 commit `a5e9c1ed`、M2q 無し) での実測**であり、M2q 込み IR では効果を確認できない。現 HEAD (main 取り込み後) は未測定 (§10 の差分節)。機構 (`dl=0` → `410320` 欠落 → `410360` の oob) は仮説で、直接観測していない。190 は旧 IR でのみ ON で ok→oob (未解決 #1274。c05c11e4 では ok)。受入条件 3 は c05c11e4 で ON/OFF の差 0 で成立するが、fix912 の効果によるものではない (M2q で同じ現象が消えている可能性。未確認)。PR は `Refs #912` の部分達成。

## 1. 基準

- 検証起点 (測定の基準 main): `origin/main` = `412e302d`。PR ブランチの merge-base もこの commit (`git merge-base` で確認)。REPORT 旧版の「99b87bc2」は誤記で、`99b87bc2` は `412e302d` の祖先。
- 測定 commit (コードを変えた最後): `a5e9c1ed`。`2e6fba53` は `m11_build.sh` の既定値 (`M11_FIX_912:-0`→`:-1`) とコメントだけを変え、`fix912/` は変えていない (`git diff a5e9c1ed 2e6fba53 -- tools/m11/fix912` は 0 行)。
- **現 HEAD は測定 commit と同一ではない** (WORKFLOW §6 の差分 0 の条件を満たさない)。`git diff a5e9c1ed HEAD -- tools/m11/m11_passes.py tools/m11/m11_build.sh` は 2 files, 17 insertions(+), 2 deletions(-) で、内訳は (a) `m11_passes.py` の `pass_m2q_fn980ed0` (#1043 の function_980ed0 VA→LVA remap。`m11_gen_ir2.sh` が実行する pass で、IR を変える)、(b) `m11_build.sh` の `M11_FIX_912` 既定値変更。`a5e9c1ed` の IR は M2q を含まないため、§2・§7 の数値は**現 HEAD の IR の測定ではない**。
- 以下の §2 の IR は `a5e9c1ed` 時点 (M2q 無し) のもの。M2q 込み IR (c05c11e4) の実測は §10 が正 (既定 ON/OFF とも ok 870・全 942 unit 一致)。
- 既定値の変更 (`M11_FIX_912` 既定 1→0) の確認 (`cmp` の結果) は §11 に記録する。
- `m11_gen_ir2.sh`: 37.9 s (rc=0)。ldfix=applied (F1=902、errors=0)。
- `m11_build.sh` ON: 22.9 s (rc=0、signature mismatch 0・undefined symbol 0)。OFF: rc=0。
- `survey_units.mjs`: ON 9.3 s (rc=0)、OFF (rc=0)。load average 0.24–0.49。

## 2. 測定 (修正前・同一 IR・同一 build 系列)

以下は修正 (`fix912`) を入れる前の測定。修正後の数値は §7。

| 構成 | ok | oob | halt0 | miss | noproc | other |
|---|--:|--:|--:|--:|--:|--:|
| OFF | 869 | 16 | 8 | 47 | 1 | 1 |
| ON | 867 | 18 | 8 | 47 | 1 | 1 |

- `survey_diff.py` (OFF→ON): ok→oob 4 (101 190 291 296)、oob→ok 2 (304 555)。ok 退行 unit: 101, 190, 291, 296。
- REPORT_704 の表 (OFF oob 17 / ON oob 19) とは 1 ずつ違う (本 run は OFF oob 16 / ON oob 18)。原因は未切り分け (基準 IR の差の可能性)。ok 数 (869 / 867) は一致。
- ON では 0x41037d が 1049 ok / miss 2 (OFF は 0)。4 件の unit ではいずれも 0x41037d が 1 hit 立つ。

## 3. 4 件の trap 位置 (SV_RAW の生 frame を `oob_insn.py` で逆引き)

| unit | 最上位 frame | 命令 (wasm offset) | 備考 |
|--:|---|---|---|
| 101 | `function_410360` | `i64.load` (`[ptr-80]` 相当) | 直前に VA-big 125.3 MB (#20) |
| 190 | `function_412e40` | `i32.load` (`[ptr-8]` 相当) | 呼出し元 `function_6cf480` ほか。410360 を経由しない |
| 291 | `function_410360` | 同上 | 直前に VA-big 125.3 MB (#23) |
| 296 | `function_410360` | 同上 | 直前に VA-big 125.3 MB (#24) |

## 4. 410360 の入力値 (C 側に一時 probe を入れて実測。probe は取り除き済み)

- `function_410360` の入口で `inst` を記録した。unit 101 では `inst=0x10bb93a0` (正常な heap 値) の呼出しが通った後、VA-big が出て、次の呼出しで `inst=0x000f2b18` になり trap した。291 / 296 も同じ形 (`0x10bb9520` / `0x10bb9580` → `0xf2b18`)。
- 190 は `inst=0x10bd4d10` の 1 回で trap し、410360 の入口はこの 1 回だけ。
- 上流の `410320` (ClassCreate) の戻り値を記録すると、unit 101 の VA-big 直前の最後の `410320` は `ret=0x10bb93a0` を返していた (記録の末尾 8 行で確認。全 unit・全呼出しでは未確認)。`0xf2b18` を返した `410320` は、記録した範囲では見えていない。
- 呼出し元 `function_4fa070` は、`dl != 0` のとき `410320` の戻り値を `[rbp+0x70]` に保存し (4fa09f)、後段 4fa0f3 で `rcx=[rbp+0x70]` を `410360` に渡す。`0xf2b18` はこの経路の戻り値ではない。

## 5. 観測事実と未特定の点 (起票先付き)

観測済み:
- unit 101 / 291 / 296 では `410360` の `inst` が `0x10bb93a0` 系の正常値の後に `0x000f2b18` になって trap する (§4)。
- 記録した範囲で、最後の `410320` の戻り値は `0x10bb93a0` だった。`0xf2b18` を返した `410320` は見えていない。

未特定:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x000f2b18` が `410360` の `inst` に入る経路 (`4fa070` の 2 回目の invocation の入力、または VA-big 直後の `[rbp+0x70]` 上書き)。§6 の機構との対応は未確認 | 4 件の oob の直接経路 | #912 (本 issue) |
| 190 の `412e40` 経由の trap (410360 を経由しない) | ON の ok 退行 1 件 | #1274 `[M11-N77]` |
| `Q(inst)` が指す値の中身 (ON で `0xf2b18` の内容) を未測定 | 値の破損元の切り分け | #912 (本 issue) |

## 6. 事実・仮説の分離

**実測で言えること (修正の効果)**:
- IR の `function_4fb090` 内の `4fa070` 呼出しは、第 2 引数が定数 1 ではなくスタック変数の下位 byte になっている (`%39 = call @function_4fa070(994072, i64 %37, ...)`)。機械語は `4fb12f: mov dl,1`。
- `fix912` (第 2 引数を 1 に置換) を入れると、unit 101 / 291 / 296 は ok に戻る (§7)。
- `fix912` の OFF 比較 (`M11_FIX_912=0` と 1、OFF 構成) では kind 差 0・frames 差 0 (§7)。

**仮説 (直接観測していない)**:
- `dl = 0` のとき `4fa070` が `410320` (ClassCreate) を飛ばし、VMT 自身を `410360` に渡して `[vmt-0x50]` の読みで oob になる。
- 注意: `4fb090` の `rcx` は VMT `0x4f2b18` だが、§4 の `inst=0x000f2b18` とは上位桁が違う。この 2 つの値が同じ経路かは未確認。`dl=0` で `410320` が実際に飛ばされることも、直接観測はしていない (観測済みは `410320` の戻り値 `0x10bb93a0` だけ)。
- 上の仮説は修正の実測効果で支持されるが、機構としては確定していない。

**分類**: D4 (deref・引数の取り違え) と同系の lift 欠陥を疑う。`docs/DEFECTS.md` への登録は未実施 (類型名の確定は PM 判断。#912)。

**修復**: `tools/m11/fix912/m11_fix912.py` (IR pass・冪等・双方向。`m11_build.sh` に組み込み、既定 `M11_FIX_912=0` (OFF)、`1` で有効化)。SSA 名 (`%37`/`%39`/`%38`) と定数 `994072` を直書きしており、IR 再生成で変わると count != 1 で fail-loud になる (非必須・後続)。`--mode off` は修正済み IR に対しては未検証 (現 IR に対しては実質 no-op)。

## 7. 測定

- M2q 込み IR (測定 commit `c05c11e4`) の測定は §10 が正 (ON/OFF ともに ok 870、全 942 unit 一致。fix912 の効果はこの IR では無い)。
- 以下の §7-旧 は `a5e9c1ed` 時点・M2q 無し IR の実測。旧 IR での効果 (101 / 291 / 296 の回復) の根拠として残す。c05c11e4 には当てはまらない。

### 7-旧. 測定 commit `a5e9c1ed`、M2q 無し IR (旧 IR での実測。c05c11e4 で再現せず)

| 構成 | ok | oob | halt0 | miss | noproc | other | abort |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (修正 0 / 前) | 869 | 16 | 8 | 47 | 1 | 1 | 0 |
| OFF (修正 1) | 869 | 16 | 8 | 47 | 1 | 1 | 0 |
| ON (修正 0 / 前) | 867 | 18 | 8 | 47 | 1 | 1 | 0 |
| ON (修正 1 / 既定) | 868 | 15 | 8 | 47 | 1 | 1 | 2 |

- OFF 修正 0 vs 1: kind 差 0 (`survey_diff.py`)。frames の差も 0。
- 既定 ON (修正 1) vs OFF: ok→ok 868・ok→oob 1 (unit 190)・oob→ok 0・oob→abort 2 (304 / 555 は ON で abort。OFF では oob)。OFF の ok 869 が ON で 868 になる差し引き -1 は、unit 190 の 1 件。
- 101 / 291 / 296 は OFF で oob・ON で ok に戻った (この 3 件が修正の効果)。
- **(旧 IR 時点の判断。現在は撤回し既定 OFF。§10 参照)** 既定 ON にする理由: 修正で 101 / 291 / 296 の ok 退行 3 件が回復する。その代償として 190 が ok→oob の 1 件として残る。修正の効果 (+3) を優先し、既定 ON にした。190 の解消は #1274 で扱う。
- 304 / 555: ON で oob → abort (`function_535c2e` が IR 未定義で fail-fast)。ok 退行ではない。

## 8. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ON の ok 退行 190 (`function_412e40` で trap。`410360` を経由しない。呼出し元が多数) | 受入条件 (ON で ok 退行 0) が未達。既定 ON の差し引き -1 | #1274 `[M11-N77]` (親 #912) |
| 304 / 555 の ON abort (`function_535c2e` が IR 未定義 closure 外) | ON の abort 2 件 (OFF では oob のまま) | #1275 `[M11-N78]` (親 #912) |
| 修正 (`m11_fix912.py`) の DEFECTS 類型登録 | 文書のみ | #912 (本 issue) |
| `m11_fix912.py` の SSA 名・定数の直書き (IR 再生成で壊れやすい) | fail-loud (count != 1) で害は小さい | #912 (本 issue、非必須) |

## 9. 既定値変更の鮮度と、現 HEAD の再測定

- 既定値は現在 OFF (`M11_FIX_912` 既定 0)。`m11_build.sh` の fix912 ブロックは、`c05c11e4` (既定 1) から `e8dde459` (既定 0) で 3 行置換された (`:-1`→`:-0` を含む。差分の詳細は §10)。
- 既定 0 の動作は `M11_FIX_912=0` と同じ OFF 経路 (`[ "${M11_FIX_912:-0}" = 1 ]` が偽) なので、§10 の OFF 行は既定 build の動作の実測として扱う。
- 現 HEAD (main 取り込み後) の再測定は本 run では未実施。理由は §10 の「差分」節のとおり。現 HEAD の数値は本 REPORT に無い。
- `functions_dll.csv` の作成手順・素材の内訳は §10 が正。

## 10. 現 head の実測 (測定 commit `c05c11e4`・M2q 込み IR)

- 測定 commit (コードを変えた最後): `c05c11e4`。本節は `c05c11e4` の測定であり、**現 HEAD の測定ではない** (下の「差分」節のとおり、`c05c11e4` 以降に測定経路のコード差分が入っている)。
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `work-m11` を展開 (`$HOME/artifacts` の実在確認済み。この測定は `c05c11e4` 時点の run)。[EMSDK] は既存。Ghidra は無いが、`m11_gen_ir2.sh` は `functions_dll.csv` を読まずに完走する (`m11_bounds.py` 等の別経路が使う)。
- 注意: 本 fix run (`e8dde459` 以降) では `work-m11` が `$ARTIFACTS_DIR` に無く未展開。よって本節の数値は現 HEAD ではなく `c05c11e4` の測定。
- IR: `m11_gen_ir2.sh` rc=0 (43.3 s)。`ir_conditions.json` の `ir_sha256` = `16d1bae6…d869` (fix912 適用前の `boot_final.ll`)。`ldfix=applied`。
- build: 既定 ON rc=0 (24.5 s、`[fix912] mode=on replaced=1`)。`M11_FIX_912=0` rc=0 (`[fix912] mode=off replaced=1`)。wasm の sha256 は ON `e1d20106…` / OFF `9fe86216…` で異なる (build の切替は効いている)。
- survey: `survey_units.mjs` 各 rc=0 (約 13 s、load avg 0.41)。

| 構成 | ok | oob | halt0 | miss | noproc | other | abort |
|---|--:|--:|--:|--:|--:|--:|--:|
| 既定 ON (`c05c11e4` 時点の既定 1・環境変数なし) | 870 | 16 | 7 | 47 | 1 | 1 | 0 |
| OFF (`M11_FIX_912=0`) | 870 | 16 | 7 | 47 | 1 | 1 | 0 |
| ON 再 build (既定 1・2 回目) | 870 | 16 | 7 | 47 | 1 | 1 | 0 |

- 942 unit の kind を unit 単位で比較: ON (既定) と OFF は**全 942 unit 一致**。ON と ON 再 build も全 942 unit 一致。
- 101 / 190 / 291 / 296 は ON・OFF ともに ok。304 / 555 は ON・OFF ともに oob (abort ではない)。
- **既定 ON の差し引き: ok 0 (OFF と同数)。** §7 の「OFF で 101 / 291 / 296 が oob」は、c05c11e4 では再現しない。よって §7 の +3 / -1 はc05c11e4 の効果ではない。
- c05c11e4 で oob の 16 unit: 144 149 275 280 304 477 484 492 513 520 555 659 745 830 880 923。halt0 の 7 unit: 114 245 279 314 509 647 895。
- 未解明: `m11_passes.py` の M2q (`a5e9c1ed` 後に入った) が、旧測定の IR を変えた可能性。本 run では切り分けていない。`fix912` の対象行 (`i64 %37`→`i64 1`) は ON build の `boot_final3.ll` で置換されている (count 1)。

### 差分 (測定 commit から HEAD まで)

`git diff c05c11e4 HEAD -- tools/m11 ':(exclude)*.md'` は 0 行ではない。内訳:

- `c05c11e4` → `e8dde459` (main 取り込み前の head): `tools/m11/m11_build.sh` の fix912 ブロックの 3 行置換 (コメント 2 行と呼出し行。既定値 `:-1`→`:-0` を含む)。既定 0 の経路は OFF 行と同一なので、既定 OFF の build は §10 の OFF 行で代替する。
- `e8dde459` → 現 HEAD (merge `2fe2dd25`、main `a03c1d2f` 取り込み): main 由来の測定経路の変更が入る。`m11_win.c` (EnumDisplayMonitors / GetMonitorInfoW の仮実装)、`m11_extra_ranges5.txt` (範囲 0x85df70-0x85dfa8 の追加)、`ldfix/` 配下 (`ldfix_509_e2e.sh`・`retdec_stage_1091.py`・`retdec_negctl_1091.py`・`trk_probe_1134.py`・`trap_units.mjs`・`results/reach_930.json`)。IR・build に効きうるため、現 HEAD の数値は測定が必要。
- 現 HEAD の再測定は本 fix run では未実施。理由: `work-m11` が `$ARTIFACTS_DIR` に無く、全 lift (`m11_lift_all.sh`・Ghidra 解析を含む) の再生成が fix モードの上限 (40 分) に収まらないと判断した。途中で打ち切られると push も記録も残らないため、測定はせず、この差分と未実施を記録する。次の再測定は #912 で行う。

### functions_dll.csv の作成 (依頼 3)

- 作成: 可。Ghidra 12.1.4 (`Ghidra_12.1.4_build` の公開 release zip を `gh release download` で取得し `$RUNNER_TEMP` に展開) + JDK 21 (`/usr/lib/jvm/temurin-21-jdk-amd64`)。`tools/m2/README.md` の headless 手順 (`DumpFunctions.java`、`-analysisTimeoutPerFile 1200`) で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` を解析。rc=0、9 分 44 秒。
- 出力: `tools/m2/work/ghidra_dll/functions_dll.csv` (2.0 MB)。gitignore 対象のため commit しない。
- `m11_gen_ir2.sh` と `m11_build.sh` は `functions_dll.csv` を読まずに完走した (§10)。`functions_dll.csv` は `m11_bounds.py` 等の別経路の入力。
- 注意: `FL_WIN64_DIR` を export せずに Ghidra を起動すると、空のパス `/extracted/block00031_PE.bin` で即失敗する。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` を明示する。

## 11. 既定 OFF の build と main の cmp (測定 commit `e8dde459`、main `90a6e664`)

- 測定 commit (コードを変えた最後): `e8dde459` (`M11_FIX_912` 既定 0)。`git diff origin/main e8dde459 -- tools/m11/m11_build.sh` は fix912 の 4 行追加 (コメント 2 行・呼出し・`cmp` による置換) のみ。main (`90a6e664`) との差はこの 4 行だけ。
- IR: `m11_gen_ir2.sh` rc=0 (43.7 s)。`boot_final.ll` sha256 = `16d1bae6…d869` (fix912 適用前、§10 と同一)。main 側 (`origin/main` = `90a6e664` の detached worktree) でも同じ IR・同じ sha256 `16d1bae6…`。
- build (既定、環境変数なし): `m11_build.sh` rc=0 (25.1 s)。`[fix912] mode=off replaced=0` (no-op)。`boot_final3.ll` sha256 = `12a49c09…b99`。
- main 側の既定 build: rc=0 (22.7 s)。`boot_final3.ll` sha256 = `12a49c09…b99`。
- **`cmp work/boot_final3.ll` (ws-1276 の既定 build と main の build): 一致 (CMP_IDENTICAL)。**
- 結論: `e8dde459` 時点の既定 build の挙動は、同時点の main (`90a6e664`) と同一。fix912 は既定 OFF で no-op。ON 時 (`M11_FIX_912=1`) の効果は §10 (`c05c11e4` 測定の ON/OFF 差 0) を参照。
- 注意: 上の cmp は `90a6e664` との比較で、merge `2fe2dd25` で取り込んだ main (`a03c1d2f`) とは比較していない。現 HEAD と main の cmp は未実施 (§9・§10 と同じ理由)。
