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
| 0x416750 | 0x416750〜 | 型記述子 (r8) の tag `0x16` で分岐する汎用マーシャリング。tag 0x16 の枝は `[rbx+0x19]` の関数ポインタを呼ぶ。全分岐は読み切っていない |

- 0x416750 の意味 (holder に何を写すか) は未確定。REPORT_PY120_2984・REPORT_PY139_3030 の `getMapItemColor` と同じ要素取得の関数として扱う。

## 実装

- `host/fl_mock.mjs`: `launchMapPages.setMapItemTarget` (arity 3・`argI` ×3)。戻り undefined (None)。状態は変えない。
- `provider/fl_engine.c`: `FL_H(launchMapPages, setMapItemTarget)` (NARGS 3・`A_INT` ×3・`fl_ret_none`)。
- `tests/launchmap_diff.mjs`: 呼出し 1 件 (`[0, 1, 1]`) と引数違い 2 件 (個数 2・型 `"x"`)。
- `tests/provider_expect/pe243.json`: 新規。`provider_check` の実装集合に入る。

## 検証

測定 commit: `9edd0f327` (コードを変えた最後の commit)。環境: runner (4 core、`uptime` 10:04 時点 load average 1.43 1.30 0.64)、node 22.23.3。

| コマンド | 結果 | wall |
|---|---|---|
| `provider/build.sh` | rc 0 (`dist/flprov.wasm` 72,030 B) | 1 回目の計測なし (rc 0) |
| `build_cpython_wasm.sh` | rc 0 (`work/build-wasm` 新規) | 4 分 8.7 秒 (`real 4m8.708s`) |
| `FLPY_SKIP_TABLE=1 build_flpy.sh` | rc 0 | 6.09 s |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 206 / unimplemented 229 / mcp_static 60) | 0.367 s |
| `node tests/launchmap_diff.mjs` | calls 18・diffs 0・PASS | 0.049 s |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、soft_error 0、raised 0、host_calls 37,425、callback_roundtrip true | 2.099 s |
| 負のコントロール: mock の `setMapItemTarget` の arity を `3,3` から `2,3` に緩める | `launchmap_diff.mjs` が rc 1 (検出)。mock を元に戻して PASS (rc 0) | — |

- `provider_check` の期待値は集合から導出する (手書きの件数は持たない)。前回 PR の 165/270 は main 取り込み後の値のため、本 PR の実測は 206/229。

コード差分 (測定 commit 以降、テスト・mock・C・解析に効く範囲): 最終 HEAD で取った。

```
$ git diff 9edd0f327 HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 項目書込み (0xd7a280) の副作用 (`item[itemIndex]+1` への target 書込み) と 0x416750 の意味 | `setMapItemTarget` は状態を変えない (mock・C)。実機と項目の状態が違う可能性 | #4581 (PY-344) |
| itemIndex・index の範囲検査 (PE に検査が無いように見える) | 範囲外の引数の扱いは未モデル。mock・C は値をそのまま受ける | #4581 (PY-344) |
| `flapi_table.json` の `setMapItemTarget` の戻り型 `int` | 表と PE の None が食い違う。生成元 (`analysis/flapi_table.py`) の戻り型の扱いは未確認 | #4581 (PY-344・受入条件に追記済み) |
