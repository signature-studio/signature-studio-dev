# tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_3880.md — engine の effProcessEvents (opcode 25) の VstEvents 読取箇所 (#3880)

親: `REPORT.md` §9.5・§9.6 (#894 受入 1 の続き)。 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/slayer_engine_ia32/trace_effevents.py` (gate) と `… --nega` (ネガコン)。 素材 `block22434_PE.bin` の sha256 `84b64c43…de724a9` を検証。 capstone 5.0.7 固定。

## 1. 結論

- engine (block22434) で opcode 25 (effProcessEvents) の `numEvents` / `events[]` を読む関数は **`0x10008FA0`** (vtable `0x10013690` の `+0xc8`)。
- 呼出し連鎖は静的に確定した: `AEffect.dispatcher` (0x10001000) → object の vtable `0x10013690` の `+0x18` = 派生 dispatcher `0x10001BF0` → opcode 25 (jump table 先頭 0x1000217C) → `0x10001C0D` → `call [vtable+0xc8]` = `0x10008FA0`。
- 読取の配置は MARSHAL.md §4 の x32 表と一致: `numEvents` は `[arg+0]` (`cmp dword ptr [eax],0`)、`events[i]` は `[arg+8 + 4*i]` (ポインタ 4 B、stride 4)。 各要素を `[esi]` (VstEvent の type) で分岐する。
- REPORT.md §9.3 の「dispatcher では読まれない」は**正しい** (0x10001300 は基底 vtable の dispatcher で、opcode 25 は既定分岐)。 読取は**別の派生 dispatcher** (0x10001BF0) にある。 受入 1 は本付録で達成 (静的)。

## 2. 経路の実測 (逆アセンブル・capstone 5.0.7・CS_MODE_32)

| 段 | VA | 実測 |
|---|---|---|
| AEffect.dispatcher (thunk) | 0x10001000 | opcode 1 以外を `call dword ptr [edx+0x18]` (edx = object の vtable)。 AEffect の `+0x24` に格納 (ctor RVA 0x10E0 の `mov [edx+0x24],0x10001000`) |
| 基底 vtable | 0x100130E0 | `+0x18` = 0x10001300 (基底 dispatcher・opcode 25 は既定分岐 0x149C)。 ctor 0x10E0 が設定 |
| 派生 vtable (ctor 0x1BB0・0x1BE0) | 0x100131E8 | `+0x18` = 0x10001BF0。 `+0xc8` = 0x10001A90 (`xor eax,eax; ret 4` の no-op。 events を読まない) |
| 派生 dispatcher | 0x10001BF0 | `lea edx,[esi-0x19]`・`cmp edx,0x33`・`ja 0x1000215A`。 opcode 25 (0x19) から 76 (0x4C) まで jump table `0x1000217C` で分岐 |
| case 25 | 0x10001C0D | `mov edx,[esp+0x1c]` (VstEvents* 引数) → `push edx` → `call dword ptr [eax+0xc8]` |
| events 走査本体 | 0x10008FA0 | `cmp dword ptr [eax],0` (numEvents)・`add eax,8`・`mov esi,[eax]` (events[i]、4 B)・`cmp dword ptr [esi],1` (type 分岐)・ループ末尾 `add esi,4` (0x100091C8) |
| 走査本体を持つ vtable | 0x10013690 | `+0x18` = 0x10001BF0。 `+0xc8` = 0x10008FA0。 設定元 ctor 0x7F30 (`mov [ebp],0x10013690`、`push 0x2204`) |

- `0x10008FA0` を指す絶対 dword 参照は vtable `0x13758` (= `0x13690` の +0xc8) の 1 箇所だけ。 ただし vtable の**呼出し元の全数**は未確認 (ctor 0x7F30 の呼出し元は 0x7CD0 のみ・そこから先は未追跡)。
- 0x10008FA0 の `[esi]` (type) による分岐は switch table `0x100091F8` で、type 0〜4 は個別の処理先、type 5 以上は `0x04040400` 等の値が並ぶ (分岐先ではない)。 各分岐が読む `[esi+0x18]`・`[esi+0x19]`・`[esi+0x1a]` の意味は未確認。

## 3. 範囲と限界 (未確認)

- **静的のみ**。 engine を実行していない。 `numEvents` / `events[]` の実値・配置 (`arg+8` の先頭が events[0] であること) は、実行トレースで確認するまで推定。 これは issue の範囲外 (動的確認は別件)。
- 0x10008FA0 の 1 件目の要素の type 分岐先 (0x10009006 / 0x10009066 / 0x1000913B / 0x10009167 / 0x100091B9) の各々が何を書くかは本付録では詳細化しない。 VstMidiEvent の内容 (`[esi+0x18]` 等) の意味は未確認。
- 派生 vtable 0x131E8 と 0x13690 の関係 (どちらが実際の host から使われるか) は、2 系統の ctor (0x1BB0 系 / 0x7F30 系) の呼出し元を辿っていない。 この関数の到達 (case 25 → 0x10008FA0) のみ確認。
- 殻 (x64) 側の VstEvents / ERect の実物定義は本件の範囲外 (MARSHAL.md §4・受入 3 は #674 の継続)。

## 4. marshal.py への入力

- 受入 1 の結果 (読取箇所の確定 = 0x10008FA0・numEvents `[arg+0]`・events `[arg+8]` stride 4) は、`marshal.py` の events 受入 (ネガコン付き) の期待値として使える。 `trace_effevents.py` の `check()` がその期待値を持つ。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/slayer_engine_ia32/trace_effevents.py` → `[trace] OK`・exit 0。 ネガコン `--nega` は `nega: 3/3 hit, 0 miss`・exit 0。
