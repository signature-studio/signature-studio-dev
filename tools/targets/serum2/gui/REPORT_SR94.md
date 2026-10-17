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

- 確定 0 の理由: 証拠あり 72 行のうち、vtable 側 7 行は宛先 F を disp だけで照合しており、受け手の型が未確定。
- 直接側 65 行 (trace 行の数) と、呼出元 call 65 箇所 (`arg_caller_types.py` の数) は同じ数だが、別の量である。直接側 65 行の所属関数は `direct.tsv` の 17 関数で、その呼出元 call は `direct.tsv` の 65 箇所 (17 関数の全呼出元) に一致する。
  - この 65 箇所の呼出元関数は、SC が 0 件・slot 関数が 2 件・それ以外が 63 件 (`caller_evidence` 列で確認)。rdx/r8/r9 に SC の this が現れる呼出元は 0 件 (`arg_caller_types.py` の SC this 0)。
  - join の直接側 65 行それぞれについて、所属関数 F の呼出元 call 数と、そのうち SC の呼出元数を数えた (`direct.tsv` と `trace.tsv` から集計・§2 と同じ入力)。結果: 呼出元 call 数は 1 / 2 / 3 / 4 / 5 / 7 / 30 のいずれかで、SC の呼出元は全行で 0。
- 証拠なし 236 行は、呼出元がこのツール群の照合 (直接 call・disp 一致) では見つからないもの。これらが SC 由来かは本 REPORT では判定しない。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) vtable 候補 (disp のみの照合) の受け手の型 (reg の指す object の class) を確定する。型が決まれば、F の所属 class と一致するかで確定・非確定を分けられる | 受入 1 の確定 0 件の理由。確定件数を出すための前提 | #5612 (本 issue 残) |
| (b) 呼出元の SC 判定 (SerumController の関数集合) の境界 | SC 19 件・14 箇所の母集団 | #4930 (親・REPORT_SR82 §6 (b)) |
| (c) 証拠なし 236 行: SC 証拠は 0 件。ただし「SC の呼出元が見つからない」ことの判定で、非 SC の確定ではない (§5) | 確定件数の上界は 308 のまま | #5612 (本 issue 残・#5987 で §5 の判定済み) |

## 4. 測定 commit と差分

- 測定 commit: `9754af068` (origin/main。§2 の 4 ツールと `arg_row_join.py` の出力は、この版の入力で得た)。
- 測定 commit 以降の変更: `arg_row_join.py` (新規) と本 REPORT のみ。既存の測定ツールは変えていない。
- 鮮度の証跡: `git diff --quiet 9754af068 HEAD -- tools/targets/serum2/gui/receiver_this_trace.py tools/targets/serum2/gui/arg_caller_types.py tools/targets/serum2/gui/arg_vt_indirect.py tools/targets/serum2/gui/arg_vt_args.py` は 0 (差分 0 バイト・終了コード 0)。`git diff 9754af068 HEAD -- tools/targets/serum2/gui` の stat は `REPORT_SR94.md` と `arg_row_join.py` の 2 ファイルのみ。

## 5. 証拠なし 236 行の SerumController 由来判定 (#5987)

判定: `arg_none_sc_judge.py` (新規・PE 不要・既存 TSV のみ)。行ごとに、所属関数 F の証拠で分けた。

- SC 関数集合 (21 関数): `receiver_this_trace.py` の `sc_closure()` の結果 (`--vtable 0x180a2bf58`・PE sha256 `501e7bb3…`)。
- 判定順: (1) F が SC 集合に入る → SC 証拠 (self) / (2) 直接呼出元 (`direct.tsv`) に SC の関数がある → SC 証拠 (direct) / (3) vtable 候補の `n_sites_sc` > 0 → SC 証拠 (vtable) / (4) 上記が無い → 「呼出元なし」。

| trace 行 | 証拠なし | SC 証拠 | 呼出元なし (vtable 候補は非 SC のみ) | 呼出元なし (候補 0) |
|---|---|---|---|---|
| ARG | 228 | 0 | 227 | 1 |
| ARG-CHILD | 8 | 0 | 8 | 0 |
| 計 | 236 | 0 | 235 | 1 |

- 証拠なし 236 行は 122 関数に載る。うち 121 関数は vtable 候補があり、候補の呼出元はどれも SC の関数ではない (`n_sites_sc` = 0)。残り 1 関数 (`0x1806f9660`・ARG 1 行) は直接・vtable のどちらの候補も無い。
- 直接呼出元 (`direct.tsv` の 17 関数) に、証拠なし 122 関数は 1 つも含まれない。
- 判定の意味: 「SC 由来の証拠が無い」ことまでしか言えない。「呼出元なし」は、呼出元が見つからないことで、非 SC と確定したわけではない。よって、SC 由来の確定は 0 件、非 SC の確定も 0 件である。
- 件数の検算: `vt_ind.tsv` の `n_sites_sc` 合計 19・`n_sites` 合計 118,222 は §2 と一致。

測定 commit: `68c4a5b81` (本 PR で追加したのは `arg_none_sc_judge.py` と本 §5 のみ)。測定ツール (`receiver_this_trace.py` / `arg_caller_types.py` / `arg_vt_indirect.py` / `arg_vt_args.py`) の `9754af068` から HEAD までの差分は 0 バイト。
SC 集合 `sc.txt` (1 行 1 アドレス・21 行) は `receiver_this_trace.py` を runpy で読み、`sc_closure()` の戻り値を書き出して作った (出力先はリポジトリ外)。
実行: `python3 arg_none_sc_judge.py join.tsv direct.tsv vt_ind.tsv sc.txt` 0.02 s・出力 md5 `7e3b713b…`。
入力 md5 (`/tmp` の作業 dir・リポジトリ外): `join.tsv` `c762b72e…`・`direct.tsv` `b449ddd0…`・`vt_ind.tsv` `42bcf98b…`・`trace.tsv` `1e1f5500…` (§2 と一致)。
