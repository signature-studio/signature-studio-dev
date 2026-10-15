# REPORT — [SR-75 #4483] Serum 2 setState の `call [rax+0x88]` 2 件の受信要素の型 (部分達成・静的)

- 日付: 2026-10-15 / 親: #4242 (SR-63) / 前段: `REPORT_SR63.md` §2・§5
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。FLEngine 起動・GUI は動かしていない。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` を実測 (REPORT_SR63 と一致)。作業用 dir はリポジトリ外 (`tools/targets/serum2/gui/work/`、gitignore 対象)。
- 測定 commit (解析に使ったコード): `e87c2ef27` (origin/main)。本 PR は解析スクリプトを変えていない (`git diff e87c2ef27 HEAD -- tools/targets/serum2/gui` は REPORT_SR75.md の追加のみ)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. 2 件の要素の vptr 先が SC `0x180a2bf58` (index 17) か | **件 1 (`0x18049e656`): 確定。vptr 先は `.?AVSerumEditor@@` (`0x180a86998`)。SC ではない。** 件 2 (`0x1804bda03`): **未確定** |
| 2. Splice 生成 `0x180498090` への経路の有無 | **件 1: 直接 call の閉包では非到達** (slot 17 `0x18049e110` の閉包 C に `0x1800c9680` が無い。間接 call は未解決の制限つき)。件 2: 未確定 |
| 3. REPORT に測定 commit と再現手順 | **達成** (§1・§5) |

部分達成のため `Refs #4483`。残りは §4 の表で #4483 に残す。

## 1. 再現手順と実測

```sh
# S: tools/targets/serum2/gui/work (gitignore)。P: tools/targets/serum2/gui
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/receiver_this_trace.py Serum2_win64.vst3 --vtable 0x180a2bf58 --tsv rtt.tsv > rtt.txt
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x18049e110 --target 0x180498090
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0x22380 --offset 0x1da80
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0x22388 --offset 0x223b8
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x180498090 0x180498380
```

| 実行 | 所要時間 (実測) | 結果 |
|---|---|---|
| receiver_this_trace (`--vtable 0x180a2bf58`) | 24.3 秒 (real)・user 23.1 秒 | rc 0。件 1 `0x18049e656` は `R-nodom`、件 2 `0x1804bda03` は `vptr:NODOM` (REPORT_SR63 と同じ) |
| slot_reach (root `0x18049e110`, target `0x180498090`) | 未計測 | `C = 94 関数` (BFS 深さ max 16)、`target 0x180498090: not in C`、`R = 2 関数`、`C ∩ R = 0` |
| slot_reach offset `0x22380`/`0x1da80`、`0x22388`/`0x223b8` | 未計測 | 出力は §2・§3 の行 |

実行環境: 本 run の runner。逐次実行 (並列なし)。load は測っていない。

## 2. 受入 1・2: 件 1 (`0x18049e656`)

### 2.1 受信の確定

- `0x18049e5d0` は `rsi = rcx` (受信そのもの) を保持し、`0x18049e656` で `call [rax+0x88]` (`rax = [rsi]`)。受信 = 呼出元 `0x1800c2ed3` が渡す配列要素。
- 配列は setState `0x1800c2b50` の `[rsi+0x22380]`〜`[rsi+0x22388]` (`0x1800c2eb7`・`0x1800c2ebe`)。
- **要素を積むのは slot 17 `0x1800c9680` の 1 箇所**。`0x1800c9968` で end ポインタ `+0x22388` を読み、`0x1800c9978` で `mov [rdx], rax` (要素)、`0x1800c9986` で end を進める。`+0x22388` の書込は他に無い (`--offset 0x22388` の W は 1 件)。
- 要素 `rax` の源: `0x1800c9680` が `call 0x180498090` (`rcx = new 0x3a0 object`、`rdx = rdi`、`r8d = 1`) の戻り値を `[rbp+0x30]` 経由で積む (`0x1800c994b`〜`0x1800c9960`)。`0x180498090` の戻り値は `[rbp-0x20]` (`0x18049827b` で `mov [rbp-0x20], rdi`) が源で、vptr を書かれた `rdi` と同一 object。
- `0x180498090` は `[rdi+0]` に `lea rax, [rip+0x5ee843]` (`0x18049814e`) → `mov [rdi], rax` (`0x180498155`) で vptr `0x180a86998` を書く。RTTI (COL `0x180a86d60`) で `.?AVSerumEditor@@` と確定。
- 同じ vtable への rip 参照は 2 件: ctor `0x18049814e` (`0x180498090` 内) と `0x1804986ea` (関数 `0x1804986d0`、未調査)。

**判定: 件 1 の受信要素の vptr 先は SerumEditor (`0x180a86998`)。SerumController (`0x180a2bf58`) ではない。** (REPORT_SR63 §2.1 の『型は未確定』を確定に更新)

### 2.2 件 1 の呼出先と Splice 経路

- 件 1 の `call [rax+0x88]` の宛先 = SerumEditor の index 17 = `0x18049e110` (`[0x180a86998 + 0x88]` を実測)。
- `slot_reach --target 0x180498090` で root `0x18049e110` の閉包 C = 94 関数。`0x180498090` の direct 逆閉包 R = 2 関数 (`0x180498090` 自身と `0x1800c9680`)。`C ∩ R = 0`。
- **結論: direct call の閉包では `0x180498090` に到達しない。** ただし C 内の間接 call (`mem` 101・`rip-import` 37・`reg` 10 件) は宛先未解決で、非到達の証明としては不完全。

## 3. 件 2 (`0x1804bda03`): 未確定

- 受信は `this` (`0x1800c3080` の `rbp+0xc0`) の `[+0x1da80 + 8k]` (k = 0〜11、`0x1800c4f97` `mov rcx, [rax+rsi]`)。`this` の配列 `+0x1da80`〜`+0x1dae0` の要素。
- `+0x1da80`〜`+0x1dae0` を `[reg+disp]` で直接 `mov` 書込する命令は `.text` 全体で 0 件 (`disp` 0x1da80〜0x1dae0 の範囲を走査)。`0x1800c4dc5`〜`0x1800c4e04` の `lea r14, [rax+0x1dae0]`・`call 0x180017d20` は、この配列の積み込みかどうか未確認 (呼出先 `0x180017d20` の中身は未調査)。
- 件 2 の要素の源と vptr 先は**未確定**。
- `+0x1da80` の読出は `0x1800a9f40` (ctor) など 13 箇所で、ctor `0x1800aaac6` は `[rax+0x500]` に `r14` を書く。
- **件 2 の vptr 先と Splice 経路は未確定。**

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 件 2 `0x1804bda03` の要素の源 (`0x180017d20` の呼出し元・`+0x1da80` 配列の積み込み) と vptr 先 | 受入 1・2 の件 2 | #4483 (本 issue) |
| (b) SerumEditor 閉包 (`0x18049e110`) の間接 call 101 件・rip-import 37 件の宛先 | 件 1 の非到達の完全性 | #4483 (本 issue) |
| (c) `0x1804986ea` (vtable `0x180a86998` の 2 つ目の rip 参照元) の役割。要素の vptr が後から書き換えられるか | 件 1 の vptr 確定の完全性 | #4483 (本 issue) |
| (d) `+0x22798` の escape、`+0x20408` の書込元 | REPORT_SR63 §3・§4 の受入 3 | #4484 [SR-76] (既存) |

## 5. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
