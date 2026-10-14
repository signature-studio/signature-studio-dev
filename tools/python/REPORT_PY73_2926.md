# PY-110 解析記録 (#2926・WIP): midiNoteOn のゲートの 3 フラグ・note-on 経路・0x63a730 の PE 確定

注: WIP (PR なし)。ゲート式・vtable (§1) は PR #2931 (`2817-midinote-on-gate`、親 #2817 の付録 `REPORT_PY73_APPENDIX_2817.md`) と重複する。main へ取り込むときは #2931 の merge 後に重複を外す。`pe_slot_writers.py` は #2931 の版を使う (本ブランチの版は同内容の初版)。

親: #2817 (PY-93)。本 issue: #2926 (PY-110)。本体: `tools/python/REPORT_PY73.md` §2・§8-3 (未確定の列挙)。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルと参照列挙による解析)。
実装: 0 件 (`provider/`・`host/`・`tests/` は未変更。推測の状態モデルでは実装しない)。

## 結論

- **ゲート `0x1262a90`** (vtable `V = 0x125b1c0` の `+0x88`。親 #2817 の `[T.vptr+0x88]` と一致) の判定式は `!flagA && !flagB && !flagC`。flagC は `this` の仮想呼出し `[vptr+0x48]` (= `0x1262950`、flagC を `movzx` で返すだけ) 経由で読む。戻り `al = 1` の条件はこの式で確定した。
- **3 フラグの初期値は全て 0**。flagA・flagB は `.bss` (ロード時ゼロ)、flagC は `.data` の初期値 0。3 つの指し先ポインタ変数は `.data` の静的初期値で、実行中に書き換える RIP 相対 store は 0 件。
- **書込み元** (命令 VA) は flagA 4 箇所・flagB 12 箇所・flagC 2 箇所を §2 で列挙した。各書込みが実行される条件 (呼出し元・到達条件) は未確定 → 子 issue。
- **`0x10002a0` (midiNoteOn 本体) の note-on 経路**: note の bit31・velocity の符号・channel の扱い・note 単位の状態表 `item+0x808+note` への書込み・イベント投入 `0x10602e0` の呼出しを §3 で確定。note-off 側と `0x10602e0` の中身は未読 → 子 issue。
- **`0x63a730` の副作用は無し** (書込みはスタックのみ)。戻り値は `QueryPerformanceCounter` の値を `QueryPerformanceFrequency` の値で割った double (取得失敗・周波数 0 のときは 0.0)。したがって wrapper 側 (REPORT_PY73 §2) の書込み値は壁時計に依存する (§4)。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (実測 2.2 秒)。`toolchain-retdec` は本件では未使用。
- 測定 commit: `9f45af12` (`tools/python/analysis/flapi/pe_slot_writers.py` の追加。コードを変えた最後の commit)。以下の件数は全て `9f45af12` で再現した (初回の所要時間は同一コードの初回実行の実測。load average 0.4・並列 1)。
- 実行 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`):
  - `pe_slot_writers.py 15e04a8` (flagA のスロット): loads 54・書込み 4・slot_stores 0 (初回 67.4 秒)
  - `pe_slot_writers.py 15e0ff0` (flagB のスロット): loads 102・書込み 12・slot_stores 0 (初回 66.3 秒)
  - `pe_slot_writers.py 15e1890` (flagC のスロット): loads 58・書込み 2・slot_stores 0 (初回 66.5 秒)
  - ネガティブコントロール `pe_slot_writers.py 15e04a9` (1 バイトずらし): loads 0
  - `pe_xref.py 16baff0,16baff1,13e7628` (フラグ本体の RIP 直接参照): hits 0・stores 0 (49.0 秒)。全アクセスはスロット経由
  - `pe_xref.py 15e04a8,15e0ff0,15e1890` (スロット): hits 214・stores 0 (47.8 秒)
  - `pe_xref.py 15f3308` (QPC 周波数): hits 7 (読み 6・`lea` 1)・stores 0 (47.7 秒)
  - 逆アセンブル (`pe_disasm.py`): `1262900`・`1262a90`・`10002a0`・`100074c`・`63a730`・`423ac0`
- 注 (走査の限界): 既存の `pe_xref.py` は 64 KiB の chunk 境界で 1 命令を読み飛ばし得る (#2931 の未解決表に記載)。RIP 参照の件数 (hits 0・214・7) はこの影響を受け得る。スロットへの store 0 件は、境界処理のない `pe_slot_writers.py` の `slot_stores 0` と一致している。
- 検証範囲: 逆アセンブルと参照列挙のみ。wasm・mock・C provider の実行はしていない (コード差分 0)。範囲外の主張はしない。
- 差分 0 の証跡: `git diff 9f45af12 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR の後続 commit は docs のみ)。

## 1. ゲート `0x1262a90` と vtable

vtable 候補 `V = 0x125b1c0` の内容 (全て `.text` 内の関数ポインタ。`V+0x00`〜`V+0x98` を確認):

| slot | 関数 VA | 内容 (逆アセンブル) |
|---|---|---|
| `+0x48` | `0x1262950` | `mov rax,[slotC]; movzx rax, byte ptr [rax]; ret` = flagC の getter (this 未使用) |
| `+0x50` | `0x1262930` | `cmp byte ptr [rcx+0x50],0` → 非 0 なら 1、否なら flagC の値 (`obj.f50 || flagC`) |
| `+0x60` | `0x1262970` | `mov rax,[slotC]; mov byte ptr [rax],1; ret` = flagC を 1 にする |
| `+0x68` | `0x1262960` | `mov byte ptr [rcx+0x50],1; ret` |
| `+0x88` | `0x1262a90` | ゲート (下) |
| `+0x90` | `0x1262ad0` | ゲートと同形 (flagA・flagB・`[rbx+0x48]` の順) |
| `+0x80` | `0x1262b10` | flagA・flagB・`[rbx+0x48]` の後に別の判定 (`[G]+0x168`) を持つ。未読 |

ゲート `0x1262a90` (逆アセンブルの要約):

```
mov rax,[slotA]        ; rip+0x37da0c → VA 0x15e04a8
cmp byte ptr [rax],0 ; jne → 偽 (0)
mov rax,[slotB]        ; rip+0x37e548 → VA 0x15e0ff0
cmp byte ptr [rax],0 ; jne → 偽 (0)
mov rax,rcx ; mov rbx,[rcx] ; mov rcx,rax
call [rbx+0x48]        ; = 0x1262950 = flagC (slotC = VA 0x15e1890)
test al,al ; je → 真 (1)
```

→ `al = 1` ⇔ flagA = 0 ∧ flagB = 0 ∧ flagC = 0。偽のとき REPORT_PY73 §2 の内部 code `-2` (`Operation unsafe at current time`) になる。
- 同定の根拠: `V+0x88` が親の特定した `0x1262a90` と一致し、`V+0x48` (ゲートが呼ぶ getter) が flagC の getter である。`V` が `T` の vtable であることは、`T = [[G3]+8]` の実体が実行時値でないと確定しないため、未確定 (§5)。

## 2. 3 フラグの由来

### 2-1 指し先と初期値

| フラグ | スロット (`.data`) → 指し先 | 初期値 (実行時) | 根拠 |
|---|---|---|---|
| flagA | `0x15e04a8` → `0x16baff0` (`.bss`) | 0 | `.bss` はロード時ゼロ (ファイルにデータ無し) |
| flagB | `0x15e0ff0` → `0x16baff1` (`.bss`) | 0 | 同上 |
| flagC | `0x15e1890` → `0x13e7628` (`.data`) | 0 | ファイル上のバイト (file offset `0xfe6028`) = 0 |

- 3 スロットへの RIP 相対 store は 0 件 (`pe_xref.py` の stores 0)。スロットは静的初期値のまま。
- 3 フラグ本体への RIP 相対参照は 0 件。全アクセスはスロット経由 (間接)。

### 2-2 書込み元 (`pe_slot_writers.py`: スロットを読んだ後、数命令内で基底レジスタに対して書く命令)

flagA (スロット `0x15e04a8`・load 54・書込み 4):

| ロード VA | 書込み VA | 命令 | 書く値 |
|---|---|---|---|
| `0xc4de99` | `0xc4dea0` | `mov byte ptr [rax], 1` | 1 |
| `0xc4ea34` | `0xc4ea3b` | `mov byte ptr [rax], 0` | 0 |
| `0xd1a2a5` | `0xd1a2ac` | `mov byte ptr [rax], 1` | 1 |
| `0xd1cb12` | `0xd1cb19` | `mov byte ptr [rax], 0` | 0 |

flagB (スロット `0x15e0ff0`・load 102・書込み 12):

| ロード VA | 書込み VA | 命令 | 書く値 |
|---|---|---|---|
| `0xf46331` | `0xf46338` | `mov byte ptr [rax], 0` | 0 |
| `0xf520e4` | `0xf520eb` | `mov byte ptr [rax], 1` | 1 |
| `0xf53f19` | `0xf53f20` | `mov byte ptr [rax], 0` | 0 |
| `0xfefbcc` | `0xfefbd3` | `mov byte ptr [rax], 1` | 1 |
| `0xfefcd0` | `0xfefcd7` | `mov byte ptr [rax], 0` | 0 |
| `0xfff30a` | `0xfff311` | `mov byte ptr [rax], 1` | 1 |
| `0xfff3bc` | `0xfff3c3` | `mov byte ptr [rax], bl` | レジスタ値 (未読) |
| `0x1042e40` | `0x1042e47` | `mov byte ptr [rax], 1` | 1 |
| `0x10440a3` | `0x10440af` | `mov byte ptr [rax], cl` | レジスタ値 (未読) |
| `0x11d613e` | `0x11d6145` | `mov byte ptr [rax], 1` | 1 |
| `0x11d6309` | `0x11d6310` | `mov byte ptr [rax], 0` | 0 |
| `0x11d6318` | `0x11d631f` | `mov byte ptr [rax], 0` | 0 |

flagC (スロット `0x15e1890`・load 58・書込み 2):

| ロード VA | 書込み VA | 命令 | 書く値 | 備考 |
|---|---|---|---|---|
| `0x11c7615` | `0x11c761c` | `mov byte ptr [rax], 1` | 1 | 関数内 (直前に `call [rbx+0x58]`・`call 0x976f40`) |
| `0x1262970` | `0x1262977` | `mov byte ptr [rax], 1` | 1 | vtable `+0x60` 関数そのもの (呼出しは仮想呼出し) |

- 限界: スロット経由の書込みだけを列挙した。絶対アドレス指定と、関数引数で渡ったポインタ経由の書込みは見ていない。
- 書込み元の**到達条件** (どの呼出し経路で実行されるか) は未確定。flagA・flagB は書込み値が定数 0/1 で、flagB は `bl`・`cl` 由来の 2 箇所がある。

## 3. midiNoteOn 本体 `0x10002a0(item=rcx, note=edx, velocity=r8d, channel=r9d)`

フレーム: item `[rbp+0x140]`・note `[rbp+0x148]`・velocity `[rbp+0x150]`・channel `[rbp+0x158]` (`0x10002f2`〜`0x1000306` で退避)。

### 3-1 note の bit31 (`0x100032d`)

- 立つ側 (`0x1000334`〜`0x1000379`): `note &= 0x7fffffff`。velocity > 0 なら `[rbp+0xf9]` = velocity の下位 byte (`0x100035f`)、velocity ≤ 0 なら `[rbp+0x104]` = -velocity (`0x1000347`〜`0x100034f`)。`[rbp+0xfc]` = `(note >> 16) & 0xff` (`0x1000365`〜`0x1000373`)。`0x100050d` へ。
- 立たない側 (`0x100037e` 以降): 速度テーブルの要素 (基準 `[0x5e0413]`、velocity ≤ 0 で index 1、他は 0) を `[rbp+0xe8]` に置く。要素の count (`[elem+0]`) ≥ 1 のとき速度スケール計算を行い (`|velocity|` を 0x80 で clamp → テーブル係数 → `round`)、結果を velocity > 0 なら `byte [rbp+idx+0xf8]`、≤ 0 なら `[rbp+0x104]` に置く (`0x10004b6`〜`0x10004ef`)。count < 1 のときは計算をスキップ (`0x1000434`)。

### 3-2 velocity の符号

- `0x1000579`〜`0x10005f1` (前段): `byte [0x5df978] != 0` かつ velocity > 0 のとき、EnterCriticalSection (`0x4232e0`)、`0x11c9a70(cl=1)`、条件付きで `item.byte[+0x6ee] = 1` (`0x10005c0`)、`*[0x5e10ba] = *[0x5e08c3]` (`0x10005d8`)、LeaveCriticalSection (`0x423980`)。その後 `dword [0x5e394a] ≥ 0` なら `0x1000dd6` (終了)、そうでなければ `0x10005f7` へ続く。
- `0x10005f7`〜`0x1000601`: `byte [0x5e0b9a] == 0` なら `0x10007d2` (共通後段)。
- `byte [0x5e0b9a] != 0` のとき: velocity > 0 → `0x100074c` (note-on 本体、§3-4)、velocity ≤ 0 → `0x1000614` (note-off 側。未読、§5)。

### 3-3 channel の扱い

- 既定値: `[rbp+0xfc] = byte [[0x5e0ad4]+0x13] & 0xf` (`0x10004f5`〜`0x1000507`。グローバル由来)。bit31 立つ側は `(note >> 16) & 0xff` で置換される (§3-1)。
- 上書き (`0x100051f`〜`0x1000543`): `item.byte[+0x300] != 0` かつ channel (符号付き) ≥ 0 のとき `[rbp+0xfc] = channel`。それ以外は既定値のまま (channel = -1 は既定扱い)。
- イベント語 `[rbp+0x100]`: `([rbp+0x104] << 16) | 0x78` (`0x100050d`〜`0x1000519`)、続けて `| ([rbp+0xfc] << 24)` (`0x1000544`〜`0x100054d`)。つまり channel は語の上位 8 bit に入る。
- `note &= 0xff00ffff` (`0x1000553`): note の bit16〜23 は `[rbp+0xfc]` の算出後に落とす。`note` の bit30 が立つ側は bit30 を落として `0x1000c36` へ (未読)。

### 3-4 note-on 本体 (velocity > 0、`0x100074c`〜`0x10007cf`)

- tick: `[rbp+0x108] = round(double [*0x5e060d])` (`0x100074c`〜`0x100075c`)。
- EnterCriticalSection (`[0x5e189f]`)、`0x10602e0(rcx=[*0x5e1ba3], edx=tick, r8d=[item+0x9c]+0x4000, r9d=0x7ffffff0, [rsp+0x20]=note, [rsp+0x28]=イベント語 [rbp+0x100], [rsp+0x30]=[rbp+0xf8])` (`0x10007b7`)、LeaveCriticalSection (`[0x5e1845]`)。`0x10602e0` の中身は未読 (イベント投入先の候補)。
- `dword [*0x5e3a09] += 1` (`0x10007c8`〜`0x10007cf`)。

### 3-5 note 単位の状態表 `item + note + 0x808`

- 条件 (`0x10007d2`〜`0x10007f6`): `dword [item+0x804] > 0` かつ `0 ≤ note ≤ 0x83` (符号付き)。
- `[item+0x804] > 1` (`0x1000812`〜`0x1000861`): velocity > 0 → `byte [item+note+0x808] = 0` (`0x1000829`)、`0x10008d4` へ。velocity ≤ 0 → 既に 0 なら変更なし (`0x1000844`〜`0x100084c`)、0 でなければ `= 1` (`0x1000859`)、`0x1000dd6` へ。
- `[item+0x804] ≤ 1` (`0x1000866`〜`0x10008ce`): `byte [item+note+0x808] != 2` かつ velocity > 0 のとき自己再帰 `0x10002a0(item, note, 0x80000001, -1)` (`0x100089e`)。続けて `byte [item+note+0x808] = (velocity ≤ 0)` (`0x10008b4`)。velocity > 0 → `0x10008d4`。velocity ≤ 0 でも `== 0x80000001` なら `0x10008d4`、それ以外は `0x1000dd6`。

### 3-6 未読

`0x1000614` 以降 (note-off)・`0x1000c36` (bit30 経路)・`0x1000dd6` (終了処理)・`0x10602e0` (イベント投入先)・`0x11c9a70`・`0x92d090`・`0x1311d90`・`0xe5a350`・`0x12d16a0` (`byte [rax+0x54]` で分岐)。

## 4. `0x63a730` の副作用

| 項目 | 内容 (VA) |
|---|---|
| 周波数の判定 | `0x63a734`: `cmp qword ptr [0x15f3308], 0` |
| 時計読み | 周波数 ≠ 0 → `lea rcx,[rsp+0x28]`; `call 0x423ac0` (IAT `0x19716a8` = kernel32 `QueryPerformanceCounter`) (`0x63a73e`〜`0x63a743`) |
| 戻り値 | 成功 → `xmm0 = (double)tick / (double)freq` (`0x63a74c`〜`0x63a760`)。失敗または周波数 0 → `xmm0 = 0.0` (`0x63a762`、定数 `0x63a770` は 8 byte の 0) |
| 書込み | スタック `[rsp+0x28]` のみ。グローバル書込み 0 件 |
| 周波数の由来 | `0x63ab43`: `lea rcx,[0x15f3308]` → `call 0x423ad0` (IAT `0x19712d0` = kernel32 `QueryPerformanceFrequency`)。初期化関数内 (入口は未特定)。`pe_xref 15f3308` で store 0 件 |
| 呼出し元の副作用 | `0xd5c88b` 付近で `xmm0 × const` を `*(double*)(*[0x884601])` に書く (REPORT_PY73 §2 の読み。本 run では再検証していない) |

→ `0x63a730` の副作用は「OS の高精度時計を読む」だけ。wrapper 側の書込み値は時刻に依存する (コードからの推定。実機未確認)。

## 5. 未解決 (子 issue へ移した範囲)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| §2-2 の書込み箇所 (flagA 4・flagB 12・flagC 2) の到達条件 (呼出し元の列挙。flagC の `vt+0x60` は仮想呼出し元を含む) | 3 フラグの実行時値 (いつ 1 になるか) が決まらない | 子 issue (親 #2926) |
| note-off 側 (`0x1000614` 以降)・`0x1000c36`・`0x10602e0` (イベント投入先) | note-on/off の状態変化の全体と副作用が決まらない | 同上 |
| `0x11d1430` の `T = [[G3]+8]` の実体 class | `V = 0x125b1c0` が `T` の vtable と確定していない (`V+0x88` の整合のみで支持) | 同上 |
