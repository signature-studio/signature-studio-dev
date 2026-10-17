# #6246 (CI-258): function_f552a0 の間接 call `[rsi+0x18]` の写し落としと脱出後 call の第 1 引数 (親 #5995)

既知類型との関係: D15 (メモリ間接 call の欠落。f55396 について)

## 1. 結論

- **受入 1 (間接 call `f55396`)**: IR に写っていない。本 run では写さない。callee は実行時の vtable (`*arg1` の `[+0x18]`) で決まり、静的に関数 VA へ解決していないため。写すには callee の解決が要る (lift 側の別 PR・§4)。
- **受入 2 (`f5539c` の第 1 引数)**: #5999 と同じ原因。IR は loop-carry の `%rcx.1.reload` (`%arg1` と `%21` の合流) を使い、機械語は `*arg1` (`f55399: mov rcx, [rbx]`)。既存の修正 pass `ldfix/fix_f552a0.py` は脱出後の call (`%45`) も `*arg1` に直し、判定器 6/6 OK。
- 修正 pass は既定 OFF のままで、この PR では IR 生成を変えない。REPORT の追記と分割移動のみ。

## 2. 機械語 (boot3.drc.dsm・probe M1)

| VA | 命令 | 意味 |
|---|---|---|
| f5538d | `mov rax, [rbx]` | `rax = *arg1` (`rbx = arg1`) |
| f55390 | `mov rcx, rax` | this = `*arg1` |
| f55393 | `mov rsi, [rax]` | vtable |
| f55396 | `call [rsi+0x18]` | 間接 call (this = rcx・戻り値は後で使われない) |
| f55399 | `mov rcx, [rbx]` | 脱出後の第 1 引数 = `*arg1` |
| f5539c | `call 0x12df760` | 直接 call (第 1 引数 = `*arg1`) |

## 3. IR の照合 (probe M2・M3)

`ldfix/probe_f552a0_6246.py` で、機械語の列 (M1) と脱出ブロック `dec_label_pc_f5538c` の call 件数 (M2) を見る。

| IR | 間接 call | 直接 call の第 1 引数 | probe |
|---|---|---|---|
| `work/boot_final3.ll` (素材) | 0 件 | `%rcx.1.reload` | M1 OK・M2 OK |
| `work/boot_final.ll` (#5999 の入力) | 0 件 | `%rcx.1.reload` | M1 OK・M2 OK |
| `boot_final.ll` に `fix_f552a0.py` を適用 | 0 件 | `%fx5999o45` (= `*arg1`) | M1 OK・M2 OK |

- 判定器 `judge_arg1_5999.py`: 素材の IR は calls=6 ok=0 ng=6 (`%rcx.1.reload` の出所 `{arg1, %21}`)。修正後は calls=6 ok=6 ng=0。
- `fix_f552a0.py` は素材 `boot_final3.ll` を `define weak` の見出しで拒否する (fail-closed)。`boot_final.ll` (`define i64`) なら適用できる。素材の見出しの違いは未確認。

## 4. 間接 call を写さない理由

- 脱出ブロックに `f55396` に当たる call が無い。機械語の `call [mem]` が IR で落ちる類型は DEFECTS の D15 と同じ (`vtable` 読出しと `mov rcx` は残り、call だけ消える)。
- `REPORT_3382.md` の補足 (`f55396` は IR で間接呼出しとして出ない。callee が特定の関数 VA ではないため判定の対象外) と一致。
- 写すには、`*arg1` の vtable を静的に解決して slot `+0x18` の target VA を得る必要がある。本 run では解決していない。`m11_icall` (`m11_ov.c`) で動的に解決するなら、miss の扱いを決める必要がある。
- 返り値は使われない。書込みの有無は callee 次第で、未確認。silent miscompile の候補として残る。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `f55396` の callee (`*arg1` の vtable slot `+0x18`) の解決と間接 call の写し | 書込みを持つ callee が落ちると結果が変わる候補 | #6252 (CI-259・`親: #5995` の子・lift 側の別 PR) |
| 修正 `fix_f552a0.py` の既定 ON の判断と e2e 効果 | 本 run では IR を変えず未測定 | #6253 (CI-260・`親: #5995` の子。#5999 は CLOSED のため使わない) |

## 6. 測定

- 測定コマンド: `python3 ldfix/probe_f552a0_6246.py work/boot3.drc.dsm work/boot_final3.ll` (rc 0)、同 `work/boot_final.ll`、同 修正後の IR (rc 0)。
- 測定 commit: `fc6b9368e` (コードを変えた最後の commit。PR 本文と同じ)。
- e2e は未実行。IR 生成・lift のコードを変えていないため (KPI は起動に関わらないので書かない)。
- 素材: `work-m11` のみ展開 (`tools/m11/work/`、展開 2.4 秒)。`fl-win64` は取得済みだが展開していない (本 run の probe は `work/boot3.drc.dsm` を使うため不要)。
