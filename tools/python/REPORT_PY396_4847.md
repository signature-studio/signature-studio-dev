# PY-396 (#4847・親 #3817): Q を返す `0x416091` の呼出元と、戻り値 Q の先の `[Q+8]` 書込み

親 #3817 の受入 3 を切り出した issue。Q = `[[0x15e4790]]` (setChannelPitch の guard の対象)。

## 結論

- Q を `rcx` に載せて `0x415c30` を呼ぶ直接 call は **1 件** (`0x40fc2c`)。
- その戻り値 (`rax` = Q) は `0x40fc31` の `mov rax, [rsi-0x78]` で上書きされ、**使われない**。
- よって戻り値 Q から `[Q+8]` への書込みは **0 件** (追う先が無い)。受入 3 は満たした。

## 関数 `0x415c30` の戻り値 (PE で確認)

- `0x415c40`: `mov [rbp+0xb0], rcx` (第 1 引数を保存)。
- `0x415cab`〜`0x415cb2`: `mov rax, [rbp+0xb0]`; `mov [rbp+0x48], rax`。
- `0x416079`〜`0x416091`: `mov rax, [rbp+0xb0]`; `mov [rbp+0x48], rax`; `mov rax, [rbp+0x48]`; `ret`。
- つまり `0x415c30` は第 1 引数をそのまま返す。`0x416091` はその `ret`。

## 測定 1: Q の流れ (既存 probe `analysis/flapi/pe_chain_alias.py`)

コマンド: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_chain_alias.py 0x15e4790 8`

| 項目 | 件数・内容 |
|---|---|
| seed (G・Q スロットの `mov r, [..]`) | 2425 |
| 追跡した状態 | 8742 (ret 止まり 23) |
| `callee-arg` (rcx = Q で呼ぶ直接 call) | 22 件。`0x415c30` へは **`0x40fc2c` の 1 件** |
| `ret-with-Q-in-rax` | `0x416091` 1 件 (= `0x415c30` 内。Q を返す ret) |
| `[Q+8]` 非 0 書込み | 2 (`0x1263571`・`0x1264145`。前段と同じ) |

- 前段 REPORT_PY72_APPENDIX_3212 §8 と比べて、`[Q+8]` 書込み 2 件・load 278 件・callee 22 件・indirect Q 引数 8 件は変わらない。

## 測定 2: `0x415c30` の全直接 call 元 (Q に限らない・参考)

コマンド: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_ret_propagation.py 415c30`

| 分類 (call 直後の rax) | 件数 |
|---|---|
| CLOBBER (書き換えてから抜ける。戻り値は捨てられる) | 906 |
| RET (書き換えず ret まで届く) | 801 |
| READ (戻り値を後続で読む) | 18 |
| 合計 | 1725 |

- READ の 18 件は `mov r8, rax` で戻り値を次の関数の引数に渡すもの (例 `0x49658b`・`0x497064`・`0x497140`)。戻り値の利用は実在する。ただし `rcx` に Q が載るのは `0x40fc2c` だけ (測定 1) なので、Q の問いには関係しない。
- RET の 801 件は `rcx` が何であっても戻り値が上位へ伝わる、という意味で、Q が伝わるとは限らない。Q の流れは測定 1 で確定する。
- 前 run (run 38735524097) は rax を読む候補 50 件を `xor eax,eax` 後の `stosq` (ゼロ埋め) と判定した。本 probe は `xor eax,eax` を先に CLOBBER と数えるので、同じ箇所はこの分類に入る (rax の値は 0 で、戻り値ではない)。

## 測定 3: `0x40fc2c` 周辺 (逆アセ)

- `0x40fc2c`: `call 0x415c30`。
- `0x40fc31`: `mov rax, [rsi-0x78]`。戻り値 rax はここで捨てられる。
- `0x40fc35`〜`0x40fc40`: rax のテストとループ (`mov rax, [rax]`)。Q を使わない。

## 限界

- 測定 1 は seed (G と Q スロットからの `mov r, [..]`) から始まる追跡。seed を経ない別名は対象外 (probe の docstring どおり)。
- 間接 call の先は追わない。`0x415c30` 内の `call [rbx+0x11]` (`0x415ca8`) は Q 引数の間接 call で、#4848 (PY-397) の範囲。

## 測定

- 測定 commit: `814f2ebba` (probe `pe_ret_propagation.py` を追加した最後のコード commit)。HEAD で再現した。
- 素材: `$HOME/artifacts/fl-win64.tar.zst` の `extracted/block00031_PE.bin` (22,227,016 B)。展開 2.2 秒。
- 再現: 上記 2 コマンド。測定 2 は HEAD で 0.6 秒 (1725 件)。測定 1 は 46.6 秒 (load は未計測)。
- 差分: `git diff 814f2ebba HEAD -- tools/python/analysis` は REPORT 追記のみで、解析コードは変わらない。
