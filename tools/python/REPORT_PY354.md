# tools/python REPORT: PY-354 戻り値 out+0x08 の出所 (PE) (#4682, 親 #3024 (PY-155))

> 前段: `tools/python/REPORT_PY141.md` (PY-141・#3034)。0x415610 が out+8 に作用しないことと、0xd84680 経路の out+8 の未確定を確定済み。本書は undo 系 (PY-155 #3024 の受入 3) の経路で同じ問いに答える。
> 検算: `analysis/flapi/pe_py354_probe.py` (`FL_WIN64_DIR=<展開先>`)。素材は fl-win64 (`extracted/block00031_PE.bin`)。

## 結論

- **undo 系の戻り値 `out+0x08` の出所: PE からは確定できない。** 成功経路に out+8 への書込みが無い (未初期化)。
  - undo 系 4 呼出し (`0xd68e0e` cmd 0x14・`0xd68ece` 0x15・`0xd68f8e` 0x16・`0xd69070` 0x16) は、`out` (`[rbp+0x48]`) を `0x415610` と `0xd84680` に渡す。`out+0x08` (`[rbp+0x50]`) はどの store でも書かれない。
  - `0xd84680` は out への store が `out+0` の 3 箇所だけ (`0xd846b7`・`0xd846c0`・`0xd846c9`)。`out` (rbx) は `0xfdd2c0` に渡らない。
  - `0x415610` (関数末尾 `0x4158b2`) は、`out` の書込みを managed field の経路 (`[rbp+0x38]` = `arg + FldOffset`) だけで行う。ローカル (`[rbp+...]`) 以外の store は `0x4157b9` (`[rax]`) と `0x4157c8`〜`0x4157cc` (`stosq [rdi]`) の 2 系統で、どちらも `out+0x08` を書かない (`[rbp+0x38]` の値は `out+FldOffset`)。
  - 実行時には `[rbp+0x50]` の値が `ecx` として vtable 呼出し (`0xd68e26`・`call qword ptr [rax]`) に渡される。この vtable 先は未同定。
- **`0x415610` の managed 種別の分岐 (逆アセンブルで確認)**: `eax` = 種別 (`movzx eax, byte [rax]`、0x415777)。種別 18 (`string`) は `0x41579d`→`0x4157a4`→`0x4157aa` を経て `0x4157b5` の `mov qword ptr [rax], 0` (`0x4157b9`) に入り、8 バイトだけを 0 にする。`stosq` の 3 回 (`0x4157c8`〜`0x4157cc`、0x18 バイト) は種別 10 の枝 (`sub eax, 0xa` の後の `je 0x4157c2`、0x415790) だけで、`string` のフィールドは通らない。
- 前段 PY-141 の「0x415610 は out+0x10 だけを 0 にする」は、この分岐の確認でも崩れない (`string` の経路は `[rax]` の 8 バイトだけ)。

## 確定・保留

| 項目 | 判定 | 根拠 (VA) |
|---|---|---|
| undo 系の呼出し (cmd 0x14/0x15/0x16) | 確定 | `0xd84680` の呼出し元のうち、直前の `r8d` が 0x14/0x15/0x16 のもの 4 件 (`0xd68e0e`・`0xd68ece`・`0xd68f8e`・`0xd69070`) |
| undo ハンドラの out | 確定: `[rbp+0x48]` | `0xd68dc0` 先頭で `lea rcx,[rbp+0x48]` → `0x415610` (`0xd68dd8`) |
| `0xd84680` の out への store | 確定: `out+0` だけ | `0xd846b7`・`0xd846c0`・`0xd846c9` (`qword ptr [rbx]`) |
| `0xd84680` が out を `0xfdd2c0` に渡すか | 確定: 渡さない | `0xfdd2c0` の呼出し前に `, rbx` で終わる mov が無い |
| `0x415610` の store の内訳 | 確定: `out+FldOffset` (0x10) と stosq (kind 10 枝 0x18 バイト) | `0x415610`〜`0x4158b2`、全 20 store を列挙。`stosq` は kind 10 枝 `0x4157c2` の内側だけ |
| undo 4 ハンドラの `out+8` への store | 確定: 無し | `0xd68dc0`・`0xd68e80`・`0xd68f40`・`0xd69000` の関数内に `[rbp+0x50]` への mov 無し |
| `0xd843d0` 経路の `out+8` | 確定: `0xd844c6` の 1 箇所 (値は `[obj+0x10]`) | PY-141 と同じ。undo 系は `0xd843d0` を呼ばない |
| **undo 系の戻り値の値 (out+8 の実行時の値)** | **保留 (PE から未確定)** | 成功経路で `[rbp+0x50]` は書かれず、呼出し前の値は caller の未初期化スロット |
| `0xd68e26` の vtable 先 (`[0x87b45a]` が指す関数) | 未同定 | 戻り値へ `out+8` を `ecx` で渡す。変換先が `PyLong_FromLong` か否かは未確認 |

## 実機で観測する方法 (PE で確定できないため)

`unicorn` は未導入 (`ModuleNotFoundError`)。本 run では導入せず、観測の方法だけを書く (受入 3 の「確定できなければ」)。

1. 実機 (FL Studio 26.1.7 win64) で undo 系の `ui.undo()` を 1 回呼ぶ。
2. デバッガで `0xd68e26` (undo ハンドラの `call qword ptr [rax]`、`ecx = dword [rbp+0x50]`) にブレークを張り、呼出し直前の `ecx` と `[rbp+0x50]` (8 バイト) を読む。
3. 呼出し直前の `[rbp+0x50]` が前回呼出しの残り (スタックのゴミ) か、`0` かを、呼出し前後で 2 回読んで比べる。
4. 結果を `REPORT_PY354.md` の実測節に追記する (実機の観測は人間オーナーの手元で行う。本 issue では求めない)。

## 手段

- 逆アセンブル: `analysis/flapi/pe_disasm.py <VA> <命令数>` (`FL_WIN64_DIR` 指定)。
- 検算: `analysis/flapi/pe_py354_probe.py`。5 群を assert する: (1) undo 系の呼出しを `r8d` の即値で列挙、(2) `0xd84680` の out store と `0xfdd2c0` の引数、(3) `0x415610` の +8 オフセットの有無、(4) `0xd843d0` の `[rsi+8]` の 1 箇所、(5) undo 4 関数の `[rbp+0x50]` への mov 無し と、`0xd68dc0` の `out` 渡し。
- `0x415610` の store 列挙は一時スクリプト (commit しない)。probe の (3) は `+8` のテキストだけを見るので、store 列挙の結果を本書の表で補う。

## 検証

- 測定 commit: `3dff75fd4` (`test(python): PY-354 out+8 writer check probe`。probe のコードを変えた最後の commit)。REPORT の文言だけを変える後続 commit は測定に影響しない。
- 測定 commit から HEAD までの probe 差分: 0 (`git diff 3dff75fd4 HEAD -- tools/python/analysis/flapi/pe_py354_probe.py` の出力は空)。
- 実測 (測定 commit `3dff75fd4`、素材 fl-win64・展開先 `/tmp/opencode/fl`):

| コマンド | 結果 | wall | load |
|---|---|---|---|
| `FL_WIN64_DIR=/tmp/opencode/fl python3 analysis/flapi/pe_py354_probe.py` | PASS (rc 0・全項目 ok) | 3.712 秒 | 0.12 / 0.20 / 0.12 (11:02 UTC) |
| 既存の検算 `analysis/flapi/pe_py141_probe.py` (回帰確認・素材同じ) | PASS (rc 0・「PASS」行を確認) | 未計測 | 未計測 |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| undo 系の戻り値の値 (out+8 の実行時の値) | undo 5 関数の戻り値の値。mock の戻り値を PE から決められない | 本書の「実機で観測する方法」 (受入 3 の代替手段。実機観測は人間オーナーの手元で行う) |
| `0xd68e26` の vtable 先の同定 | out+8 を変換する関数が `PyLong_FromLong` か否か | 起票なし (次の PY-155 の解析で扱う。#3024 の受入に含まれる) |
| 実機での観測 | 上の「実機で観測する方法」の結果 | 起票なし (人間オーナーの手元。issue 本文で求めない) |
