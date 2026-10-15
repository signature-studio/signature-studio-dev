# tools/python REPORT: PY-354 戻り値 out+0x08 の出所 (PE) (#4682, 親 #3024 (PY-155))

> 前段: `tools/python/REPORT_PY141.md` (PY-141・#3034)。0x415610 が out+8 に作用しないことと、0xd84680 経路の out+8 の未確定を確定済み。本書は undo 系 (PY-155 #3024 の受入 3) の経路で同じ問いに答える。
> 検算: `analysis/flapi/pe_py354_probe.py` (`FL_WIN64_DIR=<展開先>`)。素材は fl-win64 (`extracted/block00031_PE.bin`)。

## 結論

- **undo 系の戻り値 `out+0x08` の出所: PE からは確定できない。** 成功経路に out+8 への書込みが無い (未初期化)。
  - undo 系 4 呼出し (`0xd68e0e` cmd 0x14・`0xd68ece` 0x15・`0xd68f8e` 0x16・`0xd69070` 0x16) は、`out` (`[rbp+0x48]`) を `0x415610` と `0xd84680` に渡す。`out+0x08` (`[rbp+0x50]`) はどの store でも書かれない。
  - `0xd84680` は out への store が `out+0` の 3 箇所だけ (`0xd846b7`・`0xd846c0`・`0xd846c9`)。`out` (rbx) は `0xfdd2c0` に渡らない。
  - `0x415610` (関数末尾 `0x4158b2`) は、`out` の書込みを managed field の経路 (`[rbp+0x38]` = `arg + FldOffset`) だけで行う。ローカル (`[rbp+...]`) 以外の store は `0x4157b9` (`[rax]`) と `0x4157c8`〜`0x4157cc` (`stosq [rdi]`) の 2 系統で、どちらも `out+0x08` を書かない (`[rbp+0x38]` の値は `out+FldOffset`)。
  - 実行時には `[rbp+0x50]` の値が `ecx` として vtable 呼出し (`0xd68e26`・`call qword ptr [rax]`) に渡される。この vtable 先は未同定。
- **`0x415610` の managed 種別の分岐 (逆アセンブルで確認)**: `eax` = 種別 (`movzx rax, byte ptr [rax]`、0x415777)。`0x4157b9` (`mov qword ptr [rax], 0`) は種別 18 (`string`) と、種別 10・11 の枝 (`0x4157b5` へ入る) が通る 8 バイト store。`stosq` の 3 回 (`0x4157c8`〜`0x4157cc`、0x18 バイト) は `0x415792` の `je 0x4157c2` (`eax = kind - 12 == 0`、kind 12 の枝) だけから入る。
- 書込み先の基底は両方とも `[rbp+0x38]` (= `arg + FldOffset`。`FldOffset` は記述子の `dword [entry+0x12]` から読む実行時値)。`out` (`[rbp+0x48]`) の本体への直接の store は `0x415610` 内に無い。
- 前段 PY-141 の「0x415610 は out+0x10 だけを 0 にする」は、この分岐の確認でも崩れない (`string` の経路は `[rax]` の 8 バイトだけ)。
- 列挙の再現: `analysis/flapi/pe_py354_probe.py` の (3b) が、関数内の非フレーム store が `0x4157b9` と `stosq` ×3 の 4 命令だけであること、その基底と `je` の入口を assert する。

## 確定・保留

| 項目 | 判定 | 根拠 (VA) |
|---|---|---|
| undo 系の呼出し (cmd 0x14/0x15/0x16) | 確定 | `0xd84680` の呼出し元のうち、直前の `r8d` が 0x14/0x15/0x16 のもの 4 件 (`0xd68e0e`・`0xd68ece`・`0xd68f8e`・`0xd69070`) |
| undo ハンドラの out | 確定: `[rbp+0x48]` | `0xd68dc0` 先頭で `lea rcx,[rbp+0x48]` → `0x415610` (`0xd68dd8`) |
| `0xd84680` の out への store | 確定: `out+0` だけ | `0xd846b7`・`0xd846c0`・`0xd846c9` (`qword ptr [rbx]`) |
| `0xd84680` が out を `0xfdd2c0` に渡すか | 確定: 渡さない | `0xfdd2c0` の呼出し前に `, rbx` で終わる mov が無い |
| `0x415610` の store の内訳 | 確定: `[rbp+0x38]` 基底 (`out+FldOffset`) への 8 バイト store (`0x4157b9`) と `stosq` ×3 (`0x4157c8`〜`0x4157cc`、kind 12 枝 `0x4157c2` だけから入る) | `0x415610`〜`0x4158b2` の非フレーム store を probe (3b) が列挙して assert (`analysis/flapi/pe_py354_probe.py`) |
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
- probe の限界: (5) の undo 検査は `[rbp+0x50]` の文字列だけを見る。out を別レジスタへ写した後の store は検出しない。(3b) は `0x415610` の非フレーム store を全件列挙するが、`0x415610` の外 (呼出し先) の書込みは対象外。種別 10・11 の分岐 (`0x4157b5` へ入る経路) は probe で assert せず、逆アセンブルの目視確認のみ。

## 検証

- 測定 commit: `38e8ba9bf` (probe のコードを変えた最後の commit)。以降の commit は REPORT の文言だけを変える。
- 測定 commit から検証 HEAD までの probe 差分: 0 (`git diff 38e8ba9bf HEAD -- tools/python/analysis/flapi/pe_py354_probe.py tools/python/analysis/flapi/pe_py141_probe.py` の出力は空)。
- 検証 HEAD: `5e66804da` (probe のコードは `38e8ba9bf` から無変更。`5e66804da` は REPORT の検証節だけを変える)。
- 実測 (HEAD `5e66804da`、素材 fl-win64 の `extracted/block00031_PE.bin` だけを展開):

| コマンド | 結果 | wall | load |
|---|---|---|---|
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py354_probe.py` | PASS (rc 0・全 13 項目 ok) | 3.54 秒 | 0.52 / 0.35 / 0.14 (11:20 UTC、開始時) |
| 既存の検算 `analysis/flapi/pe_py141_probe.py` (回帰確認・素材同じ) | PASS (rc 0・「PASS」行を確認) | 0.23 秒 | 0.56 / 0.36 / 0.14 (11:20 UTC、終了時) |

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| undo 系の戻り値の値 (out+8 の実行時の値) | undo 5 関数の戻り値の値。mock の戻り値を PE から決められない | #3024 (PY-155)。受入 3 の残り (実機観測の手順は本書の「実機で観測する方法」) |
| `0xd68e26` の vtable 先の同定 | out+8 を変換する関数が `PyLong_FromLong` か否か | #3024 (PY-155)。受入 1・3 の解析範囲 (親の受入に含まれる。子は起票しない) |
| 実機での観測 | 上の「実機で観測する方法」の結果 | #3024 (PY-155)。人間オーナーの手元の作業で、結果は #3024 のコメントに残す |
