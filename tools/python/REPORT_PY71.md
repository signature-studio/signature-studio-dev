# PY-71 (#2501): VMT (RTTI) で型を確定 — 受入 1・2a を確定、2b・3・4 は未達

親: #2159 (PY-67)・前段: `REPORT_PY67.md` §4〜§5 (PR #2558、main 取り込み済み)。

## 結論

| # | 受入条件 (#2501) | 結果 |
|---|---|---|
| 1 | `0x86a4cf` の戻り値 P の型と `+0x794` の対象型 | **確定**。P は VMT `0x13063c8` の `TGraphEditorForm` (インスタンスサイズ `0x840`)。chan ではない |
| 2a | `0xffe370` の所属 | **確定**。`TPublicChannel` (VMT `0xfe2cf8`・サイズ `0x8a8`)。親は `TChannel` (`0xfe2978`) |
| 2b | `0xffe370` の呼出し元 | **未達**。`call [reg+0x1a0]` は `.text` に 37 件。受け手の型が分からず絞れない (§4) |
| 3 | `0xec60ae` の対象型 | **未達**。本 run では未着手 (`REPORT_PY67.md` §5.5 の未解決のまま) |
| 4 | `0x8ed012` の `[rbp+0x70]` が chan か | **未達**。本 run では未着手 (同上) |

- 本 REPORT の chan の定義: `TChannel` とその子孫 (`TPublicChannel` を含む)。依頼文の「chan」の定義との照合は未了。
- `REPORT_PY67.md` §5.2 の「クラス名は無い (stripped)」は誤りだった。RTTI にクラス名が残っている (§1)。該当箇所は同 REPORT 側で訂正した。

## 1. VMT の配置 (RTTI で検証)

64-bit Delphi の VMT 配置を仮定し、3 クラスで検証した。`py71_vmt.py` で再現する。

| VMT | クラス | `-0xc8` 自己 | `-0xa8` TypeInfo | `-0x88` クラス名 | `-0x80` サイズ | `-0x78` 親 (親 VMT) | `+0x1a0` slot 52 |
|---|---|---|---|---|---|---|---|
| `0xfe2cf8` | TPublicChannel | OK | `0xfe2ec8` | OK | `0x8a8` | `0xfe2978` (TChannel) | `0xffe370` |
| `0x13063c8` | TGraphEditorForm | OK | `0x1306a38` | OK | `0x840` | `0x803168` (TChildVectorForm) | `0x80ab60` |
| `0xfe2978` | TChannel | OK | `0xfe2c00` | OK | `0x798` | `0x12b05b0` (TChanPlugin) | `0xfed770` |

- OK: `-0xc8` が VMT 自身を指し、`-0x88` のクラス名が TypeInfo の名前と一致 (3/3)。
- 格納の並び: TypeInfo は `kind(0x07)`・長さ接頭辞付きの名前・VMT ポインタの順。TGraphEditorForm は `0x1306a38`〜`0x1306a4a`、TPublicChannel は `0xfe2ec8`〜`0xfe2ed8`。
- 親フィールド (`-0x78`) の値は、親 VMT のポインタを格納した位置。その位置の値が親 VMT (表の括弧内)。

## 2. 受入 1: P の型

- `0x86a4cf` の `call [A-0x30]` (A = `0x13063c8`) は factory `0x40f960` で、`dword[A-0x80]` (= `0x840`) のサイズを確保し、`0x40fb40(this=A, X)` が `*X = A` (VMT 書込み) する (`REPORT_PY67.md` §5.1)。よって P の VMT は A。
- A の TypeInfo 名は `TGraphEditorForm`。`0x1306dbf`・`0x130760f` の `+0x794` 書込みは P (= TGraphEditorForm) のフィールドへの書込み。
- P は chan の系統 (`TChannel`) ではない。親は `TChildVectorForm` (`0x803168`)。

## 3. 受入 2a: 所属

- `0xffe370` は `TPublicChannel` (VMT `0xfe2cf8`) のスロット 52 (`+0x1a0`)。
- 親の `TChannel` の同スロットは `0xfed770` で別の実装。`0xffe370` は TPublicChannel が上書きした実装と読める (上書きの有無は VMT の比較で確認)。

## 4. 受入 2b: 呼出し元 (未達)

- `python3 analysis/py71_slotcallers.py "$P" 0xfe2cf8 0x1a0` の実測:
  - スロット呼出し `call qword ptr [reg+0x1a0]`: 37 件 (`.text` 全体)。
  - クラス参照 (VMT-0xc8 または VMT 自身を RIP 相対・即値で持つ) を持つ関数: 56 件。
  - 両方を持つ関数: 0 件。
- 解釈: slot 52 は `TChannel` 系の仮想メソッドで、TChannel 型の受け手も同じ `call [reg+0x1a0]` で `0xffe370` (TPublicChannel の実装) に分岐しうる。37 件のうち TPublicChannel 受けの件数は、受け手の型が分からないと決まらない。
- 限界: 関数先頭は int3 パディングの直後で近似する (分割・統合の誤りを含む)。受け手の型は追跡していない。

## 5. 受入 3・4 (未達)

- 本 run では解析していない。`REPORT_PY67.md` §5.5 の未解決 (`0xec60ae` の `[rbp+0x120]`・`0x8ed012` の `[rbp+0x70]` の出所) がそのまま残る。
- 次の手順 (提案): 受け手の値について、VMT のポインタを書く箇所 (即値・RIP 相対 `lea` で VMT を格納する命令) と、VMT-0xc8 の読出しを探す。見つかれば §1 の表で型と chan の判定が決まる。

## 6. 測定

- 素材: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 バイト)。`tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (2.8 秒)。`tools/**/work/` は使わない。
- 測定 commit: `91d7db52` (スクリプト追加・コードを変えた最後の commit)。基点 origin/main `e1e816c2`。
- 差分 0 の証跡 (測定 commit から HEAD までのコード範囲):

  ```
  $ git diff 91d7db52 HEAD -- tools/python/analysis tools/python/src
  (出力 0 行)
  ```

- 実測 (HEAD `91d7db52`・逐次・load は実行前の 1 分平均):
  - `py71_vmt.py "$P" 0xfe2cf8,0x13063c8,0xfe2978 0x1a0`: 0.03 秒 (load 0.20)。
  - `py71_slotcallers.py "$P" 0xfe2cf8 0x1a0`: 87.3 秒 (load 0.20)。出力は §4 の件数。
- 再現: `cd tools/python` の後、上の 2 コマンド (`P=$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `call [reg+0x1a0]` 37 件の受け手の型 (TPublicChannel 受けの件数) | 受入 2b | #2501 (Refs で残す) |
| `0xec60ae` の `[rbp+0x120]` の型と出所 | 受入 3 | #2501 |
| `0x8ed012` の `[rbp+0x70]` の出所と chan 判定 | 受入 4 | #2501 |
| 本 REPORT の chan の定義 (TChannel 系) と依頼文の chan の定義の照合 | 受入 3・4 の判定基準 | #2501 |
