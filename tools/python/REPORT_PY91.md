# PY-91 (#2809): playlist 操作コア・helper の作用を逆アセンブルで確定 (#2026 の残り)

親: #2026 (PY-61)。前段: `tools/python/REPORT_PY61.md` (引数・戻り値の型・範囲 code は確定済み)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- **inc 系 4 件の作用を確定**: `incLivePosSnap`・`incLiveTrigSnap`・`incLiveLoopMode`・`incLiveTrigMode` は、track 要素の 4 フィールドを `(現値 + value + 7) % 7` または `(現値 + value + 4) % 4` で更新する (C の `%` 規則)。対応する `getLive*` が同じフィールドを読む (§1・§2)。
- **getLive 系の状態 helper 5 件と `getLiveBlockColor` の helper (`0x100c030`) を確定**: 状態は 3 bit のマスク。`getLiveBlockStatus` の mode 0/1/2 と `getLiveStatus` の mode 0/1 で、マスクから状態への写像が異なる (§3)。写像の値が表す状態名 (LB_Status の値の意味) は未確定 (§10)。
- **選択・solo の呼び出し先**: `0x12e83a0` の mode 0〜10、`0x12e8760` (選択 index の一覧)、`isTrackSelected` の helper `0xd56990` (一覧への包含判定)、solo 判定 `0x12e68a0` と範囲 `0x12e8210` を確定。`0x12e7f80`・`0xbd68e0` は一部推定 (§4)。
- **書式文字列 5 件を回収**: `getLiveBlockStatus`='ii\|i'・`getLiveStatus`='i\|i'・`liveDisplayZone`='iiii\|i'・`soloTrack`='i\|ii'・`triggerLiveClip`='ii\|id' (§5)。
- **未確定 (子 #2906・#2908・#2909 へ移した)**: `lockDisplayZone`・`liveDisplayZone`・`triggerLiveClip`・`refreshLiveClips` のコア本体 (zone の vtable と trigger の後半)、時間 ↔ block 変換の定数、`0x12e7f80`・`0xbd68e0` の副作用、例外型 `[[[rip+0x85e38a]]]` の型名 (静的には特定不可、§7)。
- 実装は行わない (確定のみ)。`provider/`・`host/`・`tests/` は変更しない。

## 1. 操作系コア 8 件

各コアは job 構造体 (rbx) を受ける。引数は `[rbx+0x18]`〜`[rbx+0x38]`、status は `[rbx+0x60]`。準備判定は `call [rax+0x98]` (0xd56fe4 ほか)。偽なら status は -2 のまま。

| 関数 | コア VA | 作用 (確定した範囲) | 根拠 VA | 未確定 |
|---|---|---|---|---|
| lockDisplayZone | 0xd56fc0 | 準備真なら status=0 (0xd56fee)。zone = `[[rbx+8]+0x50]` (0xd56ffa)。NULL なら -7 (0xd5701d)。非 NULL なら `zone->vtbl[+0x148](rdx=index=[rbx+0x18], r8=([rbx+0x20]≠0))` (0xd57012〜0xd57015) | 0xd56fe4・0xd56fee・0xd56ffa・0xd5701d・0xd57015 | `[+0x148]` の実体 (zone の型が未確定) → #2906 |
| liveDisplayZone | 0xd57150 | 準備真で status=0 (0xd57183)。zone = `[[rbx+8]+0x50]` (0xd5718f)、NULL は -7 (0xd571c5)。`0x420980(&rect, [rbx+0x18], [rbx+0x20], [rbx+0x28], [rbx+0x30])` で rect を作り (0xd571ae)、`0xd84f70(zone, &rect, [rbx+0x38]=duration)` (0xd571be) | 0xd571ae・0xd571be。0x420980 は out[0],out[4],out[8],out[0xc] に 4 引数を書く。0xd84f70 は 0xfdc630 へ転送 (0xd84f70〜0xd84f7d) | 0xfdc630 内の `zone->vtbl[+0x80]` 準備判定 (0xfdc66b)・`e5abd0(g, zone, rect)` (0xfdc685)・`0x420b00(rect)` の意味、`zone+0x58 ← duration ÷ *[g]` (0xfdc696〜0xfdc6a6) の単位、遅延実行 0x737020 → #2906 |
| triggerLiveClip | 0xd577e0 | 準備真で `0x1221bc0(ecx=[rbx+0x18] index, edx=[rbx+0x20] subNum, r8d=[rbx+0x28] flags, xmm3=(f32)*[rbx+0x30] velocity)` (0xd57821)、status=0 (0xd57826)。velocity は wrapper が double で受け (書式 'd')、既定値 -1.0 | 0xd57821・0xd57826。コア本体は §1-1 | 0x1221bc0 の後半 (§1-1) → #2906 |
| refreshLiveClips | 0xd579d0 | 準備真で `0x1222b90()` (0xd579fe)、status=0 (0xd57a03) | 0x1222b90 = `0x1221bc0(-1, 0, 0x30000, -1.0f)` (0x1222b94〜0x1222ba7) | K=3 経路の意味 (推定: 全 track のリセット) → #2906 |
| incLivePosSnap | 0xd57af0 | 準備真で `S = 0x12e1a20()[index*0x114 + 0x24]` (0xd57b1e〜0xd57b2b)、`0x100bad0(S, value=[rbx+0x20])` (0xd57b33)、status=0 | 0xd57b33 | — (§2 で確定) |
| incLiveTrigSnap | 0xd57c70 | 同形。`0x100ba70(S, value)` (0xd57cb3) | 0xd57cb3 | — |
| incLiveLoopMode | 0xd57df0 | 同形。`0x100b9c0(S, value)` (0xd57e33) | 0xd57e33 | — |
| incLiveTrigMode | 0xd57f70 | 同形。`0x100ba20(S, value)` (0xd57fb3) | 0xd57fb3 | — |

`S` は track 要素 (0x114 B) の +0x24 にある block 配列のサブオブジェクト (`imul rcx,0x45` 後の `lea rcx,[rax+rcx*4+0x24]`)。`0x12e1a20()` は track 表の先頭 (REPORT_PY61 §4-1 と同じ)。

### 1-1 triggerLiveClip のコア `0x1221bc0` (確定した分岐のみ)

- 早期 return: `byte [*(g)] ≠ 0` なら 0x1222b5c (0x1221be5〜0x1221bef)。
- 引数の格納: ecx→`[rbp+0x58]` (index)、edx→`[rbp+0x8c]` (subNum)、r8d→`[rbp+0x38]` (flags)、xmm3→`[rbp+0xf8]` (velocity f32) (0x1221bd0〜0x1221bdd)。
- 範囲: `index < 0` は全 track (start=1)。`index ≥ 0` かつ flags bit31=0 は単一 track (start=end=index, 0x1221c25〜0x1221d1b)。bit31=1 は `0x12e8210` でグループ範囲に絞る (0x1221cb6)。終端 E は `flags & 0x30000 ≠ 0` で 0x1f3 (=499)、それ以外は `*[g]` (0x1221c3e〜0x1221c4f)。
- フィールド (flags):
  - M = `(flags>>8)&3` (0x1221bfe)。bit0 は `S+0xa0 < 0` で status=-2 (0x122221f〜0x1222231)、bit1 は `S+0x20 ≠ [rbp+0x60]` で -2 (0x1222233〜0x1222243)。
  - K = `(flags>>16)&7` (0x1221c1b)。書込み先は下表。
  - bit5 (0x20): 真なら `S+0xd0/+0xd4` の更新を抑止 (0x12222b1・0x1222360・0x12223c5・0x122247f)。
  - bit7 (0x80): start=end かつ K≤1 のとき再帰 (0x1222113〜0x122218a)。再帰時 velocity=-1.0f (0x1222b70)。
  - bit0 (0x1): `[rbp+0x57]` に保存 (0x1221d21)。bit1 (0x2): 真かつ `*[g] ≥ 1` で `0x1311f70(20.0)` → 0x40c660 → 0x4232e0 (0x1222745〜0x1222799)。bit2 (0x4): 真なら `0xd2a550(index)` の戻り値を採用 (0x1222858)。bit3〜4: `(flags>>3)&3` を `S+0xa8` へ (0x1221d52〜0x1221d58)。
- K ごとの書込み (範囲ループ内):
  - K=0: `S+0xa0 ← (subNum<0 ? -1 : subNum<<16)`、`S+0xa8 ← M3` (0x1221d77〜0x1221ddd)。
  - K=1〜3: `S+0xa0`・`S+0xa4 ← -1`、`S+0xa8 ← M3`。K=2 のみ index 自身を除外 (0x1221e2e〜0x1221e95)。
  - K≥4: `S+0xa8` のみ (0x1221dea〜0x1222028)。
- velocity 適用: `byte [0x1222265]` の bit K が立ち、かつ `S+0xa0 ≥ 0` のとき (0x1222254〜0x122227e)。velocity ≥ 0 は `count` (該当 block の要素数 = `qword[ptr-8]`) を掛けて `0x63a690` で整数化し [0, count-1] に丸めて `S+0xa0` へ加算 (推定)。velocity < 0 は `S+0xd4` が同じ block なら `(sub+1)%count` を `S+0xa0` へ加算 (推定) (0x12222a0〜0x12223b9)。
- **未読**: 0x1222805〜0x1222b5c の全 track ループの大部分。`S+0xa0`・`S+0xa8` の意味、bit 0/1/2/3-4/5/7 の名前 (推定に留まる) → #2906。

## 2. inc 系 helper の更新式 (4 件・確定)

S は §1 の `S` (track+0x24)。各 helper は更新の前後に `0x4232e0`・`0x423980` を呼ぶ (global を渡す。排他の可能性は未確定)。

| helper | 更新するフィールド | 更新式 (C の `%`) | 対応する getter (読むフィールド) | 根拠 VA |
|---|---|---|---|---|
| 0x100b9c0 (incLiveLoopMode) | `S+0x1c` = elem+0x40 | `(f + v + 7) % 7` | getLiveLoopMode (+0x40) | 0x100b9c0 の `mov ecx,[rbx+0x1c]`・`add ecx,esi`・`add ecx,7`・magic 0x92492493 (÷7)・`mov [rbx+0x1c],r8d` |
| 0x100ba20 (incLiveTrigMode) | `S+0x20` = elem+0x44 | `(f + v + 4) % 4` (`and eax,0x80000003` の符号処理で C の `%` と一致) | getLiveTriggerMode (+0x44) | 0x100ba20 の `mov eax,[rbx+0x20]`・`add eax,esi`・`add eax,4`・`and eax,0x80000003` |
| 0x100ba70 (incLiveTrigSnap) | `S+0x24` = elem+0x48 | `(f + v + 7) % 7` | getLiveTrigSnap (+0x48) | 0x100ba70 の `mov ecx,[rbx+0x24]`・`add ecx,esi`・`add ecx,7` |
| 0x100bad0 (incLivePosSnap) | `S+0x30` = elem+0x54 | `(f + v + 7) % 7` | getLivePosSnap (+0x54) | 0x100bad0 の `mov ecx,[rbx+0x30]`・`add ecx,esi`・`add ecx,7` |

- `f` は現値、`v` は呼出し引数 (value)。`+7`/`+4` は負の v を非負にするためのオフセット (推定)。除算は符号付きで、結果は被除数と同じ符号 (C の `%` 規則)。`0x100b9c0`・`0x100ba70`・`0x100bad0` は magic `0x92492493` の符号付き除算 (`sar`・符号の補正 `shr 0x1f`)、`0x100ba20` は `and 0x80000003` と負の補正で処理する。X = f+v+7 が負になるのは `v ≤ -(f+8)` (`v = -(f+7)` では X=0 で結果は 0)。X = f+v+4 が負になるのは `v ≤ -(f+5)`。wrapper の値域検査は未確認。
- 4 つの inc と 4 つの getter は同じフィールドを対象とする (elem+0x40/+0x44/+0x48/+0x54 の対応は REPORT_PY61 §2-1 の表と一致)。

## 3. getLive 系の状態 helper (5 件 + getLiveBlockColor・写像と分岐は確定、状態名は未確定)

- 共通の入力: `S` (track+0x24)。`S+0xf8` は block 配列 (要素は 8 B のポインタ、件数は `qword[ptr-8]`)。`S+0xd2`・`S+0xda` は符号付き 16 bit の block 番号。`S+0xd0`・`S+0xd8` は dword。
- `0x100bb30(S, key)`: `key<0` は 0。`outer = key>>16` が件数以上なら 0。`inner = key & 0xffff` が `vec[outer]` の件数未満なら `&vec[outer][inner]` (要素 0x58 B、0x100bb30 の `imul rcx,0xb`・`lea rax,[rax+rcx*8]`)、それ以外は 0。
- マスク (0..7):
  - `m_blk(S,b) = [b < 件数 ∧ vec[b] ≠ 0] + 2·[b == w(S+0xd2)] + 4·[b == w(S+0xda)]` (0x100beb0)。件数との比較は符号付き (`cmp r8,rax; jge`) で、`0 ≤ b` の検査は無い (下の注意)。`w(·)` は符号付き 16 bit。
  - `m_obj(S) = [S+0xf8 ≠ 0] + 2·[d(S+0xd0) ≥ 0] + 4·[d(S+0xd8) ≥ 0]` (0x100c0f0)。
- 写像表 (8 entry の dword、VA はそれぞれ `lea` の rip 先):

| 表 | VA | m=0..7 の値 | 使う helper |
|---|---|---|---|
| tbl1 | 0x1545394 | 0,1,3,3,2,2,2,2 | 0x100bf10 `m_blk` → tbl1 |
| tbl2 | 0x15453b4 | 0,1,2,2,2,2,2,2 | 0x100bfa0 `m_blk` → tbl2 |
| tbl3 | 0x15453d4 | 0,2,0,1,0,3,0,1 | 0x100c130 `m_obj` → tbl3 |

- 表から読める規則 (節は上から順に判定。8 件すべてと一致。`playlist_core_facts.py` の (6) で検算): tbl1 は「bit2 → 2、bit1 → 3、bit0 → 1、他 0」。tbl2 は「bit1 または bit2 → 2、bit0 → 1、他 0」。tbl3 は「bit0 = 0 (vec=0) → 0、bit0 かつ bit1 (d0≥0) → 1、bit0 かつ bit2 かつ ¬bit1 (d0<0 かつ d8≥0) → 3、bit0 のみ (d0<0 かつ d8<0) → 2」。enum の名前 (LB_Status の値の意味) は未確定 (§10)。
- 生マスク版: `0x100beb0` (m_blk)、`0x100c0f0` (m_obj) は表を通さず m を返す。

wrapper の mode 分岐 (既定 mode = 0):

| wrapper | mode 0 | mode 1 | mode 2 | 他 |
|---|---|---|---|---|
| getLiveBlockStatus 0xd57550 | 0x100beb0 (生マスク、0xd575d5) | 0x100bf10 (tbl1、0xd575fc) | 0x100bfa0 (tbl2、0xd57623) | -4 (0xd5764a) |
| getLiveStatus 0xd57670 | 0x100c0f0 (生マスク、0xd576d9) | 0x100c130 (tbl3、0xd576fd) | — | -4 (0xd57721) |

- getLiveBlockColor 0x100c030 (S, b): `0x100bb30(S, b<<16)` (= `vec[b][0]`) が非 0 なら、`theme = *(*(g)+0xd2c)` の `vtbl[+0x218](theme, clip)` の u32 を返す (0x100c045〜0x100c062)。0 なら `S+8` の dword (= elem+0x2c、track 色) を返す (0x100c035・0x100c06a)。theme の型は未確定。
- **注意 (観測)**: `0x100beb0`・`0x100bf10`・`0x100bfa0` は `movsxd r8,edx; cmp r8,rax; jge` の符号付き比較のみで、b<0 を弾かない。wrapper の blockNum 検査も見当たらない (0xd575e7 で `edx=[rbp+0x48]` を直接渡す)。したがって b<0 は `vec + b*8` の範囲外を読む (未実行。再現は未確認)。この懸念は親 #2809 へのコメントで提案する (§10)。

## 4. 他の helper と呼び出し先

| 関数 | 確定した作用 | 根拠 VA | 未確定 |
|---|---|---|---|
| 0xd56990 (isTrackSelected の helper, index) | `0x12e8760(0x12e1a20(), &vec)` で選択 index の一覧を作り (0xd569a9〜0xd569b5)、要素と index を比較して一致なら al=1 (0xd569e3)。一覧の件数は `qword[ptr-8]` | 0xd569a9・0xd569b5・0xd569e3 | — |
| 0xd85210 (zone → int) | `return dword [zone+0xa0]` (zone の現在値)。getDisplayZone (0xd56f80) が使う | 0xd85210〜0xd85216 | zone+0xa0 の意味 (表示 zone 番号と推定) |
| 0x12e8760 (選択 index の一覧) | `k = 1..500` (ループ 0x12e878f〜0x12e87ec) のうち `byte(k,+0xe5) ≠ 0` を昇順に動的配列へ追加 (追加位置 0x12e87e0、長さの拡張 `0x417fc0` は推定)。`0x418210` で out へ代入して返す | 0x12e8779〜0x12e8814 | — |
| 0x12e8210 (範囲) | flag=0 は `[index,index]`。flag≠0 は `+0x3e` の連結 (group) を `[1..500]` の範囲で広げる | 0x12e8216〜0x12e8258 | `+0x3e` の意味 (group の連結と推定) |
| 0x12e68a0 (solo 判定、戻り al) | `F = solo(index)≠0 ∧ [∀k∈[1..500]∖[first..last]: solo(k)=0 ∨ byte(k,+0xd5)≠0]`。`solo(k)=byte[base+k*0x114+0x3c]` | 0x12e68e3〜0x12e694a | `+0xd5` の意味 |
| 0x12e83a0 (select の mode) | §4-1 の表 | 0x12e83a5〜0x12e8449 (dispatch) | — (mode 5・7〜10 の本体は §4-1 で VA 付きに確認) |
| 0x12e7f80 (solo 設定) | F=偽: `+0x3c ← [first≤k≤last]` (k: `+0xd5=0` または k=index)、`+0xd4 ← [k=index]`。F=真: `+0x3c ← ebx ∣ (cfg+0x49e≠0 ? byte(k,+0xd6) : 1)` | 0x12e7fa4・0x12e8058〜0x12e8063・0x12e80d7〜0x12e80e8 | cfg・`+0xd4`・`+0xd6` の意味 (推定のみ) |
| 0xbd68e0 (引数 0x26, 0) | `flag[0x26]≠0` なら flag を 0 にして `0x666780(obj,0,0x26,0)` を発火 (保留通知のフラッシュと推定) | 0xbd68ee〜0xbd691d | 0x666780 の中身、flag の立て元 |
| 0x526190 (job 実行) | 同じ実行コンテキストなら `[rbx]` を同期で直接呼ぶ。違えばキューに載せる (0x525f3d〜0x525f7d)。別スレッドは起こさない | 0x5261cb〜0x5261dc・0x525f3d〜0x525f7d | キュー経路 (0x525faf 以降) |

### 4-1 select の mode (0x12e83a0、dispatch は本作業で確認)

| mode | 作用 | 本体の入口 VA |
|---|---|---|
| 0 | `S(idx)=1` (加算) | 0x12e844e |
| 1 | 排他: 全 k で `S(k) = (k==idx)`、続けて `0x12e3a60(base, idx)` | 0x12e8462 (後処理 0x12e8487) |
| 2 | トグル `S(idx) = !S(idx)` | 0x12e8491 |
| 3 | `S(idx)=0` (解除) | 0x12e84b6 |
| 4 | 全選択 `S(1..500)=1` | 0x12e84ca |
| 5 | k=1..500 の全てが選択済み、または `S(idx)=0` なら排他 (`S(k)=(k==idx)` のループ、0x12e852e〜0x12e8553)。それ以外 (未全選択かつ `S(idx)≠0`) は `S(1..500)=1` (0x12e8558)。排他側は `0x12e3a60` を呼ばない (mode 1 との違い) | 0x12e84ee |
| 6 | 全解除 `S(1..500)=0` | 0x12e857c |
| 7 | f = 最小の選択 (無ければ 1)。`mode 1` を `max(f-1,1)` で再帰 (`call 0x12e83a0`、r8b=1) | 0x12e85ef |
| 8 | f = 最小の選択 (無ければ 1)。`mode 1` を `min(f+1,500)` で再帰 | 0x12e85a0 |
| 9 | f = 最小の選択 (無ければ 1)。f>1 なら `S(f-1)=1` (加算) | 0x12e8681 |
| 10 | l = 最大の選択 (無ければ 1)。l<500 なら `S(l+1)=1` (加算)。選択が無いときは `S(2)=1` | 0x12e863c |
| 他 | 通知のみ (0x12e86c3) | 0x12e83d6・0x12e83f5 ほか |

- mode 5〜10 の本体は、dispatch (`0x12e83a0`: `cmp r8d,5`/`je 0x12e84ee`、`cmp r8d,8`/`je 0x12e85a0`、`sub r8d,9` の順の分岐) の先として、`pe_disasm.py` で VA を読み直して確認した (本作業の逆アセンブル)。

- `S(k)` は `byte(k, +0xe5)` (選択フラグ)。`0x12e8760` が `+0xe5 ≠ 0` を選択とみなす (§4) から確定。
- 呼出し側 (`0xd56ab0`、selectTrack)。value が -1 なら mode 2 (0xd56b02〜0xd56b10)。それ以外は `al` (value の下位 1 B) で分岐: `al ≠ 0` は mode 0 (0xd56b17〜0xd56b29)、`al = 0` は mode 3 (0xd56b30〜0xd56b3e)。REPORT_PY61 §3 の記述と一致。
- selectAll は mode 4、deselectAll は mode 6 (REPORT_PY61 §3 のまま)。

## 5. 書式文字列 (5 件を回収)

| 関数 | wrapper VA | 書式 (VA) | 引数 |
|---|---|---|---|
| getLiveBlockStatus | 0xd57550 | `'ii\|i'` (0xd57660) | index, blockNum, mode (既定 0) |
| getLiveStatus | 0xd57670 | `'i\|i'` (0xd57738) | index, mode (既定 0) |
| liveDisplayZone | 0xd57200 | `'iiii\|i'` (0xd57364) | left, top, right, bottom, duration (既定 0) |
| soloTrack | 0xd56830 | `'i\|ii'` (0xd56984) | index, value (既定 -1), inGroup (既定 0) |
| triggerLiveClip | 0xd57860 | `'ii\|id'` (0xd579c4) | index, subNum, flags, velocity (double、既定 -1.0) |

- 書式は `PyArg_ParseTupleAndKeywords` の `r8` の `lea` 先 (wrapper の書式引数)。値は `playlist_core_facts.py` の (4) で再現する。
- `getLiveBlockColor` の書式 `'ii'` (0xd577d8) も併せて確認。

## 6. -4 ↔ RANGE

REPORT_PY61 §4-2 のまま変更なし (文言対応・数値非対応)。今回の作業で新たに判明したのは、mode の範囲外 (getLiveBlockStatus・getLiveStatus) が index の範囲外と同じ sink 0xd5764a / 0xd57721 (`rax=-4`、`0xd82c20` を呼ぶ) に入ること。

## 7. 例外型 `[[[rip+0x85e38a]]]` (0xd82daf) の調査

- 呼出し列: `rcx = *(*(0x15e1140))` (0xd82daf〜0xd82db9)、`rdx = c_str (rax)`、`rbx = *(0x15e49b8)`、`call [rbx]` (0xd82dbf〜0xd82dc6)。`[rbx]` は例外投入 (PyErr_SetString 相当と推定)。
- 参照チェーン: `0x15e1140` (.data) の中身は `0x16b8488` (.bss。ファイルに実体が無い)。その先は実行時に入る値で、静的には型のオブジェクトに到達しない。
- 文字列の確認: `IndexError` はバイナリに 2 箇所 (file offset 362602・362637、VA 0x45946a 付近)。どちらも Delphi の `EVariantBadIndexError` の一部で、`System.Variants` の文字列と並ぶ。Python の例外名ではない。
- import 表: 24 DLL、`PyExc_*` の名前は無い。Python の API は実行時に読み込む方式と推定。
- 参照の確認 (`pe_rip_refs.py 0x15e1140`): 7 件の読込みのみ。`rip` 相対の直接書込みは 0 件。
- **結論**: 型の名前は静的には確定できない。実行時の値 (`PyExc_IndexError` 等の実体) の確認が要る → #2909 (fl-win64 での実行確認)。

## 8. 変更範囲

- 追加: `tools/python/analysis/flapi/playlist_core_facts.py` (本作業の事実抽出)、本 REPORT、`docs/DOC_MAP.md` の索引行。
- 変更なし: `tools/python/analysis/flapi/` の既存スクリプト、`provider/`、`host/`、`tests/`。

## 9. 検証

- 素材: `fl-win64`。`mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'`。実測 real 2.888 s (user 3.991 s / sys 1.527 s)。
- 再現 (1 コマンド): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_core_facts.py`。実測 real 0.08〜0.09 s (n=3、user 0.06〜0.07 s / sys 0.01〜0.02 s)。実行直前の load average `0.01 0.11 0.07` (`/proc/loadavg`)、並列 1。
- 測定 commit (コードを最後に変えた commit): `8979e2a5` (`fix(flapi): add write-table rule check and negative control`)。以後の差分: `git diff 8979e2a5 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (この commit より後の変更は REPORT と DOC_MAP だけ)。
- 既存の再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_undecided_facts.py` (real 0.09 s ×3、`fmt=` を含む行 26 件、REPORT_PY61 と同じ集合)。
- 検算 (別アルゴリズム・`playlist_core_facts.py` の (6)): §3 の規則 (節は優先順) を表の 8 件 × 3 表に当てた不一致は 0 件 (`mismatch=0`)。ネガティブコントロール (1 節を外したときの不一致件数): tbl1 は bit2 節 4 件・bit1 節 2 件・bit0 節 1 件、tbl2 は (bit1 または bit2) 節 6 件・bit0 節 1 件、tbl3 は (bit0∧bit1) 節 2 件・(bit0∧bit2∧¬bit1) 節 1 件・(bit0∧¬bit1∧¬bit2) 節 1 件。すべての節が不一致を生むので、規則の節は冗長でない。
- §4-1 の mode 5〜10 の本体 (`0x12e84ee`・`0x12e85ef`・`0x12e85a0`・`0x12e8681`・`0x12e863c`) と `0x12e83a0` の dispatch、`0x12e8760` のループ、`0xd56ab0` の al 分岐 (value=-1 で mode 2、al≠0 で mode 0、al=0 で mode 3) は、`pe_disasm.py` で VA を読み直して表どおりを確認した (再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py 12e83a0 60`、同様に `12e84ee 40`・`12e85ef 60`・`12e85a0 24`・`12e8760 52`・`d56ab0 40`)。
- 範囲外: 実行による検証 (fl-win64 の起動・ランタイム値) は行わない。`0x1221bc0` の後半、zone の vtable、`0x12e7f80` の cfg は未読。

## 10. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lockDisplayZone の `zone->vtbl[+0x148]`、liveDisplayZone の `zone->vtbl[+0x80]`・`e5abd0`・`0x420b00`・`0x737020`、`zone+0x58` の単位 | zone 系の C 実装の中身 | #2906 (PY-104) |
| triggerLiveClip のコア `0x1221bc0` の後半 (0x1222805〜0x1222b5c)、flags の bit 0/1/2/3-4/5/7 の意味、refreshLiveClips の K=3 の作用 | triggerLiveClip・refreshLiveClips の C 実装 | #2906 (PY-104) |
| `0x1221b30`・`0x1221aa0` の定数 (分母・乗数 `*[g]`)、`0x442c00`、`0x12e1a20()+0x21c48` の表 | 時間 ↔ block 番号の変換式 | #2908 (PY-105) |
| `0x12e7f80` の cfg (+0x49e)・`+0xd4`・`+0xd6`、`0x12e3a60`、`0xbd68e0` の `0x666780` | solo 設定・select mode 1 の副作用 | #2908 (PY-105) |
| 例外型 `[[[rip+0x85e38a]]]` の型名 (RANGE → IndexError の割当) | `RANGE` の割当の確認 | #2909 (PY-106) |
| 負の blockNum で `0x100beb0`・`0x100bf10`・`0x100bfa0` が範囲外読みをする (§3 の注意) | 不正入力での OOB 読み (未実行) | 親 #2809 へのコメントで提案 |
| getLive 系の写像の値 (0〜3) が表す状態名 (LB_Status の値の意味)。§3 の表は数値だけ | 状態名つきの仕様記述 | 親 #2809 へのコメントで提案 |
| getLiveBlockColor の色オブジェクト (`*(g)+0xd2c`) の型と `vtbl[+0x218]` | 色の出所の確認 | #2908 (PY-105) |
| `0x4232e0`・`0x423980` (inc 系の前後) の意味 | 排他か通知か未確定 | #2908 (PY-105) |
