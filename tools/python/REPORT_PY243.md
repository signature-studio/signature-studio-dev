# tools/python REPORT: PY-243 launchMapPages.setMapItemTarget の戻り型 (None) の PE 確定と実装 (#3745・親 #3029)

> 正本: `tools/python/REPORT_PY138.md` §保留 (setMapItemTarget)。本付録は PY-243 の実測のみ。

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- **戻り型は None と PE で確定した** (flapi 表の `int` は誤り)。成功経路は `0xd7a3a0` → `0xd82c20(0)` → `0xc38bc0` → `[0x16b82e0]`。`0x16b82e0` は loader が `GetProcAddress("_Py_NoneStruct")` を格納する変数 (REPORT_PY141・`pe_py141_probe.py` PASS)。int 変換 (`[0x15e4280]`) は通らない。
- mock と C provider に `launchMapPages.setMapItemTarget` (arity 3・`iii`) を実装し、戻りは None。mock と C の差分 0。
- **項目書込み (0xd7a280) の副作用は未実装** (項目の状態を持たないため)。0x416750 の意味と範囲検査も未確定。子 issue へ移した (下の未解決表)。

## 手段

- 素材: `fl-win64` の `extracted/block00031_PE.bin` を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C /tmp/opencode/fl 'extracted/block00031_PE.bin'` で展開 (`FL_WIN64_DIR=/tmp/opencode/fl`)。`block00031_PE.bin` は 22,227,016 バイト。
- 逆アセンブル: `python3 analysis/flapi/pe_disasm.py <VA> [命令数]` (0xd7a3a0・0xd7a280・0x416750・0xd82c20・0xc38bc0)。
- 入力: `fetch_inputs.sh` で `work/` (midi.py・utils.py・MCPTools.pyc・device script・fl-stubs) を生成。`work/` は gitignore。
- CPython 3.12.1 wasm: `build_cpython_wasm.sh` (`work/build-wasm`) を worktree 上で新規ビルド (`provider_check` の前提)。

## 戻り型の根拠 (VA)

| 段 | VA | 内容 |
|---|---|---|
| 本体 | 0xd7a3a0 | 書式 `iii` (lea rdx `0xd7a3d8`→`[0x15e1e58]`)。成功時は `call 0xd82c20` (0xd7a489) の戻り値を `[rbp+0x78]` に返す |
| 結果 | 0xd82c20 | code == 0 かつ `PyErr_Occurred` が NULL → 0xd82c55 → `0xc38bc0` (0xd82c5c)。code ≥ 0 の既定経路も 0xc38bc0 |
| 成功の戻り | 0xc38bc0 | `mov rax, [rip+0xa7f719]` (= 0x16b82e0)・`ret` |
| 大域 | 0x16b82e0 | `.bss` (ファイル上は無い)。REPORT_PY141 の loader 確認により `_Py_NoneStruct` のアドレス |

- `pe_va_read.py 16b82e0` は `section=.bss not-in-file` を返す (期待通り)。値の確定は loader の GetProcAddress 格納 (REPORT_PY141) に依る。

## 項目書込み (0xd7a280) の読み

| 段 | VA | 内容 |
|---|---|---|
| index < 0 | 0xd7a318 | `pm+0x3d4` を `0x416750` の第 2 引数に渡す |
| index ≥ 0 | 0xd7a2f5〜0xd7a300 | `[pm+0x3c0] + index×32` を渡す。**件数 (`[arr-8]`) との比較は無い** |
| 項目書込み | 0xd7a32f〜0xd7a348 | `item = holder`・`itemIndex × 0xb` の位置 +1 に `target` (1 バイト) を書く。**itemIndex の範囲検査は無い** |
| 0x416750 | 0x416750〜 | 型記述子 (r8) に従って src から dst へ値を写す汎用処理。詳細は下の「0x416750 の意味 (PY-4902)」 |

- 0x416750 の意味は PY-4902 (#5287) で VA 根拠により確定した (下節)。`r8` の型記述子は tag `0x16` ではなく `0x0e` (struct `TLaunchMap`) である。

## 0x416750 の意味 (PY-4902・#5287)

検証: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B) を `tar --zstd -xf` で展開。イメージベース `0x400000`・`.text` 0x401000〜。`FL_WIN64_DIR=<展開先> python3 tools/python/pe_py4902_va.py dis|desc <VA>` で再現する (capstone)。

| 項目 | VA | 根拠 |
|---|---|---|
| 呼出し側の記述子 | 0xd7a304 | `r8 = [0xfd5518]` → 記述子 `0xfd5520`。`desc 0xfd5520` は tag `0x0e`、名前 `TLaunchMap`、項目 1 (tag `0x11`・`0xfd54d8`) |
| 既存 REPORT の誤り | 0x416750 の 0x416773〜0x416777 | `cmp byte [r8], 0x16` は存在するが、この記述子は `0x0e` なので tag `0x16` の枝には入らない |
| 分岐 | 0x4167ae〜0x416a0d | tag `0x0e` は既定の struct 走査。項目ごとに 0x4169e8 で `0x418210` (refcount 付きポインタ代入) を呼ぶ |
| 項目書込み先 | 0xd7a32f〜0xd7a348 | `item = holder ([rbp+0x30])`・`[pm+0x20]×0xb` の位置 +1 に `target` (1 バイト) を書く |
| holder の取得 | 0xd7a2d7〜0xd7a311 | 基点 `rax = [[pm+8]+0x50]`。`[rax+0x3c0] + index×32` を 0x416750 の dst に渡し、`[rbp+0x30]` の記述子を読む。index < 0 は `rax+0x3d4` (0xd7a318〜0xd7a32a) |
| 範囲検査 | 0xd7a2e8〜0xd7a348 | `index` の件数 (`[arr-8]`) との比較は無い。`index < 0` の判定 (0xd7a2ef) のみ。`itemIndex` の比較・分岐は無い |

- 結論: 0x416750 は `(dst, src, 型記述子)` を取り、記述子の項目ごとに src の値を dst へ写す (呼出しは `dst = &[rbp+0x30]`・`src = 配列要素`・`r8 = 0xfd5518`)。tag `0x0e` の struct では、tag `0x11` の項目を `0x418210` (refcount 付きポインタ代入) で写す。`setMapItemTarget` は、写した holder の先頭ポインタ `[rbp+0x30]` を基点に `itemIndex×0xb+1` へ `target` を書く。`index` と `itemIndex` の範囲検査は PE に無い。
- 未確定: `[rax+0x3c0]` の配列要素の型 (`index×32` の要素が何か) と、`+1` 書込みの前後で他の項目が変わるか。`0x415610`・`0x415c30` (acquire/release 相当) の対応は読み切っていない。

## 実装

- `host/fl_mock.mjs`: `launchMapPages.setMapItemTarget` (arity 3・`argI` ×3)。戻り undefined (None)。状態は変えない。
- `provider/fl_engine.c`: `FL_H(launchMapPages, setMapItemTarget)` (NARGS 3・`A_INT` ×3・`fl_ret_none`)。
- `tests/launchmap_diff.mjs`: 呼出し 1 件 (`[0, 1, 1]`) と引数違い 2 件 (個数 2・型 `"x"`)。
- `tests/provider_expect/pe243.json`: 新規。`provider_check` の実装集合に入る。

## 検証

測定 commit: `c9e1620b3` (コードを変えた最後の commit)。環境: runner (4 core、load average 1.32 1.40 0.71)、node 22.23.3、emsdk 6.0.12 (`[EMSDK]`)。

| コマンド | 結果 | wall |
|---|---|---|
| `provider/build.sh` | rc 0 (`dist/flprov.wasm` 75,506 B) | 1.193 s |
| `build_cpython_wasm.sh` | rc 0 (`python.wasm` 5,927,853 B) | 4 分 27.9 秒 (`real 4m27.888s`) |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | rc 0 (`flpy.wasm` 5,924,680 B) | 6.11 s |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 228 / unimplemented 207 / mcp_static 60) | 0.360 s |
| `node tests/launchmap_diff.mjs` | calls 18・diffs 0・PASS | 0.050 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2.060 s |
| 負のコントロール: mock の `setMapItemTarget` の arity を `3,3` から `2,3` に緩める | `launchmap_diff.mjs` が rc 1 (検出)。mock を元に戻して PASS (rc 0) | — |

- `provider_check` の期待値は集合から導出する (手書きの件数は持たない)。実測の推移: `9edd0f327` (main 取り込み前) で implemented 206 / unimplemented 229、`c9e1620b3` (本 PR HEAD) で 228 / 207。

コード差分 (測定 commit 以降、テスト・mock・C・解析に効く範囲): 測定 commit = 最後のコード変更 commit のため、`c9e1620b3` 以降のコード差分はない。

```
$ git diff c9e1620b3 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 項目書込み (0xd7a280) の副作用 (`item[itemIndex]+1` への target 書込み) と 0x416750 の意味 | `setMapItemTarget` は状態を変えない (mock・C)。実機と項目の状態が違う可能性 | #4581 (PY-344) |
| itemIndex・index の範囲検査 (PE に検査が無いように見える) | 範囲外の引数の扱いは未モデル。mock・C は値をそのまま受ける | #4581 (PY-344) |
| 項目書込み・範囲検査 (受入の 2・3) | mock・C は項目の状態を持たない (`launchMapPages.length` も仮置き 0) | #4581 (PY-367) |

戻り型の表の修正 (#4581): `analysis/flapi_table.py` の `RETURN_OVERRIDES` で `setMapItemTarget` の戻り型を `None` に上書き (公開 stub の `int` は PE と食い違う)。`flapi_table.json` は 1 行だけ変わり、`provider/gen/fl_table.c` の `'i'` → `'n'` になる。
