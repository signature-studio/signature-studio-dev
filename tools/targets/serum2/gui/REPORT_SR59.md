# REPORT — [SR-59 #4122] Serum 2 vtable 経由の呼出元で ARG・THIS の型を確定する (SR-48 残・静的)

- 日付: 2026-10-15 / 親: #3236 (SR-48) / 前段: `REPORT_SR43.md` (受信 base の分類 `receiver_this_trace.py`)
- 範囲: 静的解析のみ。データ表 (vtable 形) に所属関数の入口が現れるかを見る。呼出元の引数は追跡していない。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-43 と一致)。作業用 dir はリポジトリ外。
- 測定 commit: `ea3ffa68d` (`arg_vtable_callers.py` を追加した commit。分類の入力 `receiver_this_trace.py` は `06ca6fb0` から変えていない)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. ARG 240 件・ARG-CHILD 68 件について、vtable 経由の呼出元をたどり、引数が SerumController の this かを確定する | **未達。確定 0 件**。所属関数 F の入口が vtable に載ることは分かったが、F を呼ぶ側の引数 (rdx/r8/r9) の型は決まらない。残りは子 [SR-60 #4164] |
| 2. THIS 67 件・THIS-CHILD 191 件の所属関数について、vtable 経由の呼出元を加えて SC 伝播を広げ、SC の証拠の件数を書く | **部分達成**。THIS-CHILD の SC 証拠は 6 件 (5 関数)。THIS 67 件は SC 証拠 0 件 (§2) |
| 3. 測定 commit と再現手順を書く。表の境界 (連続する関数ポインタの run の先頭) の決め方を明記する | **未達 (境界は未実装)**。本 run は表の境界を決めていない。各出現を数えるだけ (§3) |

本 run で得たもの: 「所属関数 F の入口が、どの vtable (RTTI) に載るか」を候補ごとに数えるツール (`arg_vtable_callers.py`) と、その件数。
ARG の型を確定するには、F を呼ぶ側の引数を見る作業が要る (子 [SR-60 #4164])。

## 1. 方法 (`arg_vtable_callers.py`)

- 入力: `receiver_this_trace.py --tsv` の出力 (`cat_strict` の分類)。対象は `--cats` で選ぶ (既定 `vptr:ARG,vptr:ARG-CHILD`)。
- 所属関数 F の入口 VA を、`.rdata`・`.data` の全 8 byte 値と照合する。一致した位置 (スロット) から手前へ走査し、COL (signature=1) を指す先頭を探す。COL の pTypeDescriptor から RTTI クラス名を得る。
- 出力: 関数ごとに「データ表の出現数・vtable 先頭 (head)・index・RTTI」。
- 解釈: F が表に載る = 「F は RTTI `X` の仮想関数として登録されている」。よって F の **rcx (this)** は `X` の型の候補。**引数 (rdx/r8/r9) の型は示さない**。

## 2. 分類結果 (測定 commit `ea3ffa68d`・候補単位)

### 2a. ARG 系 (受入 1)

| 分類 (F の入口が載る表の RTTI) | ARG 240 | ARG-CHILD 68 |
|---|---|---|
| RTTI `XferViewCreator<...>` | 226 | 0 |
| RTTI `std::num_get` | 0 | 10 |
| その他の RTTI | 3 | 4 |
| データ表に現れない (vtable 外) | 10 | 54 |
| 表の先頭が見つからない (未確認・§3) | 1 | 0 |
| **SerumController** | **0** | **0** |

- 関数単位 (ARG 系の所属関数 145 個): データ表に現れる 129 個・現れない 16 個。SerumController の表に現れる関数は 0 個。
- 単位: 240・68・67・191 は呼出 (`receiver_this_trace.py` の TSV の行) の数で、関数の数ではない (関数は ARG 系 145 個)。
- 未記録: 表の列への集計 (TSV 行と `arg_vtable_callers.py` の関数表の join) を行うスクリプトは本 PR に無い。F が複数の RTTI の表に載る場合 (`n_tables` ≥ 2) に、その行をどの分類に数えたかは本 REPORT に記録していない。この数え方は再現できていない。join の手順は本 run では書いていない (入力 PE が無く、実行して確かめられないため)。
- 読み方: 226 件は「所属関数の this が XferViewCreator」を示すだけで、ARG の型ではない。ARG 240 件・ARG-CHILD 68 件は、すべて「確定 0 件・未確定 308 件」。

### 2b. THIS 系 (受入 2)

| 分類 | THIS 67 | THIS-CHILD 191 |
|---|---|---|
| **SerumController** (F が SC の vtable に載る) | 0 | **6** (5 関数) |
| XferViewCreator / その他の RTTI | 43 | 84 |
| データ表に現れない | 24 | 87 |
| 表の先頭が見つからない | 0 | 14 |

- SC の証拠 (THIS-CHILD 6 件): `0x1800ab4d0`・`0x1800b4640`・`0x1800b5580`・`0x1800cf690`・`0x1800d0a70` の 5 関数。いずれも SC の vtable に載る override で、rcx (this) は SC。候補の受信は this の子 (`this[+off]`) なので、子の型は未確定。
- THIS 67 件の所属関数は SC の証拠 0 件。

## 3. 限界・未達の内容 (受入 3)

- **表の境界の決め方 (受入 3 の要求) は未実装**。本ツールは、F の入口が 8 byte 値として現れる各位置を数えるだけで、「連続する関数ポインタの run の先頭」は決めていない。`n_tables` は run の数ではなく出現の数。
- 「表に現れない」(ARG 10 + 54、THIS 24) は、データ表経由の登録が見つからない関数。直接呼出元の有無はこの REPORT では見ていない。
- 「表の先頭が見つからない」(ARG 1・THIS-CHILD 14) と、`0x180139ff0` (24 出現・表の先頭なし) の原因は未確認。`find_head` は手前 64 slot (`range(64)`) までしか探さない。vtable の index が 63 を超えると、COL があっても `-` になる。窓を広げた対照 (例: 4096 slot) は未実施 (入力 PE が無い)。配列状の関数ポインタ表という見方も確認していない。
- 「F が表に載る」は、F が仮想関数として登録されていることまでを示す。F が実際に vtable 経由で呼ばれるかは示さない。
- 関数間の引数 (rdx/r8/r9) の型は確定していない。ARG の確定は子 [SR-60 #4164] の作業。

## 4. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir (RUNNER_TEMP 配下)。$P: tools/targets/serum2/gui
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
venv/bin/python $P/arg_vtable_callers.py Serum2_win64.vst3 trace.tsv --tsv arg_vt.tsv
venv/bin/python $P/arg_vtable_callers.py Serum2_win64.vst3 trace.tsv --cats vptr:THIS,vptr:THIS-CHILD --tsv this_vt.tsv
```

- 入力の確認: sha256 `501e7bb3…` / 19,236,864 B (SR-43 と一致)。
- 実測 (`receiver_this_trace.py`・n=3・逐次・測定 commit `ea3ffa68d`)。load は `/proc/loadavg` の 1 分値:

| 実行 | real (s) | user (s) | load (1 分値) |
|---|---|---|---|
| 1 | 22.92 | 21.73 | 0.02 |
| 2 | 22.83 | 21.64 | 0.35 |
| 3 | 22.83 | 21.65 | 0.58 |

- 決定性: `receiver_this_trace.py` の TSV md5 は 3 回とも `ea2d93a2…` (SR-43 の値と一致)。THIS 系の TSV md5 は `d8851c27…` (1 回の値)。
- `arg_vtable_callers.py` の実測: 単発 (n=1)。real 3.57 s。load・並列数は未記録。n=3 の min–max は無い。上の表の `receiver_this_trace.py` の n=3 とは別の測定。
- 注: 上の 3 回の TSV md5 一致は `receiver_this_trace.py` のもの。`arg_vtable_callers.py` は 1 回だけ実行したので、出力 md5 の再現性は確認していない。

### 鮮度の証跡 (`docs/WORKFLOW.md` §6)

- 測定 commit `ea3ffa68d` → `3ba9939e6` (レビュー対象の head) の差分。本 commit での REPORT の追記は、PR 本文に最終 HEAD の差分を別途添付する。
- `git diff --stat ea3ffa68d 3ba9939e6 -- tools/targets/serum2/gui` の出力:

```
 tools/targets/serum2/gui/REPORT_SR59.md | 96 +++++++++++++++++++++++++++++++++
 1 file changed, 96 insertions(+)
```

- code 範囲 (`*.py`) の差分: `git diff --stat ea3ffa68d 3ba9939e6 -- 'tools/targets/serum2/gui/*.py'` は出力 0 行。`git log --oneline ea3ffa68d..3ba9939e6 -- 'tools/targets/serum2/gui/*.py'` も 0 行。
- 結論: 測定に使ったコードは変わっていないので、再測定は不要。この REPORT の修正 commit は `*.py` を変えない (REPORT のみ)。最終 HEAD の差分は PR コメントに添付する。

### 未再現 (入力 PE 不在)

- `plugins-serum2` が `$ARTIFACTS_DIR` に無い (`fl-win64.tar.zst` のみ)。このため、§2 の件数の再集計・窓の対照・md5 の再確認は、この run では実行していない。
- 必要な素材: `plugins-serum2` (`docs/WORKFLOW.md` §11)。取得後に §2 の集計手順と §3 の窓の対照を再実行する。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) ARG 240 件・ARG-CHILD 68 件の引数 (rdx/r8/r9) の型を、F を呼ぶ側の引数で確定する (直接・vtable 経由の呼出元) | 受入 1 | [SR-60 #4164] |
| (b) 表の境界 (連続する関数ポインタの run の先頭) の決め方 | 受入 3 | [SR-60 #4164] に含める |
| (c) THIS 67 件 (SC の証拠 0) と THIS-CHILD の子の型 | 受入 2 | [SR-60 #4164] に含める |
| (d) `0x180139ff0` (24 出現) と表の先頭が見つからない 15 件の中身 | 分類の精度 | [SR-60 #4164] に含める |
