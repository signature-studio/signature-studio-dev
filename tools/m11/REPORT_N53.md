# M11 REPORT (#953 / 親 #131): sigfix 0 詰め引数の理由別分類と退行検査

結論: **部分達成**。0 詰め 1,963 引数 (1,049 site) の理由別分類を `m11_argrecover.py` に追加し REPORT に実測を残した。`M11_SIGFIX_RECOVER=1` の survey は既定と同数 (ok 870 = 870) で退行なし。未復元 1,550 引数の**データフロー復元は未達**で、子 #1154 ([M11-N68]) に分離した。

## 1. 理由別の内訳 (`m11_argrecover.py`, `work/sigfix_pads.json` 1,049 site 由来)

`why:` は分類結果ごとの理由。`boundary` = 窓が call / jmp / jcc / ret / 分岐先で切れた, `entry` = 関数入口まで代入が無い (caller の live-in を素通し), set 系の `load` / `reg` / `arith` / `other` = 代入命令の型。

| 分類 | 引数数 | 理由 (内訳) |
|---|---:|---|
| callee_unused | 313 | (callee が読まない: 0 詰めは無害) |
| set_const (復元済) | 18 | load 2 / arith 5 / other 11 |
| set_const_xmm_callee (復元せず) | 48 | load 7 / arith 11 / other 30 |
| set_other | 378 | load 226 / reg 103 / arith 14 / other 35 |
| stack_set_other | 32 | reg 10 / other 22 |
| inherit | 1,172 | boundary 1,119 / entry 53 |
| callee_nopdata | 2 | - |

未復元 1,550 引数 (inherit 1,172 + set_other 378 + stack_set_other 32 + 一部 xmm) の内訳は、`boundary` (窓の切れ目の向こう側の def を要する) が最多 1,119 で、`set_other:load` 226 (メモリ読出し由来) が次に大きい。

## 2. 検証

| 項目 | 結果 |
|---|---|
| 分類の再現 | `m11_argrecover.py` の分類 (kind) と fixes は理由追加前後で完全一致 (`args same: True`, `fixes same: True`) |
| 別アルゴリズム検算 `m11_argrecover_verify.py` (`work/sigfix_fixes.json`, 18 件) | **18/18 一致** (mismatch 0) |
| `m11_e2e.sh` `M11_SIGFIX_RECOVER=0` (同一 IR `ir_sha256` 1fc847…) | reached_stage 4/6, units_run 53/942, **survey ok 870 / trap 25 / miss 46 / noproc 1 / clobber 0**, judge rc 0, e2e 41.5 秒 (増分) |
| `m11_e2e.sh` `M11_SIGFIX_RECOVER=1` (同一 IR) | reached_stage 4/6, units_run 53/942, **survey ok 870 / trap 25 / miss 46 / noproc 1 / clobber 0**, judge rc 0, e2e 125.5 秒 (boot5 を含む IR の再生成込み) |
| 受入条件 2 (`M11_SIGFIX_RECOVER=1` で survey 退行無し = ok 数 ≥ 既定) | 870 ≥ 870 で**満たす** |

注: 同じ `m11_e2e.sh` 経路で作った IR (`boot5` 込み) の指紋は `1fc847…` で、検証の初回 (手動 build 経路、`boot5` 無し) の `39008e…` とは別物。survey の ok 数 869 は手動経路の値で、e2e 経路の 870 とは比較しない。

## 3. 受入条件の判定

* 受入 1 (set_other / inherit を実値化、または「復元不能」と分類した件数を REPORT に残す): **部分達成**。理由別の分類件数は §1 で実測を残した。ただし「復元不能」として確定させた件数は無い (全件が「未復元」)。実値化は 0 件 (既存の 18 件のみ)。残りは子 #1154 (`[M11-N68]`) で扱う。
* 受入 2 (`M11_SIGFIX_RECOVER=1` の e2e で survey の退行無し): **達成** (§2)。

## 4. 未解決

| 未解決 | 起票先 |
|---|---|
| set_other 410 / inherit 1,172 / stack 32 引数の機械語データフロー復元 (IR の SSA 値への接続) と「復元不能」の確定 | #1154 ([M11-N68], 親 #953) |
| xmm 引数を読む callee の 48 引数 (IR に xmm 引数が無い) | #1154 の対象外。`REPORT_APPENDIX.md` §9 の未解決に既出 (#131 へ提案) |
