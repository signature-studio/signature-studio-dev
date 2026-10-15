# tools/python REPORT: PY-136 screen 初期化・メニュー系 10 件の PE 確定と C provider 実装 (#3025, 親 #2985)

> 正本: `tools/python/REPORT_PY121_2985.md` (screen 状態の 5 件・手順の雛形)。本付録は PY-136 の実測のみ。

## 結論

- screen の初期化・メニュー系 10 件 (`init`・`setup`・`update`・`deInit`・`keepDisplayActive`・`hideMenu`・`menuShowing`・`menuItemClick`・`menuNext`・`menuPrev`) を PE で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/screen_menu_diff.mjs` 42 呼出し)。
- 確定したのは **制御フローと戻り値と scr の状態遷移** (`init` で生成・`deInit` で破棄・`setup` の書込み先・`hideMenu`/`menuShowing` の読み書き・dirty の遷移)。
- **値・引数の意味は未確定**: `init` の a1〜a6、`setup` の L と i1〜i5 は格納先だけ確定し、意味は未確定 (PY-116 の範囲)。scr 未生成の経路は PE で AV (例外を返さない) のため、mock と C は Unspecified error (code 2) を仮置きした。
- メニュー項目の選択・移動 (`menuItemClick`・`menuNext`・`menuPrev`) は、呼び出す helper の効果が未同定のため **no-op**。
- 件数: 実装 162 → 172、未実装 273 → 263 (`tests/provider_check.mjs`)。C のハンドラ数 162 → 172 (`gen_provider.py --check-handlers`)。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (`extracted/block00031_PE.bin`)。10 件とも entry・fn・flags が issue 本文の表と一致した。`init` は entry 0x151e5b8 を選んだ (0x151e058 は別の名前衝突)。
- 逆アセンブル: `analysis/flapi/pe_disasm.py <VA>`。共通の読み方は REPORT_PY121_2985 と同じ (`call 0xd7eca0` → `[rax]` → `+0x50` → `+0x3f8` で scr)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` (7.9 秒)。emsdk は `/opt/emsdk` を使用 (`toolchain-emsdk` の展開先 `$RUNNER_TEMP/tc` は build には未使用)。

## PE 根拠 (10 件)

| 関数 | entry | fn (VA) | flags | 書式 | 戻り値 | scr への作用 (PE) | scr 未生成 (PE) | 確定 |
|---|---|---|---|---|---|---|---|---|
| `init` | 0x151e5b8 | 0xd7aa40 | 1 | `iiiiii` | None | ctor 0xd7cd20 で新 scr を作り `[M+0x3f8]` に格納 (旧 scr は解放せず上書き) | — | 格納は確定。a1〜a6 の意味は未確定 |
| `setup` | 0x151e5d8 | 0xd7ab00 | 1 | `Liiiii` (表は `iiiiii`) | None | `[scr+0x1d4]` (L・qword)・`+0x1dc`・`+0x1e0`・`+0x1e4`・`+0x1e8`・`+0x1ec` (i1〜i5) に書く。null 判定なし | AV | 格納は確定。意味は未確定 |
| `update` | 0x151e6b8 | 0xd7b0a0 | 1 | (読まない) | None | cb 0xd7b050: gate 真かつ scr≠0 なら dirty を描画して空 (0,0,-1,-1) に戻す | None | 制御は確定。描画は未確定 |
| `deInit` | 0x151e698 | 0xd7b000 | 4 | NOARGS | None | scr≠0 のとき `[M+0x3f8]=0` にして delete (0x40faa0) | None (何もしない) | 確定 |
| `keepDisplayActive` | 0x151e918 | 0xd7ccb0 | 4 | NOARGS | None | scr≠0 かつ dirty 空 (+0x15c<0) のとき dirty=(0,0,1,1)。+0x1cc は触らない | None | 制御は確定 |
| `hideMenu` | 0x151e6f8 | 0xd7b1f0 | 4 | NOARGS | None | 直接 hide(scr) (0xd52c50): `+0x164≠0` かつ `+0x188=1` なら `+0x188=0`。cb でも同じ | AV (0xd52c50 が `[0+0x164]` を読む) | 制御は確定 |
| `menuShowing` | 0x151e6d8 | 0xd7b170 | 4 | NOARGS | bool (変換 `0x15e4280`) | 読むだけ: `byte [scr+0x188]` | AV | 確定 |
| `menuItemClick` | 0x151e8b8 | 0xd7c9a0 | 4 | NOARGS | None | cb 0xd7c950: gate 真かつ scr≠0 なら 0xd52e70(M) (効果は未同定) | None | 制御は確定。helper の効果は未確定 |
| `menuNext` | 0x151e8d8 | 0xd7cac0 | 4 | NOARGS | None | cb 0xd7ca70: 同条件で 0xd52db0(M, +1) | None | 同上 |
| `menuPrev` | 0x151e8f8 | 0xd7cbe0 | 4 | NOARGS | None | cb 0xd7cb90: 同条件で 0xd52db0(M, +1) (menuNext と同一) | None | 同上。step の逆方向は未確認 |

根拠の VA (主要な命令):
- `init`: `0xd7aa52 mov rsi,[rax]`・`0xd7aad0 call 0xd7cd20`・`0xd7aad9 mov [rcx+0x3f8],rax`。
- `setup`: `0xd7ab18` が書式 `'Liiiii'`・`0xd7ab60 mov rcx,[rax+0x3f8]` (null 判定なし)・`0xd7ab88 call 0xd7d050`。`0xd7d050`〜`0xd7d07d` が +0x1d4〜+0x1ec を書く。
- `update`: cb `0xd7b050` の `0xd7b067 call 0x11d1430` (gate)・`0xd7b088 call 0xd7d090`・`0xd7d0f5 call 0xd52790` (dirty を空に戻す)。
- `deInit`: `0xd7b014 cmp [rax+0x3f8],0`・`0xd7b034 mov [rcx],0`・`0xd7b03e call 0x40faa0`。
- `keepDisplayActive`: `0xd7ccc7` (scr≠0)・`0xd7ccd8 cmp [rbx+0x15c],0; jge`・`0xd7ccf8 call 0x4f2990` (rect (0,0,1,1))。
- `hideMenu`: `0xd7b221 mov rcx,[rax+0x3f8]`・`0xd7b228 call 0xd52c50` (guard なし)。`0xd52c5c cmp [rbx+0x164],0`・`0xd52c66 cmp byte [rbx+0x188],0`・`0xd52c6f mov byte [rbx+0x188],0`。
- `menuShowing`: `0xd7b180 mov rax,[rax+0x3f8]`・`0xd7b187 movzx rcx, byte [rax+0x188]`・`0xd7b196 call [rax]` (bool 変換)。
- メニュー系の cb: `0xd7c979 cmp [rax+0x3f8],0`・`0xd7c986 call 0xd52e70` (menuItemClick)・`0xd7caab call 0xd52db0` (menuNext)・`0xd7cbcb call 0xd52db0` (menuPrev)。

共通部品:
- 戻り変換 `0xd82c20(v)`: v=0 は None、v<0 は gate (vtbl+0x88) が偽なら None、真なら例外 (負コード表)。gate 真の例外は code -2 "Operation unsafe at current time" の経路を含む。
- dispatch `0xd843d0`: `out=-2` から始まり、M-check `0xd84f30(M)` が偽なら即 return (out=-2)。真なら op を作って cb を実行。

## mock / C の実装 (本 PR)

- 状態: `screenAlive` (scr 生成の有無)・`screenDirty`・`screenMenuShowing` (+0x188)・`screenSetup` (L と t1〜t5)。
- `init`: scr を生成し dirty 空・menu 非表示・setup 値を既定値 (`30, 10, 10, 2, 4000`、PE の ctor 既定の代入定数) にする。None。
- `setup`・`hideMenu`・`menuShowing`: scr 未生成なら Unspecified error (code 2) を仮置き。
- `deInit`: scr を破棄 (状態を全て初期化)。None。
- `update`: scr 有りなら dirty を空にする。`keepDisplayActive`: scr 有りなら dirty を立てる。None。
- `menuItemClick`・`menuNext`・`menuPrev`: 何もしない (None)。
- 引数検査は flapi 表 (`fl_table.c`) に従う (`update` は 0 引数 → code 5)。型違い (float・str) は code 5 で、scr の有無より先に判定する。

## 検証

測定 commit: `8588639a2` (コードを変えた最後の commit。`feat(python): screen 初期化・メニュー系 10 件の PE 確定と C provider 実装 (#3025)`)。以下の表はこの commit のクリーンな作業ツリーで、`provider/build.sh` を実行してから測定した。
前提の生成物 (gitignore): `fetch_inputs.sh` (rc 0・`FL_WIN64_DIR` は全展開済み)・`build_cpython_wasm.sh` (rc 0、211 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、4 秒)。
環境: runner 4 core、測定時の load average 1.62 (uptime)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 172 (fl_table 435 関数) | 0.8 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 172 / unimplemented 263 / MCP 静的 60) | 0.27 秒 |
| `node tests/screen_menu_diff.mjs` | calls 42、diffs 0、型違い期待値一致、PASS | 0.04 秒 |
| `node tests/screen_diff.mjs` (回帰) | calls 32、diffs 0、PASS | 0.04 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.2 秒 |

ネガティブコントロール (`docs/WORKFLOW.md` §5): `host/fl_mock.mjs` の `screen.menuShowing` から `scrNeed()` を外すと、`node tests/screen_menu_diff.mjs` は `AssertionError: screen 初期化・メニュー差分 2 件` で rc 1 (FAIL)。戻すと `cmp` が一致し、calls 42・diffs 0・PASS (rc 0)。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外。本 REPORT を含む md のみの commit を後から足しても 0 行のまま):

```
$ git diff 8588639a2 HEAD -- tools/python ':!*.md'
(空)
```

## 訂正の候補 (未検証)

- `REPORT_PY121_2985.md` の `0xd82c20` の記述「正の値は `0xc38bc0` (整数化)」は誤りの疑い。`0xc38bc0` は定数セル `[0x16b82e0]` を返すだけに見える。本 PR では PY-121 の記述を訂正していない (実機確認が要る)。
- `setup` の書式は PE が `Liiiii`、flapi 表 (`fl_table.c`) が `iiiiii` で食い違う。`update` は PE が引数を読まない (VARARGS) のに、表は 0 引数。どちらも表の生成元の整理 (PY-116) の範囲。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `init` の a1〜a6 の意味と、`setup` の L・i1〜i5 の意味 (`0xd7cd20` の引数・`0xd7d110` の再設定値は推定) | mock/C は値を保存するだけで、観測できる効果はない | #2952 (PY-116・引数名と書式の範囲) |
| scr 未生成の経路 (`setup`・`hideMenu`・`menuShowing`)。PE は AV で例外を返さない | mock/C の code 2 は仮置き。実機の挙動は未確定 | 本 PR の未解決表 (追跡のみ) |
| gate (`0x11d1430` の vtbl+0x88) と M-check (`0xd84f30`) の条件 | mock/C は真と仮定。gate 偽 (None)・M-check 偽 (code -2) の経路は未実装 | 本 PR の未解決表 (追跡のみ) |
| `menuShowing` の true 経路 (`+0x188=1` の書込み元が未発見)・`+0x164` (menu 実体) の書込み元 | `menuShowing` は mock/C とも常に false。`hideMenu` の解放処理は未実装 | 本 PR の未解決表 (追跡のみ) |
| `menuItemClick`・`menuNext`・`menuPrev` の helper (`0xd52e70`・`0xd52db0`) の効果。`menuPrev` が +1 固定 (menuNext と同一) | mock/C は no-op。副作用の検査はできない | 本 PR の未解決表 (追跡のみ) |
| `init` が旧 scr を解放せず上書きする (`0xd7aad9`) | 実機での leak の疑い (観察のみ) | 本 PR の未解決表 (追跡のみ) |
| 値は全て仮置き (`init` の既定値 `30, 10, 10, 2, 4000` は ctor の代入定数で、実機値は未実測) | 値を観測する関数が無いので現時点で影響なし | 本 PR の未解決表 (追跡のみ) |
| 訂正の候補 (上の節): `REPORT_PY121_2985.md` の `0xc38bc0` 記述、`setup`・`update` の書式の食い違い | 文書上の誤りの疑い | #2952 (PY-116) |
