# PY-4871 (#5130): patterns 書き込み系 6 関数 (clearPattern / clonePattern / setChannelLoop / burnLoop / setLoopStarterRootNote / ensureValidNoteRecord) の PE 意味論

親: #4214 (PY-309) / 上位: #1799 (PY-47) / 前段: `REPORT_PY43.md` (入口・書式) / 兄弟: #5129 (PY-4870, 書込み系 A 5 件)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。

## 結論

- 6 関数すべてについて、ハンドラ (wrapper)・PyArg 書式・既定値・範囲判定 (code)・コア (`0xd843d0` に渡す関数ポインタ) の VA を PE 実測で確定した (§2)。
- 範囲外 code: `setChannelLoop` (list 要素数超え) と `clearPattern` / `clonePattern` / `ensureValidNoteRecord` の上限超え (> 999) は **`-4` ("Index out of range")**。index ≤ -1 は clearPattern / clonePattern で無音 no-op (§3)。
- 確定した「無音 no-op」: `clearPattern` / `clonePattern` の index ≤ -1 (`jle`・符号付き)、`setLoopStarterRootNote` の global flag が 0、`setChannelLoop` の list 要素が NULL。いずれも status 0 (None) で返る。
- 未確定 (実装の前に必要): 副作用の本体 (vt+0x100・vt+0xe8・vt+0xf0・vt+0x1f0 の中身)、`burnLoop` の `0x1063c40` 本体、`0x12d8af0`・`0xdc0cc0` の後段、`0x11e7430` の意味。§4 に起票先を書く。**実装は行わない** (推測実装の禁止)。

## 測定

- 測定 commit (コードを最後に変えた commit): `dc31ff4c8` (`tools/python/analysis/flapi/pattern_write_semantics.py` の追加と本 REPORT の訂正)。
- 素材: `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を確認)。展開: `tools/python` で `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py5130 --wildcards '*block00031_PE.bin'` (実測 real 2.910 s)。展開先は `work/py5130/extracted/` (gitignore・commit しない)。
- 再現 (1 コマンド): `cd tools/python && python3 analysis/flapi/pattern_write_semantics.py work/py5130/extracted/block00031_PE.bin` (HEAD `dc31ff4c8` で実測 real 0.086 s・user 0.069 s・sys 0.018 s、n=1。実行直前の load average は `0.09 0.19 0.08`。結果 `RESULT OK fail=0 total=11`)。
- 前段の再現: `cd tools/python && python3 analysis/flapi/pattern_write_cores.py work/py5130/extracted/block00031_PE.bin` (実測 real 0.060 s・user 0.044 s・sys 0.016 s、n=1。`pattern_write_cores.py` は `317a10e46` で追加・変更なし)。
- 逆アセンブル: `python3 analysis/py41_disasm.py work/py5130/extracted/block00031_PE.bin <VA...>` (`pe_disasm.py` と同じ capstone + pefile の方式)。
- コード差分 (測定 commit から HEAD まで): `git diff dc31ff4c8 HEAD -- tools/python/analysis tools/python/provider tools/python/host` の出力は 0 行 (C provider・mock・テストは変えない。`all_tools.mjs` は再測定しない: `docs/WORKFLOW.md` §6)。

## 1. 共通の呼び出し形

- 6 ハンドラのうち 5 件は `0xd843d0` (job 投入) を経由する。投入時、コア VA は `lea r8, [rip+..]` で渡し、job+0x18〜0x40 に引数、`*rdx` に結果 status を受ける。`ensureValidNoteRecord` (0xd65930) は `0xd843d0` を経由せず、同期で呼ぶ (§2-6)。
- 5 コアは入口で `[rbx+0x60] = -2` (未準備。`0xd82c20` で "Operation unsafe at current time") を書き、`call [vt+0x98]` (準備判定) が真のときだけ `0` にして本体に入る。偽のときは -2 のまま戻る。
- 戻り値: `0xd82c20(status)` が変換する。status 0 または ≥0 は `0xc38bc0` の値 (= None) を返す (0xd82c5c)。status < 0 は文言付き例外 (`REPORT_PY61.md` §4-2)。

## 2. 6 関数の確定事項

| # | 関数 (wrapper VA) | 書式 (fmt) と既定値 | コア VA | 範囲 code (根拠 VA) | 確定した経路 | 未確定 |
|---|---|---|---|---|---|---|
| 1 | clearPattern (0xd66d50) | `\|i`・index 既定 -1 (0xd66d84) | 0xd66cb0 | index > 999 → -4 (0xd66d39)。index ≤ -1 → 無音 no-op・status 0 (`jle` 0xd66d03→0xd66d41) | ready → index == -1 なら global int32 `[0x87d324]` (現在パターン) で置換 (0xd66ced)。0..999 なら `0x12d8af0(index)` (値を返さない・§6) の後、`[[0x87da6f]+0x10]->vt+0x100(index)` (0xd66d31) | vt+0x100 の中身 (消去の範囲・副作用)。vtable の型 |
| 2 | clonePattern (0xd66b80) | `\|ii`・arg1/arg2 既定 -1 (0xd66bb4・0xd66bbe) | 0xd669f0 | arg1 > 999 → -4 (0xd66a84→0xd66b36)。arg1 ≤ -1 → 無音 no-op (0xd66a69) | arg1 == -1 は global int32 `[0x87d5c6]` で置換。`0x12d8af0(arg1)`。arg2 == -1 なら `0x418190`・`0xe81d00` で空き範囲を求め `vt+0xe8(obj, base, last)`。arg2 ≠ -1 なら `vt+0xf0(obj, arg1, arg2)` | vt+0xe8・vt+0xf0 の中身。arg2 の範囲検査は core に無い (vt+0xf0 側は未読) |
| 3 | setChannelLoop (0xd65e00) | `ii` (index, value) | 0xd65d60 | wrapper: index < 0 または index > (list 要素数 - 1) → -4 (0xd65f5f → 0xd65f66)。dispatch 前に判定する | list `[0x87a38b]` の `0xfe8bb0(list, index)` が NULL なら無音 (0xd65dab)。非 NULL なら list2 `[0x87a374]` の `0xfe8bb0(list2, index)` → `[elem+0x7f4]` を sub-obj として `vt+0x1f0(sub, value, 1)` (0xd65dd2) | vt+0x1f0 の中身。成功後の `0x12cfce0`・`0x12d0090`・`0x11e7fa0` (0xd65de1〜) |
| 4 | burnLoop (0xd666d0) | `i\|ii` (index, storeUndo, updateUi)・storeUndo 既定 1 (0xd66712)・updateUi 既定 1 (0xd66708)。注: 既定値の書込みは 0xd66708・0xd66712 | 0xd66630 | wrapper は index に範囲判定を持たない。core も無し。判定は `0x1063c40` 側 | obj = `g_table[cur].+0x28` (`cur` = int32 `[0x87d9a4]`、stride 24)。`0x12d16a0` が作る record を読む (§2-6)。`call 0x1063c40(obj, index, storeUndo==1 → r8b, updateUi==1 → r9b, -1)` | obj が NULL のときの挙動 (core に NULL 判定は無い)。`0x1063c40` 入口の `[obj+0x54] == 0` で後始末 `0x1064077` へ抜ける (§6)。range 外 code の有無は、`[obj+0x58]` の list 走査で key 一致が無いときに後始末へ抜けるため、core からは -2/-4 を返す経路は見当たらない (§3) |
| 5 | setLoopStarterRootNote (0xd668c0) | `i` (rootNoteNum) | 0xd66830 | 範囲 code 無し。clamp: n ≤ 0 → 0、n > 11 → 11 (0xd6687a〜0xd66884) | global flag `*[0x87af0b]` == 0 なら無音 no-op (0xd66871)。非 0 なら `0xdc0cc0(obj, clampedNote, r8d=[0x87d77c] int32)` | `0xdc2ed0`・`[0x87af0b]` の正体。`0xdc0700` の即値 `0xc3bfb9` は Python コード片 (§6) で、表示文字列ではない |
| 6 | ensureValidNoteRecord (0xd65930) | `i\|i` (index, playNow)・playNow 既定 0 (0xd65938) | なし (dispatch 無し) | index < 0 または index > 999 → -4 (0xd659a3)。0..999 のみ有効 | `0x12d16a0(index, playNow==1)`: `g_table[index].+0x28` が NULL なら `0x1063a20` で record を作り `+0x3c = index`。playNow かつ flag 非 0 なら `0x11e7430`。戻りは record。成功時の wrapper の戻りは定数 0 を変換器に渡した結果 (0xd65998) | `0x11e7430` 後段 (`0x11c8eb0` 以降・`0x11e7652` 以降の走査の意味)・変換器 `[0x87e8e1]` の正体 (値 0 は確定、型は未確定) |

### 2-1 補足 (読んだ範囲の事実)

- `0x12d8af0` の訂正 (§6): 値を返さない (`ret` 前に戻り値の設定が無い)。中身は `[[global 0x87…] + 0x7a8]` の object の `vt+0x1f0(index, 1)` と、後段の条件呼び出し。
- `0xfe8bb0(list, index)` = 要素取得。0 ≤ index ≤ count-1 なら `list[index]`、それ以外は NULL (0xfe8bb3〜0xfe8bd5)。
- `0xc38bc0` = global の値 (None) を返す (0xc38bc0〜0xc38bc7)。
- `0xd67690` = 引数の解析・取得 (dispatch 前の共通処理)。値の意味は未読。
- burnLoop の obj は `g_table` の `+0x28` を読むだけで、NULL 判定が無い。そのため「record が作られていない pattern に burnLoop を呼ぶ」と `0x1063c40` に NULL が渡る。作られる経路は `0x12d16a0` (ensureValidNoteRecord) 以外に未確認。

## 3. 無音 no-op と範囲外の判定 (issue の既知論点への答え)

- **範囲外 code の上限**: clearPattern / clonePattern は index > 999 で `-4`。index ≤ -1 は `-4` ではなく無音 no-op (status 0) である。
- **setChannelLoop / burnLoop の範囲外 code**: setChannelLoop は wrapper で `-4` (list 要素数で判定)。burnLoop は範囲判定が無く、範囲外の扱いは `0x1063c40` の走査結果 (未読) に依存する。-2 は準備未了のときだけ。
- **setLoopStarterRootNote の無音 no-op**: `*[0x87af0b]` が 0 のとき何もせず status 0 (None)。issue の「silent no-op の疑い」は、この分岐で確定する。ただし `[0x87af0b]` が何の flag か (= 実機でいつ 0 になるか) は未確定。実測が要る。
- **ensureValidNoteRecord の成功時の戻り値**: wrapper は定数 0 を変換器に渡して返す (0xd65998〜0xd659a1)。値は 0 と読める (変換器の型は未確定)。失敗 (index 範囲外) は -4 の例外。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| vt+0x100 (clearPattern)・vt+0xe8 / vt+0xf0 (clonePattern)・vt+0x1f0 (setChannelLoop) の vtable の型と中身 (副作用の書込み先) | 3 関数の副作用が決まらない | #5130 (本 issue を Refs で残す) |
| burnLoop の obj が NULL のときの挙動 (core に NULL 判定無し・`0x1063c40` 入口の `[obj+0x54]` 判定は読了) | 未登録 pattern に burnLoop を呼んだときの振る舞い | #5130 |
| `0x11e7430` 後段 (`0x11c8eb0` 以降)・`0x1046a30` / `0x6667f0` の意味 | ensureValidNoteRecord の playNow 側の副作用 | #5130 |
| `0xdc0cc0` 後段 `0xdc2ed0`・`[0x87af0b]` の flag の正体・即値 `0xc3bfb9` (Python コード片) を `0x6682f0` が何に使うか | setLoopStarterRootNote の no-op 条件と表示の意味 | #5130 |
| 変換器 `[0x87e8e1]` の型 | ensureValidNoteRecord の戻り値の型 (値 0 は確定) | #5130 |

- 本 PR は **受入条件を全て満たしていない** (副作用の本体が未読)。`Refs #5130`。本 run の範囲では、子 issue は起票しない (未読の leaf は同じ issue の続きとして #5130 に残す)。
- 実装 (`provider/fl_engine.c`) は行わない。issue の「確定しなかった関数は #4215 に渡さない」に従い、本 REPORT の確定事項だけを #4215 の入力にする。

## 5. 検証

- `pattern_write_cores.py` の出力は、§2 の handler・fmt・core VA と一致する (実測)。
- 5 コアの入口 (`[rbx+0x60]` = -2 → 準備判定) は `0xd65d60`・`0xd66cb0`・`0xd669f0`・`0xd66630`・`0xd66830` で確認した。
- `pattern_write_semantics.py` (§6 の読解を VA ごとに命令順で判定): 11 件 PASS・0 件 FAIL (実測 `RESULT OK fail=0 total=11`)。
- 負の対照: ハンドラ以外の VA (`0xd843d0` 等) を `pattern_write_cores.py` の対象に入れていない。書式抽出は `FMT` (英字と `|` のみ) で判定しており、文字列でない場合は除外される。

## 6. 読解の証跡 (本 PR で読み直した事実・VA と命令)

前 run までの §2 の記述を、逆アセンブル (`analysis/py41_disasm.py`) で読み直した結果。`pattern_write_semantics.py` が同じ判定をする。

- **`0x12d8af0` (訂正)**: 値を返さない。`[[0x87…]+0x7a8]` の object (rcx) に対し `call [vt+0x1f0]` (edx = index, r8b = 1) を呼ぶ (0x12d8b30)。後段は `[0x87…]` の list 範囲判定と `0x11e84a0`・`0x12ddaa0`・`0x1046710` の条件呼び出し。
- **clearPattern のコア `0xd66cb0` (0..999)**: `0x12d8af0(index)` → `[[0x87da6f]+0x10]->vt+0x100(index)` (0xd66d15〜0xd66d31)。`vt+0x100` の型は未確定。
- **burnLoop のコア `0x1063c40`**: 入口 (0x1063c6f) で `[obj+0x54]` が 0 なら 0x1064077 (後始末: `0x412d60` → `0x418190`) へ抜ける。0 でなければ `[obj+0x58]` の list (stride 20) を先頭から走査し、`key == index` (+0) かつ `flag != 0` (+4) の要素を探す。見つからなければ後段へ進まず後始末へ抜ける (0x1063cf0)。
- **record 生成 `0x1063a20`**: `[obj+0x54] = 0` (0x1063a5c)・`[obj+0x50] = 1` (0x1063a64)。戻りは obj。
- **`0x11e7430` 前半**: `[0x87…]` の 1000 件 (stride 0xc0) に `+0x6c = 0x80000001` (0x11e74ce)・`+0x70 = 0x7fffffff` (0x11e74d5) を設定 (0x11e74bf〜0x11e74e8)。後段は 0x11e7652 以降で、record の `+0x4` と `+0x8` を使って `0x663bf0` (比較) と `0x1046a30` を呼ぶ。意味は未確定。
- **setLoopStarterRootNote の後段 `0xdc0cc0` → `0xdc0700`**: `0xdc0700` は `table[cur].+0xa4 != 0` のとき `+0xa8 - 1` を `0x661dc0` に渡し、`[0x87…]+0x9c0` 系の値を `0x413480` に渡す (0xdc0757〜0xdc0779)。その後 `0x6682f0(obj+0x340, 0xc3bfb9)` を呼ぶ (0xdc07a3〜0xdc07b3)。即値 `0xc3bfb9` は UTF-16LE の Python コード片 (`spec_from_file_location('imported_code', …)` で始まる) で、表示文字列ではない。`0x6682f0` の用途は未確定。
- **注意**: 前 run の「`0xdc0700` は表示用の文字列経路と推定」は誤り。上の記述で置き換える。
- **`0x663bf0` (読了・PY-5329 の run で追加)**: `[rcx+8]` のポインタ配列 (`[rcx+0x10]` 件) を先頭から `== rdx` で線形探索し、見つかった index を返す。見つからなければ `-1` (`or eax, 0xffffffff`)。
- **`0x11e7430` 後段の走査 (0x11e7652〜0x11e76d0・読了)**: `[rbp+0x48]` の配列 (stride 12、件数は `[..-8]`) を走査。各要素の `+8` を `0x663bf0` に渡し、負なら `0x1046a30(+8, +4, 1)` を呼ぶ。その後 `[global]` の flag が 0 のとき `0x6667f0(…, 6, +8, 0)` を呼ぶ。`0x1046a30` と `0x6667f0` の中身は未読。
- **`0x11e7430` の後段 (0x11e7673 以降)**: 0x11e76dc で `0x11e6e20(rbp)` を呼んだ後、0x11e76ec 以降で `[global]` の配列 (`[rax+8]`・stride 8) を走査し、各 record の `+0x20`・`+0x29` を書く。`0x12df210` を呼ぶ分岐あり (意味は未確定)。
