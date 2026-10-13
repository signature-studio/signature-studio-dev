# M11 REPORT (#1371 / 親 #1154): sigfix 0 詰め set_other の代入元台帳と検算

結論: 0 詰め引数のうち set_other 系 410 件 (set_other 378 + stack_set_other 32) を、代入元の型で台帳化し、独立検算と 410/410 で一致させた。受入 1 は **実値化 0 / 復元不能 410 / 未分類 0** で分類した (§2)。ただし「復元不能」は本 PR の接続処理で判定できなかった件数で、意味的に復元不能と確定したものではない。SSA 接続による実値化は #1154 に残す。

> 注: 本 REPORT の §1〜§4 は `work-m11` の `boot_final.ll` (sha `69c774…`・1049 site・410 件) の実測値。旧 REPORT の `416` 件・1061 site は再生成 IR (§5・§6) の値。

## 1. 代入元の台帳 (`m11_argrecover.py` の `src:*`)

台帳コードは `621c0d67` で追加済み。本 REPORT の数値は測定 commit `cb45c284` (検算 `m11_setother_ledger_verify.py` を台帳照合版に直した commit) の HEAD で再生成した。

実行: `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json` → `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <block00031_PE.bin> --out work/sigfix_stats/fixes.json`

| kind | 代入元 | 件数 |
|---|---|---|
| set_other | imm (定数が代入されているが fix 化されず) | 46 |
| set_other | lea_ptr | 17 |
| set_other | lea_stack | 59 |
| set_other | mem_global | 11 |
| set_other | mem_ptr | 89 |
| set_other | mem_stack | 50 |
| set_other | reg | 106 |
| stack_set_other | imm | 15 |
| stack_set_other | reg | 17 |
| **合計** | | **410** (set_other 378 + stack_set_other 32) |

## 2. 受入 1: 実値化・復元不能・未分類の 3 値

410 引数を次の 3 値で数えた (IR `69c774…`・`m11_argrecover.py` の `src:*` 台帳)。合計は 410 に一致する。

| 分類 | 件数 | 定義 |
|---|---|---|
| 実値化 (fix 化) | **0** | `fixes.json` の `fixes` (18 件) は全件 `set_const` 由来。set_other 系からの fix 化は 0 件 |
| 復元不能 | **410** | 本 PR の接続処理で、代入元を IR の SSA 値に接続できず判定不能とした引数。理由は kind 別 (下表) |
| 未分類 | **0** | 上記以外なし |
| **合計** | **410** | 0 + 410 + 0 = 410 |

kind 別の内訳と「接続できない理由」:

| 台帳 kind | 件数 | 判定不能の理由 |
|---|---|---|
| imm | 61 (46 + 15) | 定数代入だが `const_of` が `r8b`・`r9b`・`dl` 等の部分書込を扱わない。実値化の候補 (#1154) |
| lea_ptr / lea_stack | 76 (17 + 59) | アドレス生成。SSA の値への接続処理が無い |
| mem_global / mem_stack / mem_ptr | 150 (11 + 50 + 89) | メモリ読込。読み元を SSA に接続する処理が無い |
| reg | 123 (106 + 17) | レジスタ由来。元の def を SSA に接続する処理が無い (#1154) |

注: 「復元不能」は本 PR で判定できなかった件数であり、値が本質的に復元できないことの証明ではない。imm 61 件は定数なので、部分書込対応 (#1154) で実値化の候補になる。

## 3. 受入 3: 検算 (別アルゴリズム) と 49 件の内訳

`tools/m11/m11_setother_ledger_verify.py`: operand 型の判定に capstone を使わず、代入元の判定を `op_str` の文字列だけで行う。命令列の取得には `ldmach.disasm_fn` (内部で capstone) を使う。台帳 (`fixes.json` の `site_detail[].src`) と引数単位で突き合わせ、一致・不一致を数えて `ledger_verify_rows.json` に全行を保存する。不一致があれば exit 1。

現行の検算コードでの実測:

```
[ledger-verify] set_other 系 引数 410 (台帳 410)
  kind:set_other:match                     378
  kind:stack_set_other:match               32
  match                                    410
EXIT=0
```

**初版 49 件について (経緯の注記)**: `621c0d67` のコミット履歴には、49 件不一致だった初版は残っていない (検算スクリプトは 1 commit のみ)。本 REPORT では、現行スクリプトの判定から「8/16bit 部分書込の名前」と「`al`・`xmm` の reg 判定」を外した変種 (`ALIAS` を 32bit/64bit 名のみ、stack 判定を `r*`/`e*` 名のみ) で、同じ `fixes.json` を照合して再現した。下表の 49 件はこの再現の結果であり、コミット済みの初版そのものではない。

| 検算の判定 | 一致 | 不一致 |
|---|---|---|
| 初版 (8/16bit 名なし・`al`/`xmm` reg 判定なし) | 361 | **49** |
| 現行 (8/16bit 名あり・`al`/`xmm` reg 判定あり) | 410 | **0** |

49 件の内訳 (`ledger_verify_rows.json` の旧版を (kind, pos, 台帳, 初版変種の検算) で数えた実測):

| 台帳 kind | pos | 台帳 | 初版変種の検算 | 件数 |
|---|---|---|---|---|
| set_other | 2 (r8) | imm | boundary | 19 |
| set_other | 2 (r8) | imm | entry | 2 |
| set_other | 3 (r9) | imm | boundary | 14 |
| stack_set_other | 4 | reg | other | 10 |
| stack_set_other | 5 | reg | other | 1 |
| stack_set_other | 6 | reg | other | 1 |
| stack_set_other | 7 | reg | other | 1 |
| stack_set_other | 9 | reg | other | 1 |
| **合計** | | | | **49** |

**機械語での個別確認** (49 件を `ldmach.disasm_fn` で、引数 pos を書く直前の命令まで全件分類。`no_write_in_window` は 0 件):

| 台帳 kind | pos | 直前の書込 (数値は N に正規化) | 件数 | 台帳の判定 |
|---|---|---|---|---|
| set_other | 2 (r8) | `mov r8b, N` | 20 | imm (正しい: 定数代入) |
| set_other | 2 (r8) | `mov r8w, N` | 1 | imm (正しい: 定数代入) |
| set_other | 3 (r9) | `mov r9b, N` | 14 | imm (正しい: 定数代入) |
| stack_set_other | 4 | `mov byte ptr [rsp+N], al` | 6 | reg (正しい: al 由来) |
| stack_set_other | 4 | `movss dword ptr [rsp+N], xmm0` | 3 | reg (正しい: xmm 由来) |
| stack_set_other | 4 | `movss dword ptr [rsp+N], xmm6` | 1 | reg (正しい: xmm 由来) |
| stack_set_other | 5 | `movss dword ptr [rsp+N], xmm6` | 1 | reg (正しい: xmm 由来) |
| stack_set_other | 6 | `movss dword ptr [rsp+N], xmm6` | 1 | reg (正しい: xmm 由来) |
| stack_set_other | 7 | `mov dword ptr [rsp+N], eax` | 1 | reg (正しい: eax 由来) |
| stack_set_other | 9 | `movsd qword ptr [rsp+N], xmm0` | 1 | reg (正しい: xmm 由来) |

49 件すべてで、台帳の kind (imm/reg) は直前の書込の種類と一致する。初版変種は、8/16bit 名 (`r8b`・`r9b`・`r8w`) と `al`・`xmm`・`eax` を reg として照合しなかったため、これらを `boundary`/`entry`/`other` と誤判定していた。

**独立性の限界**: 検算は代入元の判定を文字列で行うが、(a) 命令列の取得 (`ldmach.disasm_fn`・capstone)、(b) call 位置の対応付け (`k` 番目の call)、(c) 窓の範囲 (分岐・call で打ち切り) は台帳と共通である。したがって検算が確かめるのは「代入元の分類」だけで、窓の取り方や call 対応付けの誤りは検出できない。初版の判定修正は、台帳の値を見た後に行った。修正は規則 (8/16bit 名・`al`/`xmm` を含める) の追加で、台帳の kind を個別に書き換えてはいない。

## 4. 既定出力の byte 一致 (測定)

測定 commit: `cb45c284`。`git diff cb45c284 HEAD -- tools/m11` の出力は、この REPORT の追記のみ (コードの差分 0)。

`621c0d67` 時点の `m11_post.py` の出力と、現行 HEAD の `m11_post.py` の出力を比較した:

```
$ cmp work/sigfix_stats/old/final3_base.ll work/sigfix_stats/final3_chk.ll && echo CMP_IDENTICAL
CMP_IDENTICAL
ecab191b13590dd005de7278697bb4bd1ff12d2de964b62c7a5493a3a4f8e819  work/sigfix_stats/old/final3_base.ll
ecab191b13590dd005de7278697bb4bd1ff12d2de964b62c7a5493a3a4f8e819  work/sigfix_stats/final3_chk.ll
```

両者とも `ecab191b…` で byte 一致。

## 5. IR 差分 (旧 REPORT との不一致)

旧版の記述 (IR sha `5389208821…`・0 詰め 1,061 site・set_other 416) は、本 commit の `work-m11` 展開物とは一致しない:

| 項目 | 旧 REPORT | 本 commit の実測 |
|---|---|---|
| `boot_final.ll` sha256 | `5389208821…` | `69c774ded8aaf717c66d…` (先頭 20 字) |
| 0 詰め site | 1,061 | **1,049** (引数 2,064 → 1,963) |
| set_other 系 引数 | 416 (384 + 32) | **410** (378 + 32) |

REPORT_N53 の 410 (378 + 32) とは一致する。

再現時の別 IR: `m11_e2e.sh --full` は Ghidra 中間物 `functions_dll.csv` が無く失敗した。`m11_e2e.sh` (非 full) は `gen_ir2 (boot5 追加)` を経由して IR を `c9308c98…` に作り直し、この再生成 IR では 1,061 site・引数 2,084・set_other 系 416 (384 + 32) になった (`m11_setother_ledger_verify.py` は再生成 IR でも `match 416` / exit 0)。旧版の 1,061 / 416 は、この再生成 IR と一致する。

## 6. survey 退行検査 (受入 2)

測定は `m11_e2e.sh` (`M11_SIGFIX_RECOVER=0` と `=1`) を foreground で実行した。`e2e_expect.env` の期待値 (stage 4 / survey ok 800) は両方で満たした。

| IR | `M11_SIGFIX_RECOVER` | reached_stage | survey ok / trap / miss / clobber | 所要 |
|---|---|---|---|---|
| 再生成 IR `c9308c98…` (1061 site・416 件) | 0 | 4 | 872 / 23 / 46 / 0 | 2 分 34 秒 |
| 再生成 IR `c9308c98…` (1061 site・416 件) | 1 | 4 | 872 / 23 / 46 / 0 | 54.9 秒 (`m11_e2e.sh` の全体) |

**受入 2 の判定**: ok 872 ≥ 870 で退行なし。ただし、測定に使った IR は `69c774…` ではなく `c9308c…` である。

経緯: 展開物の `boot_final.ll` (`69c774…`・1049 site) を `m11_e2e.sh` で使うと、`m11_e2e.sh` が `gen_ir2 (boot5 追加)` を毎回呼び、IR を `c9308c…` に作り直す。`ir_conditions` の指紋・`lift_pe.sha256`・`boot5` の mtime は揃えたが、再生成を止められなかった (原因は未特定)。このため `69c774…` の IR に対する survey は取れていない。

**残件**: `69c774…` の IR での survey 再測定 (再生成を止める条件の特定が必要)。起票先は #1154。

## 7. 再現

- 素材: `work-m11` (`tools/m11/work/boot_final.ll`・`boot_final3.ll`) と `fl-win64` (`extracted/block00031_PE.bin`)。
- `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json`
- `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <PE> --out work/sigfix_stats/fixes.json`
- `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe <PE>` (exit 0 = 全件一致)

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 410 引数の SSA 値接続による実値化 (現状 実値化 0 / 復元不能 410 / 未分類 0) | 0 詰め引数の意味が未保証 | #1154 (親 #953) |
| `imm` 61 件 (部分書込 `r8b`・`dl` 等) の `const_of` 対応 | 定数復元の取りこぼし | #1154 |
| inherit 側の呼出元 def 追跡 | 受入の inherit 分 | #1373 ([M11-N87]) |
| `69c774…` IR の survey 再測定 (`m11_e2e.sh` が gen_ir2 で IR を作り直すため未達) | 受入 2 が再生成 IR での値のみ | #1154 |
