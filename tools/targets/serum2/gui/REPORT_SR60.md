# REPORT — [SR-60 #4164] Serum 2 vtable 経由の呼出元で ARG・THIS の引数型を確定する (SR-59 残・静的)

- 日付: 2026-10-15 / 親: #4122 (SR-59) / 前段: `REPORT_SR59.md` (vtable 形の表への所属関数の出現・`arg_vtable_callers.py`)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…` / 19,236,864 B (SR-43・SR-59 と一致を確認)。作業用 dir はリポジトリ外 (`work/`・gitignore)。
- 測定 commit: `1396977c9` (`arg_vtable_callers.py` の窓の修正と `arg_caller_types.py` の追加を含む commit)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. ARG 240 件・ARG-CHILD 68 件の引数 (rdx/r8/r9) が SC の this かを、直接・vtable 経由の呼出元で確定する | **未達 (確定 0 件)**。直接 call の呼出元は追跡した (§2)。vtable 経由の呼出元は未実装。残りは子 [SR-82 #4930] |
| 2. THIS-CHILD の SC 証拠 6 件の子の型を確定し、THIS 67 件の SC 伝播を広げる | **未達**。THIS は 69 件 (REPORT_SR59 は 67)。SC 証拠の数は §3 のとおり前 run の記録と食い違う。子 [SR-82] |
| 3. 表の境界 (連続する関数ポインタの run の先頭) の決め方を明記し、出現数を run 数に直す | **未達 (境界は未実装)**。ただし「表の先頭の探索窓」の欠陥は直した (§1)。子 [SR-82] |
| 4. 測定 commit と再現手順を書く | **達成** (§4)。 |

## 1. 変更点

- `arg_vtable_callers.py`: 表の先頭の探索窓を `range(64)` から `HEAD_WINDOW = 4096` に広げた。
  - 根拠: 関数ポインタ `0x180139ff0` (24 出現) の先頭は、窓 64 では 0/24 件、窓 4096 では 24/24 件が見つかる (`REPORT_SR59.md` §3 の仮説どおり)。見つかった先頭の RTTI は `ClipSlot`・`AutomationLaneTabContainer`・`XferUIViewSwitchContainer`・`FXMenuContainer` など、index 83 の表。
  - 窓の修正で変わった件数 (実測): ARG 系の表の集計は変わらず (データ表に現れる 129 / 現れない 16 / SC 0)。THIS 系は「RTTI が SerumController の表に現れる関数」が 5 → 6 (`this_vt4096.tsv` の SC 行 6)。
- `arg_caller_types.py` (新規): ARG 系の所属関数 F への**直接 call** の呼出元 C で、rdx/r8/r9 の出所を `receiver_this_trace.py` の `origin` / `category` で分類する。
  - 所属の判定は C が `SC` (SerumController の this 集合) の関数か、と、引数の category が THIS / THIS-EMB か。

## 2. 直接呼出元の集計 (受入 1 の一部)

`arg_caller_types.py` (測定 commit `1396977c9`):

- ARG 系の所属関数 = 145 個。直接 call の呼出元がある = 17 個。呼出元 call 数 = 65。
- 呼出元が SC (SerumController) の関数で、rdx/r8/r9 のいずれかが SC の this (THIS/THIS-EMB) の呼出 = **0 件**。
- 引数の出所の内訳 (上位・呼出 × reg の行。全 196 行の一部): `r8:ARITH` 29・`rdx:ARG-CHILD` 22・`r9:NODOM` 20・`r9:ARG` 18・`r9:CLOBBER` 14・`r8:ARG` 13・`rdx:ARG` 10。
- 読み方: 直接 call 経由では、ARG の型を SC と確定できる呼出元は無い。145 関数のうち 128 関数は直接 call の呼出元が見つからない (vtable 経由か、呼出元なし)。vtable 経由の呼出元は未実装 (子 [SR-82])。
- `NODOM` (支配関係で未解決) と `ARITH`・`CLOBBER` が多く、引数の出所は多くが未解決。

## 3. 前 run (REPORT_SR59) との食い違い

| 項目 | REPORT_SR59 の記録 | 本 run の実測 | 扱い |
|---|---|---|---|
| ARG 240・ARG-CHILD 68 | 240 / 68 | 240 / 68 (`trace.tsv` の cat_strict) | 一致 |
| THIS 67 | 67 | **69** (所属関数 65) | 不一致。原因は未確認 |
| THIS-CHILD 191 | 191 | **197** (所属関数 142) | 不一致。原因は未確認 |
| THIS-CHILD の SC 証拠 6 件 (5 関数) | 6 件 (5 関数) | 証拠列 (`evidence`) は S 0・C 0・K 1 (THIS-CHILD)。`arg_vtable_callers` の SC 表に載る関数は 6 (窓 4096) | 根拠が違う。SC 証拠の定義を揃えて再集計が必要 (子 [SR-82]) |
| `receiver_this_trace.py` の TSV md5 | `ea2d93a2…` (3 回一致) | `1e1f5500…` (1 回) | 不一致。出力の差 (列・行順) の原因は未確認 |

前 run の数値をそのまま引き継がない。上の不一致は子 [SR-82] の最初の作業で解消する。

## 4. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir (work/serum2_sr60)。$P: tools/targets/serum2/gui
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
venv/bin/python $P/arg_vtable_callers.py Serum2_win64.vst3 trace.tsv --tsv arg_vt.tsv
venv/bin/python $P/arg_vtable_callers.py Serum2_win64.vst3 trace.tsv --cats vptr:THIS,vptr:THIS-CHILD --tsv this_vt.tsv
venv/bin/python $P/arg_caller_types.py Serum2_win64.vst3 trace.tsv --tsv arg_callers.tsv
```

実測 (測定 commit `1396977c9`・逐次・load は `/proc/loadavg` の 1 分値):

| ツール | 実行 | real (s) | load (1 分値) | 出力 md5 |
|---|---|---|---|---|
| `arg_vtable_callers.py` | 1 | 3.73 | 0.37 | `c61a1732…` |
| `arg_vtable_callers.py` | 2 | 3.75 | 0.42 | `c61a1732…` |
| `arg_vtable_callers.py` | 3 | 3.96 | 0.47 | `c61a1732…` |
| `arg_caller_types.py` | 1 | 24.86 | 0.47 | `b449ddd0…` |
| `arg_caller_types.py` | 2 | 28.08 | 0.65 | `b449ddd0…` |
| `arg_caller_types.py` | 3 | 24.75 | 0.79 | `b449ddd0…` |

- `receiver_this_trace.py` は 1 回 (real 23.96 s・load は未記録)。

### 鮮度の証跡 (`docs/WORKFLOW.md` §6)

- 測定 commit `1396977c9` 以降、本 PR の HEAD までの差分は REPORT (`REPORT_SR60.md`) と `DOC_MAP.md` の追記だけ。ツールは変えていない。
- `git diff --stat 1396977c9 HEAD -- 'tools/targets/serum2/gui/*.py'` の出力: 0 行 (REPORT 作成時点)。

### 未再現

- 測定 commit の前の `ea3ffa68d` の TSV md5 (`ea2d93a2…`) とは再現しなかった (§3)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) vtable 経由の呼出元で ARG 240・ARG-CHILD 68 の引数型を確定する (直接 call の呼出元は §2 で 17 関数のみ) | 受入 1 | [SR-82] |
| (b) 表の境界 (連続する関数ポインタの run の先頭) の決め方と、出現数の run 数への換算 | 受入 3 | [SR-82] |
| (c) THIS 69 件・THIS-CHILD 197 件の件数の不一致 (§3) と、THIS-CHILD の SC 証拠 (6 件 / 5 関数 の根拠) | 受入 2 | [SR-82] |
| (d) `receiver_this_trace.py` の TSV md5 の不一致 (§3) | 再現性 | [SR-82] |
