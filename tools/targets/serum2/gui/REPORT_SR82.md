# REPORT — [SR-82 #4930] Serum 2 vtable 経由の呼出元で ARG・THIS の引数型を確定し、表の境界を決める (SR-60 残・静的)

- 日付: 2026-10-16 / 親: #4164 (SR-60) / 前段: `REPORT_SR60.md` (直接 call の呼出元・`arg_vtable_callers.py` の窓 4096)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…` / 19,236,864 B (SR-60 と一致を確認)。作業用 dir はリポジトリ外 (`work/`・gitignore)。
- 測定 commit: `6c2b01972` (`arg_vt_indirect.py` を追加した commit。このツールの実測はこの commit で行った)。

## 0. 結論

本 issue の受入条件は全て未達。今回は受入 1 の一部 (vtable 経由の候補の列挙) と、受入 3 の前提 (表の slot 数の実測) だけを実装した。確定は行っていない。

| 受入条件 | 判定 |
|---|---|
| 1. ARG 240 件・ARG-CHILD 68 件の呼出元 (直接・vtable 経由) をたどり、引数が SC の this かを確定、件数を REPORT に書く | **未達**。vtable 経由の候補を列挙した (§2)。候補の宛先 (reg の型) は未確定のため、確定・非確定の件数は出せない |
| 2. THIS 69・THIS-CHILD 197 の SC 伝播と SC 証拠の件数 | **未達**。§3 に現状の件数のみ |
| 3. 表の境界の決め方と、出現数の run 数への換算 | **未達**。決め方は未決定 (§4) |
| 4. 測定 commit と再現手順 | **達成** (§5) |

未解決は §6。

## 1. 変更点

- `arg_vt_indirect.py` (新規): F (ARG / ARG-CHILD の所属関数) の入口を指す表の slot ごとに、`arg_vtable_callers.py` と同じ窓 (`HEAD_WINDOW = 4096`) で表の先頭 h・index k を得る。`call qword ptr [reg + 8k]` の候補 (disp = 8k で照合) を数え、呼出元が SC の関数かを数える。
- 限界: disp だけで照合するため、同じ disp を持つ別クラスの呼出が全て候補に入る。宛先の型 (reg の指す object) は見ない。よって候補は「F を呼び得る箇所」の上界であり、F を確実に呼ぶ箇所ではない。

## 2. vtable 経由の候補 (受入 1 の一部)

`arg_vt_indirect.py` (測定 commit `6c2b01972`):

- ARG 系の所属関数 = 145 個 / 表の slot に現れる = 129 個 (`arg_vtable_callers.py` の値と一致)。
- 間接 call の候補 (slot × 先頭ごと) = 113,548 件 **(旧値・取りこぼしを含む)**。
- うち呼出元が SerumController の関数 = 12 件 **(旧値・取りこぼしを含む)**。
- 参考: `.text` 全体で SC の関数内の `call qword ptr [reg+disp]` = 26 件 (`disp` を問わない)。

**注 (レビュー指摘への対応):** 測定 commit `6c2b01972` の `arg_vt_indirect.py` は `qword ptr [reg + 0x..]` だけを受けており、capstone 5.0.7 が `[reg]` (disp 0) と `[reg + 8]` (disp 8、10 進出力) を出す呼出を落としていた。上の 113,548 件と 12 件は、この取りこぼしを含む旧値である。修正 commit では正規表現を `[reg]` と `[reg + 10進|0x16進]` の両方を受けるように直した。修正後の件数は未測定 (下記)。

読み方: 候補の大半は別クラスの同じ disp の呼出であり、ARG の型の確定には使えない。SC 関数内の件数も、受けた object が F の所属 class かは未確定。

## 3. THIS・THIS-CHILD の件数 (受入 2 の現状)

`arg_vtable_callers.py --cats vptr:THIS,vptr:THIS-CHILD` (測定 commit `6c2b01972`・`REPORT_SR60.md` の窓 4096 と同じ):

- THIS 系の所属関数 = 201 個 / データ表に現れる = 114 個 / 現れない = 87 個。
- RTTI が SerumController の表に現れる関数 = 6 個。

`receiver_this_trace.py --vtable 0x180a2bf58` の分類件数 (`cat_strict`): THIS 69・THIS-CHILD 197・ARG 240・ARG-CHILD 68 (`REPORT_SR60.md` §3 の不一致 (THIS 67→69、THIS-CHILD 191→197) は、本 run でも同じ値)。原因は未確認。

## 4. 表の境界 (受入 3)

未決定。連続する関数ポインタの run の先頭をどう切るかは、本 run では決めていない。現状の `arg_vtable_callers.py` は表の出現数をそのまま数えており、run には換算していない。

## 5. 再現手順・実測

```sh
# $S: リポジトリ外の作業用 dir ($RUNNER_TEMP/serum2_4930)。$P: tools/targets/serum2/gui
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv trace.tsv
venv/bin/python $P/arg_vt_indirect.py Serum2_win64.vst3 trace.tsv --tsv vt_ind.tsv
```

実測 (測定 commit `6c2b01972`・逐次・load は `/proc/loadavg` の 1 分値):

| ツール | 実行 | real (s) | load (1 分値) | 出力 md5 |
|---|---|---|---|---|
| `receiver_this_trace.py` | 1 | 27.07 | 0.74 | (TSV 1053 行) |
| `arg_vt_indirect.py` (旧 commit・取りこぼしあり) | 1 | 31.61 | 0.73 | `9b4cb2ff` |
| `arg_vt_indirect.py` (旧 commit・取りこぼしあり) | 2 | 31.74 | 0.91 | `9b4cb2ff` |

- 修正後の再測定は未実施。理由: 再測定には `plugins-serum2` 素材が必要だが、`$ARTIFACTS_DIR` (`fl-win64.tar.zst` のみ) に無く、`Serum2_win64.vst3` の実体もこの run のどこにも無い。再測定は素材を用意した run で行う (未解決 (e))。
- `receiver_this_trace.py` の TSV md5 は未記録 (§3 の不一致の検証は本 run では行っていない)。

### 鮮度の証跡 (`docs/WORKFLOW.md` §6)

- 測定 commit `6c2b01972` から HEAD までのコード差分: `git diff 6c2b01972 HEAD -- 'tools/targets/serum2/gui/*.py'` は、REPORT の追記のみで 0 行 (本 PR の変更はこの REPORT と `arg_vt_indirect.py` の commit のみ)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 間接 call の候補の宛先 (reg の指す object) の型を確定する。候補 113,548 件は disp のみの照合で、SC 関数内の 12 件も受け手は未確定 | 受入 1 | #4930 (本 issue 残・親 #4164 の子) |
| (b) THIS 69・THIS-CHILD 197 の SC 伝播と、THIS-CHILD の SC 証拠 (6 件 / 5 関数) の定義を揃えた再集計 | 受入 2 | #4930 (本 issue 残) |
| (c) 表の境界 (連続する関数ポインタの run の先頭) の決め方と、run 数への換算 | 受入 3 | #4930 (本 issue 残) |
| (d) `receiver_this_trace.py` の TSV md5 の不一致 (REPORT_SR60 §3) | 再現性 | #4930 (本 issue 残) |
| (e) `arg_vt_indirect.py` の修正後の再測定 (件数・md5 を 2 回一致で確認)。素材 `plugins-serum2` を要する | 受入 1 の件数 | #4930 (本 issue 残) |
