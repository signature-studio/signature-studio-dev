# PY-218 (#3596): getGridBit・getGridBitWithLoop の件数超え event 経路 (PE 0x12d3e20) を mock/C に写す

既知類型との関係: 該当なし (逆アセンブル解釈と mock/C の照合。`docs/DEFECTS.md` の lift 欠陥類型には当たらない)。

親: #2932 (PY-112)。前段: PR #3601 (件数超えの RANGE を外して `false` にした)・`tools/python/REPORT_PY112.md`・`tools/python/REPORT_PY101.md`。

## 結論

- 件数超え (position が件数以上) の経路を PE で読み、4 関数の役割を確定した (下の表)。event は「pattern 1 の項目のうち、閾値 `[position*V, (position+1)*V)` に入り、channel が一致し、flag 0x20 が無いものが 1 件でもあれば 1、無ければ 0」。
- 項目を持つ state を mock/C に入れ、件数超えは event の有無で 1/0 を返すようにした。`tests/channels_diff.mjs` は diffs 0 (件数超えの呼出し 1200 件のうち真になるもの 30 件)。項目が無いときは件数超えが全て偽 (`{ok:false}`)。
- **件数 `[grid+0x22fc]-8` (64 か) は未確定**。mock/C は既存の steps 配列長 64 (NSTEP) を仮定した。確定は子 #3651 (`[PY-225]`) に移した。
- 受入条件の前提の訂正: issue 本文は「mock/C は件数超えを `false` 固定」とするが、着手時点の main (`03df83be4`) は RANGE (code 4) を返していた。PR #3601 (`6e7d1e59b`) で `false` になった。本 PR はその上に載せた。

## 測定

- 測定 commit: `0ca4a1903` (`feat(python): getGridBit の件数超えを event 経路 (PE 0x12d3e20) で写す (PY-218, #3596)`。コードを変えた最後の commit)。基点は `origin/main` = `6e7d1e59b`。
- 検証 HEAD: 本 REPORT の commit。`git diff 0ca4a1903 HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis` は 0 行 (本 REPORT は範囲外)。
- 環境: runner 4 core。素材: `fl-win64` を `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C $RUNNER_TEMP/fl-win64` で全展開 (5.6 秒)。`fetch_inputs.sh` rc 0。`build_cpython_wasm.sh` rc 0 (4 分 7.5 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0 (5.9 秒)。

| 検査 (0ca4a1903) | コマンド | 結果 | 所要 |
|---|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0 | 1.5 秒 |
| channels 差分 | `node tests/channels_diff.mjs` | calls 214・diffs 0・grid_calls 1200・grid_true 30・grid_diffs 0・PASS | 0.066 秒 |
| 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37425・callback_roundtrip true | 1.6 秒 |
| 実装数 | `node tests/provider_check.mjs` | functions 435・implemented 155・unimplemented 280・PASS | 0.35 秒 |
| note 列挙差分 | `node tests/note_enum_diff.mjs` | calls 33264・diffs 0・PASS | 0.83 秒 |
| 他の差分 (回帰) | `general` `device` `ui_state` `screen` `mixer` `arrangement` `arrangement_selection` `playlist` `patterns` `step_item` `ui_display` の `*_diff.mjs` | 全て diffs 0・PASS | 各 0.1 秒未満 |

- 負荷: 開始時の load average 0.11 / 0.70 / 0.65 (4 core)。
- ネガティブコントロール (1 件ずつ壊して戻す。作業中の同一の式で実施):
  - mock の flag 判定 (`!(flag & 0x20)`) を外す → `channels_diff` は `件数超え (event 経路) の差分 7 件` の AssertionError で rc 1 (FAIL)。戻すと PASS。
  - C の flag 判定を外して provider を再ビルド → 同じく `差分 7 件` で rc 1 (FAIL)。戻して再ビルドすると PASS。
  - mock の閾値 `hi = lo + V` を `lo + 2V` にする → `差分 8 件` で rc 1 (FAIL)。戻すと PASS。
- 測定後、作業ツリーを元に戻し、`git diff 0ca4a1903 -- tools/python` の出力が空であることを確認した。

## PE 解析 (FL_WIN64_DIR の `extracted/block00031_PE.bin`)

逆アセンブルは `analysis/flapi/pe_disasm.py` (capstone)。VA は絶対 VA。

| VA | 役割 | 読めた処理 |
|---|---|---|
| `0x12d3e20` | 基底の読出し (件数超えの event 経路を含む) | position<0 で 0 (`0x12d3e34`〜`0x12d3e36`)。件数は `[grid+0x22fc]` の配列の `[ptr-8]` (`0x12d3e3c`〜`0x12d3e48`)。position < 件数 なら byte (`0x12d3e54`〜`0x12d3e5b`)。件数以上は event: 閾値 `(position+1)*V` と下限 `position*V` を 32bit で作り、`0x12d16a0(G1, dl=1)` の pattern を走査 (`0x12d3e65`〜`0x12d3ef2`) |
| `0x12d16a0` | pattern の取得 | 行テーブル (VA `0x193fce0`・行幅 `0xc0`) の行 `G1` の `[row+0x28]` を返す。無ければ `0x1063a20` で作り、`[obj+0x3c] = G1` (`0x12d16a0`〜`0x12d1705`) |
| `0x12df210` | 項目の lower_bound | `*idx` に、`dword [item+0] >= target` を満たす最初の添字を書く。件数 0 なら 0 (`0x12df210`〜`0x12df290`) |
| `0x12df530` | 項目の添字アクセス | `[list+8] + idx*[list+0x10]`。範囲検査なし (`0x12df530`〜`0x12df53f`) |
| `0xfe8bb0` | ポインタ配列の添字参照 | `0 <= i < [arr+0x10]` なら `[[arr+8]+i*8]`、範囲外は 0 (`0xfe8bb0`〜`0xfe8bd5`。PY-39 と一致) |

項目の字段 (event 経路で読むもの): `+0` dword start・`+6` word channel 添字・`+0x13` byte flag (`test al,0x20` で除外)。`0x12df2a0` が件数 `[list+0x14]` を増やすので、件数は項目の個数。

event の式 (PE の読み):

```
thr = (position+1)*V                     (32bit。PE: r13d = position*G2 + G2)
lb  = lower_bound(items, position*V)     (PE 0x12df210)
for i in lb .. count-1:  item = items[i]
    if chan_table[item.word6] == [grid+0x3b4] && item.start < thr && !(byte[item+0x13] & 0x20): return 1
return 0
```

`[grid+0x3b4]` は `0xff63f0` が `[grid+0x3b4] = obj` で入れる channel obj。PE は `start < thr` で走査を止めず続けるが、項目は start 昇順なので結果は同じ。

### 変数の静的値

| 変数 | 静的値 | 状態 |
|---|---|---|
| `G1` = `dword [0x15d51a0]` | 1 (`REPORT_PY179.md` と一致) | 実行時の書込み元は未確定 (`REPORT_PY179.md` の #3536) |
| `V` = `dword [*(0x15e25f8)]` (`G2`) | 24 (`REPORT_APPENDIX_3310.md` の静的値) | 実行時の既定は未確定 (`REPORT_APPENDIX_3310.md` の #3311) |
| channel 一致の写し方 | — | PE は `0xfe8bb0([*0x15e2218], item+6) == [grid+0x3b4]` で比べる。mock/C は「項目の channel 添字 == 対象 channel の添字」と写した。表の添字と channel 添字が一致するという前提は、PY-41 の `getChannelIndex` の読みによる推定 |

## 件数 `[grid+0x22fc]-8` (未確定)

- `analysis/flapi/pe_disp_scan.py 22fc` (`[reg+0x22fc]` の .text 全走査): **store 0 件・load 5 件・lea 1 件** (load は `0x118629a`・`0x11862c7`・`0x118639b`・`0x12d3e3c`・`0x12d3e54`、lea は `0x1186378`)。直接の store は見つからない。
- `0xff63f0` (grid 生成) が `0x12d3070` を呼ぶ (`0xff6469`〜`0xff6473`) 3 番目の引数 `r8` は `[[0x15e0ff8]]` で、件数ではなく obj のポインタ (`REPORT_PY72_APPENDIX_3440.md` の `obj`)。
- よって件数の生成元は未特定。mock/C は NSTEP = 64 を仮定した。確定は子 #3651 (`[PY-225]`)。

## 実装の内容

- `provider/fl_engine.c`: `grid_bit(index, k, p)` (`p < 0` は 0、`p < NSTEP` は steps、それ以外は `grid_event`)。`grid_event` は pattern 1 の項目 (`grid_items`・`GRID_V` = 24) を走査する。`fl_engine_grid_items_probe(seed, n)` は検査用に項目を入れる (n = 0 で空)。`fl_engine_reset` で件数を 0 に戻す。
- `host/fl_mock.mjs`: `gridBit`・`gridEvent`・`gridGen` (C と同一の LCG)。`st.gridItems` を追加し、probe `gridItemsProbe(seed, n)` を置く。
- `host/fl_provider.mjs`: `gridItemsProbe` を wasm 側に追加。`provider/build.sh`: `_fl_engine_grid_items_probe` を export に追加。
- `tests/channels_diff.mjs`: 項目無しで件数超えが全て偽 (`{ok:false}`) であることを確認。seed 5 × n 4 の項目で mock と wasm の差分 0、真になる件数が 30 (空振りでない) を確認。
- 32bit の扱い: PE は位置と閾値を 32bit で計算し、`edx` の符号で `position < 0` を判定する。mock は `| 0`、C は `int32_t` に揃えた。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 件数 `[grid+0x22fc]-8` の値 (64 か) と生成経路 | 件数超えの境界。64 以外なら event 経路と steps の境界が変わる | 子 #3651 (`[PY-225]`) |
| `V` の実行時の既定値 (静的 24 の後の書込み) | 閾値 `(position+1)*V` の実値 | `tools/python/REPORT_APPENDIX_3310.md` の #3311 (既存) |
| `G1` の実行時の書込み元 | pattern 行の番号 (mock は 1 固定) | `tools/python/REPORT_PY179.md` の #3536 (既存) |
| 項目の実体 (pattern 1 の note 列) と mock の `gridItems` の対応 | probe で項目を入れるのは検査用。実際の項目の作られ方は未確認 | #3651 (`[PY-225]`・コメントで追記) |
| `getGridBitWithLoop` の件数超え (`0x12d3ff0` 側の経路) | loop 版の件数超えは base と同じ経路と仮定 | #3595 (`[PY-217]`・コメントで追記) |
| channel 一致の前提 (表の添字 = channel 添字) | 別 channel への誤一致の可能性 | #3651 (`[PY-225]`・コメントで追記) |

## 範囲外

- `getGridBitWithLoop` の loop 分岐 (`0x12d3ff0`) は子 #3595 (`[PY-217]`) の範囲。
- `setGridBit` の件数検査は未照合。

## 再現

- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` (`FL_WIN64_DIR=<展開先>`)。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 12d3e20 70` ほか、`12df210 80`・`12df530 40`・`12d16a0 80`・`fe8bb0 60`。
- 件数の走査: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disp_scan.py 22fc` (約 25 秒)。
- 検査: `bash tools/python/provider/build.sh` → `cd tools/python && node tests/channels_diff.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (前提: `fetch_inputs.sh` と `build_flpy.sh` 済み)。

## KPI

起動・GUI に関わらない PR のため対象外。
