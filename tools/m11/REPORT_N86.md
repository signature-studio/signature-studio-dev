# M11 REPORT (#1371 / 親 #1154): sigfix 0 詰め set_other の代入元台帳と検算

結論: **部分達成**。0 詰め引数のうち set_other 系 410 件 (set_other 378 + stack_set_other 32) について、代入元の型で台帳化し、独立検算と 410/410 で一致させた。**SSA 値への接続による「実値化」は 0 件、「復元不能」の確定も 0 件**。残件は #1154 / #1373 に紐づける。

> 注: 本 REPORT の数値は、本 commit 時点で `work-m11` の `boot_final.ll` から再生成した実測値。旧 REPORT (`416` 件・IR sha `5389208821…`) とは一致しない (§5)。

## 1. 代入元の台帳 (`m11_argrecover.py` の `src:*`)

台帳コードは `621c0d67` で追加済み。本 REPORT の数値は本 commit の HEAD で再生成した。

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

410 引数を次の 3 値で数えた。合計は 410 に一致する。

| 分類 | 件数 | 定義 |
|---|---|---|
| 実値化 (fix 化) | **0** | `fixes.json` の `fixes` (18 件) はすべて `set_const` 由来。set_other 系は 0 件 (突合せ済み) |
| 復元不能 | **0** | 代入元が特定の SSA 値に接続できたと判定した引数は 0 件 |
| 未分類 | **410** | 上記以外。代入元の型 (台帳) までは分かるが、SSA 値への接続は未実施 |
| **合計** | **410** | 0 + 0 + 410 = 410 |

台帳の kind の内訳 (imm 61 + lea 76 + mem 150 + reg 123 = 410) は §1 のとおり。

「実値化 0・復元不能 0」になる理由: 台帳は代入元の型まで分類するが、**その代入元を IR の SSA 値 (fix の const) に接続する処理は未実装**。このため「実値化」も「復元不能」も判定されない。`imm` 61 件 (set_other 46 + stack 15) は定数だが、`const_of` が `r8b`・`dl` 等の部分書込を未対応のため fix 化されていない (m11_argrecover.py `const_of` の L221)。次の作業で、`imm` 61 件を実値化の候補に、`reg`・`mem_*`・`lea_*` を SSA 接続の対象にする必要がある (#1154)。

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

REPORT_N53 の 410 (378 + 32) とは一致する。旧版の 1,061 site / 416 の出どころ (どの IR か) は、この commit では再現できなかった。

## 6. survey 退行検査 (受入 2・旧測定)

旧測定 (`5389208821…` の IR) での値。本 commit の IR では再測定していない。

| 条件 | 結果 | 所要 |
|---|---|---|
| `M11_SIGFIX_RECOVER=0` | reached_stage 4, units 53/942, survey ok 872 / trap 23 / miss 46 / clobber 0 | 10 分 2 秒 (IR 再生成込み) |
| `M11_SIGFIX_RECOVER=1` | 同上 ok 872 / trap 23 / miss 46 / clobber 0 | 55.5 秒 (増分) |

ok 872 = 872 で退行なし。ただし、この e2e の IR は本 commit の IR と別物 (§5)。

## 7. 再現

- 素材: `work-m11` (`tools/m11/work/boot_final.ll`・`boot_final3.ll`) と `fl-win64` (`extracted/block00031_PE.bin`)。
- `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json`
- `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <PE> --out work/sigfix_stats/fixes.json`
- `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe <PE>` (exit 0 = 全件一致)

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 410 引数の SSA 値接続による実値化・復元不能の確定 (現状 0/0、未分類 410) | 0 詰め引数の意味が未保証 | #1154 (親 #953) |
| `imm` 61 件 (部分書込 `r8b`・`dl` 等) の `const_of` 対応 | 定数復元の取りこぼし | #1154 |
| inherit 側の呼出元 def 追跡 | 受入の inherit 分 | #1373 ([M11-N87]) |
| 旧 REPORT の IR (1,061 site・sha `5389…`) と本 IR (1,049 site) の差の切り分け | 数値の比較基準が 2 つになる | #1154 |
