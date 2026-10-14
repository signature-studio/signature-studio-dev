# PY-41 (#1514): channels 状態参照 18 関数の PE 解析 (ハンドラ位置・書式・引数)

親: #1343 (PY-33)。前段: #1336 (PY-32, 棚卸し)、#1527 (PY-39)、#1529 (PY-40)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 18 関数すべてについて、PyMethodDef 表の entry・ハンドラ先頭 VA・書式 (fmt)・kwlist を FLEngine PE から取得し、`flapi_kwargs.json` の `fn_va`・flags・fmt・kwlist と一致することを確認した。
- **戻り値・範囲外 code・状態の副作用は未確定**。ハンドラから下位関数への委譲先を追っていないため、`provider/fl_engine.c` への実装は今回行わない (推測実装の禁止)。
- コード変更は `provider/` `host/` `tests/` で 0 件。本 PR は解析の記録のみ。受入条件は部分達成 (`Refs #1514`)。

## 測定

- 解析対象: `$FL_WIN64_DIR/extracted/block00031_PE.bin` ([WIN64]・FL 26.1.7.5653 の FLEngine PE)。素材 `fl-win64.tar.zst` を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開 (実測 2.3 秒)。展開先は `$RUNNER_TEMP` 相当の作業領域 (repo 外・gitignore 対象外のため commit しない)。
- 解析補助: `tools/python/analysis/flapi/pe_handler_probe.py` (既存・未変更)。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <18 関数名>` → 終了 0。18 関数すべての表エントリを検出 (`selectAll` 等は PE 内に複数の同名表エントリがあり、channels 側は `flapi_kwargs.json` の `fn_va` で選んだ)。
- 測定 commit: 本 PR のコード commit (doc のみ)。差分 0 の証跡は PR 本文に記載。

## ハンドラ位置と書式 (PE 実測・flapi_kwargs と一致)

| 関数 | fn_va | flags | 書式 (fmt) | kwlist |
|---|---|---|---|---|
| channelNumber | 0xd58f80 | 3 | `\|ii` | canBeNone, offset |
| getActivityLevel | 0xd5d060 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelColor | 0xd594b0 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelIndex | 0xd5bd60 | 1 | `i` | なし |
| getChannelMidiInPort | 0xd5bcd0 | 3 | `i\|i` | index, useGlobalIndex |
| getChannelPitch | 0xd5a600 | 3 | `i\|ii` | index, mode, useGlobalIndex |
| getChannelType | 0xd5abc0 | 3 | `i\|i` | index, useGlobalIndex |
| getCurrentStepParam | 0xd5bb30 | 3 | `iii\|i` | index, step, param, useGlobalIndex |
| getGridBit | 0xd5b420 | 3 | `i\|ii` | index, position, useGlobalIndex |
| getGridBitWithLoop | 0xd5bc10 | 3 | `ii\|i` | index, position, useGlobalIndex |
| getRecEventId | 0xd5c0f0 | 3 | `i\|i` | index, useGlobalIndex |
| getStepParam | 0xd5ba00 | 3 | `iiii\|i` | step, param, offset, startPos, padsStride |
| getSwing | 0xd5dbf0 | 4 (NOARGS) | なし | なし |
| isChannelMuted | 0xd59790 | 3 | `i\|i` | index, useGlobalIndex |
| isChannelSolo | 0xd59a80 | 3 | `i\|i` | index, useGlobalIndex |
| isGridBitAssigned | 0xd5b360 | 3 | `i\|i` | index, useGlobalIndex |
| isGraphEditorVisible | 0xd5c8f0 | 4 (NOARGS) | なし | なし |
| isHighLighted | 0xd5c7a0 | 4 (NOARGS) | なし | なし |

## 未確定 (次に決める事項)

1. **戻り値の型と意味**: 各ハンドラの末尾で返す値 (None / bool / int / float) は、下位関数の戻り規約を読んでいないため未確定。
2. **範囲外 code**: index・position・step が範囲外のときの code (`FL_E_RANGE` か別 code か) は未確定。PY-40 §3 未確定 1 と同じ参照関数 (`0x1005730` 系) の後半が未読。
3. **`channelNumber` の kwlist**: `canBeNone`・`offset` は実 FL の引数名として自然だが、`flapi_table.json` の `sig` との対応は未照合。
4. **`getChannelIndex` (flags 1)**: VARARGS のみで kwlist なし。引数 1 個 (`i`) の受け取りは確定。

## 次にやること (#1514 で継続)

1. 書式で受け取った引数の後段を読み、戻り値と範囲外 code を関数ごとに REPORT に追記する。
2. 確定した関数から順に `provider/fl_engine.c` に実装し、mock (`host/fl_mock.mjs`) に同じ意味論を足して diffs 0 を取る。
3. `tests/provider_check.mjs` の実装数を更新し、`FL_ENGINE=wasm node tests/all_tools.mjs` の 48/48 を再測定する。
