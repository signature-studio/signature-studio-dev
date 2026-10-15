# REPORT — [SR-63 #4242] Serum 2 setState 閉包の `call [rax+0x88]` 2 件の受信型と Splice 経路 (静的・部分達成)

- 日付: 2026-10-15 / 親: #3399 (SR-54) / 前段: `REPORT_SR54.md` §2・§3・§5、`REPORT_SR44.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。本 run で展開し、sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` を実測 (REPORT_SR54 §0 の値と一致)。作業用 dir はリポジトリ外。
- 測定 commit (解析に使ったコード): `40902feb7` (origin/main)。本 run の setState 出力 md5 `434362cc04773d5d60b957d5888a7de2` は REPORT_SR54 §1 の値と一致 (再現)。
- 測定 commit の差分: `917e48fc7` (REPORT_SR54 の測定 commit) から HEAD までに `slot_reach.py` (`git diff --numstat` で +6/-1) と `receiver_this_trace.py` が変わっている。REPORT_SR54 の『差分 0 行』は後続 commit で成り立たなくなった。出力の md5 は変わらなかった (§1)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `call [rax+0x88]` 2 件の受信オブジェクトが SC の this か、別オブジェクトか | **別オブジェクト (setState の this の要素) と判定**。2 件とも、受信は配列要素を読んだ値で、this 自身ではない (§2.1・§2.2)。要素の型 (vptr) は未確定 |
| 2. Splice 生成 `0x180498090` への経路の有無 | **未確定**。受信要素の型が決まらないため、宛先 (vptr 先) が slot 17 `0x1800c9680` かを判定できない (§2.3) |
| 3. `+0x20408` の書込元 `0x1803573f0` の呼出元と、`+0x22798` の escape | **未達**。`+0x22798` の lea escape は 3 箇所を確認 (§4)。`0x1803573f0` の呼出元の追跡は本 run で未着手 |
| 4. REPORT に測定 commit と再現手順 | **達成** (§1・§5) |

## 1. 再現手順と実測

```sh
# S: リポジトリ外の作業用 dir。P: 本ディレクトリ (tools/targets/serum2/gui)
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --target 0x1800c9680 --target 0x180498090 --target 0x1803573f0 --disp 0x88 > setstate.txt
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv rtt.tsv > rtt.txt
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0x22798 --offset 0x20408 --offset 0x227a0 > offs.txt
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0x22380 --offset 0x1da80 > offs2.txt
venv/bin/python $P/virt_callers.py Serum2_win64.vst3 0x1800a9f40 0x30
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800c3080 0x1800c3140
```

| 実行 | 所要時間 (実測) | 結果 |
|---|---|---|
| setstate (`--target` 3 件 + `--disp 0x88`) | 10.1 秒 (user 10.0 秒) | rc 0・94 行・md5 `434362cc…` (一致) |
| receiver_this_trace (`--vtable 0x180a2bf58`) | 22.0 秒 (user 21.1 秒) | rc 0。`0x18049e656` は `R-nodom`、`0x1804bda03` は `vptr:NODOM` (strict) |
| offset 0x22798 / 0x20408 / 0x227a0 | 未計測 (出力 88 行のみ記録) | 出力 88 行 |
| offset 0x22380 / 0x1da80 | 未計測 | 出力 (`offs2.txt`) の行数のみ記録 |

実行環境: 本 run の runner (同 run 内で逐次実行。並列実行なし。load は測っていない)。

## 2. 受入 1・2: 2 件の受信

### 2.1 件 1: `0x18049e656` in `0x18049e5d0`

- 入口: setState `0x1800c2ed3` の `mov rcx, [rdi]`。`rdi` は `[rsi+0x22380]`〜 の 8 byte 配列を走る (`0x1800c2eb7` `mov rdi, [rsi+0x22380]`、`0x1800c2ed8` `add rdi, 8`)。`call 0x18049e5d0` の `rcx` は配列要素の内容。
- `0x18049e5d0`: `mov rsi, rcx` の後に `mov rcx, rsi` → `call [rax+0x88]`。受信 = 要素 `[[rdi]]`。
- 判定: setState の this (`rsi`) そのものではなく、this の配列要素。型は未確定。

### 2.2 件 2: `0x1804bda03` in `0x1804bcff0`

- setState `0x1800c2cbc` `lea rbx, [rsi-0x30]` (`rbx` = this-0x30)。`0x1800c2cd2` `call 0x1800c3080` (`rcx = rbx`)。
- `0x1800c3080`: `mov [rbp+0xc0], rcx` で `this` を保存。`0x1800c4f70` の 8 byte 刻みループ (`esi` = `0x1da80`〜`0x1dae0`、12 本) の `0x1800c4f9b` `call 0x1804bcff0` で、受信 `rcx = [this + rsi]`。
- `0x1804bcff0` `mov rsi, rcx` → `0x1804bda00` `mov rcx, rsi` → `0x1804bda03` `call [rax+0x88]`。受信 = `this` の `+0x1da80`〜`+0x1dae0` の要素。
- 判定: `this` 自身ではなく、this の配列要素。型は未確定。

### 2.3 vptr の型と SC との関係

- `0x180a2bf58` は MSVC RTTI (COL) で `.?AVSerumController@@` (COL `0x180a2c800`、this-offset 0x30)。実測。`0x180a2bf18` (offset 0x18)・`0x180a2bb98` (offset 0) も同じ SC の vtable。
- `0x180a2bf58` の rip 相対参照は ctor `0x1800a9f40` の 1 件 (`0x1800a9fa9`→`0x1800a9fb0` `mov [rsi+0x30], rax`)。ctor の direct 呼出元は 2 件 (`0x180002bc2` in `0x180002b80`、`0x180002db2` in `0x180002d70`)。どちらも `0x1809a4b80` の戻り値 (新規確保) を `rcx` に渡し、`[rbp-8]+0x30` を続けて使う。SC の構築箇所と読める (型名は RTTI で確定)。
- ただし件 1・件 2 の受信は §2.1・§2.2 のとおり配列要素で、`vptr:THIS` (this 直接) の経路ではない。要素の vptr がどの vtable を指すかは未確定。したがって『件 2 の vptr が SC の `0x180a2bf58` か』は**未確定**のまま。

### 2.4 Splice 生成への経路 (受入 2)

- `0x180498090` の direct 逆閉包 R = `0x1800c9680` (slot 17) と `0x180498090` 自身 (2 関数)。setState の direct 閉包 C (854 関数) との交わりは 0。
- `0x1800c9680` は `0x180a2bf58` の index 17 (`0x88`/8) の slot (実測: data slot `0x180a2bfe0`)。
- 件 1・件 2 の宛先 (要素の vptr 先) が SC の index 17 なら slot 17 → Splice 生成の 1 辺で届く。要素の型が未確定のため、届く・届かないは**未確定**。

## 3. 受入 3 (一部): `+0x20408`

- `0x1803573f0` の direct 逆閉包 R = 8 関数 (`0x18004fad0`・`0x1800506b0`・`0x180064d60`・`0x18006fc80`・`0x1800709e0`・`0x180353080`・`0x180353400` 等)。setState の C との交わりは 0 (実測)。
- `+0x20408` の書込 `0x180357931` (`0x1803573f0` 内)・読出 `0x1800c96a8` (slot 17)。demo-bit 関数との交わりは無し。
- 呼出元の追跡 (8 関数の間接呼出し経由) は本 run で未着手。

## 4. 受入 3 (一部): `+0x22798` の escape

- `+0x22798` (Splice オブジェクト) の参照は 7 箇所・3 関数 (実測):
  - R `0x1800aa341` in `0x1800a9f40` (ctor): `lea rcx, [rsi+0x22798]` (スロットのアドレスを callee に渡す)
  - W `0x1800ac6e9` in `0x1800ac190` (dtor 側): `mov [rsi+0x22798], rax`
  - R `0x1800ac798` in `0x1800ac190`: `lea rcx, [rsi+0x22798]` (同上)
  - R/W `0x1800c96b9`・`0x1800c98d8`・`0x1800c990a`・`0x1800c9925` in slot 17
- スロットのアドレスは ctor・dtor で `lea` により callee へ渡される。callee が中身を書換えるかは未確認。escape の先は未解決。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 件 1・件 2 の要素の型 (vptr 先の vtable が SC の index 17 か)。`[rsi+0x22380]`・`[this+0x1da80]` の要素を書く箇所の追跡 | 受入 2 (デモ bit=0 で Splice 表示が偽になる経路の有無) | #4483 [SR-75] |
| (b) `+0x22798` の lea escape 先 (ctor `0x1800a9f40` の `lea` 先の callee)、`+0x20408` の書込元 `0x1803573f0` の呼出元 | 受入 3 | #4484 [SR-76] |
| (c) 閉包外へ出る間接 call の宛先 (REPORT_SR44 §9 (a)) | 受入 2 の『非到達』の完全性 | [SR-53] (#3398) |

## 6. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
