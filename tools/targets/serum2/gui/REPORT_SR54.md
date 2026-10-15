# REPORT — [SR-54 #3399] setState 閉包の `call [rax+0x88]` 2 件の受信型 (静的・部分達成)

- 日付: 2026-10-15 / 親: #2175 (SR-44・CLOSED) / 前段: `REPORT_SR44.md` §3.2・§4・§9
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。間接 call の受信型は vptr の値を追う範囲に限る。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。`Serum2.vst3` の sha256 `501e7bb3…4ecd4e5283` (REPORT_SR44 §0 の値を引用。本 run では素材未展開・未照合)。作業用 dir はリポジトリ外。
- 測定 commit: `917e48fc7` (`slot_reach.py` の最終変更)。`git diff 917e48fc7 HEAD -- tools/targets/serum2/gui/slot_reach.py` は差分 0 行 (実測)。`disasm_range.py` も本 PR で変更していない。
- 同じ `slot_reach.py` 版 (`917e48fc7` 以降) の出力を使う。setState の出力 md5 `434362cc…` は REPORT_SR44 §1 の値を引用 (本 run では未再実行)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `call [rax+0x88]` 2 件の受信オブジェクトが SerumController の this か、別オブジェクトか | **部分達成**。2 件とも受信は `[vptr+0x88]` の間接呼出し。受信 `rcx` の経路は §2 で追跡。vptr が SC の vtable head `0x180a2bf58` かどうかは未確定 (§2.3) |
| 2. Splice 生成 `0x180498090` への経路の有無 | **未確定**。setState の direct 閉包 C (854 関数) に `0x180498090` の逆閉包 R (2 関数: `0x1800c9680`・`0x180498090`) との交わりは無い (C ∩ R = 0)。ただし閉包の外へ出る間接 call を解いていない |
| 3. `+0x20408` の書込元 `0x1803573f0` の呼出元と、`+0x22798` の Splice オブジェクトの escape | **未着手の一部**。`0x1803573f0` の direct 逆閉包 R は 8 関数で、C ∩ R = 0 (§3)。`+0x22798` の escape は未確認 |
| 4. REPORT に測定 commit と再現手順 | **達成** (§1・§5) |
| 5. slot 17 のゲート入力 `[rax+0xb8]` の全 `.text` 列挙 | **記録のみ (本 run 未再実行)**。前回 run の記録で全 `.text` 4,309 箇所 (1,372 関数)。デモ bit 関数 (`0x1800c2b50`・`0x1800c6090`) の箇所は 0 件 (§4)。再現には `plugins-serum2` 素材が要る |

本 run では素材 (`plugins-serum2`) が無いため、解析スクリプトを再実行していない。下記の値はすべて前回 run の記録で、本 run の実測ではない。
記録された結果: 2 件の `call [rax+0x88]` の受信 `rcx` の伝播 (setState → `0x18049e5d0`・`0x1800c3080` → `0x1804bcff0`)、`[rax+0xb8]` の全 `.text` 参照表。
受信型 (vptr が SC か) は未解決。受入 1〜3 は子 issue へ移管 (§5)。

## 1. 再現手順

```sh
# S: リポジトリ外の作業用 dir。P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --target 0x1800c9680 --target 0x180498090 --target 0x1803573f0 --disp 0x88 > setstate.txt   # §2・§3
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0xb8 --disp 0x88 > offb8_setstate.txt   # §4
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x18049e5d0 0x18049e680   # §2.1
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800c2b50 0x1800c2f40  # §2.2
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800c3080 0x1800c3140  # §2.2
```

- 依存: `pefile` `capstone` `zstandard`。
- 実行状況: 本 run では未実行 (`plugins-serum2` 素材が本 run に無いため)。所要時間は本 REPORT では測定していない。

| 実行 | 状態 | 出力 (前回 run の記録・引用) |
|---|---|---|
| setstate (`--target` 3 件 + `--disp 0x88`) | 本 run 未実行 | md5 `434362cc…` (REPORT_SR44 §1 の値を引用) |
| offset 0xb8 (`--offset 0xb8 --disp 0x88`) | 本 run 未実行 | 出力 4,386 行 (前回 run の記録。md5 は未記録) |

## 2. `call [rax+0x88]` 2 件の受信 (受入 1・2)

### 2.1 件 1: `0x18049e656` in `0x18049e5d0`

- 入口: setState `0x1800c2ed3` が `rcx = [rdi]` (`rdi` は `[rsi+0x22380]`〜`[rsi+0x22388]` の要素) を渡す (`call 0x18049e5d0`)。
- `0x18049e5d0`: `mov rsi, rcx` (入口 `rcx` を保存)。`mov rcx, rsi` の直後に `call [rax+0x88]`。受信 = 入口 `rcx` = 要素 `[[rdi]]`。
- 要素の型は未確定。SC の this ではなく、setState の配列要素である。

### 2.2 件 2: `0x1804bda03` in `0x1804bcff0`

- setState `0x1800c2cbc` で `rbx = rsi-0x30` (`rsi` は setState の this)。`0x1800c2cd2` で `rcx = rbx` のまま `call 0x1800c3080`。
- `0x1800c3080` は `mov [rbp+0xc0], rcx` で入口 `rcx` (= `rbx`) を保存する。`0x1800c4f70` で `esi = 0x1da80` から `0x1dae0` まで 8 byte 刻みのループ。`0x1800c4f9b` の `call 0x1804bcff0` の受信は `rcx = [this + rsi]` (`this = [rbp+0xc0]`)。つまり受信は `rbx` そのものではなく、`this` のオブジェクト内 (`+0x1da80`〜`+0x1dae0`、8 byte 刻み 12 本) の要素。
- `0x1804bcff0` の `mov rsi, rcx` で `rsi` = その要素。`0x1804bda00` `mov rax,[rsi]` (vptr) → `0x1804bda03` `call [rax+0x88]` (`rcx = rsi`)。要素の型は未確定。

### 2.3 vptr の型 (未解決)

- vtable head `0x180a2bf58` の rip 相対参照は ctor `0x1800a9f40` の 1 件だけ (`0x1800a9fa9` `lea rax,[rip+0x981fa8]` → `0x1800a9fb0` `mov [rsi+0x30], rax`)。ctor は `[rsi]` (`lea` 先 `0x180a2bb98`)・`[rsi+0x10]`・`[rsi+0x18]`・`[rsi+0x30]` (`0x180a2bf58`)・`[rsi+0x38]` に vptr を書く。複数の vtable を持つ型である (型名は未確認)。
- `0x180a2bf58` の書込は `[rsi+0x30]` だけ。ctor の `rsi` が setState の `rbx` (= `B`) と同じ object かは未確認 (`0x1800a9f40` の呼出元の追跡が要る)。もし同じなら setState の `rsi = B+0x30` は `0x180a2bf58` の副基底を指すが、§2.2 の 2 件目の受信は `B` の要素であり `B+0x30` ではない。
- したがって 2 件の vptr がどの vtable head を指すかは本 run では確定していない。受入 1 の『SC の this か』は未確定。

### 2.4 Splice 生成への経路 (受入 2)

- `0x180498090` の direct 逆閉包 R は `0x1800c9680` と `0x180498090` 自身の 2 関数。setState の閉包 C と C ∩ R = 0。
- したがって『direct 閉包の範囲では Splice 生成へ届かない』。`call [rax+0x88]` の宛先 (vptr が指す関数) は direct 辺ではないため、この結論の外にある。
- vptr の型が SC の vtable head `0x180a2bf58` なら、index 0x88/8 = 17 の `0x1800c9680` (slot 17) に届き得る。その場合は slot 17 → `0x180498090` の 1 辺で Splice 生成に届く。型未確定のため『届く』も『届かない』も確定しない。

## 3. `+0x20408` の書込元 `0x1803573f0` (受入 3・一部)

- `0x1803573f0` の direct 逆閉包 R は 8 関数 (`0x18004fad0`・`0x1800506b0`・`0x180064d60`・`0x18006fc80`・`0x1800709e0`・`0x180353080`・`0x180353400` 等)。
- setState の direct 閉包 C ∩ R = 0。
- 呼出元は direct 逆閉包の 8 関数で与えられる。`+0x22798` の Splice オブジェクトの escape は本 run では未確認 (未解決)。

## 4. `[rax+0xb8]` の全 `.text` 列挙 (受入 5)

`slot_reach.py <pe> 0x1800c2b50 --offset 0xb8 --disp 0x88` (`--offset` は [reg+off] の全 `.text` 参照):

- 全 `.text` の `+0xb8` の memory operand: 4,309 箇所 (1,372 関数)。W 1,310・R 2,999。
- デモ bit 関数 (`0x1800c2b50`・`0x1800c6090`) の箇所: **0 件**。
- slot 17 (`0x1800c9680`) のゲート入力 `[rax+0xb8]` は `0x1800c96d2` (`cmp byte ptr [rax+0xb8], 1`) の 1 箇所の読み。書込は slot 17 の中に無い。

結論 (受入 5): `+0xb8` の多数の参照は他のオブジェクト型のフィールドで、デモ bit と結ぶ直接の読み書きは無い。slot 17 の `[rax+0xb8]` の参照元 (`rax` が Splice オブジェクトを指す) は `+0x22798` の escape に依存し、そこが未解決。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) `call [rax+0x88]` 2 件の vptr の型 (SC の vtable head `0x180a2bf58` か)。`0x1800a9f40` (ctor) と `0x1800c2b50` 閉包内の `rsi` の出所の追跡 | 受入 1・2 (デモ bit=0 で Splice 表示が偽になる経路の有無) | [SR-63] #4242 (親: #3399) |
| (b) `+0x22798` (Splice オブジェクト) の escape (slot 17 の `r14`)、`+0x20408` の書込元 `0x1803573f0` の呼出元 (受入 3 の後段) | 受入 3 | [SR-63] #4242 (親: #3399) |
| (c) 閉包外へ出る間接 call の宛先 (REPORT_SR44 §9 (a) の #3398 と同じ) | 受入 2 の『非到達』の完全性 | [SR-53] (#3398) |

## 6. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
