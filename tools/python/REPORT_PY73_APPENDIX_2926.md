# PY-110 付録 (#2926): midiNoteOn ゲートの 3 フラグの書込み元と note-on 経路・`0x63a730` の PE 確定

親: #2817 (PY-93)。前段: `tools/python/REPORT_PY73_APPENDIX_2817.md` §6・§7 (ゲート `0x1262a90` の式と vtable)。本体: `tools/python/REPORT_PY73.md` §2・§8-3。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルと参照列挙による解析)。
実装: 0 件 (`provider/`・`host/`・`tests/` は未変更。推測の状態モデルでは実装しない)。

## 結論

- **3 フラグの書込み元を全数で確定した**: 書込み命令は flagA 4 件・flagB 12 件・flagC 2 件 (計 18 件。§1)。以前の WIP 記録 (`REPORT_PY73_2926.md`・前 run) と件数・VA が一致した。
- **書込みの到達条件は未確定**: 各書込みが実行時に通るか (呼出し元)、flagB の `bl`・`cl` 由来の値、flagC の `vt+0x60` 仮想呼出し元は決まっていない。したがって 3 フラグの実行時値は未確定 → 子 issue (§4)。
- **`0x10002a0` (midiNoteOn 本体) の note-on 経路**: 書込み先 (note 単位の状態表 `item+note+0x808`・カウンタ `[*0x5e3a09]`)・channel の扱い・イベント投入 `0x10602e0` の呼出し引数を確定 (§3)。note-off 側 (`0x1000614` 以降) と `0x10602e0` の中身は未読 → 子 issue。
- **`0x63a730` の副作用は無し** (書込みはスタックのみ。`QueryPerformanceCounter` の値を周波数で割った double を返すだけ。§3-5)。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 22,227,016 B。実測 2.7 秒)。`toolchain-retdec` は本件では未使用。
- 測定 commit: `8665e7f47` (main `f54e7907b` の取り込み merge。`tools/python/analysis` の解析スクリプトは main と同一。解析スクリプトを最後に変えた commit は `6d404849a`)。
- 差分 0 の証跡: 測定後の本付録 commit から測定 commit までの `git diff 8665e7f47 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (§6 の表に記録)。
- 実行 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。並行度は 1〜3):

| 測定 | 結果 | 所要 |
|---|---|---|
| `analysis/flapi/pe_slot_writers.py 15e04a8 8` (既定 disp) | loads 54・candidates 0 | 82.5 秒 |
| `analysis/flapi/pe_slot_writers.py 15e0ff0 8` (既定 disp) | loads 102・candidates 0 | 59.4 秒 |
| `analysis/flapi/pe_slot_writers.py 15e1890 8` (既定 disp) | loads 58・candidates 0 | 83.1 秒 |
| `analysis/flapi/pe_slot_writers.py 15e04a8 0` | loads 54・candidates 19 (偽陽性を含む。§1-2) | 58.1 秒 |
| `analysis/flapi/pe_slot_writers.py 15e0ff0 0` | loads 102・candidates 22 (同上) | 80.5 秒 |
| `analysis/flapi/pe_slot_writers.py 15e1890 0` | loads 58・candidates 4 (同上) | 82.1 秒 |
| 直線区間の全数走査 (一時スクリプト。リポジトリ外・§1-2) | loads 214 (A 54・B 102・C 58)・書込み A 4・B 12・C 2 | 54.9 秒 |
| `analysis/flapi/pe_xref.py 16baff0,16baff1,13e7628` | hits 0・stores 0 | 81.3 秒 |
| `analysis/flapi/pe_xref.py 15e04a8,15e0ff0,15e1890` | hits 214・stores 0 | 81.1 秒 |
| `analysis/flapi/pe_xref.py 15f3308` | hits 7 (読み 6・lea 1)・stores 0 | 58.0 秒 |
| `analysis/flapi/pe_disasm.py 63a730 30`・`100074c 30` | 逆アセンブル (§3) | 各 1 秒未満 |

- 走査の注: `pe_xref.py`・`pe_slot_writers.py` は main の走査修正 (`9e3f9edc`。64 KiB 境界で命令を読み飛ばさない) を含む版。上の件数はこの版の値。
- 検証範囲: 逆アセンブルと参照列挙だけ。wasm・mock・C provider の実行は未実施 (コード差分 0)。起動・GUI に関わらないため製品 KPI は対象外。

## 1. 3 フラグの書込み元 (確定。HEAD で再測定)

### 1-1 フラグとスロット

| フラグ | スロット (`.data`) → 指し先 | 初期値 | スロットへの RIP 相対 store |
|---|---|---|---|
| flagA | `0x15e04a8` → `0x16baff0` (`.bss`) | 0 | 0 件 |
| flagB | `0x15e0ff0` → `0x16baff1` (`.bss`) | 0 | 0 件 |
| flagC | `0x15e1890` → `0x13e7628` (`.data`、file offset `0xfe6028` = 0) | 0 | 0 件 |

- `pe_xref.py` でフラグ本体への RIP 相対参照は 0 件。全アクセスはスロット経由 (測定表の `16baff0,16baff1,13e7628` hits 0・`15e04a8,15e0ff0,15e1890` hits 214)。

### 1-2 書込み命令 (18 件)

スロットを `mov reg,[slot]` で読んだ直後の直線区間で、読込みレジスタを基底にした `mov byte ptr [reg], 値` を列挙した。

| フラグ | 書込み VA | 書く値 | ロード VA | 備考 |
|---|---|---|---|---|
| A | `0xc4dea0` | 1 | `0xc4de99` | |
| A | `0xc4ea3b` | 0 | `0xc4ea34` | |
| A | `0xd1a2ac` | 1 | `0xd1a2a5` | |
| A | `0xd1cb19` | 0 | `0xd1cb12` | |
| B | `0xf46338` | 0 | `0xf46331` | |
| B | `0xf520eb` | 1 | `0xf520e4` | |
| B | `0xf53f20` | 0 | `0xf53f19` | |
| B | `0xfefbd3` | 1 | `0xfefbcc` | |
| B | `0xfefcd7` | 0 | `0xfefcd0` | |
| B | `0xfff311` | 1 | `0xfff30a` | |
| B | `0xfff3c3` | `bl` | `0xfff3bc` | 値は未読 (レジスタ値) |
| B | `0x1042e47` | 1 | `0x1042e40` | |
| B | `0x10440af` | `cl` | `0x10440a3` | 値は未読 (レジスタ値) |
| B | `0x11d6145` | 1 | `0x11d613e` | |
| B | `0x11d6310` | 0 | `0x11d6309` | |
| B | `0x11d631f` | 0 | `0x11d6318` | |
| C | `0x11c761c` | 1 | `0x11c7615` | 関数内 (関数先頭は未算出。WIP 記録では `0x11c75d0` 付近) |
| C | `0x1262977` | 1 | `0x1262970` | vtable `+0x60` の関数そのもの (呼出しは仮想呼出し) |

- 値 1 の書込みは、そのフラグを非 0 にし、ゲートを偽 (内部 code -2) にする。値 0 は解除。
- 書込みの**到達条件** (どの呼出し経路で実行されるか) は未確定 (§4)。したがって「どの時点でフラグが 1 になるか」は決まっていない。

### 1-3 候補の検証方法と偽陽性

- `pe_slot_writers.py` の既定 disp は 8 で、フラグの byte 書込み (disp 0) を拾えない (候補 0)。disp 0 で走らせると候補 19・22・4 件を得たが、**偽陽性を含む**。ツールは「直近 64 バイト以内のロード」と「書込みの基底レジスタの一致」を見ないため、基底が別レジスタ・間に同じレジスタの再ロードがある候補を拾う (例: `0x11d48b3` の直前 `0x11d48ac` は `mov rax,[0x15e4628]` で rax が別スロットになる)。
- そこで、スロットのロード 214 件すべてを起点に、分岐・`call`・`ret`・同じレジスタへの別の書換えまでの直線区間 (最大 0x200 バイト) を逆アセンブルして全数で列挙した (一時スクリプト。リポジトリ外・未コミット)。結果は上の 18 件で、WIP 記録 (4・12・2) と一致する。
- 限界: 直線区間を超える書込み、関数引数で渡ったポインタ経由の書込み、絶対アドレス指定の書込みは見ていない。

## 2. 3 フラグと実行時値

- ゲート (`0x1262a90`。付録 2817 §6) は `!A && !B && !C`。どれか非 0 なら内部 code -2。
- 初期値は 3 つとも 0 (ファイル上 or `.bss`)。したがって実行時に 1 になるのは §1-2 の値 1 の書込みが実行された後のみ。
- 実行時値の確定には、各書込みの到達条件 (§4) が要る。ここでは静的に「値 1 を書く箇所」を確定したところまで。

## 3. midiNoteOn 本体 `0x10002a0(item=rcx, note=edx, velocity=r8d, channel=r9d)` の note-on 経路

フレーム: item `[rbp+0x140]`・note `[rbp+0x148]`・velocity `[rbp+0x150]`・channel `[rbp+0x158]` (`0x10002f2`〜`0x1000306` で退避)。

### 3-1 note の bit31 (`0x100032d`)

- 立つ側: `note &= 0x7fffffff`。velocity > 0 なら `[rbp+0xf9]` = velocity の下位 byte、velocity ≤ 0 なら `[rbp+0x104]` = -velocity。`[rbp+0xfc]` = `(note >> 16) & 0xff` → `0x100050d`。
- 立たない側 (`0x100037e` 以降): 速度テーブル要素の count ≥ 1 のとき速度スケール (`|velocity|` を 0x80 で clamp → テーブル係数 → round) を `byte [rbp+idx+0xf8]` (velocity > 0) または `[rbp+0x104]` (≤ 0) に置く (`0x10004b6`〜`0x10004ef`)。

### 3-2 velocity の符号

- `0x1000579`〜`0x10005f1` (前段): `byte [0x5df978] != 0` かつ velocity > 0 のとき、`0x11c9a70(cl=1)`、条件付きで `item.byte[+0x6ee] = 1` (`0x10005c0`)、`*[0x5e10ba] = *[0x5e08c3]` (`0x10005d8`)。
- `0x10005f7`〜`0x1000601`: `byte [0x5e0b9a] == 0` なら `0x10007d2` (共通後段)。
- `byte [0x5e0b9a] != 0`: velocity > 0 → `0x100074c` (note-on)、velocity ≤ 0 → `0x1000614` (note-off。未読 → §4)。

### 3-3 channel の扱い

- 既定値: `[rbp+0xfc] = byte [[0x5e0ad4]+0x13] & 0xf` (`0x10004f5`〜`0x1000507`。グローバル由来)。bit31 立つ側は `(note >> 16) & 0xff` で置換される (§3-1)。
- 上書き (`0x100051f`〜`0x1000543`): `item.byte[+0x300] != 0` かつ channel (符号付き) ≥ 0 のとき `[rbp+0xfc] = channel`。それ以外は既定値 (channel = -1 は既定扱い)。
- イベント語 `[rbp+0x100] = ([rbp+0x104] << 16) | 0x78 | ([rbp+0xfc] << 24)` (`0x100050d`〜`0x100054d`)。channel は語の上位 8 bit。
- `note &= 0xff00ffff` (`0x1000553`)。

### 3-4 note-on 本体 (velocity > 0、`0x100074c`〜`0x10007cf`。逆アセンブルで確認)

```
0x100074c mov rax,[*0x5e060d]; movsd xmm0,[rax]; call 0x40c660; mov [rbp+0x108],eax   ; tick = round(double)
0x1000762 mov rcx,[0x5e189f]; call 0x4232e0                                            ; lock 取得 (API 名は未同定)
0x100076e mov rax,[0x5e1ba3]; mov rcx,[rax]; edx = tick; r8d = [item+0x9c]+0x4000; r9d = 0x7ffffff0
              [rsp+0x20] = note; [rsp+0x28] = イベント語 [rbp+0x100]; [rsp+0x30] = [rbp+0xf8]
0x10007b7 call 0x10602e0                                                               ; イベント投入 (中身は未読 → §4)
0x10007bc mov rcx,[0x5e1845]; call 0x423980                                            ; lock 解放
0x10007c8 mov rax,[0x5e3a09]; add dword [rax], 1                                       ; カウンタ +1
```

### 3-5 note 単位の状態表 `item + note + 0x808`

- 条件 (`0x10007d2`〜`0x10007f6`): `dword [item+0x804] > 0` かつ `0 ≤ note ≤ 0x83` (符号付き)。
- `[item+0x804] > 1` (`0x1000812`〜`0x1000861`): velocity > 0 → `byte [item+note+0x808] = 0` (`0x1000829`)。velocity ≤ 0 → 0 でなければ `= 1` (`0x1000859`)。
- `[item+0x804] ≤ 1` (`0x1000866`〜`0x10008ce`): `byte [item+note+0x808] != 2` かつ velocity > 0 のとき自己再帰 `0x10002a0(item, note, 0x80000001, -1)` (`0x100089e`)。続けて `byte [item+note+0x808] = (velocity ≤ 0)` (`0x10008b4`)。

### 3-6 `0x63a730` の副作用: 無し

| 項目 | 内容 (VA) |
|---|---|
| 逆アセンブル | `0x63a730`〜`0x63a76e` (30 命令。`pe_disasm.py 63a730 30`) |
| 周波数の判定 | `0x63a734`: `cmp qword ptr [0x15f3308], 0`。0 なら `0x63a762` |
| 時計読み | `lea rcx,[rsp+0x28]`; `call 0x423ac0` (IAT = kernel32 `QueryPerformanceCounter`) |
| 戻り値 | 成功 → `xmm0 = (double)tick / (double)freq` (`0x63a74c`〜`0x63a760`)。失敗・周波数 0 → `xmm0 = 0.0` (`0x63a762`。`movsd xmm0,[rip+6]` = `0x63a770` の 8 byte 0) |
| 書込み | スタック `[rsp+0x28]` のみ。グローバル書込み 0 件 (`pe_xref.py 15f3308` の stores 0) |
| 周波数の由来 | `0x63ab43`: `lea rcx,[0x15f3308]` → `call 0x423ad0` (IAT = kernel32 `QueryPerformanceFrequency`)。初期化関数内 (入口は未特定) |

→ `0x63a730` は OS の高精度時計を読むだけ。wrapper 側の書込み値 (REPORT_PY73 §2) は時刻に依存する (コードからの推定。実機未確認)。

## 4. 未解決 (子 issue に移した範囲)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| §1-2 の書込み 18 件の到達条件 (呼出し元。C の `vt+0x60` は仮想呼出し元を含む)、flagB の `bl`・`cl` の値の由来 | 3 フラグの実行時値 (いつ 1 になるか) が決まらない | 子 issue (親 #2926) |
| note-off 側 (`0x1000614` 以降)・`0x1000c36`・`0x10602e0` の中身 (イベント投入先) | note-on/off の状態変化の全体と副作用が決まらない | 同上 |
| `T = [[G3]+8]` の実体 class (`V = 0x125b1c0` の一致は `V+0x88` の整合のみ) | 実体の同定には実行時値が要る | #2817 (親。本付録では扱わない) |

## 5. 受入条件 (#2926) の判定

- [x] flagA・flagB・flagC の書込み元 (命令 VA・書く値) を PE 解析箇所つきで確定し、本付録 §1 に残す。到達条件は子 issue へ移した
- [x] `0x10002a0` の note-on 経路 (書込み先・channel の扱い) と `0x63a730` の副作用を PE 解析箇所つきで残す (§3)。note-off 側と `0x10602e0` は子 issue へ移した
- [x] 推測の状態モデルでは実装しない (provider・mock は未実装)

## 6. 差分 0 の証跡

- 測定 commit `8665e7f47` から本付録の commit までの `git diff 8665e7f47 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本付録の commit 直前に確認)。
