# PY-283 付録 (#3649): 3 フラグ書込みの呼出し元・bl/cl の由来・note-off 側と `0x10602e0` (親 #2926)

親: #2926 (PY-110)。前段: `tools/python/REPORT_PY73_APPENDIX_2926.md` §1〜§4 (書込み 18 件の VA と値)・`REPORT_PY73_APPENDIX_2817.md` §5〜§6 (vtable 先 `0x1262a90`・ゲート式)。本体: `tools/python/REPORT_PY73.md` §2・§8-3。子: #3965 (PY-278)・#3966 (PY-279)。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルと直接 call の閉包)。
実装: 0 件 (`provider/`・`host/`・`tests/` は未変更)。製品 KPI: 対象外 (起動・GUI に関わらない解析)。

## 結論

- **bl (`0xfff3c3`) と cl (`0x10440af`) は、フラグ B 自身の旧値**。関数に入って flagB を 1 にする前に読んだ値を、関数の終わり近くで戻す (save/restore)。定数ではない (§2)。
- **書込み 18 件の所属関数と直接呼出し元を全件列挙した** (§1)。flagC の `0x1262977` は vt+0x60 (`V = 0x125b1c0` の +0x60 の格納値 `0x1262970` で確認) で、直接呼出し元は 0 件。`call qword ptr [reg+0x60]` の間接 call は 517 箇所あり、個々の特定は子へ。
- **書込み関数 12 件のどれも、直接 call だけでは midiNoteOn ハンドラ `0xd5c800` に到達しない** (深さ 60 まで 0/12)。ゲート (`0xd5c858`) より前に書込みが実行されるかは、この経路では決まらない (§3)。
- note-off 側 (`0x1000614`〜`0x1000747`) と `0x1000c36`・`0x10602e0` は一部のみ読了 (§4)。残りは子。
- 探索器の対照 (正 4・負 1・変更 3) を §7 に数値で残した。既知の直接経路は見つかり、1 件足すと 0/12 が 1/12 に変わるので、0/12 は探索器の見落としとは言えない。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 22,227,016 B。実測 2.9 秒)。`toolchain-retdec` は未使用。
- 測定 commit: `c7bbcc03a` (間接 call の数え方を直し、対照スクリプトを加えた commit。コードを変えた最後の commit)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_flag_scope_check.py`。実測 37.8 秒・37.6 秒 (real, n=2)・開始時 load 0.16・0.76・並列 1。出力 44 行。2 回の出力はバイト単位で一致。§1・§3 の数値はこの出力から転記した。
- 対照: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_flag_scope_negctl.py` (実測 38.5 秒・load 0.16・並列 1)。§7。
- 逆アセンブル・命令列の確認: `analysis/flapi/pe_disasm.py` と `pe_callgraph.py` (`load`・`walk` は新スクリプトから再利用)。間接 call の数と §2-2 の呼出し先は `objdump -d -M intel` でも検算した。
- 差分 0 の証跡: §6。
- 検証範囲: 逆アセンブル・直接 call の閉包・vtable 格納値の読取りだけ。wasm・mock の実行は未実施。

## 1. 書込み 18 件の所属関数と直接呼出し元

所属関数は int3 パディング直後を先頭とみなす (`pe_callgraph.function_starts`)。直接呼出し元は、所属関数の先頭 VA への E8 (直接 call)。直接 jmp (末尾呼出し) は 12 関数のいずれにも 0 件。

| flag | 書込み VA | 値 | 所属関数 | 直接呼出し元 (件数・箇所) | 所見 |
|---|---|---|---|---|---|
| A | `0xc4dea0` | 1 | `0xc4dba0` | 1: `0xc4f32e` (in `0xc4ecf0`) | set。`0xc4ecf0` の set 側の呼出し。`0xc4dba0` は note-on 本体 `0x10002a0` を直接 call (`0xc4e438`・`0xc4e479`) |
| A | `0xc4ea3b` | 0 | `0xc4e570` | 1: `0xc4f35b` (in `0xc4ecf0`) | clear。`0xc4ecf0` の clear 側 |
| A | `0xd1a2ac` | 1 | `0xd17fd0` | 6: `0xd1896a`・`0xd18ba9`・`0xd18c81`・`0xd18fb9` 他 2 | set。同関数に clear なし |
| A | `0xd1cb19` | 0 | `0xd1af20` | 0 | clear。直接 call は 0 件。ただし `lea` で callback 構造体に格納される (訂正: #3965 付録 §2) |
| B | `0xf46338` | 0 | `0xf46310` | 4: `0xf53d09`・`0xf53d7d`・`0xf53dca`・`0xf53e75` (全て in `0xf51fd0`) | clear のみ |
| B | `0xf520eb` | 1 | `0xf51fd0` | 4: `0xf547f3`・`0x10055ec`・`0x125946c`・`0x1319d61` | set。同関数の `0xf53f20` で clear |
| B | `0xf53f20` | 0 | `0xf51fd0` | 4 (同上) | clear |
| B | `0xfefbd3` | 1 | `0xfefba0` | 15 | set。同関数の `0xfefcd7` で clear |
| B | `0xfefcd7` | 0 | `0xfefba0` | 15 (同上) | clear |
| B | `0xfff311` | 1 | `0xfff070` | 0 | set (§2-1)。関数ポインタ表の要素 (§1-2) |
| B | `0xfff3c3` | bl | `0xfff070` | 0 | 旧値へ復元 (§2-1) |
| B | `0x1042e47` | 1 | `0x1042d20` | 54 | set (§2-2) |
| B | `0x10440af` | cl | `0x1042d20` | 54 (同上) | 旧値へ復元 (§2-2) |
| B | `0x11d6145` | 1 | `0x11d55c0` | 2: `0xf480c3` (in `0xf46490`)・`0x11d64c1` (同関数内・自己再帰) | set。同関数の `0x11d6310`・`0x11d631f` で clear |
| B | `0x11d6310` | 0 | `0x11d55c0` | 2 (同上) | clear |
| B | `0x11d631f` | 0 | `0x11d55c0` | 2 (同上) | clear |
| C | `0x11c761c` | 1 | `0x11c71b0` | 1: `0x11c88d3` (in `0x11c8870`) | set。C への 0 の書込みは無い |
| C | `0x1262977` | 1 | `0x1262970` | 0 | vt+0x60 の関数 (§1-1)。`[reg+0x60]` の間接 call 517 箇所 |

### 1-1 vtable・関数ポインタ格納の確認

- `V = 0x125b1c0` の格納値 (ファイル上): +0x48 = `0x1262950` (flagC の読出し)・+0x60 = `0x1262970` (flagC の set)・+0x88 = `0x1262a90` (ゲート)・+0x90 = `0x1262ad0`。`0x1262970` を 8 byte 境界で格納する箇所は `0x125b220` (= V+0x60) のみ。
- 間接 call の数 (`.text` 全体): `call qword ptr [reg+0x60]` 517 箇所、`[reg+0x88]` 333 箇所。far call (`call FWORD PTR [reg+0x60]`・FF /3) の 2 件 (`0x5a5d95`・`0x6e561e`) は数えない。objdump (`call QWORD PTR [..+0x60]` 517・`[..+0x88]` 333) でも一致。
- `[reg+0x60]` のうち、どのオブジェクトの vtable 経由かは未特定 (子 #3965 (PY-278))。

### 1-2 関数ポインタ表 (`0xfff070`)

- `0xfff070` を 8 byte 境界で格納する箇所は `0xfe2e48` のみ。この箇所は `.text` 内の関数ポインタ表 (`0xfe2c80`〜`0xfe2ea0`、69 要素) の 57 番目。
- 表の範囲 (格納値が `.text` 内の VA の連続で判定) を指す RIP 相対参照は 0 件、絶対アドレスでの参照も 0 件 (分岐先を除く)。表を使う呼出しの元は静的には追えなかった (子 #3965 (PY-278))。
- `0xd1af20` は直接呼出し・末尾 jmp が 0 件。関数ポインタ格納は 0 件ではない (訂正: `lea` で `0xd16123`・`0xd16163` の callback 構造体に格納される。#3965 付録 §2)。

## 2. bl・cl の由来 (確定)

### 2-1 bl (`0xfff3c3`) = flagB の旧値 (関数 `0xfff070`)

```
0xfff2c7  je 0xfff2f3                      ; call 0x65e3c0 の戻り eax == 0 の経路 (set に入る)
0xfff2ff  mov rax, [rip+0x5e1cea]         ; slot 0x15e0ff0 (→ flagB 0x16baff1)
0xfff306  movzx rbx, byte ptr [rax]       ; rbx = flagB の旧値
0xfff30a  mov rax, [rip+0x5e1cdf]         ; slot 0x15e0ff0
0xfff311  mov byte ptr [rax], 1           ; flagB = 1 (set)
          ... call qword ptr [rsi+0x168] / [rsi+0x190] 等 (rbx は callee-saved)
0xfff3bc  mov rax, [rip+0x5e1c2d]         ; slot 0x15e0ff0
0xfff3c3  mov byte ptr [rax], bl          ; flagB = 旧値 (復元)
```

- `0xfff311`〜`0xfff3c3` の間に ret・関数外への分岐は無い (内部の `je 0xfff33e`・`jmp 0xfff357` のみ。`pe_flag_scope_check` と逆アセンブルで確認)。
- rbx は 0xfff306 から 0xfff3c3 まで書き換えられない (間の call は callee-saved に依存。Win64 ABI に従う前提)。

### 2-2 cl (`0x10440af`) = flagB の旧値 (関数 `0x1042d20` の局所 `[rbp+0x47]`)

```
0x1042e32  mov rax, [rip+0x59e1b7]       ; slot 0x15e0ff0
0x1042e39  movzx rax, byte ptr [rax]     ; flagB の旧値
0x1042e3d  mov byte ptr [rbp+0x47], al   ; 局所に保存
0x1042e40  mov rax, [rip+0x59e1a9]
0x1042e47  mov byte ptr [rax], 1         ; flagB = 1 (set)
          ... (0x1042e4a〜0x10440a3 の間の呼出し)
0x10440a3  mov rax, [rip+0x59cf46]      ; slot 0x15e0ff0
0x10440aa  movzx rcx, byte ptr [rbp+0x47]
0x10440af  mov byte ptr [rax], cl        ; flagB = 旧値 (復元)
```

- `[rbp+0x47]` を読み書きする箇所は 0x1042e3d (保存) と 0x10440aa (復元) の 2 箇所のみ。`lea` でその領域を指す命令、0x40〜0x47 を指すポインタを渡す call は関数内に 0 件。
- `rbp` 自身を `rcx` に入れて call する箇所は関数内に 5 件 (`mov rcx,rbp` の直後 6 命令以内に call がある件数。objdump の検算で、0x1042eaa・0x1043223・0x1043346・0x10433ac・0x104340b)。5 件の呼出し先はすべて `0x1042d00` で、その本体 (`push rbp` から `ret` まで 10 命令) は `mov ecx,[rcx+0xf8]` と `[rax+rdx*8]` の読取りだけで、書込み命令は無い (`objdump -d -M intel --start-address=0x1042d00`)。`rbp` を他の引数レジスタに入れて渡す call と、残りの callee が `[rbp+0x47]` を書かないことは未確認。
- 0x1042e32〜0x10440b1 の区間で、区間外へ出る分岐・ret は 0 件 (内部分岐だけ)。

両関数とも、flagB は「関数の動的範囲の中だけ 1」になり、関数を抜けると入った時点の値に戻る (復元は ret より前。§2-1・§2-2 の区間)。ゲート `0x1262a90` の flagB 判定が -2 を返すのは、その範囲の中で midiNoteOn のゲートが評価されたときだけ、という点は 2817 付録からの推論で、本付録では検証していない。

## 3. ゲート前後と閉包 (未確定。子 #3965 (PY-278))

### 3-1 ハンドラ `0xd5c800` の直接 call

| 箇所 | 区分 | 呼出し先 |
|---|---|---|
| `0xd5c858` | ゲート (最初の call) | `0x11d1430` (→ vt+0x88 = `0x1262a90`) |
| `0xd5c88b` | 後段 | `0x63a730` |
| `0xd5c8b0` | 後段 | `0xfe8bb0` |
| `0xd5c8c3` | 後段 | `0x10002a0` (note-on 本体) |
| `0xd5c8d5` | 後段 | `0xd82c20` |

ゲートより前に直接 call は無い。

### 3-2 書込み関数から midiNoteOn への到達

- 書込み関数 12 件のどれも、直接 call で前進して `0xd5c800` に至らない (深さ 60。`pe_flag_scope_check` 出力)。
- `0x11d1430` の直接呼出し元 22 件のうちハンドラ内は `0xd5c858` の 1 件のみ。`0x11d1430` 自体はゲート判定を持つ関数で、midiNoteOn 以外の呼出しもある。
- `0x10002a0` (note-on 本体) の直接呼出し元は 18 件。ゲート判定 (`0xd5c858`) を含むのはハンドラ `0xd5c800` からの `0xd5c8c3` の 1 件だけで、残り 17 件はゲート判定を含まない関数からの呼出し (うち `0x100089e` は自己再帰)。その 17 件の中に `0xc4dba0` (flagA を 1 にする関数) からの 2 件 (`0xc4e438`・`0xc4e479`) がある。

ハンドラの入口は Python 側のメソッド表から間接的に呼ばれるため、ホストからの呼出しと書込み関数の動的範囲の入れ子は、直接 call の閉包では決まらない。

### 3-3 静的に確定した寿命 (フラグごと)

- **flagC**: 静的に見える書込みは全て 1 (`0x11c761c`・`0x1262977`)。0 を書く箇所は無い。したがって、静的に見える範囲では一度 1 になると 0 に戻らない (ラッチの候補。0 を書く間接経路の有無は未確定)。
- **flagA**: set は 2 件 (`0xc4dea0` = `0xc4dba0` 内、`0xd1a2ac` = `0xd17fd0` 内)。clear も 2 件 (`0xc4ea3b` = `0xc4e570` 内、`0xd1cb19` = `0xd1af20` 内)。`0xc4ecf0` の中で、set (`0xc4f32e` の呼出し → `0xc4dba0`) と clear (`0xc4f35b` の呼出し → `0xc4e570`) が対。その間に `0xc4f333`〜`0xc4f34e` の loop (`0xc51f80` 等の呼出し)。一方 `0xd17fd0` (呼出し元 6) は 1 を書くだけで、同関数に clear は無い。`0xd17fd0` の後に走るのが `0xc4e570` (`0xc4ecf0` の `0xc4f35b` からだけ直接 call される) か `0xd1af20` (静的な呼出し経路が 0 件) かは未確定。したがって `0xd17fd0` の後に flagA が 0 へ戻る経路の有無は未確定 (子 #3965 (PY-278) の範囲)。
- **flagB**: 同一関数内で set と clear が対になるもの (`0xf51fd0`・`0xfefba0`・`0x11d55c0`)、clear のみ (`0xf46310`)、save/restore (`0xfff070`・`0x1042d20`)。

## 4. note-off 側と `0x1000c36`・`0x10602e0` (一部確定。残りは子 #3966 (PY-279))

### 4-1 note-off 側 (`0x10002a0` 内・`0x1000614`〜`0x1000747`)

- `0x1000614`: `[0x5e3bbd] > 0` のとき `[0x5e3bb1]` を 1 減らし、`[0x5e3ba7] == 0` なら `call 0x1180d40(ecx=1, edx=0)` (未読)。
- `0x1000642`: `[0x5e3b8f] != 0` なら `0x10007d2` (共通後段。イベントは書かない)。
- `0x1000652`〜`0x1000668`: tick = round(double `[0x5e0707]`) (`call 0x40c660`)。`EnterCriticalSection([0x5e1999])` (`call 0x4232e0`)。
- `0x1000676`〜`0x1000731` (ループ): n = `[[0x5e1c9b]+0x14]`。i = 0 から n−1 まで `obj = call 0x12df530([*0x5e1c74], i)`。`0x12df530` は `[rcx+8] + i*[rcx+0x10]` の要素アドレス計算だけ (副作用なし)。
  - `dword [obj+8] == 0x7ffffff0` の要素だけを更新する (`0x10006c0`)。tick > `[obj]` なら `[obj+8] = tick − [obj]`。tick ≤ `[obj]` なら `[obj+8] = [obj] − tick` かつ `[obj] = tick` (`0x10006d8`〜`0x10006fe`)。その後 `byte [obj+0x12] = byte [rbp+0x104]` (= −velocity) (`0x1000714`〜`0x100071c`)。
  - 注: この経路に note 値の照合は無い (`[obj+8]` の値だけで対象を選ぶ)。照合の有無は他経路を読んでいないため未確定。
- `0x1000732`: `LeaveCriticalSection([0x5e18cf])` (`call 0x423980`)。`0x1000742`: `call 0x12cab20(cl=0, dl=0)` (未読)。`0x1000747`: `jmp 0x10007d2`。
- この経路は `0x10602e0` を呼ばない。この経路で直接書くグローバルは `[0x5e3bb1]` (デクリメント) だけで、ほかはループ内の `obj` の要素。`0x1180d40`・`0x12cab20` の中の書込みは未読。

### 4-2 `0x1000c36` (分岐後の振り分け)

- `0x1000c09` の `je 0x1000c23` の経路: `call qword ptr [rbx+8]` (`*[0x5e400e]`) の後に `0x1000c36`。
- `0x1000c36`: `cmp dword [rbp+0x150], 0` (velocity の符号)。
  - velocity ≤ 0: `0x1000c57` `call 0xff50c0` (r8d = `[rbp+0x104]` = −velocity、r9d = −1)、`jmp 0x1000c8a`。
  - velocity > 0: `0x1000c5e`〜`0x1000c80` で引数を積んで `0x1000c85` `call 0xff4e10` (r8d = `[rbp+0xf8]`、`[rsp+0x20]` = channel `[rbp+0xfc]`、`[rsp+0x28]` = 0、r9d = −1)、`0x1000c8a`。
- 呼出し先 `0xff50c0`・`0xff4e10` の中身は未読 (子 #3966 (PY-279))。

### 4-3 `0x10602e0` (イベント投入)

- 呼出し前 (`0x1000762`〜`0x10007b7`): `EnterCriticalSection([0x5e189f])` (`call 0x4232e0`)。rcx = `*[0x5e1ba3]` (queue オブジェクト)、edx = tick、r8d = `[item+0x9c]+0x4000`、r9d = 0x7ffffff0、`[rsp+0x20]` = note、`[rsp+0x28]` = イベント語 `[rbp+0x100]`、`[rsp+0x30]` = `[rbp+0xf8]`。
- `0x10602e0` 本体 (`0x10602e0`〜`0x106033d`): 6 個の push と `sub rsp,0x48` の後、スタック上の record (`rbp+0x28` 起点) に引数を格納する。tick → +0、r8d → +4、r9d → +8、note (word) → +0xc、イベント語 → +0x10、velocity (dword) → +0x14。
  - 格納前に `call qword ptr [r14+0x10]` (queue の vt+0x10、引数 `&rec`) を呼ぶ (`0x1060304`)。格納後に `call qword ptr [rax+8]` (vt+8、引数 `&rec`) を呼ぶ (`0x106033a`)。
  - グローバルへの書込みは 0 件 (スタック上の record のみ)。副作用は 2 つの仮想呼出し先に移る。queue オブジェクトの class (vtable) は未確定のため、vt+0x10・vt+8 の中身は未読 (子 #3966 (PY-279))。
- 直接呼出し元 12 件: `0xdd1460`・`0xe1ee27`・`0xeb41ef`・`0x10007b7`・`0x1000aa6`・`0x1000b88`・`0x1000fd4`・`0x10014cf`・`0x108a1ef`・`0x12caa58`・`0x1319c5b`・`0x1319e48`。`0x10002a0` 内は 3 件 (`0x10007b7` は note-on、`0x1000aa6`・`0x1000b88` は未読)。

## 5. 受入条件 (#3649) の判定 (縮小後)

親 issue の受入条件のうち、本付録で完了した範囲:

- [x] bl・cl の値の由来を PE 解析箇所つきで §2 に残した (旧値の save/restore)
- [x] 書込み 18 件の所属関数・直接呼出し元を全件列挙し、vtable 先 (V+0x60) と関数ポインタ表 (`0xfe2c80`) の所在を §1 に残した
- [x] 推測の状態モデルでは実装しない (`provider/`・`host/`・`tests/` は未変更)

子 issue に移した範囲 (本文から外した):

- ゲート (`0xd5c858`) より前に書込みが実行されるかと、間接呼出し元 (§3)・flagA の clear 2 件の実行順 (§3-3) → 子 #3965 (PY-278)
- note-off 側 (`0x1000614` 以降)・`0x1000c36` の呼出し先・`0x10602e0` の仮想呼出し先と副作用 (§4) → 子 #3966 (PY-279)

## 6. 差分 0 の証跡

- 測定 commit `c7bbcc03a` から本付録の commit までの `git diff c7bbcc03a HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本付録の commit 直前に確認)。
- 測定 commit の直前 (`68d3da528`・main 取り込み) から測定 commit までの差分は、`pe_flag_scope_check.py` (間接 call の regex 2 行と docstring 1 行) と `pe_flag_scope_negctl.py` (新規) だけ。

## 7. 対照 (正の対照・負の対照・1 件変更)

再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flag_scope_negctl.py` (測定 commit `c7bbcc03a`・実測 38.5 秒・load 0.16・並列 1)。

| 対照 | 期待 | 実測 |
|---|---|---|
| 正: `0xc4dba0` → `0x10002a0` | 経路あり (深さ 1) | depth 1: `0xc4dba0 -> 0x10002a0` |
| 正: `0xc4ecf0` → `0x10002a0` | 経路あり (深さ 2) | depth 2: `0xc4ecf0 -> 0xc4dba0 -> 0x10002a0` |
| 正: `0xd5c800` → `0x10002a0` | 経路あり (深さ 1) | depth 1: `0xd5c800 -> 0x10002a0` |
| 正: `0xd5c800` → `0x63a730` | 経路あり (深さ 1) | depth 1: `0xd5c800 -> 0x63a730` |
| 負: `0xc4dba0` → `0xd5c800` | 経路なし | no path |
| 基準 | 到達 0/12・`mov byte ptr` 18/18 | 到達 0 of 12・18 of 18 |
| 変更 1: 0xc4f32e の直接 call (`0xc4ecf0` → `0xc4dba0`) を 1 件外す | `0xc4ecf0` → `0x10002a0` が消える | no path |
| 変更 2: `0xc4dba0` → `0xd5c800` の直接 call を 1 件足す | 到達 0/12 → 1/12 | 1 of 12 |
| 変更 3: 書込み VA `0xd1a2ac` を +1 にずらす | `mov byte ptr` 18/18 → 17/18 | 17 of 18 |

- 書込み 18 件の列挙は #2926 付録の表が入力で、本スクリプトはその VA を読む。変更 3 の `mov byte ptr` 検査は「VA が byte 書込み命令の先頭か」だけを確かめる。書込みの値 (0/1・bl/cl) は §1・§2 の逆アセンブルで確認した。
- 対照は、同じ逆アセンブル結果の上で、呼出し辞書を複製して 1 件だけ変えて走らせた (PE ファイルは変更しない)。

## 8. `0x12cab20` の間接 call 閉包と書込み先 (#5765・PY-5386・部分)

再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_closure_writes_5386.py 0x12cab20 3` (測定 commit `948c60093`。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`)。

### 8-1 解決方法 (決定)

- 間接 call は**静的に解決しない**。閉包は直接 call (E8) だけで辿り、間接 call の箇所は未解決の枝として数えて列挙する。
- 理由: 閉包内の間接 call 139 件のうち `mem` (`call qword ptr [...]`) は 138 件、`reg` は 1 件 (`0x12dfa06` の `call rsi`)。`mem` のうち `[rip+disp]` は 9 件 (例: `0x40941e`・`0x411e47`)、残りは `[reg+disp]` (仮想呼出し)。`[reg+disp]` の呼出し先は受け手オブジェクトの class (vtable) で決まり、PE だけでは確定しない。`[rip+disp]` の 9 件は PE 内の初期値しか読めず、実行時の登録先は未確定。
- よって閉包の書込み集合は**下限**であり、「閉包の副作用の完全列挙」とは書かない。

### 8-2 閉包の実測 (`pe_closure_writes_5386.py`)

| 項目 | 実測 |
|---|---|
| 閉包関数数 (深さ ≤ 3) | 155 (親 #5049 の `pe_callgraph.py fwd` と一致) |
| 間接 call 箇所 | 139 (`mem` 138・`reg` 1。親の計測と一致) |
| 閉包内の `[rip+disp]` 書込み (誤逆アセンブル 2 件を除く) | 21 |
| 閉包内の `[rbp/rsp+disp]` 書込み (関数ローカル) | 724 (副作用ではない) |
| 閉包内の `[reg+disp]` 書込み (先が静的に未確定) | 547 |

- 誤逆アセンブル 2 件 (`0x104cf5f`・`0x12cb4a2`) は、`ret` の後の 0 埋め領域を命令として読んだもの。`0x12cb4a2` の書込み先 `0x12cb7ab` は `.text` 内。両方を除外した。
- 実行: 測定 commit `948c60093`・実測 83.4 秒・real・user 82.4 秒 (load 0.52・並列 1)。コード差分 0 の証跡は §6 と同じ手順 (`git diff 948c60093 HEAD -- tools/python/analysis` の出力は 0 行)。

### 8-3 `[rip+disp]` 書込み 21 件 (閉包内)

`0x12cab20` 自身が書く 9 件 (親 #5049 のコメントの 9 件と一致):

| 書込み先 VA | 書込み箇所 (所属関数 `0x12cab20`) | 命令 |
|---|---|---|
| `0x15d4f28` | `0x12cb16d` | `mov byte ptr [rip+0x309db4], 1` |
| `0x15d4f29` | `0x12cb234` | `mov qword ptr [rip+0x309cee], rax` |
| `0x15d4f31` | `0x12cab74` | `mov byte ptr [rip+0x30a3b6], 0` |
| `0x15d4f31` | `0x12cac71` | `mov byte ptr [rip+0x30a2b9], 1` |
| `0x15d4f34` | `0x12cac7e` | `mov dword ptr [rip+0x30a2b0], eax` |
| `0x193fc68` | `0x12cb1ea` | `mov dword ptr [rip+0x674a74], 0xffffffff` |
| `0x193fc6c` | `0x12cb1f4` | `mov dword ptr [rip+0x674a6e], 0x80000001` |
| `0x193fc88` | `0x12cab4a` | `mov byte ptr [rip+0x675137], 1` |
| `0x193fc88` | `0x12cb259` | `mov byte ptr [rip+0x674a28], 0` |

閉包内の子 (`0x12cb2e0`・`0x12de9d0`・`0x12de9e0`・`0x12dfa30`・`0x12e2ff0`・`0x412a60`・`0x11d54f0`) が書く 12 件:

| 書込み先 VA | 書込み箇所 (所属関数) |
|---|---|
| `0x15d4f31` | `0x12cb2f3` (`0x12cb2e0`) |
| `0x193fc88` | `0x12cb491` (`0x12cb2e0`) |
| `0x13a5008` | `0x412a6c` (`0x412a60`) |
| `0x16bc9f4` | `0x11d54fc` (`0x11d54f0`) |
| `0x196eb20`・`0x196eb24` | `0x12de9d0` (`0x12de9d0` 内の `0x12de9d0`・`0x12de9d6` の 2 箇所) |
| `0x196eb28`・`0x196eb2c` | `0x12de9e0`・`0x12de9e6` (`0x12de9e0`) |
| `0x196eb40` | `0x12dfa38` (`0x12dfa30`) |
| `0x196eb70`・`0x196eb78`・`0x196eb80` | `0x12e3011`・`0x12e3034`・`0x12e3055` (`0x12e2ff0`) |

### 8-4 受入条件 (#5765) の判定

- [x] 間接 call の解決方法を決めた (§8-1: 静的に解決せず、未解決の枝として列挙)
- [ ] 閉包内の書込み先を全件列挙する → **未達**。`[rip+disp]` の 21 件は列挙したが、`[reg+disp]` の 547 件は書込み先が静的に未確定。間接 call 139 件の先も未確定のため、閉包の下限しか示していない

### 8-5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call 139 件 (`mem` 138・`reg` 1) の呼出し先 | 閉包の書込み集合が下限 | #5765 (継続) |
| `[reg+disp]` 書込み 547 件 (閉包全体) の書込み先 | 同上。`0x12cab20` 自身の `[reg+disp]` 書込みは未分類 | #5765 (継続) |
