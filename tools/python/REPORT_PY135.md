# tools/python REPORT: PY-135 screen 描画・メーター系 7 件の PE 根拠と mock/C 実装 (#3022, 親 #2985)

> 前段: `tools/python/REPORT_PY121_2985.md` (手順・書式・仮置きの扱い)。`tools/python/REPORT_PY125.md` (dispatch `0xd843d0` の sync 経路と述語 `vtbl[+0x88]`)。
> 既知類型との関係: 該当なし (PE の直接逆アセンブル。`docs/DEFECTS.md` の類型は対象外)。

## 結論

- 7 件すべての entry・fn VA・PyArg 書式 (個数・型の並び) を PE から確定した。書式は `analysis/flapi/flapi_kwargs.json` の `fmt` と一致した。
- **`blank` (0xd7c600) は効果を確定した**: 第 1 引数が 1 なら `isBlanked` (`scr+0x1d0`) を真に書く。真→偽の解除では `scr+0x1cc ← scr+0x1dc` (activeCounter の復元) を行う。`scr+0x1dc` の初期値は未実測のため仮置き 0。
- **残り 6 件** (`addMeter`・`displayBar`・`fillRect`・`drawRect`・`drawText`・`eraseRect`) は描画だけを行い、API から観測できる状態を変えない。mock と C は引数検査と None の返却だけを模す (`arrangement.selectionSet` 等と同じ扱い)。描画の引数の意味 (矩形の書式 x/y/w/h か l/t/r/b か) は保留。
- 実装・未実装の件数は main (`a8fc92eb5`) の 162/273 → **169/266** (`fl_table.c` 435 関数)。`tests/screen_diff.mjs` は 32 → 72 呼出しで mock と C の差分 0。
- 測定 commit: `a60dccce8` (コードを変えた最後の commit。`59dac085f` の実装を main に取り込んだ merge)。e2e はすべて PASS (下の検証表)。

## PE 根拠 (VA)

手段は REPORT_PY121_2985 と同じ (`analysis/flapi/pe_handler_probe.py`・`pe_disasm.py`、`FL_WIN64_DIR` は fl-win64 の全展開先)。書式は probe が指す文字列 (`str@`) の実測値。

| 関数 | entry | fn (VA) | 書式 (PE) | 引数の対応 (PE) | 処理 (PE) | 成功時の戻り |
|---|---|---|---|---|---|---|
| `addMeter` | 0x151e638 | 0xd7ada0 | `iiii\|i` (0xd7adbf) | a0→`0xd7d9e0` の edx、a1..a4→`0x4f2990` の矩形 (0xd7ae15〜0xd7ae2b) | `scr≠0` のとき `0x4f2990(&rect,a1,a2,a3,a4)` → `0xd7d9e0(scr,a0,&rect,-1,-1,[0x58]=0,0)` (0xd7ae55)。`[0x58]` は書式 5 項目のため書かれず 0 のまま | 解析の rc (1) を `0xd82c20` へ (0xd7ae5c) → `0xc38bc0` |
| `displayBar` | 0x151e738 | 0xd7b690 | `iisdi` (0xd7b6d0) | a0・a1 (i)、a2 (s)、a3 (d)、a4 (i) | 文字列を作る (`0x41c6e0`) → dispatch `0xd843d0` (sync=1、callback `0xd7b420`) (0xd7b78f) | dispatch の out を `0xd82c20` へ (0xd7b79b) |
| `fillRect` | 0x151e658 | 0xd7ae80 | `iiiii` (0xd7ae98) | a0..a3 → `0x4f2990` の矩形、a4 → `0xd52d10` の第 3 引数 | `scr≠0` のとき `0xd52d10(scr,&rect,a4,0x100)` (0xd7af18) | 0 → `0xd82c20(0)` (0xd7af1f) |
| `drawRect` | 0x151e678 | 0xd7af40 | `iiiii` (0xd7af58) | fillRect と同じ | `0xd52cc0(scr,&rect,a4,0x100,1)` (0xd7afe0) | 戻り経路は fillRect と同型と見たが未確認 |
| `drawText` | 0x151e778 | 0xd7bcb0 | `isiiii` (0xd7bcf0) | a0 (i)、a1 (s)、a2..a5 (i) | dispatch `0xd843d0` (sync=1、callback `0xd7bc10`) (0xd7bd67) | dispatch の out を `0xd82c20` へ |
| `eraseRect` | 0x151e798 | 0xd7bec0 | `iiii` (0xd7bef8) | a0..a3 (i) | dispatch `0xd843d0` (sync=1、callback `0xd7be40`) (0xd7bfa3)。callback は述語 `0x11d1430` が真で `scr≠0` のとき `0x4f2990` で矩形を作り、`vtbl(scr)[+0x100](scr,&rect)` を呼ぶ (0xd7be9a〜0xd7bea4) | dispatch の out を `0xd82c20` へ |
| `blank` | 0x151e7f8 | 0xd7c600 | `ii` (0xd7c638) | a0 (i)、a1 (i) | dispatch `0xd843d0` (sync=1、callback `0xd7c5a0`) (0xd7c6d7)。callback は述語が真で `scr≠0` のとき `0xd7d110(scr, a0==1, a1)` (0xd7c5e9) | dispatch の out を `0xd82c20` へ |

共通の読み方:

- 関数先頭で `0xd7eca0` を呼んで `this = *(rax)` を得る (REPORT_PY121_2985 と同じ)。`scr = *(this+0x50)+0x3f8`。`scr = 0` の経路 (書込みを飛ばす側) は未確定 (下の未解決)。
- 書式解析は `call [rax]` (大域の関数ポインタ) で行い、rc ≤ 0 なら解析失敗として `0xd82c20(rc)` へ進む。
- `0xd843d0` (dispatch) の入口で `*out = -2`、5 番目以降の引数を task (`+0x18`〜) へ複製し、sync flag を `[rsp+0x50]` に置く。callback の先頭は `task+0x60 = -2`、述語 `0x11d1430` (= `vtbl(this)[+0x88]()`、`this = *(*(0x15e4790)+8)`。REPORT_PY125 の述語 P と同一) が真なら `task+0x60 = 0` にして本体を呼ぶ。PY-125 と同じく、**`task+0x60` を `*out` へ写す処理は未確認** (推定)。
- 戻り値の変換 `0xd82c20` は REPORT_PY121_2985 の (a)〜(c) に従う。成功経路の戻り値は None と推定 (`0xc38bc0` は大域ポインタを返すだけで、指す先は未同定)。範囲外 code (4) を返す分岐は、読んだ範囲 (上の 7 関数の本体と callback) には見当たらなかった (未網羅)。

### `blank` の効果 (`0xd7d110`)

```
0xd7d124  cmp sil, byte [rbx+0x1d0]    ; sil = 新しい状態 (a0==1)
0xd7d12b  je  → return                  ; 同じなら何もしない
0xd7d130  test sil,sil ; je 0xd7d13c
0xd7d135  call 0xd52790(scr)            ; 真: 描画 (効果は観測できない)
0xd7d13c  mov eax,[rbx+0x1dc]; mov [rbx+0x1cc],eax   ; 偽 (解除): activeCounter ← scr+0x1dc
0xd7d185  call 0xd7e330(...)            ; 偽: 配列 [scr+0x1c4] の再描画 (効果は観測できない)
0xd7d198  mov byte [rbx+0x1d0], sil     ; isBlanked を書く
```

- 真→偽の解除時だけ activeCounter が変わる。`isUnBlank` (`+0x1d1`) は触らない。
- `+0x1dc` の初期値は未実測。mock と C は仮置き 0 (`screenDefaultCounter` / `scr_dflt`) を使い、コメントで仮置きと明記した。

## 実装 (mock と C)

- `host/fl_mock.mjs`: `screen.addMeter`・`displayBar`・`fillRect`・`drawRect`・`drawText`・`eraseRect` は `arity` と `argI` / `str` / `argF` による検査と None。`screen.blank` は上の効果を持つ。
- `provider/fl_engine.c`: 同じ内容を `NARGS` と `A_INT` / `A_STR` / `A_DBL` で書いた (`scr_dflt` を追加)。
- 引数の型は PE の書式に従う: `i` は int と bool、`s` は str のみ、`d` は int・bool・float。None は既定値扱い (既存 provider と同じ規則)。

## 検証

測定 commit: `a60dccce8` (コードを変えた最後の commit。`59dac085f` (`feat(python): screen 描画・メーター系 7 件の PE 確定と mock/C 実装 (#3022)`) を main `a8fc92eb5` に取り込んだ merge。取り込みで `tools/python` の他の変更も入ったため、この commit で再測定した)。以下は同じ commit のクリーンな作業ツリーで実行した。

環境: runner 4 core、emsdk は `[EMSDK]` (runner 同梱の既存版。`toolchain-emsdk` 素材は取得したが展開していない)、fl-win64 を `$RUNNER_TEMP/fl-win64` に全展開 (5.5 秒)。前提生成物: `fetch_inputs.sh` (rc 0、0.5 秒)・`build_cpython_wasm.sh` (rc 0、4 分 3 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、6.1 秒)。測定時の load average: 0.16 (1 分値、`uptime` 03:39:56)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・`fl_table.c: 435 関数, ハンドラ 169` | 1.0 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 169 / 未実装 266 / MCP 静的 60) | 0.35 秒 |
| `node tests/screen_diff.mjs` | calls 72、diffs 0、PASS | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 2.07 秒 |

ネガティブコントロール (`docs/WORKFLOW.md` §5)。`host/fl_mock.mjs` を 1 箇所ずつ壊して `node tests/screen_diff.mjs` が FAIL することを確かめ、戻した後に PASS を再確認した。実施は `59dac085f` (screen の行は `a60dccce8` と同一。`git diff 59dac085f a60dccce8` の screen 関連行は 0)。

- (1) `blank` の解除時の activeCounter 復元を外す → `AssertionError: screen 差分 1 件`、rc 1 (FAIL)。`setScreenActiveCounter(7)` → `blank(0,0)` の順で検出。
- (2) `drawText` の文字列検査を外す (`str(a[1])` → `argI(a,1,0)`) → `AssertionError: screen 差分 2 件`、rc 1 (FAIL)。型違いの `drawText(0,1,…)` と `drawText(0,"t",…,4.5)` で検出。

戻した後: `screen_diff` calls 72・diffs 0・PASS、`provider_check` 169/266・PASS、`all_tools` 48/48。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外):

```
$ git diff a60dccce8 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 描画 6 件の引数の意味 (矩形の書式、`0xd52d10`・`0xd52cc0`・`0xd7d9e0`・`0xd7e330`・`0xd7bc10`・`0xd7b420` の本体、`vtbl(scr)[+0x100]`) | 描画先は API から観測できないため、mock/C の状態に影響しない。意味論の検査はできない | #2985 (親。PY-121 の未確定と併せて追跡) |
| 述語 `0x11d1430` (= `vtbl(this)[+0x88]`) の実体。偽の経路 (`task+0x60=-2`) の Python 側の戻り値・例外 | `blank`・`displayBar`・`drawText`・`eraseRect` の偽経路は mock/C が成功経路 (None) だけを模す | #3045 (PY-125 の報告ゲート) |
| `scr = 0` (screen 未初期化) の経路 | mock/C は初期化済みの経路だけを模す (REPORT_PY121_2985 未確定 1 と同じ) | #2985 |
| `blank` 解除時の `scr+0x1dc` の初期値 | 解除後の `getScreenActiveCounter` は仮置き 0 (未実測)。mock と C は同じ仮置き | #2985 |
| flapi 表の書式表記: `displayBar` が `iisaa` (PE は `iisdi`)、`drawText` が `aaaaaa` (PE は `isiiii`) | `fl_table.c` の dispatch は通すので実害はない。表記の不一致のみ | #2952 (PY-116・書式表記) |

起票した子 issue: なし (残りは既存 issue に紐づけた。子は不要と判断)。
