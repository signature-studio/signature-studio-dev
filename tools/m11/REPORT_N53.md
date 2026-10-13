# M11 REPORT (#953 / 親 #131): sigfix 0 詰め引数の理由別分類と退行検査

結論: **部分達成**。0 詰め 1,963 引数 (1,049 site) の理由別分類を `m11_argrecover.py` に追加し REPORT に実測を残した。`M11_SIGFIX_RECOVER=1` の survey は既定と同数 (ok 870 = 870) で退行なし。未復元 1,582 引数 (stack 32 を含む) の**データフロー復元は未達**で、子 #1154 ([M11-N68]) に分離した。

## 1. 理由別の内訳 (`m11_argrecover.py`, `work/sigfix_pads.json` 1,049 site 由来)

`why:` は分類結果ごとの理由。`boundary` = 窓が call / jmp / jcc / ret / 分岐先で切れた, `entry` = 関数入口まで代入が無い (caller の live-in を素通し), set 系の `load` / `reg` / `arith` / `other` = 代入命令の型。

kind 別の件数 (callee_unused 313 / set_const 18 / set_const_xmm_callee 48 / set_other 378 / stack_set_other 32 / inherit 1,172 / callee_nopdata 2、計 1,963) は `REPORT_APPENDIX.md` §9 の表が正本。以下は各 kind の why 内訳のみ (各行の和は §9 の件数と一致)。

| kind | 理由 (内訳) |
|---|---|
| set_const (復元済) | arith 7 / other 11 |
| set_const_xmm_callee (復元せず) | arith 18 / other 30 |
| set_other | load 150 / reg 103 / arith 90 / other 35 |
| stack_set_other | reg 10 / other 22 |
| inherit | boundary 1,119 / entry 53 |

`why` は代入命令の型。`load` は mov/movzx/movsx/movsxd のメモリ読出し、`arith` は `lea` を含む演算 (`lea` はアドレス計算でメモリを読まないため `load` に入れない)。

未復元の 1,582 引数 (inherit 1,172 + set_other 378 + stack_set_other 32、stack を含む) の内訳は、`boundary` (窓の切れ目の向こう側の def を要する) が最多 1,119 で、`set_other:load` 150 (メモリ読出し由来) が次に大きい。xmm 48 引数と callee_nopdata 2 引数は別扱い (未復元の内数に含めない)。

## 2. 検証

| 項目 | 結果 |
|---|---|
| 分類の再現 | `m11_argrecover.py` の分類 (kind) と fixes は理由追加前後で完全一致 (`args same: True`, `fixes same: True`) |
| 別アルゴリズム検算 `m11_argrecover_verify.py` (`work/sigfix_fixes.json`, 18 件) | **18/18 一致** (mismatch 0) |
| `m11_e2e.sh` `M11_SIGFIX_RECOVER=0` (同一 IR `ir_sha256` 1fc847…) | reached_stage 4/6, units_run 53/942, **survey ok 870 / trap 25 / miss 46 / noproc 1 / clobber 0**, judge rc 0, e2e 41.5 秒 (増分) |
| `m11_e2e.sh` `M11_SIGFIX_RECOVER=1` (同一 IR) | reached_stage 4/6, units_run 53/942, **survey ok 870 / trap 25 / miss 46 / noproc 1 / clobber 0**, judge rc 0, e2e 125.5 秒 (boot5 を含む IR の再生成込み) |
| 受入条件 2 (`M11_SIGFIX_RECOVER=1` で survey 退行無し = ok 数 ≥ 既定) | 870 ≥ 870 で**満たす** |

注: 同じ `m11_e2e.sh` 経路で作った IR (`boot5` 込み) の指紋は `1fc847…` で、検証の初回 (手動 build 経路、`boot5` 無し) の `39008e…` とは別物。survey の ok 数 869 は手動経路の値で、e2e 経路の 870 とは比較しない。

注 (lift の再現範囲): 上の e2e は `work/lift_pe.sha256` を現 PE から作って RetDec 再 lift を省いている。`ir_sha256` 一致は同一 IR 間の比較の根拠に限られ、lift 込みの再現ではない。

why の再集計 (`lea` を `load` から外した後): `results/sigfix_zeropad_remaining.tsv` の 1,004 site (matched) を PE から再計算し、引数ごとの kind が TSV と 1,004/1,004 一致 (不一致 0)、kind 件数は §9 と一致。why の内訳は §1 のとおり (`set_other:load` 226 → 150, `set_other:arith` 14 → 90)。kind と fixes は変わらないため e2e は再実行していない。

## 3. 受入条件の判定

* 受入 1 (set_other / inherit を実値化、または「復元不能」と分類した件数を REPORT に残す): **部分達成**。理由別の分類件数は §1 で実測を残した。ただし「復元不能」として確定させた件数は無い (全件が「未復元」)。実値化は 0 件 (既存の 18 件のみ)。残りは子 #1154 (`[M11-N68]`) で扱う。
* 受入 2 (`M11_SIGFIX_RECOVER=1` の e2e で survey の退行無し): **達成** (§2)。

## 4. 未解決

| 未解決 | 起票先 |
|---|---|
| set_other 378 / stack_set_other 32 / inherit 1,172 引数の機械語データフロー復元 (IR の SSA 値への接続) と「復元不能」の確定 | #1154 ([M11-N68], 親 #953) |
| xmm 引数を読む callee の 48 引数 (IR に xmm 引数が無い) | #1154 の対象外。`REPORT_APPENDIX.md` §9 の未解決に既出 (#131 へ提案) |
