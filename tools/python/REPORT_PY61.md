# PY-61 (#2026): playlist 未読 26 関数の引数・戻り値の型・範囲 code を逆アセンブルで確定 (作用は子 #2809)

親: #1971 (PY-57)。未読 26 件の一覧は `tools/python/REPORT_PY57.md`。前段の所属は `tools/python/REPORT_PY44.md`。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 未読 26 件すべてについて、**引数 (flapi 表と書式・出力先の配線)・戻り値の変換・範囲 code** を逆アセンブルの VA 付きで確定した (§2)。
- **範囲 code**: index 引数は `1 <= index <= 0x1f4 (500)` で判定し、範囲外は `-4` (文言 "Index out of range")。操作系の未準備は `-2` ("Operation unsafe at current time")。`getDisplayZone` の対象無しは `-7` ("Device not assigned")。
- **-4 ↔ RANGE**: **文言で対応する** (`-4` の文言 "Index out of range" = `fl_api.h` の `FL_E_RANGE` の文言)。数値は一律には対応しない (§4-2)。
- 操作系 12 件の作用 (コアの中身) は、`muteTrackLock`・`soloTrack`・`selectAll`/`deselectAll`・`selectTrack` のコアを読んだ範囲で確定した (§3)。残りのコアと helper の意味、戻り値の値域は未確定で、子 #2809 (PY-91) に移した。
- 読めた 8 件の呼び出し先のうち `0xd82c20`・`0xd843d0`・`0x12e1a20`・`0xd58d80`・`0xc38bc0` の役割を確定した (§4-1)。`0x12e68a0` は範囲の走査までで、solo 判定の意味は未確定 (#2809)。
- `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/provider_check.mjs` は変更していない。実装は行わない。

## 測定

- 素材: `fl-win64`。`mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64`。実測 real 7.364 s (user 2.644 s / sys 5.561 s)。
- 解析: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_undecided_facts.py`。実測 real 0.079 s (user 0.061 s / sys 0.019 s)、n=1。実行直前の load average は `0.00 0.09 0.12` (`/proc/loadavg`、並列 1)。
- 対象: `extracted/block00031_PE.bin` (`flstudio_win64_26.1.7.5653.exe` と同梱)。逆アセンブルは `analysis/flapi/pe_disasm.py` (capstone + pefile) の方式。
- 所属の再確認: `playlist_membership.py` (0.077 s、n=1) の playlist 配列は 42 行で、表と一致する。
- 測定 commit (コードを最後に変えた commit): `cc781d40` (`playlist_undecided_facts.py` の追加)。この PR の他の変更は REPORT と `docs/DOC_MAP.md` の索引行だけ。差分の確認は §5。

## 2. 未読 26 件 (引数・戻り値の型・範囲 code)

- 書式 `'i'` 等は PyArg 書式文字列。`(VA)` は書式文字列の位置。書式が取れなかったものは「書式未回収」と書き、配線 (`[rsp+0x20..]` へ詰めた出力先の数) と表の引数数が一致することだけを示す。
- 戻り値は、Python へ渡す直前の変換呼び出し (`call qword ptr [rax]`) の入力で決める。`cmp 0x1f4` と `-4` (`0xfffffffffffffffc`) の VA は範囲判定。
- `playlist_undecided_facts.py` の出力と突き合わせた (`cmp1f4`・`neg4`・`core`・`fields` が一致)。

### 2-1 取得系 (index を読んで値を返す) 14 件

| # | 関数 (VA) | 引数 (表 / 書式 VA) | 戻り値 (変換の根拠) | 範囲・状態 code (VA) | 読むフィールド (track 要素 0x114 B) |
|---|---|---|---|---|---|
| 1 | getTrackColor 0xd55ea0 | index:int / `'i'` (0xd55f2c) | int: 色 u32 の R と B を入替え `\|0xff000000` (0xd55ee6〜0xd55f08) → 変換 (0xd55f11) | 1..500 (cmp 0xd55ed1), -4 (0xd55f15) | +0x2c |
| 2 | isTrackMuteLock 0xd56490 | index:int / `'i'` (0xd56500) | bool: byte を movzx (0xd564d6) → 変換 (0xd564e6) | 1..500 (cmp 0xd564c1), -4 (0xd564ea) | +0xd5 (byte) |
| 3 | isTrackSelected 0xd56a40 | index:int / `'i'` (0xd56aa4) | bool: helper 0xd56990(index) の al (0xd56a7c〜0xd56a81) → 変換 (0xd56a8c) | 1..500 (cmp 0xd56a71), -4 (0xd56a90) | helper 0xd56990 (中で 0x12e1a20・0x12e8760) |
| 4 | getTrackActivityLevelVis 0xd56f10 | index:int / `'i'` (0xd56f7c) | float: f32 を cvtss2sd (0xd56f56) → 変換 (0xd56f64) | 1..500 (cmp 0xd56f41), -4 (0xd56f68) | +0x60 |
| 5 | getDisplayZone 0xd56f80 | なし (flags 4 = NOARGS) | int: 0xd85210 の戻り → 変換 (0xd56fa6) | playlist+0x50 が NULL → -7 (0xd56faa)。範囲判定なし | playlist (0xd58d80) → +0x50 |
| 6 | getLiveLoopMode 0xd57370 | index:int / `'i'` (0xd573dc) | int: +0x40 (0xd573b6) → 変換 (0xd573c1) | 1..500 (cmp 0xd573a1), -4 (0xd573c5) | +0x40 |
| 7 | getLiveTriggerMode 0xd573e0 | index:int / `'i'` (0xd5744c) | int: +0x44 (0xd57426) → 変換 (0xd57431) | 1..500 (cmp 0xd57411), -4 (0xd57435) | +0x44 |
| 8 | getLivePosSnap 0xd57450 | index:int / `'i'` (0xd574bc) | int: +0x54 (0xd57496) → 変換 (0xd574a1) | 1..500 (cmp 0xd57481), -4 (0xd574a5) | +0x54 |
| 9 | getLiveTrigSnap 0xd574c0 | index:int / `'i'` (0xd5752c) | int: +0x48 (0xd57506) → 変換 (0xd57511) | 1..500 (cmp 0xd574f1), -4 (0xd57515) | +0x48 |
| 10 | getLiveBlockStatus 0xd57550 | index, blockNum, mode=LB_Status_Default / 書式未回収 (配線 3 本 0xd57577〜0xd57589) | int: block 配列 (+0x24, 0xd575e2) を helper 0x100beb0 / 0x100bf10 / 0x100bfa0 へ渡す (3 経路, 0xd575ea〜0xd57638) → 変換 (0xd57646) | 1..500 (cmp 0xd575b1), -4 (0xd5764a) | +0x24 (block 配列) |
| 11 | getLiveStatus 0xd57670 | index, mode=LB_Status_Default / 書式未回収 (配線 2 本 0xd57697・0xd576a0) | int: block 配列 (+0x24, 0xd576e6) を helper 0x100c0f0 / 0x100c130 へ (0xd576eb・0xd5770f) → 変換 (0xd5771d) | 1..500 (cmp 0xd576c0), -4 (0xd57721) | +0x24 |
| 12 | getLiveBlockColor 0xd57740 | index:int, blockNum:int / `'ii'` (0xd577d8) | int: helper 0x100c030(block 配列, blockNum) の u32 → R/B 入替 → 変換 (0xd577be) | index 1..500 (cmp 0xd57775), -4 (0xd577c2)。blockNum の範囲判定は wrapper に無い | +0x24 (0xd5778a) |
| 13 | liveTimeToBlockNum 0xd58150 | time:int / `'i'` (0xd5819c) | int: helper 0x1221b30(time) → 変換 (0xd58188) | 範囲判定なし。PyArg 失敗 (0) は 0xd82c20(0) へ (0xd5818e) | — |
| 14 | liveBlockNumToTime 0xd581a0 | index:int / `'i'` (0xd581ec) | int: helper 0x1221aa0(index) → 変換 (0xd581d8) | 範囲判定なし (wrapper)。PyArg 失敗は 0xd82c20(0) | — |

### 2-2 操作系 (0xd843d0 経由でコアを呼ぶ) 12 件

| # | 関数 (VA) | 引数 (表 / 書式 VA) | 戻り値 | 範囲・状態 code (VA) | コア (lea r8 の VA) |
|---|---|---|---|---|---|
| 15 | muteTrackLock 0xd565c0 | index:int, value:int=-1 / `'i\|i'` (0xd566e4) | None (0xd82c20 の status 0) | コア内: 未準備 -2 (0xd5653d で据え置き), 1..500 外 -4 (0xd565ab) | 0xd56510 (0xd56632) |
| 16 | soloTrack 0xd56830 | index, value=-1, inGroup:bool=False / 書式未回収 (配線 3 本 0xd56899〜0xd568b1。表の 3 引数と一致) | None | コア内: 未準備 -2 (0xd5679c), 1..500 外 -4 (0xd56801) | 0xd56770 (0xd568d1) |
| 17 | selectAll 0xd56d00 | なし (flags 4) | None | 範囲判定なし (index 0 = 全体) | 0xd56c90 (0xd56d33)。arg5 = 1 (0xd56d3d) |
| 18 | deselectAll 0xd56dd0 | なし (flags 4) | None | 範囲判定なし | 0xd56c90 (0xd56e03)。arg5 = 0 (0xd56e0d) |
| 19 | lockDisplayZone 0xd57030 | index:int, value:int / `'ii'` (0xd57144) | None | コアは未読 | 0xd56fc0 (0xd57098) |
| 20 | liveDisplayZone 0xd57200 | left, top, right, bottom:int, duration:int=0 / 書式未回収 (配線 5 本 0xd5725f〜0xd572f0。表の 5 引数と一致) | None | コアは頭部のみ読んだ (zone 配列 [playlist+0x50] の判定あり) | 0xd57150 (0xd572af) |
| 21 | triggerLiveClip 0xd57860 | index, subNum, flags, velocity=-1 / 書式未回収 (配線 4 本 0xd578d0〜0xd57949) | None | コアは未読 (未準備 -2 のパターン 0xd577e8・0xd57804) | 0xd577e0 (0xd57914) |
| 22 | refreshLiveClips 0xd57a20 | なし (flags 4) | None | 範囲判定なし | 0xd579d0 (0xd57a53)。全引数 0 |
| 23 | incLivePosSnap 0xd57b50 | index:int, value:int / `'ii'` (0xd57c64) | None | コアは未読 | 0xd57af0 (0xd57bb8) |
| 24 | incLiveTrigSnap 0xd57cd0 | index:int, value:int / `'ii'` (0xd57de4) | None | コアは未読 | 0xd57c70 (0xd57d38) |
| 25 | incLiveLoopMode 0xd57e50 | index:int, value:int / `'ii'` (0xd57f64) | None | コアは未読 | 0xd57df0 (0xd57eb8) |
| 26 | incLiveTrigMode 0xd57fd0 | index:int, value:int / `'ii'` (0xd580e4) | None | コアは未読 | 0xd57f70 (0xd58038) |

- 14 + 12 = 26。REPORT_PY57 の未読 26 件と同じ集合 (`playlist_membership.py` の `fn=` で VA を取得)。
- `getTrackColor` (0xd55ea0) は REPORT_PY44 の表に無い行だが、PyMethodDef 配列の 1 行として存在する (`fl_table.c:454` と一致)。

## 3. 操作系のコア (作用) の確定 (読めた 4 件)

コアは、wrapper が `0xd843d0` に渡す関数ポインタ (`lea r8`)。コアの第 1 引数 (rcx) は job 構造体で、`[rbx+0x18]`〜`[rbx+0x40]` に引数 6 本、`[rbx+0x60]` に status を書く。

- **muteTrackLock (コア 0xd56510)**: 状態 `[rbx+0x60] = -2` (0xd56519) → 準備判定 `call [rax+0x98]` (0xd56535)。偽なら -2 のまま。真なら 0 (0xd5653f)、`1 <= [rbx+0x18] <= 0x1f4` (0xd5654f・0xd56557) の外は -4 (0xd565ab)。`[rbx+0x20] == -1` なら、track 要素の +0xd5 byte を反転 (`cmp byte [..+0xd5], 0; sete dl`, 0xd56580〜0xd5658b)。それ以外は、その byte へ `[rbx+0x20]` の下位 1 byte を書く (`mov byte [..+0xd5], sil`, 0xd565a1)。
  - 確定: value == -1 は反転、0/1 は設定 (lock 状態は +0xd5)。
- **soloTrack (コア 0xd56770)**: 準備判定 (0xd56794) → 範囲 1..500 (0xd567b0・0xd567b6) の外は -4 (0xd56801)。`[rbx+0x20] == -1` (0xd567b8) か、`0x12e68a0(base, index, r8=0)` の戻り al が `[rbx+0x20]` と違えば、書込み経路へ (0xd567d7)。書込みは `0x12e7f80(base, index, 0, r9b = ([rbx+0x28] == 1))` (0xd567ee)。その後 `0xbd68e0(0x26, 0)` を呼ぶ (0xd567fa)。
  - 確定: value の -1/0/1 による分岐、inGroup (`[rbx+0x28] == 1`) が r9b へ渡ること。未確定: `0x12e7f80` の反転/設定の区別、`0xbd68e0` の意味。
- **selectAll / deselectAll (共通コア 0xd56c90)**: 準備判定 (0xd56cb4) → `[rbx+0x18] != 0` (selectAll: arg5 = 1) なら `0x12e83a0(base, edx=0, r8b=4)` (0xd56ce1〜0xd56cee)。`== 0` (deselectAll) なら `r8b=6` (0xd56ccd〜0xd56cda)。index は 0 固定で範囲判定は無い。
  - 確定: 0x12e83a0 の mode は 4 (全体を選択) と 6 (全体を解除) の呼び分け。mode の値の意味は未確定。
- **selectTrack (コア 0xd56ab0。wrapper は 0xd56b60)**: 準備判定 (0xd56ada) → 範囲 1..500 (0xd56aee・0xd56af6) の外は -4 (0xd56b45)。`[rbx+0x20] == -1` (0xd56afc〜0xd56b00) は `0x12e83a0(base, index, r8b=2)` (0xd56b10)。それ以外は `al` で分岐: `al == 0` は `r8b=3` (0xd56b30〜0xd56b43)、`al != 0` は `r8=0` (0xd56b1b〜0xd56b2e)。
  - 確定: selectTrack(index, value): -1 → mode 2、0 → mode 3、他 → mode 0。mode の意味は未確定。
- 0x12e83a0 の mode 値は {0, 2, 3, 4, 6} を観測した。意味 (select / toggle / deselect / 全体) の対応は #2809 で確定する。

## 4. 読めた 8 件の呼び出し先と -4 ↔ RANGE

### 4-1 呼び出し先

| 呼び出し先 | 確定事項 (根拠 VA) | 未確定 (#2809) |
|---|---|---|
| `0xd82c20` (status → PyObject) | 直接呼び出し。status 0: 保留例外の判定 `call [0x860485 のグローバル]` (0xd82c3c) が非 0 なら NULL (0xd82c4a)、0 なら None (`0xc38bc0`, 0xd82c5c)。status ≥ 0 は None。status < 0: 報告判定 `call [rax+0x88]` (0xd82c7e) が 0 なら None (0xd82dd0)。非 0 なら文言の分岐 (0xd82c8f〜0xd82d96) → `0x4135e0` で文字列を組む → `0x414000` (c_str) → 例外投入 1 本 (0xd82dc6)。 | 投入関数 `[rbx]` の正体、例外型 (§4-2) |
| `0xd843d0` (job 投入) | 第 2 引数 `rdx` は結果構造体: `*rdx = -2` を初期値 (0xd843e9)。job を `0xd841e0` で確保し、引数 6 本 (`[rbp+0x80..0xa8]`) を job+0x18〜0x40 へ、第 3 引数 `r8` (コア) を job+0x58 へ入れる (0xd84429〜0xd8446b)。`0x526190` で実行。終了後 `*rdx = [job+0x60]` (status, 0xd844d7〜0xd844db)。 | `0x526190` の実行方式、`0xd841e0` の確保 |
| `0x12e1a20` (track 表の先頭) | 4 命令: `g_table[g_index]` を返す (`mov rax,[rip+..]; movsxd rcx,[rip+..]; mov rax,[rax+rcx*8]; ret`, 0x12e1a20〜0x12e1a32)。全 track 関数が `imul rcx, 0x45` 後の `[rax+rcx*4+off]` で要素 (0x114 B) を読む。 | 表の名前 (推定: track 表) |
| `0x12e68a0` (範囲の走査) | `0x12e8210` で範囲 (first/last) を出力させ、`[first..last]` の要素の +0x3c byte を調べる (0x12e68ea)。`isTrackSolo` (0xd566f0) とコア 0xd56770 がこの戻り al を使う。 | solo 判定の定義 (どの条件で真か)、`0x12e8210` |
| `0xd58d80` (playlist 取得) | 4 命令: `g_fn(rcx)` の薄いラッパー (0xd58d84〜0xd58d8b)。戻りは `[rax]` で参照される (0xd56865 他多数)。 | グローバル関数ポインタの正体 |
| `0xc38bc0` | グローバルの値を返す (`mov rax,[rip+..]; ret`, 0xc38bc0〜0xc38bc7)。None として使われる (0xd82c5c・0xd82dd0)。 | — |
| `0xd561b9` (isTrackMuted の間接呼び出し) | `call qword ptr [rax]`: 直前の `rax` は bool 変換器 (PyBool 相当と推定)。関数ではなく間接呼び出し地点。 | 変換器の正体 |
| `0xd85210` (zone → int) | getDisplayZone (0xd56f98) が zone object を渡す。 | 未読 (#2809) |

### 4-2 -4 ↔ RANGE

- バイナリの文言 (`0xd82c20` の分岐先 `lea rdx`、`playlist_undecided_facts.py` の末尾で再現): -1 "Unspecified error" (0xd82e24)、-2 "Operation unsafe at current time" (0xd82e44)、-3 "Range error" (0xd82e74)、-4 "Index out of range" (0xd82e8c)、-5 "Wrong number of function parameters or wrong parameter type" (0xd82eac)、-6 "Linked device not assigned" (0xd82ef4)、-7 "Device not assigned" (0xd82f1c)、-8 "Plugin not valid" (0xd82f3c)。それ以外は "Unknown error" (0xd82f5c)。
- repo: `tools/python/provider/fl_api.h` の `FL_E_RANGE = 4` (文言 "Range error" / "Index out of range" → IndexError)。
- **対応**: `-4` の文言 "Index out of range" は `FL_E_RANGE` の文言の 1 つと完全一致する。よって `-4` ↔ `RANGE` は文言で対応する。バイナリでは "Range error" (-3) も同じ文言群だが、別の code である。
- **数値は一律に対応しない**: |バイナリの値| と repo の code を比べると、Unspecified は 1 ずれ (-1 ↔ 2)、Unsafe も 1 ずれ (-2 ↔ 3)、Range は -3 と -4 の 2 つ、Wrong 以降 (-5〜-8 ↔ 5〜8) は一致する。repo の 1 "Invalid value" は -1〜-8 に無い。よって `fl_api.h` の数値を実エンジンの数値とは扱えない (`fl_api.h` の「暫定値」の注記と整合する)。repo 側の対応は文言で行う。
- **例外型は code で分岐しない**: -1〜-8 のどの経路も、同じ `call [rbx]` (0xd82dc6) に入る。型の引数は `[[[rip+0x85e38a]]]` の 1 本 (0xd82daf〜0xd82db9)。よって repo の「code → IndexError 等」は、この経路では確認できない。型の実体は未確定 (#2809 に追記)。

## 5. 検証

- 再現 (1 コマンド): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_undecided_facts.py` (0.079 s)。
- 目視の突合: §2-1 の `cmp` と `-4` の VA は、`pe_disasm.py <VA> 90` の出力を読んで一致を確認した (例: getLiveBlockColor 0xd57740 の cmp 0xd57775・-4 0xd577c2)。
- 負の対照: 関数ではない `.rdata` の PyMethodDef 配列 (`0x1114ac8`) を同じ関数で解析すると、書式 0 件・`cmp 0x1f4` 0 件になる (`fmt=None cmp1f4=0`)。対照の関数 `0xd55ea0` は `fmt='i' cmp1f4=1`。
- コード差分 (測定 commit から HEAD まで、解析コードの範囲): `git diff cc781d40 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (本 PR は REPORT と DOC_MAP だけを追加)。
- `all_tools.mjs` 48/48: 本 PR は C provider・mock・テストを変えないため再測定しない (`docs/WORKFLOW.md` §6)。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 操作系 8 件のコア (`lockDisplayZone` 0xd56fc0・`liveDisplayZone` 0xd57150・`triggerLiveClip` 0xd577e0・`refreshLiveClips` 0xd579d0・`incLivePosSnap` 0xd57af0・`incLiveTrigSnap` 0xd57c70・`incLiveLoopMode` 0xd57df0・`incLiveTrigMode` 0xd57f70) の作用 | 操作系の C 実装が決まらない | #2809 (PY-91) |
| 取得系・操作系の helper (`0x100beb0`・`0x100bf10`・`0x100bfa0`・`0x100c030`・`0x100c0f0`・`0x100c130`・`0x1221b30`・`0x1221aa0`・`0xd56990`・`0xd85210`) の意味と、戻り値の値域 (LB_Status 等) | getLive* 系の戻り値の意味が決まらない | #2809 (PY-91) |
| `0x12e68a0` の solo 判定、`0x12e7f80`・`0x12e83a0` の mode (0/2/3/4/6)・`0x12e8760`・`0xbd68e0`・`0x526190` の意味 | soloTrack・selectTrack・selectAll の作用が決まらない | #2809 (PY-91) |
| 書式未回収の 5 件 (soloTrack・liveDisplayZone・getLiveBlockStatus・getLiveStatus・triggerLiveClip) の書式 | 既定値と引数順の最終確認が残る | #2809 (PY-91) |
| 例外型 `[[[rip+0x85e38a]]]` の指す型 (0xd82daf) | `RANGE` → IndexError の割当の確認 | #2809 (PY-91) に追記 |
| `fl_engine.c` 実装・`provider_check.mjs` 件数更新・mock 差分 0・`all_tools` 48/48 | 受入条件の残り | #2027 (PY-62) |

## 受入条件 (#2026) の対応

- [x] 未読 26 件ごとに (引数・戻り値の型・範囲 code) を逆アセンブルの根拠 (VA) 付きで REPORT に残す (§2)
- [x] `-4` ↔ `RANGE` の対応を REPORT に残す (§4-2。文言で確定。数値は非対応)
- [x] 読めた 8 件の呼び出し先のうち 5 件の役割を REPORT に残す (§4-1)。残りは #2809 へ移し、本 issue の本文から外した
- [x] 実装は行わない (確定のみ)
