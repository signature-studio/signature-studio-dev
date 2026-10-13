# REPORT_912 — ClassCreate ON の ok 退行 4 件 (101 190 291 296) の oob 経路の切り分け (#912, 親 #704)

結論: unit 101 / 291 / 296 の oob は、`function_4fb090` の `4fa070` 呼出し第 2 引数 `dl` の IR 取り違え (機械語 `mov dl,1` を、IR がスタック番地の下位 byte にしていた) を直すと ok に戻る (実測。§6・§7)。修復 pass `fix912/m11_fix912.py` は既定 ON (`M11_FIX_912=1`)。機構 (`dl=0` → `410320` 欠落 → `410360` の oob) は仮説で、直接観測していない。既定 ON の ok は 868 で OFF の 869 より 1 件少ない (unit 190 が ok→oob)。190 は未解決 (#1274)。受入条件 3 は未達のため `Refs #912`。

## 1. 基準

- 検証起点 (測定の基準 main): `origin/main` = `412e302d`。PR ブランチの merge-base もこの commit (`git merge-base` で確認)。REPORT 旧版の「99b87bc2」は誤記で、`99b87bc2` は `412e302d` の祖先。
- 測定 commit (コードを変えた最後): `a5e9c1ed`。`2e6fba53` は `m11_build.sh` の既定値 (`M11_FIX_912:-0`→`:-1`) とコメントだけを変え、`fix912/` は変えていない (`git diff a5e9c1ed 2e6fba53 -- tools/m11/fix912` は 0 行)。
- **現 HEAD は測定 commit と同一ではない** (WORKFLOW §6 の差分 0 の条件を満たさない)。`git diff a5e9c1ed HEAD -- tools/m11/m11_passes.py tools/m11/m11_build.sh` は 2 files, 17 insertions(+), 2 deletions(-) で、内訳は (a) `m11_passes.py` の `pass_m2q_fn980ed0` (#1043 の function_980ed0 VA→LVA remap。`m11_gen_ir2.sh` が実行する pass で、IR を変える)、(b) `m11_build.sh` の `M11_FIX_912` 既定値変更。`a5e9c1ed` の IR は M2q を含まないため、§2・§7 の数値は**現 HEAD の IR の測定ではない**。
- 以下の §2・§7 の IR は `a5e9c1ed` 時点 (M2q 無し) のもの。現 HEAD (M2q 込み) の IR での表・既定 (環境変数なし) の実測は未実施 (理由と手順は §9)。
- 素材: `fl-win64` と `toolchain-retdec` は取得済み ([RETDEC] の `bin/` が存在)。ただし IR 再生成の入力 `functions_dll.csv` (Ghidra 出力) と `toolchain-emsdk` が揃わず、再測定は未実施。§2〜§7 の数値は `a5e9c1ed` 時点の実測。
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

**修復**: `tools/m11/fix912/m11_fix912.py` (IR pass・冪等・双方向。`m11_build.sh` に組み込み、既定 `M11_FIX_912=1`、`0` でネガコン)。SSA 名 (`%37`/`%39`/`%38`) と定数 `994072` を直書きしており、IR 再生成で変わると count != 1 で fail-loud になる (非必須・後続)。`--mode off` は修正済み IR に対しては未検証 (現 IR に対しては実質 no-op)。

## 7. 測定 (前 run・測定 commit `a5e9c1ed`、`m11_gen_ir2.sh` 再生成・同一 IR)

| 構成 | ok | oob | halt0 | miss | noproc | other | abort |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (修正 0 / 前) | 869 | 16 | 8 | 47 | 1 | 1 | 0 |
| OFF (修正 1) | 869 | 16 | 8 | 47 | 1 | 1 | 0 |
| ON (修正 0 / 前) | 867 | 18 | 8 | 47 | 1 | 1 | 0 |
| ON (修正 1 / 既定) | 868 | 15 | 8 | 47 | 1 | 1 | 2 |

- OFF 修正 0 vs 1: kind 差 0 (`survey_diff.py`)。frames の差も 0。
- 既定 ON (修正 1) vs OFF: ok→ok 868・ok→oob 1 (unit 190)・oob→ok 0・oob→abort 2 (304 / 555 は ON で abort。OFF では oob)。OFF の ok 869 が ON で 868 になる差し引き -1 は、unit 190 の 1 件。
- 101 / 291 / 296 は OFF で oob・ON で ok に戻った (この 3 件が修正の効果)。
- **既定 ON にする理由**: 修正で 101 / 291 / 296 の ok 退行 3 件が回復する。その代償として 190 が ok→oob の 1 件として残る。修正の効果 (+3) を優先し、既定 ON にした。190 の解消は #1274 で扱う。
- 304 / 555: ON で oob → abort (`function_535c2e` が IR 未定義で fail-fast)。ok 退行ではない。

## 8. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ON の ok 退行 190 (`function_412e40` で trap。`410360` を経由しない。呼出し元が多数) | 受入条件 (ON で ok 退行 0) が未達。既定 ON の差し引き -1 | #1274 `[M11-N77]` (親 #912) |
| 304 / 555 の ON abort (`function_535c2e` が IR 未定義 closure 外) | ON の abort 2 件 (OFF では oob のまま) | #1275 `[M11-N78]` (親 #912) |
| 修正 (`m11_fix912.py`) の DEFECTS 類型登録 | 文書のみ | #912 (本 issue) |
| `m11_fix912.py` の SSA 名・定数の直書き (IR 再生成で壊れやすい) | fail-loud (count != 1) で害は小さい | #912 (本 issue、非必須) |

## 9. 既定値変更 (`2e6fba53`) の鮮度と、本 run の再測定

- `a5e9c1ed..2e6fba53` の差分は `tools/m11/m11_build.sh` の既定値 (`M11_FIX_912:-0`→`:-1`) とコメントのみ。`tools/m11/fix912/` と IR 生成手順は 0 行 (`git diff a5e9c1ed 2e6fba53 -- tools/m11/fix912` = 0 行)。したがって §7 の数値 (修正 1 = ON) は既定値変更の前後で同じ修正・同じ IR に対するもの。
- ただし §7 の ON 行が `M11_FIX_912=1` を明示して走らせたか、既定 (環境変数なし) で走らせたかを示すログは残っていない。
- 本 run (fix 対応) の確認: `ls $ARTIFACTS_DIR` は `fl-win64.tar.zst` と `toolchain-retdec.tar.zst` (`[RETDEC]` の `bin/` が存在)。ただし次の 2 点が揃わず、IR 再生成と build を完走できなかった。
  - `m11_bounds.py` の入力 `tools/m2/work/ghidra_dll/functions_dll.csv` (Ghidra 12.1.4 出力) が無い。`fl-win64` の一覧 (25168 entry) に Ghidra 出力は無く、[GHIDRA] も無い。
  - `m11_build.sh` は [EMSDK] の `emsdk_env.sh` を要求するが、`toolchain-emsdk` は未指定で [EMSDK] が無い。
- よって現 HEAD での既定値の再測定は未実施。不足の内訳 (この run の確認):
  - `functions_dll.csv` は素材ではなく、Ghidra 12.1.4 headless (`tools/m2/README.md`・`DumpFunctions.java`) で作る中間物。[GHIDRA] (`docs/REFERENCES.md`) は無く、JDK 21 (temurin) は runner 同梱のものを使う。GitHub への到達は確認済み (200)。
  - `toolchain-emsdk` は未取得 ([EMSDK] 無し)。PR 本文の `oc_artifacts:` 行に追加する。
  - `work/boot*.lift.ll` は RetDec の全 lift (`m11_lift_all.sh`) が無いと生成されない。`docs/WORKFLOW.md` §11 の実測は `--full` が 633 秒 (head `2e128c5c`) で、素材と Ghidra 出力が揃っている前提。
  - この run は fix モードの上限 40 分で、Ghidra の取得と解析・emsdk の導入・全 lift を連続で行うと上限に収まらないと判断した。途中で打ち切られると push も記録も残らないため、再測定は行わず、この記録と素材の追加指定に留めた。
  - 次の run の手順: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk` で起動し、Ghidra 12.1.4 + JDK 21 で `functions_dll.csv` を作る → `m11_gen_ir2.sh` → `m11_build.sh` (既定) と `M11_FIX_912=0` → `survey_units.mjs` → §7 を書き直す。起票先は #912 (本 issue)。
- 差分の証跡: `git diff a5e9c1ed dc109d61 -- tools/m11/m11_passes.py tools/m11/m11_build.sh` は 2 files, 17 insertions(+), 2 deletions(-) (M2q の pass 追加と `M11_FIX_912` 既定値)。`tools/m11/` 全体の `git diff --stat` には、main 取り込みで入った他 PR の変更 (REPORT_N55・zeropad 等) も含まれる。測定経路の差分は上の 2 files が全て。
- 現 HEAD (`dc109d61` 以降) での手順: `bash tools/m11/m11_gen_ir2.sh` → `bash tools/m11/m11_build.sh` (環境変数なし) → `survey_units.mjs` を 1 回ずつ。`M11_FIX_912=1` の明示実行は既定変更の検証にならないため含めない。OFF/ON × 修正 0/1 の 4 構成は `M11_FIX_912=0|1` と既定の組で揃える。
