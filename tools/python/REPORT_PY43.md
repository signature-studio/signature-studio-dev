# PY-43 (#1668): patterns の選択・移動・書き込み系 17 関数の PE 入口解析

親: #1345 (PY-35) / 元: #1336 (PY-32) / 兄弟: #1667 (PY-42, 読み取り系 14 件)。既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブル読解のみ)。

## 結論

- 17 関数すべてについて、PyMethodDef の entry・ハンドラ先頭 VA・flags を FLEngine PE から取得し、`analysis/flapi/flapi_kwargs.json` の `fn_va` と一致することを確認した (下表)。
- 呼び出し形: `0xd82c20` は 17/17 件、`0xd843d0` と `0x415610` は 16/17 件 (`ensureValidNoteRecord` 0xd65930 のみ直接 `0x12d16a0`・`0xd82c20` を呼び、`0xd843d0` と `0x415610` を呼ばない)。**戻り値・範囲外 code・副作用は未確定**。下位関数の本体を読んでいないため、`provider/fl_engine.c` への実装は今回行わない (推測実装の禁止)。
- 受入条件 4 件はいずれも未達 (意味論未決定 → C 実装・mock 差分・`all_tools.mjs` 48/48 未実施)。本 PR は解析記録のみで、コード変更 0 件。`Refs #1668`。
- 残りは子 issue 2 件に分割する (下記「分割先」)。

## 測定

- 測定 commit: `0eaf2989` (`origin/main` 起点・`ws-1668` worktree)。本 PR はコード変更 0 件 (追加は本 REPORT のみ)。
- `git diff 0eaf2989 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (コード差分 0)。
- 素材: `$HOME/artifacts/fl-win64.tar.zst` (`oc_artifacts: fl-win64`)。展開 (`tools/python` で実行): `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C work/py43 --wildcards '*block00031_PE.bin'` (実測 2.8 秒・`real 0m2.841s`)。展開先は `tools/python/work/py43/extracted/` (gitignore・commit しない)。
- ハンドラ探索: `cd tools/python && FL_WIN64_DIR=work/py43 python3 analysis/flapi/pe_handler_probe.py deselectAll selectAll selectPattern jumpToPattern findFirstNextEmptyPat movePattern ensureValidNoteRecord burnLoop clearPattern clonePattern duplicatePatternData incrementPatternLength setChannelLoop setLoopStarterRootNote setPatternColor setPatternLength setPatternName` → 終了 0 (実測・出力 1004 行)。
- 逆アセンブル補助: `python3 analysis/py41_disasm.py work/py43/extracted/block00031_PE.bin 0xd843d0` / `0xd82c20` (実測)。
- 呼び出し形の件数: 上記 17 ハンドラの全命令を capstone で逆アセンブルし、各関数を先頭から最初の `ret`/`int3` まで走査して `call` 先を数えた (`work/py43/callcheck2.py`・work 内の一時スクリプト)。`pe_handler_probe.py` は先頭 40 命令しか出さないため (`HEAD = 40`)、probe の出力だけでは `0xd82c20` などの呼び出しが見えない。呼び出し形の根拠に probe 出力は使わない。
- 注意: 関数境界で区切らず 0x800 バイトを連続走査すると、次の関数の call を拾って `ensureValidNoteRecord` が 17/17 に見える。件数は関数境界で区切ること。
- 同名の表エントリは PE 内に複数あるため、`patterns` モジュールの `fn_va` (flapi_kwargs.json) で選んだ。

## ハンドラ位置と書式 (PE 実測・flapi_kwargs と一致)

| 関数 | fn_va | flags | 書式 (fmt) | kwlist |
|---|---|---|---|---|
| setPatternName | 0xd64f30 | 1 | `is` | なし |
| setPatternColor | 0xd651e0 | 1 | `ii` | なし |
| setPatternLength | 0xd653a0 | 1 | `ii` | なし |
| duplicatePatternData | 0xd65540 | 1 | `i` | なし |
| incrementPatternLength | 0xd65670 | 1 | `ii` | なし |
| ensureValidNoteRecord | 0xd65930 | 3 | `i\|i` | index, playNow |
| jumpToPattern | 0xd65a10 | 1 | `i` | なし |
| findFirstNextEmptyPat | 0xd65ba0 | 3 | `i\|ii` | flags, x, y |
| setChannelLoop | 0xd65e00 | 1 | `ii` | なし |
| selectPattern | 0xd66230 | 3 | `i\|ii` | index, value, preview |
| selectAll | 0xd66430 | 4 (NOARGS) | なし | なし |
| deselectAll | 0xd66560 | 4 (NOARGS) | なし | なし |
| clonePattern | 0xd66b80 | 1 | `\|ii` | なし |
| clearPattern | 0xd66d50 | 1 | `\|i` | なし |
| movePattern | 0xd66ec0 | 1 | `\|i` | なし |
| burnLoop | 0xd666d0 | 3 | `i\|ii` | index, storeUndo, updateUi |
| setLoopStarterRootNote | 0xd668c0 | 3 | `i` | rootNoteNum |

注: 書式 (fmt) と kwlist は `flapi_kwargs.json` の値を載せた。PE 側の書式文字列との照合は本 run では未実施。`fmt` が `ii` 等の場合は kwlist なし (flags 1 は位置引数のみ)。

## 観測した呼び出し形 (17 件共通)

- 16 ハンドラは先頭で `call 0x415610` (引数解析系と推定・未読)、次に `call 0xd843d0` (共通ヘルパ)、`call 0xd82c20` を呼ぶ。`ensureValidNoteRecord` (0xd65930) は `0x415610`・`0xd843d0` を呼ばず、`0x12d16a0` と `0xd82c20` を直接呼ぶ。間接呼び出し `call qword ptr [rax]` は `0xd82c20` の先頭 (0xd82c43) にある (実測)。ハンドラ本体の間接呼び出し件数は未集計。
- `0xd843d0` (実測): 引数 (rcx/rdx/r8/r9 と 6 個のスタック引数) を構造体に詰め、`[rbx+0x50]` の既存値を見て `0xd84f30` を呼ぶ。さらに `0xd841e0` と `0x4133f0` を呼ぶ。**`0xd841e0` と `0x4133f0` の本体は未読**。
- `0xd82c20` (入口のみ実測): 第 1 引数 (index 相当) が 0 のとき間接呼び出しを行い、0 以上のとき `0xc38bc0` を呼ぶ。負のときの分岐は未読。`0xc38bc0` も未読。
- 上記から言えるのは「共通の呼び出し機構を経由する」ことまで。**どの経路で選択状態・パターン名・色・長さ・クローン/移動を書き換えるかは特定していない**。

## 未確定 (子 issue で決める事項)

1. 戻り値の型と意味 (`ensureValidNoteRecord` は int を返す旨が `flapi_table.json` にあるが、値の範囲は未確定)。
2. 範囲外 index の code (`FL_E_RANGE` か別 code か)。
3. 副作用の範囲 (選択状態・パターン名・色・長さ・クローン/移動が、どの配列/構造体のどのフィールドを書くか)。
4. `0xd841e0` / `0x4133f0` / `0xc38bc0` / `0xd82c20` の後段の本体。

## 分割先

受入条件の大半は未達のまま残るため、残りを 2 件の子 issue に分ける (1 PR あたりの子は最大 3 件)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 選択・移動系 6 関数 (deselectAll / selectAll / selectPattern / jumpToPattern / findFirstNextEmptyPat / movePattern) の実機意味論と C 実装 | #1668 の受入条件 1〜4 | #1798 (`[PY-46]`・親: #1668) |
| 書き込み系 11 関数 (ensureValidNoteRecord / burnLoop / clearPattern / clonePattern / duplicatePatternData / incrementPatternLength / setChannelLoop / setLoopStarterRootNote / setPatternColor / setPatternLength / setPatternName) の実機意味論と C 実装 | #1668 の受入条件 1〜4 | #1799 (`[PY-47]`・親: #1668) |
| 共通ヘルパ `0xd843d0` / `0xd82c20` の本体 | 上の 2 件の前提 | 子 issue 両方の本文に明記 |
