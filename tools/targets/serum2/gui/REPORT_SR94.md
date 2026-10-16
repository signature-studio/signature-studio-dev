# REPORT — [SR-94 #5612] ARG 240 件・ARG-CHILD 68 件の vtable 経由の呼出元を含めた確定・非確定の件数 (SR-82 #4930 受入 1 の子・静的)

- 日付: 2026-10-16 / 親: #4930 (SR-82) / 前段: `REPORT_SR60.md` (直接呼出元)・`REPORT_SR82.md` (vtable 候補・SC 内の受け手分類)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…` / 19,236,864 B (REPORT_SR82 と一致を確認)。作業用 dir はリポジトリ外。
- 測定 commit: 本 PR の変更 commit (`arg_vt_args.py` を追加した commit。下の §4 に hash と差分)。

## 0. 結論

受入 1 は**部分達成**。確定 0 件・非確定 308 件 (ARG 240 + ARG-CHILD 68)。SC の this と確定できた引数は、直接呼出元でも vtable 経由でも 0 件。
vtable 経由は、宛先 F を disp だけで照合するため上界しか出せず、受け手の型を確定する手段がまだ無い。

| 項目 | ARG (240) | ARG-CHILD (68) | 計 (308) |
|---|---|---|---|
| 確定 (SC の this と確定) | 0 | 0 | **0** |
| 非確定 (呼出元の証拠あり) | 12 | 60 | 72 |
| 非確定 (呼出元の証拠なし) | 228 | 8 | 236 |

- 「呼出元の証拠あり」は、F を直接 call する呼出元があるか、disp 一致の vtable 候補が SC 関数内にある行。内訳は §2。
- 「非確定」は、確定できなかったことを表す。SC と違うと確定したわけではない。

## 1. 変更点

- `arg_vt_args.py` (新規): `arg_vt_indirect.py` の候補のうち、呼出元が SC の関数にあるものについて、rdx/r8/r9 の出所を `receiver_this_trace.py` の `origin` / `category` で strict・loose の両方に分類する。加えて trace の ARG / ARG-CHILD 行を、候補あり・なしで数える。
- 既存ツールは再利用し、変更していない。

## 2. 測定 (入力は HEAD と同じ・逐次実行)

手順 (作業 dir: リポジトリ外。`$P` = `tools/targets/serum2/gui`):

```sh
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
venv/bin/python $P/arg_caller_types.py Serum2_win64.vst3 trace.tsv --tsv direct.tsv
venv/bin/python $P/arg_vt_indirect.py Serum2_win64.vst3 trace.tsv --tsv vt_ind.tsv
venv/bin/python $P/arg_vt_args.py Serum2_win64.vst3 trace.tsv vt_ind.tsv --tsv vt_args.tsv
```

| ツール | 結果 | 出力 md5 | real (s) |
|---|---|---|---|
| `receiver_this_trace.py` | cat_strict TSV 1053 行 | `1e1f5500…` (REPORT_SR82 と一致) | 22.8 |
| `arg_caller_types.py` | 所属関数 145・直接呼出元あり 17・呼出元 call 65・SC の this 0 | `b449ddd0…` | (未計測) |
| `arg_vt_indirect.py` | 候補 118,222 件・SC 呼出元 19 件 | `42bcf98b…` (REPORT_SR82 と一致) | 27.1 |
| `arg_vt_args.py` | 候補 call 14 箇所・対 57 件・SC の this 0 | `972d6267…` | 23.6 |

- 直接呼出元 (`arg_caller_types.py`) の値は REPORT_SR60 と一致した (17 関数・65 件・SC の this 0 件)。
- 間接候補 (`arg_vt_indirect.py`) の値は REPORT_SR82 と一致した (118,222 件・SC 19 件)。
- load (1 分値): 本 run の開始時 0.54〜0.67 (各ツールの前後で 0.2〜0.4 の範囲)。

### 2.1 vtable 候補の受け手 (SC 内の 14 箇所・57 対)

strict / loose の分類 (reg 単位・57 対):

- strict: ARG 3・NODOM 30・CLOBBER 11・OTHER 10・ARITH 1・GLOBAL 1・CALLRET 1
- loose: CLOBBER 34・ARITH 5・OTHER 10・ARG 3・OUTPARAM 2・GLOBAL 1・CALLRET 1・THIS-CHILD 1

「SC の this」と分類された引数は、strict 0・loose 0。NODOM (支配が取れない) と CLOBBER (途中で上書き) が多く、確定の材料にならない。

### 2.2 trace 行の内訳

| trace 行 | 証拠あり 計 | 内訳: 直接呼出元あり | 内訳: vtable 候補 (SC 内) あり | 証拠なし |
|---|---|---|---|---|
| ARG 240 | 12 | 9 | 3 | 228 |
| ARG-CHILD 68 | 60 | 56 | 4 | 8 |

(内訳の 2 列の重なりは未確認。「重ならない」は前提であり、結合の出力では示していない。証拠あり 72 行は、直接呼出元か vtable 候補のどちらかを持つ行。)

**本 HEAD で §2.2 は再現していない。** 行単位の結合を行うコードは `arg_vt_args.py` に無い。`arg_caller_types.py` は集計だけを出す。表の 9 / 3 / 56 / 4 を作った手順は REPORT に書かれていない。
再現には `plugins-serum2` の PE が要る。本 run では素材が無く、実行していない。結合の手順は未確定で、素材を取得できる run で確定する (§3 (d))。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) vtable 候補 (disp のみの照合) の受け手の型 (reg の指す object の class) を確定する。型が決まれば、F の所属 class と一致するかで確定・非確定を分けられる | 受入 1 の確定 0 件の理由。確定件数を出すための前提 | #5612 (本 issue 残) |
| (b) 呼出元の SC 判定 (SerumController の関数集合) の境界 | SC 19 件・14 箇所の母集団 | #4930 (親・REPORT_SR82 §6 (b)) |
| (c) 直接呼出元・vtable 候補のいずれにも証拠が無い 236 行 | 確定の母集団が 72 行に限られる | #5612 (本 issue 残) |
| (d) §2.2 の結合 (行単位で trace と直接呼出元・vtable 候補を突き合わせ、重なりを確認する) が無い。本 HEAD では再現していない | 証拠あり 72 行の内訳が未検証 | #5612 (本 issue 残) |

## 4. 測定 commit と差分

- 測定 commit: `7390a5a4c` (`arg_vt_args.py` を追加した commit。§2 の 4 表の数値はこの版の入力で得た)。
- 測定 commit 以降の変更: `de3045f12` (`arg_vt_args.py` から未使用の `targets` を削除)。出力に影響しない見込みだが、本 run では再測定していない。
- 鮮度の証跡 (`git diff 7390a5a4c HEAD -- tools/targets/serum2/gui`):

```
diff --git a/tools/targets/serum2/gui/arg_vt_args.py b/tools/targets/serum2/gui/arg_vt_args.py
@@ -32,14 +32,12 @@ with contextlib.redirect_stdout(io.StringIO()):
 REGS = ("rdx", "r8", "r9")
 ind_re = re.compile(r"qword ptr \[(\w+)(?: \+ (0x[0-9a-f]+|\d+))?\]")
 
-targets = set()
 trace_rows = []
 with open(tsv_trace) as f:
     next(f)
     for line in f:
         cols = line.rstrip("\n").split("\t")
         if cols[4] in ("vptr:ARG", "vptr:ARG-CHILD"):
-            targets.add(int(cols[1], 16))
             trace_rows.append((cols[4], int(cols[1], 16)))
```

- 結論: 差分は `targets` の削除だけ。`arg_caller_types.py` などの測定ツールは変わっていない。再測定は未実施 (入力の PE が本 run に無い)。
