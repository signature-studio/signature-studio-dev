# PY-105 (#2908): 時間変換・solo/select の副作用・inc 系前後処理・色の出所を逆アセンブルで確定 (#2809 の残り)

親: #2809 (PY-91)。前段: `tools/python/REPORT_PY91.md` (PR #2912 で main 取り込み済み)。既知類型との関係: 該当なし (lift 作業ではない)。
確定の表記: **確定** = 逆アセンブルの事実だけで言える。**推定** = 呼出し先の名前や意図からの読み。**未確定** = 静的には決まらない (実行時値・vtable の実体)。

## 結論

- **時間 ↔ block 変換 (確定)**: `liveTimeToBlockNum` (0x1221b30)・`liveBlockNumToTime` (0x1221aa0) は、track 表 `+0x21c48` の動的配列 (record 13 dword = 0x34 B、先頭 dword が時刻キー) と、2 つの global (`D` = 0x15d8914 の dword = 384、`L` = 0x196eca0 の dword・実行時値) で変換する。`D` は既定の block 長 (ticks) と読める。
- **0x442c00 は『現在時刻 (ローカル) の時刻部分』を返す関数 (確定)**: `GetLocalTime` (kernel32) の結果の時・分・秒・ms を 0x442670 (EncodeTime 相当・推定) で double にする。`liveBlockNumToTime` はこの値を `L` と比べる (wall clock 依存の分岐)。
- **inc 系 4 件の前後処理 (確定)**: `0x4232e0` は `EnterCriticalSection`、`0x423980` は `LeaveCriticalSection` (kernel32)。4 件とも先頭で Enter、`ret` 前で Leave する。排他は確定。
- **select mode 5・7〜10 (確定・再確認)**: REPORT_PY91 §4-1 の読みを disassembly で再確認し、5 件とも一致した (§4)。
- **未確定**: `0x12e7f80` の `+0xd4`・`+0xd6`・cfg `+0x49e` の完全な意味 (§5)、`0x12e3a60` の通知先の名前 (§6)、`0x666780` のキュー名 (§7)、`getLiveBlockColor` の theme object の型 (§8)。

## 1. 時間 ↔ block 変換 (0x1221b30・0x1221aa0)

定数と参照先 (`playlist_time_facts.py` (1)・(3)):

| 名前 | 参照 | 指す先 | 値 |
|---|---|---|---|
| `D` (block 長・割る数・掛ける数) | 0x1221b6d・0x1221ad2 | 0x15d8914 (.data) | 384 (ファイル内の初期値。実行時に書き換わるかは未確認) |
| `L` (時刻の上限・比較値) | 0x1221b3b・0x1221b60・0x1221ac5・0x1221b01 | 0x196eca0 (.bss) | 実行時値 (静的には未確定) |
| 表 `T` | `0x12e1a20()` の `+0x21c48` | 動的配列 (count = `qword[ptr-8]`) | record = 13 dword (0x34 B)、key = `record[0]` |

`liveTimeToBlockNum(t)` (0x1221b30) の流れ (確定):
1. `t < 0` または `t ≥ L` → -1 (0x1221b39・0x1221b42・0x1221b46)。
2. `T` が空、または `T[0].key ≥ L` → `t / D` (符号付き idiv・切り捨て) (0x1221b6d〜0x1221b79)。
3. それ以外: `k = max{ i : T[i].key < t }` (厳密な `<`)。`k` は `count-1` で頭打ち。見つからないときは -1 (0x1221b80〜0x1221bac)。

`liveBlockNumToTime(b)` (0x1221aa0) の流れ (確定):
1. `b < 0` → -1 (0x1221aa7〜0x1221aae)。
2. `T` が空、または `T[0].key ≥ L` → `b × D` (0x1221ad2〜0x1221ad9)。
3. `b ≥ count` → -1 (0x1221aed〜0x1221af0)。
4. `key = T[b].key`。`xmm0 = 0x442c00()` (§2) を `(double)L` と比べ、`xmm0 < L` なら `key`、そうでなければ -1 (0x1221b01〜0x1221b12)。

**注意 (確定)**: 手順 4 は wall clock の時刻部分 (0 以上 1 未満の小数) と `L` を比べる。`L ≥ 1` なら常に真で key を返す。`L ≤ 0` なら常に -1。`L` の実行時値は静的に決まらない (§10)。

## 2. 0x442c00 (確定)

- `0x442c00`: `call 0x423550` (→ `kernel32.dll!GetLocalTime`、IAT 0x1971730 を確認)。出力 `SYSTEMTIME` の wHour・wMinute・wSecond・wMilliseconds (offset 8・10・12・14) を読み、`0x442670` へ渡して double を返す。
- `0x442670` (推定: EncodeTime 相当): 0x442420 の戻りと、定数 60000 (0xea60)・60 (0x3c) を使う `0x438730` の組み合わせで時刻を double にする。`0x4425f0` の戻りが偽なら `0x438750` (推定: 例外送出)。
- 結論: `0x442c00` は『現在のローカル時刻の時刻部分』。引数は取らない。

## 3. inc 系の排他 (確定)

| helper | 先頭 Enter (0x4232e0) | ret 前 Leave (0x423980) | 更新式 (REPORT_PY91 §2) |
|---|---|---|---|
| 0x100b9c0 (incLiveLoopMode) | 1 | 1 | `(f+v+7) % 7` |
| 0x100ba20 (incLiveTrigMode) | 1 | 1 | `(f+v+4) % 4` |
| 0x100ba70 (incLiveTrigSnap) | 1 | 1 | `(f+v+7) % 7` |
| 0x100bad0 (incLivePosSnap) | 1 | 1 | `(f+v+7) % 7` |

`0x4232e0` と `0x423980` は `jmp [IAT]` の thunk で、IAT の名前は kernel32 の `EnterCriticalSection`・`LeaveCriticalSection` (確定)。どの critical section (rip 先の global) かは各 helper の `mov rcx, [rip+X]` の X で決まる (0x100b9c0 は X = 0x5d836e 側)。4 件の X が同一かは未確認 (§10)。

## 4. select の mode 5・7〜10 (確定・再確認)

`0x12e83a0` の dispatch は REPORT_PY91 §4-1 のとおり (5 は `cmp r8d,5; je 0x12e84ee`。6・7・8 は `0x12e8400` で `je 0x12e857c`・`jmp 0x12e85ef`・`je 0x12e85a0`、9 以降は `0x12e842f`)。本体を読み直した結果:

| mode | 本体 | 読み (確定) | 0x12e3a60 を呼ぶか |
|---|---|---|---|
| 5 | 0x12e84ee | `r8b` = 「全 k (1..500) が選択済み」。不成立かつ `S(idx)≠0` なら `S(1..500)=1`、それ以外は排他 `S(k)=(k==idx)` (0x12e852e〜0x12e8553) | なし |
| 7 | 0x12e85ef | `f` = 最初の選択 (無ければ 1)。`mode 1` を `max(f-1,1)` で再帰 (0x12e862d〜0x12e8632) | mode 1 の中で呼ぶ |
| 8 | 0x12e85a0 | `f` = 最初の選択 (break あり・0x12e85be の jmp)。`mode 1` を `min(f+1,500)` で再帰 (0x12e85d0〜0x12e85e5) | mode 1 の中で呼ぶ |
| 9 | 0x12e8681 | `f` = 最初の選択 (0x12e869f の jmp で break)。`f>1` なら `S(f-1)=1` (加算) (0x12e86ac〜0x12e86bb) | なし |
| 10 | 0x12e863c | `l` = 最後の選択 (break なし・0x12e8658 は上書き)。`l<500` なら `S(l+1)=1`。選択が無ければ `S(2)=1` (0x12e8665〜0x12e8677) | なし |

**REPORT_PY91 §4-1 の修正点は無い** (5 件とも表と一致)。mode 5〜10 の本体の終端は 0x12e86c3 (通知。`[g]+0x830` の vtbl `+0x178` 呼出し・確定)。

## 5. 0x12e7f80 の cfg・+0xd4・+0xd6 (一部確定・一部推定)

- `cfg = *( *(slot 0x2f930c の指す先) + 0xd98 )` (0x12e80a5〜0x12e80af)、`byte [cfg+0x49e]` を読む (0x12e80b6)。**cfg+0x49e** は bool (確定)。意味は未確定。
- `+0xd4` (track element の byte): 1〜500 のうち `+0xd4 ≠ 0` の最初の track を『anchor』とする (0x12e7fb1〜0x12e7fd2、r13 = anchor の値)。F (`0x12e68a0`) が偽のとき、anchor 側で `+0xd4 ← (k == index)` (0x12e8068〜0x12e8083) (確定)。意味は『直前に操作した track の印』と推定。
- `+0xd6`: F=真のとき `+0x3c ← bl | (cfg+0x49e ≠ 0 ? +0xd6 : 1)` (0x12e80d7〜0x12e80e8・確定)。F=偽・anchor 無しのとき `+0xd6 ← +0x3c` (0x12e8001〜0x12e8019・確定)。したがって `+0xd6` は『solo 状態の退避先』と推定 (推定)。
- 区間: `0x12e8210(base, index, flag, &first, &last)` で範囲を得る (0x12e7fe9)。`0x12e8210` の中身は REPORT_PY91 §4 のとおり。

## 6. 0x12e3a60 (select mode 1 の後処理) (確定・名前は推定)

`0x12e3a60(base, index)`:
- track の `+0xd8` が 3 の場合: `src = +0xe0` (dword)。`0 ≤ src ≤ dword[*(g)+0x10] - 1` のとき、`0x11e84a0(src)` と `0xfe8bb0(src)` を呼び、戻り object の `+0x258` (dword) を `id` とする。`byte [*(g)+0xa9] ≠ 0` かつ `1 ≤ id ≤ 500` なら `0x128f9e0(*g, id, byte [rip+0x73])` (0x12e3ae2〜0x12e3b2e)。
- `+0xd8` が 1 の場合: `byte [*(g)+0xa9] ≠ 0` かつ `1 ≤ +0xdc ≤ 500` なら `0x128f9e0(*g, +0xdc, byte [rip+0xe])` (0x12e3b41〜0x12e3b8e)。
- 確定は『UI 側への 1 件通知 (0x128f9e0)』まで。`0x128f9e0` の名前と引数の `r8b` の意味は未確定 (§10)。

## 7. 0xbd68e0 と 0x666780 (一部確定)

- `0xbd68e0(k, v)`: `flag[k] ≠ 0` なら `flag[k] ← 0` にして `0x666780(*G, 0, k, v)` を呼ぶ (0xbd68e4〜0xbd691d・確定)。`flag` は `0xae04de` の byte 配列。REPORT_PY91 の『保留通知のフラッシュ』は、この形から推定。
- `0x666780(obj, a, b, c)`: `0x666680(obj)` を呼ぶ。`0x666680` は `EnterCriticalSection(obj+0x38)` (0x666688) の後、`[[obj+0x18]+8] ≠ [obj+0x10]` なら その値を返す (Leave しない・0x66669d)。等しいときは `0x666470` を呼び、偽なら `LeaveCriticalSection` して 0 を返し、真なら `[[obj+0x18]+8]` を返す (0x6666a8〜0x6666c4・確定)。戻りが非 0 なら、その要素の +0x10・+0x18・+0x20 に `a`・`b`・`c` を書く (0x6667a6〜0x6667ae・確定)。
- 結論: `0x666780` は『排他下の通知キューへの 1 件投入』(推定)。キューの名前と、`k=0x26` (38) の意味は未確定 (§10)。

## 8. getLiveBlockColor の色の出所 (確定・型は未確定)

`0x100c030(S, b)` (確定):
1. `vec[b][0]` (= `0x100bb30(S, b<<16)`) が非 0 のとき、`theme = *( *(0x5d757c 側の global) ) + 0xd2c` を取り、`call [theme.vtbl + 0x218]` (`rcx = theme`、`rdx = vec[b][0]`) の u32 を返す (0x100c045〜0x100c068)。
2. 0 のとき `S+8` の dword (elem+0x2c、track 色) を返す (0x100c035)。

theme object の型と `vtbl[+0x218]` の実体は未確定 (vtable の書込み元が静的に追えない)。§10。

## 9. 検証

- 素材: `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を実在確認後、`tar --zstd -xf ... -C $RUNNER_TEMP/fl-win64 extracted`・real 4.3 s)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 再現 (1 コマンド): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_time_facts.py`。
- 実測: real 8.217 / 8.169 / 7.960 s (n=3)。`/proc/loadavg` 実行直前 `0.18 0.49 0.31`・`0.25 0.49 0.32`・`0.36 0.51 0.32`。並列 1。
- 測定 commit (コードを最後に変えた commit): `eb0024a88` (`feat(flapi): extract time-block and critical-section facts (PY-105)`)。以後の差分: `git diff eb0024a88 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (この commit より後の変更は REPORT と DOC_MAP だけ)。
- 逆アセンブルの再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py <VA> <命令数>` (本文の VA は全てこれで確認)。
- 範囲外: 実行による検証 (fl-win64 の起動・ランタイム値 `L`・`D` の書換え・theme の実体) は行わない。

## 10. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `L` (0x196eca0) の実行時値。`D` (384) が実行時に書き換わるか | `liveBlockNumToTime` の wall clock 分岐が常に真か否か | #2908 (PM 判断) |
| 時刻 `L` の比較で、wall clock に依存する分岐が実際に効くか | 時刻依存の挙動の有無 | #2908 |
| `0x12e7f80` の cfg+0x49e・`+0xd4`・`+0xd6` の名前 (§5 の推定) | solo 設定の副作用の名前付け | #2908 |
| `0x12e3a60` の `0x128f9e0`・`0x11e84a0`・`0xfe8bb0` の名前と引数の意味 (§6) | select の UI 通知の仕様記述 | #2908 |
| `0x666780` のキュー名と、`k=0x26` の通知内容 (§7) | 保留通知の名前付け | #2908 |
| `getLiveBlockColor` の theme object の型と `vtbl[+0x218]` の実体 (§8) | 色の出所の型確定 | #2908 |
| inc 系 4 件の critical section 対象 (rip 先 global) が同一か | 排他の対象の確定 | #2908 |
