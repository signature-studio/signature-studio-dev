# REPORT — [SR-94 #5612] ARG 240 件・ARG-CHILD 68 件の vtable 経由の呼出元を含めた確定・非確定の件数 (SR-82 #4930 受入 1 の子・静的)

- 日付: 2026-10-16 / 親: #4930 (SR-82) / 前段: `REPORT_SR60.md` (直接呼出元)・`REPORT_SR82.md` (vtable 候補・SC 内の受け手分類)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…` / 19,236,864 B (REPORT_SR82 と一致を確認)。作業用 dir はリポジトリ外。
- 測定 commit: `9754af068` (origin/main。下の §4 に差分)。

## 0. 結論

受入 1 は**部分達成**。確定 0 件・非確定 308 件 (ARG 240 + ARG-CHILD 68)。SC の this と確定できた引数は、直接呼出元でも vtable 経由でも 0 件。
vtable 経由は、宛先 F を disp だけで照合するため上界しか出せず、受け手の型を確定する手段がまだ無い。

| 項目 | ARG (240) | ARG-CHILD (68) | 計 (308) |
|---|---|---|---|
| 確定 (SC の this と確定) | 0 | 0 | **0** |
| 非確定 | 240 | 68 | **308** |

- 「非確定」は、確定できなかったことを表す。SC と違うと確定したわけではない。
- 「呼出元の証拠あり / なし」の内訳は §2.2 で再現した (`arg_row_join.py`・PE 不要)。

## 1. 変更点

- `arg_vt_args.py` (前 PR で新規): `arg_vt_indirect.py` の候補のうち、呼出元が SC の関数にあるものについて、rdx/r8/r9 の出所を `receiver_this_trace.py` の `origin` / `category` で strict・loose の両方に分類する。加えて trace の ARG / ARG-CHILD 行を、候補あり・なしで数える。
- `arg_row_join.py` (本 PR で新規): trace の ARG / ARG-CHILD 行ごとに、直接呼出元・vtable 候補の証拠を突き合わせ、組み合わせごとの行数を出す。入力は TSV のみ。
- 既存ツールは再利用し、変更していない。

## 2. 測定 (測定 commit `9754af068`・逐次実行)

手順 (作業 dir: リポジトリ外。`$P` = `tools/targets/serum2/gui`):

```sh
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
python3 $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
python3 $P/arg_caller_types.py Serum2_win64.vst3 trace.tsv --tsv direct.tsv
python3 $P/arg_vt_indirect.py Serum2_win64.vst3 trace.tsv --tsv vt_ind.tsv
python3 $P/arg_vt_args.py Serum2_win64.vst3 trace.tsv vt_ind.tsv --tsv vt_args.tsv
python3 $P/arg_row_join.py trace.tsv direct.tsv vt_args.tsv --tsv join.tsv
```

| ツール | 結果 | 出力 md5 | real (s) |
|---|---|---|---|
| `receiver_this_trace.py` | cat_strict TSV 1053 行 | `1e1f5500…` (REPORT_SR82 と一致) | 23.4 |
| `arg_caller_types.py` | 所属関数 145・直接呼出元あり 17・呼出元 call 65・SC の this 0 | `b449ddd0…` (前 PR の値と一致) | 23.9 |
| `arg_vt_indirect.py` | 候補 118,222 件・SC 呼出元 19 件 | `42bcf98b…` (REPORT_SR82 と一致) | 27.6 |
| `arg_vt_args.py` | 候補 call 14 箇所・対 57 件・SC の this 0 | `972d6267…` (前 PR の値と一致) | 23.9 |
| `arg_row_join.py` (新規・§2.2) | ARG 9/3/0/228・ARG-CHILD 56/4/0/8 | `c762b72e…` (join.tsv) | 0.02 |

- 入力 PE の sha256 `501e7bb3…` / 19,236,864 B を、本 run で `plugins-serum2` から展開して確認した。
- 直接呼出元 (`arg_caller_types.py`) の値は REPORT_SR60 と一致した (17 関数・65 件・SC の this 0 件)。
- 間接候補 (`arg_vt_indirect.py`) の値は REPORT_SR82 と一致した (118,222 件・SC 19 件)。
- 4 ツールの real 合計 99.0 s。開始時の `uptime` load (1 分値) は 0.55。

### 2.1 vtable 候補の受け手 (SC 内の 14 箇所・57 対)

strict / loose の分類 (reg 単位・57 対):

- strict: ARG 3・NODOM 30・CLOBBER 11・OTHER 10・ARITH 1・GLOBAL 1・CALLRET 1
- loose: CLOBBER 34・ARITH 5・OTHER 10・ARG 3・OUTPARAM 2・GLOBAL 1・CALLRET 1・THIS-CHILD 1

「SC の this」と分類された引数は、strict 0・loose 0。NODOM (支配が取れない) と CLOBBER (途中で上書き) が多く、確定の材料にならない。

### 2.2 trace 行の内訳 (再現済み・`arg_row_join.py`)

trace の ARG / ARG-CHILD 行を、所属関数 F の証拠で分ける。直接呼出元 (`direct.tsv` の func)・vtable 候補 (`vt_args.tsv` の func) のどちらかを持つ F の行を「証拠あり」とする。

| trace 行 | 計 | 直接呼出元あり | vtable 候補あり | 両方 | 証拠なし |
|---|---|---|---|---|---|
| ARG | 240 | 9 | 3 | 0 | 228 |
| ARG-CHILD | 68 | 56 | 4 | 0 | 8 |

- 証拠あり 72 行 (ARG 12 / ARG-CHILD 60)。直接と vtable の 2 列は**重ならない** (両方 0 行)。
- 結合の出力: `c762b72e…` (join.tsv)。

### 2.3 この結果から言えること

- 確定 0 の理由: 証拠あり 72 行のうち、vtable 側 7 行は宛先 F を disp だけで照合しており、受け手の型が未確定。直接側 65 行 (呼出元 call 65 件) は、rdx/r8/r9 に SC の this が現れる呼出元が 0 件だった (§2 の `arg_caller_types.py`)。
- 証拠なし 236 行は、呼出元がこのツール群の照合 (直接 call・disp 一致) では見つからないもの。これらが SC 由来かは本 REPORT では判定しない。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) vtable 候補 (disp のみの照合) の受け手の型 (reg の指す object の class) を確定する。型が決まれば、F の所属 class と一致するかで確定・非確定を分けられる | 受入 1 の確定 0 件の理由。確定件数を出すための前提 | #5612 (本 issue 残) |
| (b) 呼出元の SC 判定 (SerumController の関数集合) の境界 | SC 19 件・14 箇所の母集団 | #4930 (親・REPORT_SR82 §6 (b)) |
| (c) 証拠なし 236 行の扱い (呼出元が見つからない行が SC 由来かは未判定) | 確定件数の上界は 308 のまま | #5612 (本 issue 残) |

## 4. 測定 commit と差分

- 測定 commit: `9754af068` (origin/main。§2 の 4 ツールと `arg_row_join.py` の出力は、この版の入力で得た)。
- 測定 commit 以降の変更: `arg_row_join.py` (新規) と本 REPORT のみ。既存の測定ツールは変えていない。
- 鮮度の証跡: 下の差分 (`git diff 9754af068 HEAD -- tools/targets/serum2/gui`) は、測定ツール (`arg_vt_args.py`・`arg_caller_types.py`・`arg_vt_indirect.py`・`receiver_this_trace.py`) を含まない。
