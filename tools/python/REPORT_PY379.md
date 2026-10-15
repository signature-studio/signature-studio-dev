# tools/python REPORT: PY-379 launchMapPages の例外化の述語 (vt[+0x88]) と -2・-7 の gate の PE 同定 (#4765・親 #3746)

既知類型との関係: 該当なし (PE の読取りのみ。lift・IR の変換は行っていない。`docs/DEFECTS.md`・`tools/icall/REPORT.md` の類型とは照合していない)

## 結論

- **旧記録の「vt[+0x88] は実行時にしか決まらない」は誤りだった。** `[0x15e4790]→[+8]` の O は、静的に VMT `0x125b1c0` (`NewInstance` `0x40f960` が作るクラス) に決まる。`[0x141d6b8]` の値は実行時に入るが、その入る値は ctor `0x125da90` (VMT 参照は `[0x125b0f8]` = `0x125b1c0`) の返すオブジェクトである。
- **例外化の述語 (vt[+0x88]) の実体を同定した**: `VMT+0x88` = `0x1262a90`。中身は「フラグ 2 つ (`[0x16baff0]`・`[0x16baff1]`) がともに 0 かつ `vt[+0x48]` が偽 のとき真」。`vt[+0x48]` = `0x1262950` は `[0x13e7628]` (`.data` 1 byte・初期値 0) を返すだけ。
- **gate (-2・-7) の述語 vt[+0x98] も同定した**: `VMT+0x98` = `0x1262b80`。`vt[+0x48]` が偽、かつ `[[0x15e0…]+0x168]` (`dword`) > 0 のとき真。
- 受入条件「述語と -2・-7 の gate を REPORT に残す」は、本 REPORT で述語の VA と判定式を残した。**ただし 2 つのフラグ `[0x16baff0]`・`[0x16baff1]` の実行時の値を決める書込み元は未確定**のため、述語の真偽は静的には決まらない (下の未解決)。

## 手段

- 素材: `fl-win64` の `extracted/block00031_PE.bin` を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py379 --wildcards '*block00031_PE.bin'` で展開 (`work/` は gitignore)。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> [命令数]`。
- 二重間接の列挙: `pe_chain_stores.py 0x15e4790 8` (約 72 秒・store 候補 2 件)。
- 書込み列挙: `pe_xref.py`・`pe_slot_writers.py` (各約 60 秒)。
- 静的な値の読取り: 下の一時スクリプト (ファイル上の値と RVA→ファイル位置の変換)。`pefile` を使用。

## 鎖の確定 (PE 上)

| 段 | VA | 内容 |
|---|---|---|
| G | `0x15e4790` | `.data`。ファイル上の値 `0x141d6b8` (Q スロット) |
| Q | `[0x141d6b8]` | ファイル上 0。実行時に `0x976a90` (遅延生成) が ctor `0x976b60` の戻り値を格納 (`0x976aad`) |
| O | `[Q+8]` | ctor `0x976b60` が `[Q+8] = 0` (`0x976b9c`)。非 0 の格納は `0x1263571` (`0x1263540` 内) と `0x1264145` (`0x1264112` 内) の 2 件。いずれも `0x125da90` の戻り値 (rax) を格納 |
| O の生成 | `0x125da90` | 4 KB 超のフレームを持つ生成関数。呼出し元 `0x1263540`・`0x1264112` が `rcx = [0x125b0f8]` (ファイル上 `0x125b1c0` = VMT) を渡す。生成の全経路 (VMT-0x30 = `0x40f960` の先) は未読 |
| VMT | `0x125b1c0` | `VMT+0x88` = `0x1262a90` (例外化の述語)・`VMT+0x98` = `0x1262b80` (gate の述語)・`VMT+0x48` = `0x1262950` |

- 旧記録 (REPORT_PY119_2977・REPORT_PY120_2984・REPORT_PY139_3030 の「vt[+0x88] / vt[+0x98] は実行時のオブジェクトなので静的に同定できない」) は、この鎖で書き換える。

## 述語の中身 (PE の読取り)

### 例外化の述語 `VMT+0x88` = `0x1262a90`

```
mov rax, [0x15e04a8]; cmp byte [rax], 0; jne → 偽 (al=0)
mov rax, [0x15e0ff0]; cmp byte [rax], 0; jne → 偽
rcx = this; call [vt+0x48] (= 0x1262950) ; test al, al ; jne → 偽
→ 真 (al=1)
```

- `[0x15e04a8]`・`[0x15e0ff0]` は `.data` の pointer slot。ポインタ先 `0x16baff0`・`0x16baff1` は `.bss` (ファイル上は無い・実行時)。
- `vt[+0x48]` = `0x1262950`: `mov rax, [0x15e1890]; movzx eax, byte [rax]; ret`。`[0x15e1890]` の先 `0x13e7628` は `.data` 1 byte (初期値 0)。
- 真偽の意味: `[0x16baff0]`・`[0x16baff1]` が 0 で、`[0x13e7628]` も 0 のとき、例外化の判定は真。

### gate の述語 `VMT+0x98` = `0x1262b80`

```
mov rax, [0x15e04a8] (→ 0x16baff0); cmp byte [rax], 0; jne → 偽
mov rax, [0x15e0ff0] (→ 0x16baff1); cmp byte [rax], 0; jne → 偽
rcx = this; call [vt+0x48] (= 0x1262950) ; test al, al ; jne → 偽
rax = [0x15e30f8] (→ 0x15f7190) ; cmp dword [rax+0x168], 0 ; jle → 偽 (al=0)
→ 真 (al=1)
```

- gate 述語は、例外化の述語と同じフラグ 2 つと `vt[+0x48]` を見る。加えて、`[0x15e30f8]` の先 (`.data` の `0x15f7190`) の dword `+0x168` が 0 より大きいことを要求する。`general.safeToEdit` (0xd6a2c0) と同じ述語かは未確認 (下の未解決)。

## -2・-7 の経路 (PE の確定)

- `0xd82c20(status)` の負の code 経路 (`0xd82c6a`〜`0xd82c86`): `[0x861b1f]→[+8]→vt[+0x88]` (= 上の例外化の述語) が偽なら例外を立てず `0xd82dd0` (= `0xc38bc0`・None 相当)。真なら文言の例外 (-2 "Operation unsafe at current time"・-7 "Device not assigned")。
- `0x861b1f` の RIP 先は `0x15e4790` (G) と同じ `.data` の O 経路。ゆえに gate の -2 は述語 `vt[+0x88]` の真偽で決まる (REPORT_PY125 の「報告ゲート R」と同一 slot と見てよいが、一致の確認は未実施)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| フラグ `[0x16baff0]`・`[0x16baff1]` (`.bss`) の書込み元。`pe_slot_writers.py` の候補は 20・23 件 (store byte) で、どれが `0x16baff0`/`0x16baff1` 自体への書込みかは未確定 | 例外化の述語 `vt[+0x88]` の真偽が静的に決まらない。-2・-7 の発生条件 (gate 偽のとき例外か None か) が未確定 | #3746 (PY-244) |
| `[0x13e7628]` (`vt[+0x48]` のフラグ) の書込み元 | 同上 (`vt[+0x48]` の値) | #3746 |
| `vt[+0x98]` の `[0x…]+0x168` (dword) と `general.safeToEdit` (0xd6a2c0) の slot の同一性 | gate の判定が safeToEdit と同じかは未確認 | #3772 (PY-250) |
| 本 REPORT の鎖 (G→Q→O→VMT) の実行時照合 (boot 中の `[0x141d6b8]+8` の VMT 値) | 静的な確定を実行時で確かめていない | #3028 (boot 停止点の後) |

## 検証

- 測定 commit: 本 PR の変更は REPORT のみ (コード変更なし)。
- 実行したコマンドと実測値は上の「手段」に記す。素材 `fl-win64` の展開: 約 3 秒。`pe_chain_stores.py` 約 72 秒、`pe_xref.py` 約 63 秒、`pe_slot_writers.py` 約 64 秒 (1 回ごと)。
- 負のコントロール: 未実施 (本 PR はコードを変えていない。静的解析の結論を覆す検査は、上の書込み列挙の範囲のみ)。
