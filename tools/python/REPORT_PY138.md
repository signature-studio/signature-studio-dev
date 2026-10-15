# tools/python REPORT: PY-138 launchMapPages の init・updateMap・createOverlayMap の PE 確定と実装、setMapItemTarget と持ち越し 1〜3 の保留 (#3029・親 #2984)

> 正本: `tools/python/REPORT_PY120_2984.md` (launchMapPages 12 件の PyMethodDef 表と出自)。本付録は PY-138 の実測のみ。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- **4 件の共通の呼出し骨格を PE で確定した**: `PyArg_ParseTuple` (書式は `flapi_table.json` の kwsig.fmt と一致) → 状態取得 (0xd7a6d0) → 共通ディスパッチ 0xd843d0 (要求を作ってコールバックを実行し、結果を `*out` に書く) → 0xd82c20 (結果コードを戻り値にする)。
- **init・updateMap・createOverlayMap は、引数書式・個数と成功時の戻り経路を確定した**。実装 (mock・C) は引数検査と戻り (None) のみ。page 配列への副作用は未確定のため状態を変えない (#3746)。
- **setMapItemTarget は保留**。flapi の戻り型は `int` だが、PE の成功経路は int 変換を通らない。項目書込みの取得関数 0x416750 も未確定 (#3745)。
- **-2 のゲートは `general.safeToEdit` (0xd6a2c0) と同じ述語** `[0x15e4790]→[+8]→vt[+0x98]` を見る。例外化の判定 (0xd82c20 の負の code 経路の `vt[+0x88]`) は、オブジェクトが実行時に作られるため静的に同定できない (#3746)。
- **持ち越し 1〜3 は未確定**。確定に必要な情報を §持ち越し に書いた (#3746)。
- 件数 (`length`) は仮置き 0 のまま変えない。provider_check は 実装 162→**165**・未実装 273→**270** (本 PR 単独)。main (`1d04852b0`・PY-130 #3007 の pe130 3 件と PY-132 #3013 の pe132 3 件を含む) の取り込み後は 168→**171**・267→**264** (§検証)。

## 手段

- 素材: `fl-win64` の `extracted/block00031_PE.bin` と DATA 4 件を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards 'extracted/...'` で展開 (2.9 秒)。emsdk は runner 同梱の [EMSDK] (emcc 6.0.12) を使い、`toolchain-emsdk` は展開していない。
- 逆アセンブル: `python3 analysis/flapi/pe_disasm.py <VA> [命令数]` (任意 VA)。12 件の表は `python3 analysis/flapi/pe_launchmap_entries.py --disasm` (PY-120 と同じ)。
- 値の確認: `python3 analysis/flapi/pe_va_read.py <VA>` (ファイル上の値・所属セクション。`.bss` は `not-in-file` と出る)。
- 注記: 呼出し先の IAT 名は解決していない (RIP 相対の絶対アドレスを注記)。`[0x15e….]` の呼出しスロットは `.data` にあり、その先の関数ポインタ (`0x16b8xxx`) は `.bss` で実行時に埋まる。値は ELF の初期値ではなく実行時の値として扱う。

## 共通の骨格 (4 件・VA は PE 上)

| 段 | VA | 内容 |
|---|---|---|
| 状態取得 | 0xd7a6d0 | `[0x15e05b8]` (`.data` の slot → `.bss` の関数ポインタ) を呼ぶだけ。`[rax]` = obj |
| 引数 | `[0x15e1e58]` (PyArg 呼出しスロット) | init 0xd79063 `sii`・updateMap 0xd792c8 `i`・createOverlayMap 0xd7a168 `iiii`・setMapItemTarget 0xd7a3d8 `iii`。kwsig.fmt と一致 |
| ディスパッチ | 0xd843d0 | `*out = -2` (未完了) に初期化。`obj+0x50` (pm) があれば 0xd84f30 で判定。要求オブジェクトを作り、`[req+0x18..+0x40]` に 6 個の整数引数、`[req+0x48]` に r9 (init は deviceName)、`[req+0x58]` にコールバック (r8) を入れて、`[req+0x60]` の結果を `*out` に返す |
| 結果 | 0xd82c20(code) | code == 0: `[0x15e30c8]→[0x16b8470]` (`.bss` の間接呼出し・名前は未同定) が非 0 なら NULL (例外伝播)。それ以外 (code ≥ 0) は 0xc38bc0。code < 0: `[0x15e4790]→[+8]→vt[+0x88]` が真なら表の文言で例外を立て、偽なら 0xc38bc0 |
| 成功の戻り | 0xc38bc0 | `mov rax, [0x16b82e0]; ret` (引数を見ない)。`0x16b82e0` は `.bss` (ファイル上は無い・実行時の大域)。int 変換 (`[0x15e4280]`) は通らない |

- コールバックの結果は `[req+0x60]` に入る。0 (成功)・-2 (gate 偽のまま)・-7 (pm == 0) のいずれか。
- 負のコード表 (文言) は PY-120 の `0xd82c20` 表と同じ (`REPORT_PY120_2984.md`)。

## 4 件の確定状況

| 関数 (entry・fn) | fmt | 引数の流れ (PE) | 成功時の戻り (PE) | 本 PR の状態 |
|---|---|---|---|---|
| init (0x151e058・0xd79020) | sii | deviceName (`str` → 0x41c6e0 で文字列化 → `req+0x48`)・width (`req+0x18`)・height (`req+0x20`) | 0xc38bc0 (大域) | 書式・個数・戻りを実装。副作用は #3746 |
| updateMap (0x151e098・0xd79290) | i | index (`req+0x18`)。コールバック 0xd79200 で `index == -1` は全体更新 `pm->vt[+0x20](pm, pm+0x3d4)`、それ以外は `pm->vt[+0x28](pm, arr+index*32)` | 0xc38bc0 | 書式・個数・戻りを実装。副作用は #3746。索引の範囲検査は PE のコールバックに無い |
| createOverlayMap (0x151e198・0xd7a130) | iiii | offColor (`req+0x18`)・onColor (`+0x20`)・width (`+0x28`)・height (`+0x30`)。コールバック 0xd7a0b0 が `0xfdaac0(pm+0x3d4, 0xf, …)` を呼ぶ | 0xc38bc0 | 書式・個数・戻りを実装。副作用 (0xfdaac0 の先) は #3746 |
| setMapItemTarget (0x151e1b8・0xd7a3a0) | iii | index (`req+0x18`)・itemIndex (`+0x20`)・target (`+0x28`、1 バイト)。コールバック 0xd7a280: index < 0 は `pm+0x3d4`、それ以外 `arr+index*32` を 0x416750 で取得し、`item[itemIndex]+1` (項目幅 11 バイト) に target を書く | 0xc38bc0 (int 変換なし) | **保留**。stub の `int` と食い違う・0x416750 の意味が未確定 (#3745) |

- 全 4 件とも gate は `[0x15e4790]→[+8]→vt[+0x98]` (`general.safeToEdit` 0xd6a2c0 と同じ slot。REPORT_PY87 の確定と一致)。偽なら code -2 を返す。pm (`obj+0x50`) == 0 なら code -7 (4 件とも判定がある)。
- 戻り型の確認: 成功経路は全て同じ大域 `[0x16b82e0]` を返し、int 変換を通らない。flapi の None 宣言 (init・updateMap・createOverlayMap) と矛盾しないが、大域の実行時値が None であることは確認していない。setMapItemTarget の stub `int` とは食い違う (#3745)。

## 持ち越し 1〜3 (`launchMapPages.length` 0xd791b0)

1. **件数ヘッダ `[arr-8]` の意味 (件数か容量か)**: 未確定。書込み側は init のコールバック 0xd78d00 が `pm->vt[+0x98](pm+0x3c0, deviceName, width, height)` で配列を作る (vt 先は未読)。確定に必要: `pm` の vtable の同定と、その vt[+0x98] の先の `[arr-8]` への書込み。
2. **例外化の述語**: 未確定。`0xd82c20` の負の code 経路は `[0x15e4790]→[+8]→vt[+0x88]` を呼ぶ (偽なら例外を立てず 0xc38bc0)。`[0x141d6b8]` は `.data` のファイル上の値が 0 で、実行時に設定されるため、`X=[0x141d6b8]`・`Y=[X+8]`・`vt=[Y]` の先 (`vt[+0x88]`) は静的に決まらない。確定に必要: 実行時 (Y の vtable) の同定。
3. **件数の実行時初期値**: 未確定。mock・C の 0 は仮置きのまま (`lm_pages`・`st.launchPages`)。確定に必要: 項目 1 の書込みの経路。

## 実装

- `host/fl_mock.mjs`: `launchMapPages.init` (arity 3・`str(a[0])`・int 2)・`updateMap` (arity 1・int)・`createOverlayMap` (arity 4・int ×4)。戻りは undefined (None)。状態は変えない。
- `provider/fl_engine.c`: 同じ検査 (`NARGS`・`A_STR(0)`・`A_INT`) と `fl_ret_none`。
- `tests/launchmap_diff.mjs`: 呼出し 6 件 + 引数違い 9 件 = 15 件。mock と C の差分 0。
- `tests/provider_check.mjs`: `pe138` (3 件) を実装集合に追加。期待値 実装 162→165・未実装 273→270。main 取り込み後は main の `pe130`・`pe132` (各 3 件) と合わせて期待値を 実装 171・未実装 264 に更新 (`04a50c667`)。
- 実装しなかったもの: setMapItemTarget (#3745)・副作用・例外化の述語・持ち越し 1〜3 (#3746)。

## 検証

測定 commit: `04a50c667` (コードを変えた最後の commit。main `1d04852b0` の取り込み merge。競合は `tests/provider_check.mjs` の 1 件 (main の `pe132` と本 PR の `pe138` を判定集合の両方に入れた) で、期待値を 実装 171・未実装 264 に更新)。途中の取り込み (`f8600e9c6`・`24ec522f5`) と取り込み前の測定 (`fa78f9a1a`・実装 165・未実装 270) は Git 履歴に残し、本節では置き換えた。
環境: runner (4 core、測定時の load average 0.49 (1 分平均)、node 22.23.3、emcc 6.0.12 ([EMSDK]))。素材 `fl-win64` の `block00031_PE.bin` と DATA 4 件を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`・2.8 秒)。

| コマンド | 結果 | wall |
|---|---|---|
| `fetch_inputs.sh` | rc 0 | 0.7 s |
| `build_cpython_wasm.sh` (32 bit) | rc 0 (本 HEAD で増分。クリーンビルドは `f8600e9c6` 系で rc 0・244.7 s。`build_cpython_wasm.sh`・`build_flpy.sh`・`src/` は main 取り込みで差分 0) | 0.9 s |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | rc 0 | 6.0 s |
| `provider/build.sh` | rc 0 (`dist/flprov.wasm`) | 1.1 s |
| `pe_launchmap_entries.py` | 12/12 OK (entry・fn・flags・docstring が flapi と一致) | 0.09 s |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 171 / unimplemented 264 / mcp_static 60) | 0.35 s |
| `node tests/launchmap_diff.mjs` | calls 15・diffs 0・PASS | 0.05 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2.1 s |
| `tests/*_diff.mjs` (launchmap・ui_browser・ui_state・ui_display・arrangement・arrangement_selection・channels・device・general・mixer・patterns・patterns_group・playlist・screen・step_item・transport・ui・midi_path・note_enum の 19 件) | 全て rc 0・diffs 0 | 19 件合計 1.9 s |
| 負のコントロール: mock の `createOverlayMap` の引数個数を `4,4` から `3,4` に緩める | `launchMapPages 差分 1 件` で rc 1 (検出)。mock を元に戻して rc 0 | — |

- main 取り込みで入った tools/python の変更 (`fa78f9a1a` から測定 commit まで・19 ファイル・+1986/−21) も、上の測定に含めて測定した。
- コード差分 (測定 commit 以降、テスト・mock・C・解析に効く範囲): 下の出力を最終 HEAD で取った (REPORT と PR 本文の変更のみ)。

```
$ git diff 04a50c667 HEAD -- tools/python ':!*.md'
(空)
```

- 未実行: 64 bit CPython (`build_cpython_wasm64.sh`)・pthread 版 (`CPY_PTHREADS=1 …`)・`static_subinterp_browser` 等の static 系。時間枠外。受入条件 (provider_check・launchmap_diff・all_tools) の範囲では不要 (PY-120 の §再測定 (6) と同じ扱い)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| setMapItemTarget の戻り型 (stub `int` と PE の成功経路 (int 変換なし) の食い違い) と項目書込み (0x416750・itemIndex の範囲検査) | 未実装 1 件 | #3745 ([PY-243]) |
| init・updateMap・createOverlayMap の page 配列への副作用 (0xd78d00・0xd79200・0xd7a0b0 の先) | 実装は契約のみ。状態を変えないため mock・C の page 状態は実機と違う可能性がある | #3746 ([PY-244]) |
| 例外化の述語 `vt[+0x88]` (Y の実行時同定) と -2 の gate | 負の code の例外化 (length の -7 を含む) と -2 は未モデル。mock・C は gate 真と仮定 | #3746 |
| 持ち越し 1 (件数ヘッダ `[arr-8]`) と 3 (件数の初期値) | `length` の件数の意味と初期値は仮置き 0 | #3746 |
| 64 bit CPython・pthread 版の再測定 | 現 head の測定が無い (受入条件の範囲外) | 親 #2984 の提案。再測定だけの子は作らない |
