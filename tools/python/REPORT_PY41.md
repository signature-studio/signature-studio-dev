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

---


検証起点 commit: `ecf6d6e5` (origin/main)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。
親: #1525 (PY-38 / #1515 の子)。前提の PY-38 報告: `tools/python/REPORT_PY38.md`。

## 結論

- 範囲縮小後の受入条件 (呼出し元 1 件と引数設定の確定) は**達成**。本 run では C 実装・mock 差分検査・`all_tools.mjs` は未実施。
- 汎用 helper `0x1046a30` の本体・引数の意味、`chan`・status 写像は未確定。残りは子 issue #1828 (PY-49)・#1829 (PY-50) に移管する。

## 測定条件

- 素材: `oc_artifacts: fl-win64` の `flstudio_win64_26.1.7.5653.exe/extracted/block00031_PE.bin` (22,227,016 B)。
  `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C tools/python/work/py41 extracted/block00031_PE.bin` で `work/` に展開 (gitignore)。展開 2.5 秒 (実測)。
- 逆アセンブル: `python3 tools/python/analysis/py41_disasm.py tools/python/work/py41/extracted/block00031_PE.bin 0x1046a30` (capstone 5.0.7・pefile)。
- コード差分 0 の確認 (測定 commit = 本 commit、`provider/` は未変更): `git diff ecf6d6e5 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR で変更なし)。

## 0x1046a30 の入口 (確認済み・実測)

- フレーム 0x590 バイト。引数は `ecx` → `[rbp+0x5b0]`、`edx` → `[rbp+0x5b8]`、`r8d` → `[rbp+0x5c0]` に退避。
- 入口で `[rbp+0x584] = -1` を入れ、`[rip+0x59ab06]` のフラグを `cmp byte ptr [rax], 0` / `jne 0x104cc72` (0x1046d8a〜0x1046d8d) で見る。フラグが立っていれば 0x104cc72 へ飛ぶ (`0xf82c20` は呼ばない)。
- フラグが立っていなければ `[rax+0xf30]+0x49e` と `[rax+0x10]` を見て (0x1046d93〜0x1046dbc)、条件を満たす経路で `r8d` のビット判定 (`0x8a1`・`0x20`・`0x10000`) を通過したときに `0xf82c20` を呼ぶ (`call` は 0x1046e00)。0xf82c20 の中身は未確認。
- `r8d` のビット判定:
  - `test r8d, 0x8a1` が 0 なら分岐 0x1046e05 へ飛ぶ。
  - `test r8d, 0x240` (0x1046e23) と `test r8d, 0x20` / `0x10000` / `0x8000` が分岐の条件に使われている。
- `ecx` の判定 (0x1046e7c〜): `test rax, rax` / `cmp rax, 0xfffffff` の 2 段で範囲を見て、`ecx >> 16` を `[rbp+0x55c]` に取り出す。
  - `0x40000001` は `0xfffffff` より大きいので、この範囲判定で `0x1046edf` へ飛ぶ経路になる。
  - **推定**: `ecx` の上位ビット (0x40000000) がカテゴリ、下位 16 bit が index ではなく別種の値。確定には 0x1046edf 以降の読解が必要。

## 未確定 (本 run で残したもの)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1046a30` の本体 (0x1046edf 以降) と `ecx=0x40000001`・`edx=0x3dd`・`r8d=2` の意味 | setSwing/getSwing の実装が書けない | #1828 (PY-49) |
| `chan` のフィールド `+0x739` / `+0x794` / `+0x79c` と `0xffa6d0` の戻り値 2 の意味 | rerollLoopStarter* の実装が書けない | #1829 (PY-50) |
| status 値 (-1〜-10) と `finish` のエラー文字列 10 件の対応 | エラー時の例外文字列が決まらない | #1829 (PY-50) |
| C 実装 (`provider/fl_engine.c` 4 関数 + getSwing)・mock 差分 0・`all_tools.mjs` 48/48 | 受入条件 3 件 | #1828・#1829 の確定後 |

## #1765 (PY-45) 追記: `0x1046a30` の呼出し元 (実測・1 件)

- 測定: `tools/python/work/py41/extracted/block00031_PE.bin` (`tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で展開・2.8 秒)。逆アセンブルは `analysis/py41_disasm.py` (capstone・pefile)。
- 呼出し元 `0x10473a5` (`call 0x1046a30`) を確認。直前の引数設定は `ecx = [rbp+0x5b0]`・`edx = 0`・`r8d = 2`。戻り値は `[rbp+0x580]` に格納 (0x10473aa)。呼出し元 `0x10473a5` は `.pdata` (RUNTIME_FUNCTION) で `0x1046a30`〜`0x104cccb` の関数に含まれ、呼出し先 `0x1046a30` と同一関数内 (自己呼出し)。`0x1046edf` は関数の先頭ではなく、`0x1046a30` 関数内の分岐先。
- 呼出しに至る経路: `0x104734a`〜`0x1047394` の走査ループ (`0x12df530` の戻り値判定) を抜けた後。ループ内で `0x1047382` の一致が見つかった場合は `je 0x1047424` で `0x1046a30` を呼ばずに抜ける。
- **未確認 (#1828 (PY-49) に移管)**: 呼出し元の全件。全 `.text` を走査する補助スクリプトの初回実行は 0 件を返したが、スクリプト側の誤りであり、呼出し元 0 件とは判定しない。
- **未確認 (#1828 (PY-49) に移管)**: `0x1046a30` の本体 (0x1046edf 以降の分岐先)、`ecx=0x40000001` の意味、`r8d=2` の意味。
- **未着手 (#1829 (PY-50) に移管)**: `chan` のフィールド・status 写像・`finish` のエラー文字列。

受入条件の達成状況 (範囲縮小後の受入条件を基準): **達成** (呼出し元 1 件・引数設定 `ecx`/`edx`/`r8d` の確定)。**子 issue へ移管**: `0x1046a30` の本体・引数の意味・呼出し元の全件 (#1828 (PY-49))、`chan` と status・エラー文字列 (#1829 (PY-50))、C 実装・mock 差分・all_tools 48/48 (#1828・#1829 の確定後)。
