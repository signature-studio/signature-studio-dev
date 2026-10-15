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
| XferViewCreator<...> (GUI 生成関数の表) | 226 | 0 |
| std::num_get (標準ライブラリ) | 0 | 10 |
| その他の RTTI (VSTGUI 等) | 3 | 4 |
| データ表に現れない (vtable 外) | 10 | 54 |
| 表の先頭が見つからない | 1 | 0 |
| **SerumController** | **0** | **0** |

- 関数単位 (ARG 系の所属関数 145 個): データ表に現れる 129 個・現れない 16 個。SerumController の表に現れる関数は 0 個。
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
- 「表の先頭が見つからない」(ARG 1・THIS-CHILD 14) と、`0x180139ff0` (24 出現・表の先頭なし) は、COL を指す vtable 形ではない。配列状の関数ポインタ表と見られるが、本 run では中身を調べていない。
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

- 決定性: TSV md5 は 3 回とも `ea2d93a2…` (SR-43 の値と一致)。`arg_vtable_callers.py` の出力 md5 は 3 回とも `78ba6b53…` (ARG 系) で一致。THIS 系の TSV md5 は `d8851c27…`。
- `arg_vtable_callers.py` の実測: real 3.57 s (ARG 系)。
- 報告前コマンド (`docs/WORKFLOW.md` §6): `git diff ea3ffa68d HEAD -- tools/targets/serum2/gui` の出力を本 PR の検証欄に添付する。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) ARG 240 件・ARG-CHILD 68 件の引数 (rdx/r8/r9) の型を、F を呼ぶ側の引数で確定する (直接・vtable 経由の呼出元) | 受入 1 | [SR-60 #4164] |
| (b) 表の境界 (連続する関数ポインタの run の先頭) の決め方 | 受入 3 | [SR-60 #4164] に含める |
| (c) THIS 67 件 (SC の証拠 0) と THIS-CHILD の子の型 | 受入 2 | [SR-60 #4164] に含める |
| (d) `0x180139ff0` (24 出現) と表の先頭が見つからない 15 件の中身 | 分類の精度 | [SR-60 #4164] に含める |
