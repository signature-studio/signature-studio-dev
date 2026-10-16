# REPORT — [SR-82 #4930] Serum 2 vtable 経由の呼出元で ARG・THIS の引数型を確定し、表の境界を決める (SR-60 残・静的)

- 日付: 2026-10-16 / 親: #4164 (SR-60) / 前段: `REPORT_SR60.md` (直接 call の呼出元・`arg_vtable_callers.py` の窓 4096)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…` / 19,236,864 B (SR-60 と一致を確認)。作業用 dir はリポジトリ外 (`work/`・gitignore)。
- 測定 commit: `3183c3c6e` (HEAD で測定。`*.py` は `b3607f9df` と同一。§5 の鮮度欄を参照)。

## 0. 結論

受入 3 (表の境界と run 数への換算) を達成した。受入 1・2 は未達のまま残る。受入 1 は vtable 経由の候補の列挙までで、確定は行っていない。

| 受入条件 | 判定 |
|---|---|
| 1. ARG 240 件・ARG-CHILD 68 件の呼出元 (直接・vtable 経由) をたどり、引数が SC の this かを確定、件数を REPORT に書く | **未達**。vtable 経由の候補を列挙した (§2)。候補 118,222 件・うち呼出元が SC の関数 19 件。候補の宛先 (reg の型) は未確定のため、確定・非確定の件数は出せない |
| 2. THIS 69・THIS-CHILD 197 の SC 伝播と SC 証拠の件数 | **未達**。§3 に現状の件数のみ |
| 3. 表の境界の決め方と、出現数の run 数への換算 | **達成** (§4)。run = distinct な表の先頭 h。152 slot → 144 run |
| 4. 測定 commit と再現手順 | **達成** (§5) |

未解決は §6。

## 1. 変更点

- `arg_vt_indirect.py` (新規): F (ARG / ARG-CHILD の所属関数) の入口を指す表の slot ごとに、`arg_vtable_callers.py` と同じ窓 (`HEAD_WINDOW = 4096`) で表の先頭 h・index k を得る。`call qword ptr [reg + 8k]` の候補 (disp = 8k で照合) を数え、呼出元が SC の関数かを数える。
- 限界: disp だけで照合するため、同じ disp を持つ別クラスの呼出が全て候補に入る。宛先の型 (reg の指す object) は見ない。よって候補は「F を呼び得る箇所」の上界であり、F を確実に呼ぶ箇所ではない。

## 2. vtable 経由の候補 (受入 1 の一部)

`arg_vt_indirect.py` (測定 commit `3183c3c6e`):

- ARG 系の所属関数 = 145 個 / 表の slot に現れる = 129 個 (`arg_vtable_callers.py` の値と一致)。
- 間接 call の候補 (slot × 先頭ごと) = 118,222 件。
- うち呼出元が SerumController の関数 = 19 件。

**注:** 測定 commit `6c2b01972` の `arg_vt_indirect.py` は `qword ptr [reg + 0x..]` だけを受けており、capstone 5.0.7 が `[reg]` (disp 0) と `[reg + 8]` (disp 8、10 進出力) を出す呼出を落としていた。旧 commit の値 (113,548 件・SC 12 件) は、この取りこぼしを含む旧値であり、現 head の値ではない。修正 commit `b3607f9df` で正規表現を `[reg]` と `[reg + 10進|0x16進]` の両方に対応させた。

読み方: 候補の大半は別クラスの同じ disp の呼出であり、ARG の型の確定には使えない。SC 関数内の件数も、受けた object が F の所属 class かは未確定。

## 3. THIS・THIS-CHILD の件数 (受入 2 の現状)

`arg_vtable_callers.py --cats vptr:THIS,vptr:THIS-CHILD` (測定 commit `6c2b01972`・`REPORT_SR60.md` の窓 4096 と同じ。`*.py` は `arg_vt_indirect.py` 以外 `6c2b01972` から不変):

- THIS 系の所属関数 = 201 個 / データ表に現れる = 114 個 / 現れない = 87 個。
- RTTI が SerumController の表に現れる関数 = 6 個。

`receiver_this_trace.py --vtable 0x180a2bf58` の分類件数 (`cat_strict`): THIS 69・THIS-CHILD 197・ARG 240・ARG-CHILD 68 (前 run の記録。本 run 未再現)。`REPORT_SR60.md` §3 の不一致 (THIS 67→69、THIS-CHILD 191→197) の原因は未確認。

**SC 伝播の拡張 (前 run の記録・`sc_widen.py`。本 run 未再現)**: 起点 = `receiver_this_trace.py` の SC 閉包 (strict, 21 関数)。そこから直接 call の宛先へ、rcx が this のものを strict で、strict で外れたものは loose で伸ばし、不動点まで繰り返した。

- 伝播で追加された関数 = 0 (strict 0・loose 0)。閉包は 21 関数のまま飽和した。これは独立の拡張検証ではなく、`receiver_this_trace.py` の `sc_closure()` と同じ不動点計算の再確認である (構造上 0 になる)。
- THIS 69 件 (所属関数 65 個): SC 証拠 0 件 (SC 閉包の関数 0)。
- THIS-CHILD 197 件 (所属関数 142 個): SC 証拠 1 件 (所属関数 `0x1800a9f40`)。

読み方: THIS の SC 証拠 0 は「SC 閉包に未到達」であることしか示さない。THIS が SerumController の this でないとは断定しない。所属関数の vtable RTTI による照合は本 run で再現していないため、結論には使わない (RTTI 由来の数値は削除)。受入 2 の前提「THIS = SerumController の this」の見直しは、RTTI 照合を再現してから行う。THIS-CHILD の SC 証拠は 1 件のみで、件数 (SC 証拠 6 件 / 5 関数, §6 (b)) の前提を揃える必要がある。

再現: `venv/bin/python $P/sc_widen.py Serum2_win64.vst3 trace.tsv --tsv widen.tsv`。測定 commit は `224202d55` (本 PR の変更 commit)。md5 `a949316a…`・real 23.5 s / 22.8 s・load 0.20 → 0.43 は前 run の記録であり、入力 `Serum2_win64.vst3` が無い本 run では再測定していない (§5 の未解決 (f) を参照)。

## 4. 表の境界 (受入 3)

決め方 (本 run で決定): 1 つの表 (run) を、その表の先頭 h (COL 直後の slot の直前、`find_head` の戻り値) で同定する。出現数は「slot 件数」ではなく「distinct な h の件数」で数える。同じ表の中の複数 slot (例: `num_get` の 9 件が同じ h) は 1 run として数える。

測定 (`arg_vtable_callers.py`・本 PR の変更 commit で測定・2 回一致。入力 TSV は `receiver_this_trace.py` の md5 `1e1f5500…`):

- 表の出現 slot = 152 件 / 表 (distinct h) = 144 個。
- 1 F が同じ表に 2 slot 以上現れる例は 0 件。`find_head` が解決できない slot = 0 件。
- 旧表示 (slot 件数) と新表示 (run 数) の差は 8 件 (`num_get` 系の同一表内の slot)。

`arg_vtable_callers.py` は `表の出現 slot = N 件 / 表 = M 個` の 1 行を出す。受入 3 の換算 (152 slot → 144 run) はこの値で閉じる。

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

実測 (測定 commit `3183c3c6e`・逐次・load は `/proc/loadavg` の 1 分値):

| ツール | 実行 | real (s) | load (開始前 → 終了後) | 出力 md5 |
|---|---|---|---|---|
| `receiver_this_trace.py` | 1 | 19.9 | 1.40 → 1.35 | `1e1f5500…` (TSV 1053 行) |
| `arg_vt_indirect.py` | 1 | 25.0 | 1.35 → 1.57 | `42bcf98b…` (118222 件・SC 19 件) |
| `arg_vt_indirect.py` | 2 | 25.1 | 1.35 → 1.53 | `42bcf98b…` (2 回一致) |

- 素材: `plugins-serum2.tar.zst` を展開し `Install_Xfer_Serum2_2.1.5.exe` (1,313,084,056 B) から `Serum2.vst3` を取り出した。`Serum2_win64.vst3` の sha256 `501e7bb3…` / 19,236,864 B を確認 (PR 本文の記載と一致)。
- `receiver_this_trace.py` の TSV md5 は `1e1f5500…`。`REPORT_SR60.md` §3 の `ea2d93a2…` (3 回一致) とは**不一致**。`REPORT_SR49.md`・`REPORT_SR58.md` の既定 TSV md5 は `1e1f5500…` で、こちらと一致する。SR60 の値が外れ値である可能性が高いが、SR60 の差の原因は未確認。
- 鮮度 (`docs/WORKFLOW.md` §6): 測定 commit `3183c3c6e` から HEAD までの `*.py` の差分は 0 行 (`git diff 3183c3c6e HEAD -- 'tools/targets/serum2/gui/*.py'`)。測定 commit の `*.py` は `b3607f9df` と同一 (`git diff b3607f9df 3183c3c6e -- 'tools/targets/serum2/gui/*.py'` = 0 行)。旧 commit `6c2b01972` から `*.py` の差分は `arg_vt_indirect.py` の 6 行 (`b3607f9df`) のみ。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 間接 call の候補の宛先 (reg の指す object) の型を確定する。候補 118,222 件は disp のみの照合 (§5 で再測定済み)。SC 関数内の候補 14 件の受け手は §7 で出所を分類済みだが、型は未確定 | 受入 1 | #4930 (本 issue 残・親 #4164 の子) |
| (b) THIS 69・THIS-CHILD 197 の SC 伝播と、THIS-CHILD の SC 証拠 (6 件 / 5 関数) の定義を揃えた再集計 | 受入 2 | #4930 (本 issue 残) |
| (c) 表の境界の決め方 (§4 で決定・達成) | 受入 3 | 閉じた (§4) |
| (d) `receiver_this_trace.py` の TSV md5 が SR60 (`ea2d93a2…`) と不一致。本 PR の測定 (`224202d55`) では `1e1f5500…` で、REPORT_SR49・REPORT_SR58 の既定 TSV md5 と**一致する** (SR60 の `ea2d93a2…` とは不一致)。SR60 側の差の原因は未確認 | 再現性 | #4930 (本 issue 残) |
| (f) RTTI 照合 (THIS 所属関数の vtable RTTI・THIS-CHILD の SC RTTI 6 関数) は未実施。入力 `Serum2_win64.vst3` は §7 の測定で用意できた (`plugins-serum2`) | 受入 2 の前提見直し | #4930 (本 issue 残) |

(e) は §5 の再測定で閉じた (`arg_vt_indirect.py` を HEAD で 2 回実行、118,222 件・md5 `42bcf98b…` で一致)。

## 7. SC 関数内の候補の受け手型 (受入 1 の残り)

`recv_sc_sites.py` (新規): §2 の候補のうち、呼出元が SC の関数で disp が候補の表と一致する call について、受け手 (reg) の出所を `receiver_this_trace.receiver()` で strict / loose の両方で分類する。`sc_slot_stores.py` (新規): SC の関数内で `this+off` に vtable 先頭を書く `mov` を列挙する。`sc_slot_stores.py` は rcx の定義を追う際、`lea` を含む rcx への書込みで追跡を止め、`call` で打ち切る (レビュー指摘の rcx 誤記録を修正)。

**実測 (入力 `plugins-serum2` → `Serum2_win64.vst3`・sha256 `501e7bb3…`・19,236,864 B・測定 commit `d60bd796c`)**:

入力は `tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'` で `Install_Xfer_Serum2_2.1.5.exe` (1,313,084,056 B) を取り出し、`7z x` で `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` を展開して作った (作業 dir は `$RUNNER_TEMP/serum2_4930`・リポジトリ外)。

| ツール | 出力 | md5 | real (s) |
|---|---|---|---|
| `receiver_this_trace.py --vtable 0x180a2bf58 --tsv` | cat_strict の TSV 1053 行 | `1e1f5500…` | 23.6 |
| `arg_vt_indirect.py` | 候補 118,222 件・うち呼出元が SC の関数 19 件 | `42bcf98b…` | 28.3 |
| `recv_sc_sites.py` | SC 関数内の候補 call = 14 件 | `367f06dc…` | 24.2 |
| `sc_slot_stores.py` | 5 行 (this+0x0・+0x10・+0x18・+0x30・+0x38 → vtable 5 本) | `961c1d7f…` | 23.4 |

- load (1 分値): 1 本目の開始前 0.96、`arg_vt_indirect.py` 終了後 1.26、`recv_sc_sites.py` 終了後 1.31、`sc_slot_stores.py` 終了後 1.15。逐次実行。
- `recv_sc_sites.py` の 14 件の内訳 (strict / loose):
  - strict: this 3 (+0x10・+0x18・+0x40)・arg 1・stack 2・nodom 3 (+0x10・+0xc8・なし)・R-nodom 1・callret 3 (+0x118・+0xc8・なし)・stackslot 1
  - loose: this 6 (+0x10・+0x18・+0x40、および `this+0x22388`+0x10・`this+0x22798`+0xc8・`this+0x22798`)・arg 1・stack 2・stackslot 2・callret 3
- 同じ入力のレビュー側実測 (`d60bd796c`) と、4 本すべての md5 が一致した。
- `sc_slot_stores.py` の rcx 追跡修正は合成入力でも確認した: `lea rcx` の後の `mov [rcx+8], rdx` は this+8 として記録されない。rcx 以外への `lea` を経由する store (`lea rdx` → `mov [rcx+0x10], rdx`) は正しい vtable 先で記録される。実バイナリでは §7 の 5 行が上記の結果。

測れたこと: 受け手 (reg) の出所の分類 (strict / loose の件数と内訳)、SC 関数内で this+off に vtable 先頭を書く 5 箇所。

測れていないこと:
- 受け手の型 (基底 `EditController` か別 object か) は未確定。`receiver()` は出所を分類するだけで型を決めない。
- RTTI 照合 (THIS 所属関数・THIS-CHILD の SC RTTI) は未実施 (§6 (f))。
- 受入 1 の宛先型の確定は、この方法では閉じていない。`this+off` の値の書込みを追う簡易版の限界による。
