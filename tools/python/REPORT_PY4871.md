# PY-4871 (#5130): patterns 書き込み系 6 関数 (clearPattern / clonePattern / setChannelLoop / burnLoop / setLoopStarterRootNote / ensureValidNoteRecord) の PE 意味論

親: #4214 (PY-309) / 上位: #1799 (PY-47) / 前段: `REPORT_PY43.md` (入口・書式) / 兄弟: #5129 (PY-4870, 書込み系 A 5 件)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。

## 結論

- 6 関数すべてについて、ハンドラ (wrapper)・PyArg 書式・既定値・範囲判定 (code)・コア (`0xd843d0` に渡す関数ポインタ) の VA を PE 実測で確定した (§2)。
- 範囲外 code: `setChannelLoop` (list 要素数超え) と `clearPattern` / `clonePattern` / `ensureValidNoteRecord` の上限超え (> 999) は **`-4` ("Index out of range")**。index ≤ -1 は clearPattern / clonePattern で無音 no-op (§3)。
- 確定した「無音 no-op」: `clearPattern` / `clonePattern` の index ≤ -1 (`jle`・符号付き)、`setLoopStarterRootNote` の global flag が 0、`setChannelLoop` の list 要素が NULL。いずれも status 0 (None) で返る。
- 未確定 (実装の前に必要): 副作用の本体 (vt+0x100・vt+0xe8・vt+0xf0・vt+0x1f0 の中身)、`burnLoop` の `0x1063c40` 本体、`0x12d8af0`・`0xdc0cc0` の後段、`0x11e7430` の意味。§4 に起票先を書く。**実装は行わない** (推測実装の禁止)。

## 測定

- 測定 commit (コードを最後に変えた commit): `317a10e46` (`tools/python/analysis/flapi/pattern_write_cores.py` の追加)。この PR で他に変えたのは本 REPORT と `docs/DOC_MAP.md` の索引行だけ。
- 素材: `fl-win64` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を確認)。展開: `tools/python` で `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py5130 --wildcards '*block00031_PE.bin'` (実測 real 1.577 s)。展開先は `work/py5130/extracted/` (gitignore・commit しない)。
- 再現 (1 コマンド): `cd tools/python && python3 analysis/flapi/pattern_write_cores.py work/py5130/extracted/block00031_PE.bin` (実測 real 0.060 s・user 0.044 s・sys 0.016 s、n=1。実行直前の load average は `0.00 0.16 0.14`)。
- 逆アセンブル: `python3 analysis/py41_disasm.py work/py5130/extracted/block00031_PE.bin <VA...>` (`pe_disasm.py` と同じ capstone + pefile の方式)。
- コード差分 (測定 commit から HEAD まで): `git diff 317a10e46 HEAD -- tools/python/analysis tools/python/provider tools/python/host` の出力は 0 行 (C provider・mock・テストは変えない。`all_tools.mjs` は再測定しない: `docs/WORKFLOW.md` §6)。

## 1. 共通の呼び出し形

- 6 ハンドラのうち 5 件は `0xd843d0` (job 投入) を経由する。投入時、コア VA は `lea r8, [rip+..]` で渡し、job+0x18〜0x40 に引数、`*rdx` に結果 status を受ける。`ensureValidNoteRecord` (0xd65930) は `0xd843d0` を経由せず、同期で呼ぶ (§2-6)。
- 5 コアは入口で `[rbx+0x60] = -2` (未準備。`0xd82c20` で "Operation unsafe at current time") を書き、`call [vt+0x98]` (準備判定) が真のときだけ `0` にして本体に入る。偽のときは -2 のまま戻る。
- 戻り値: `0xd82c20(status)` が変換する。status 0 または ≥0 は `0xc38bc0` の値 (= None) を返す (0xd82c5c)。status < 0 は文言付き例外 (`REPORT_PY61.md` §4-2)。

## 2. 6 関数の確定事項

| # | 関数 (wrapper VA) | 書式 (fmt) と既定値 | コア VA | 範囲 code (根拠 VA) | 確定した経路 | 未確定 |
|---|---|---|---|---|---|---|
| 1 | clearPattern (0xd66d50) | `\|i`・index 既定 -1 (0xd66d84) | 0xd66cb0 | index > 999 → -4 (0xd66d39)。index ≤ -1 → 無音 no-op・status 0 (`jle` 0xd66d03→0xd66d41) | ready → index == -1 なら global int32 `[0x87d324]` (現在パターン) で置換 (0xd66ced)。0..999 なら `0x12d8af0(index)` → `[obj+0x10]->vt+0x100(index)` | vt+0x100 の中身 (消去の範囲・副作用) |
| 2 | clonePattern (0xd66b80) | `\|ii`・arg1/arg2 既定 -1 (0xd66bb4・0xd66bbe) | 0xd669f0 | arg1 > 999 → -4 (0xd66a84→0xd66b36)。arg1 ≤ -1 → 無音 no-op (0xd66a69) | arg1 == -1 は global int32 `[0x87d5c6]` で置換。`0x12d8af0(arg1)`。arg2 == -1 なら `0x418190`・`0xe81d00` で空き範囲を求め `vt+0xe8(obj, base, last)`。arg2 ≠ -1 なら `vt+0xf0(obj, arg1, arg2)` | vt+0xe8・vt+0xf0 の中身。arg2 の範囲検査は core に無い (vt+0xf0 側は未読) |
| 3 | setChannelLoop (0xd65e00) | `ii` (index, value) | 0xd65d60 | wrapper: index < 0 または index > (list 要素数 - 1) → -4 (0xd65f5f → 0xd65f66)。dispatch 前に判定する | list `[0x87a38b]` の `0xfe8bb0(list, index)` が NULL なら無音 (0xd65dab)。非 NULL なら list2 `[0x87a374]` の `0xfe8bb0(list2, index)` → `[elem+0x7f4]` を sub-obj として `vt+0x1f0(sub, value, 1)` (0xd65dd2) | vt+0x1f0 の中身。成功後の `0x12cfce0`・`0x12d0090`・`0x11e7fa0` (0xd65de1〜) |
| 4 | burnLoop (0xd666d0) | `i\|ii` (index, storeUndo, updateUi)・storeUndo 既定 1 (0xd66712)・updateUi 既定 1 (0xd66708)。注: 既定値の書込みは 0xd66708・0xd66712 | 0xd66630 | wrapper は index に範囲判定を持たない。core も無し。判定は `0x1063c40` 側 (未読) | obj = `g_table[cur].+0x28` (`cur` = int32 `[0x87d9a4]`、stride 24)。`0x12d16a0` が作る record を読む (§2-6)。`call 0x1063c40(obj, index, storeUndo==1 → r8b, updateUi==1 → r9b, -1)` | `0x1063c40` の本体 (途中まで読了: 0x1063c40 は `[obj+0x54]`・`[obj+0x58]` の list を走査)。obj が NULL のときの挙動 (core に NULL 判定は無い) |
| 5 | setLoopStarterRootNote (0xd668c0) | `i` (rootNoteNum) | 0xd66830 | 範囲 code 無し。clamp: n ≤ 0 → 0、n > 11 → 11 (0xd6687a〜0xd66884) | global flag `*[0x87af0b]` == 0 なら無音 no-op (0xd66871)。非 0 なら `0xdc0cc0(obj, clampedNote, r8d=[0x87d77c] int32)` | 0xdc0cc0 の後段 `0xdc2ed0`・`0xdc0700`。`[0x87af0b]` の正体 |
| 6 | ensureValidNoteRecord (0xd65930) | `i\|i` (index, playNow)・playNow 既定 0 (0xd65938) | なし (dispatch 無し) | index < 0 または index > 999 → -4 (0xd659a3)。0..999 のみ有効 | `0x12d16a0(index, playNow==1)`: `g_table[index].+0x28` が NULL なら `0x1063a20` で record を作り `+0x3c = index`。playNow かつ flag 非 0 なら `0x11e7430`。戻りは record。成功時の wrapper の戻りは定数 0 を変換器に渡した結果 (0xd65998) | `0x1063a20` の本体・`0x11e7430`・変換器 `[0x87e8e1]` の正体 (値 0 は確定、型は未確定) |

### 2-1 補足 (読んだ範囲の事実)

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
| vt+0x100 (clearPattern)・vt+0xe8 / vt+0xf0 (clonePattern)・vt+0x1f0 (setChannelLoop) の中身 (副作用の書込み先) | 3 関数の副作用が決まらない | #5130 (本 issue を Refs で残す) |
| `0x1063c40` (burnLoop) の本体・obj が NULL のときの挙動 | burnLoop の副作用・範囲外 code が決まらない | #5130 |
| `0x12d8af0`・`0xdc0cc0` 後段 (`0xdc2ed0`・`0xdc0700`)・`[0x87af0b]` の flag の正体 | clearPattern / clonePattern / setLoopStarterRootNote の前提 | #5130 |
| `0x1063a20` (record 生成)・`0x11e7430`・変換器 `[0x87e8e1]` の型 | ensureValidNoteRecord の戻り値の型 (値 0 は確定) | #5130 |

- 本 PR は **受入条件を全て満たしていない** (副作用の本体が未読)。`Refs #5130`。本 run の範囲では、子 issue は起票しない (未読の leaf は同じ issue の続きとして #5130 に残す)。
- 実装 (`provider/fl_engine.c`) は行わない。issue の「確定しなかった関数は #4215 に渡さない」に従い、本 REPORT の確定事項だけを #4215 の入力にする。

## 5. 検証

- `pattern_write_cores.py` の出力は、§2 の handler・fmt・core VA と一致する (実測)。
- 5 コアの入口 (`[rbx+0x60]` = -2 → 準備判定) は `0xd65d60`・`0xd66cb0`・`0xd669f0`・`0xd66630`・`0xd66830` で確認した。
- 負の対照: ハンドラ以外の VA (`0xd843d0` 等) を `pattern_write_cores.py` の対象に入れていない。書式抽出は `FMT` (英字と `|` のみ) で判定しており、文字列でない場合は除外される。
