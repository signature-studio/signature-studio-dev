# M11 REPORT (#1371 / 親 #1154): sigfix 0 詰め set_other の代入元台帳と検算

結論: 0 詰め引数のうち set_other 系 410 件 (set_other 378 + stack_set_other 32) を、代入元の型で台帳化し、文字列照合の検算と 410/410 で一致させた。受入 1 (改訂) は **実値化 0 / 復元不能 0 / 未実装 410 / 未分類 0** で分類した (§2)。「未実装」は SSA 値への接続処理が無いため判定できなかった件数で、復元不能の証明ではない。SSA 接続による実値化は子 issue [M11-N98] (親 #1371) に分離した。

> 注: 本 REPORT の §1〜§4 は `work-m11` の `boot_final.ll` (sha `69c774…`・1049 site・410 件) の実測値。旧 REPORT の `416` 件・1061 site は再生成 IR (§5・§6) の値。

## 1. 代入元の台帳 (`m11_argrecover.py` の `src:*`)

測定 commit: `1d1b4f2f` (本 PR の HEAD で再実行。§9 参照)。台帳と検算に使う実行ファイルは `m11_post.py`・`m11_argrecover.py`・`ldfix/ldmach.py`・`m11_setother_ledger_verify.py` の 4 つで、`cb45c284` から `1d1b4f2f` まで `git diff` の出力は 0 行 (`tools/m11` の他の変更は main 取り込み merge `8ddf7b41` 由来で、この 4 つの実行経路に含まれない)。

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

410 引数を次の 4 値で数えた (IR `69c774…`・`m11_argrecover.py` の `src:*` 台帳)。合計は 410 に一致する。

| 分類 | 件数 | 定義 |
|---|---|---|
| 実値化 (fix 化) | **0** | `fixes.json` の `fixes` (18 件) は全件 `set_const` 由来。set_other 系からの fix 化は 0 件 |
| 復元不能 | **0** | 機械語で元の def が存在しないと示せたもの。set_other は定義 (窓内の非定数代入) がある引数だけを含むため 0 |
| 未実装 (接続処理待ち) | **410** | 代入元の def は機械語にあるが、IR の SSA 値へ接続する処理が無く実値化できなかった引数。kind 別は下表 |
| 未分類 | **0** | 上記 3 値以外なし |
| **合計** | **410** | 0 + 0 + 410 + 0 = 410 |

kind 別の内訳 (未実装 410 の内訳。「未実装の理由」は接続処理が無いこと):

| 台帳 kind | 件数 | 未実装の理由 |
|---|---|---|
| imm | 61 (46 + 15) | 定数代入だが `const_of` が `r8b`・`r9b`・`dl` 等の部分書込を扱わない。実値化の候補 (子 issue [M11-N98]) |
| lea_ptr / lea_stack | 76 (17 + 59) | アドレス生成。SSA の値への接続処理が無い (子 issue [M11-N98]) |
| mem_global / mem_stack / mem_ptr | 150 (11 + 50 + 89) | メモリ読込。読み元を SSA に接続する処理が無い (子 issue [M11-N98]) |
| reg | 123 (106 + 17) | レジスタ由来。元の def を SSA に接続する処理が無い (子 issue [M11-N98]) |

注: imm 61 件は定数なので、部分書込対応で実値化の候補になる。「未実装」は値が復元不能であることを意味しない。

## 3. 受入 3: 検算 (別アルゴリズム) と 49 件の内訳

`tools/m11/m11_setother_ledger_verify.py`: 代入元の判定を `op_str` の文字列照合だけで行う (`regs_access` や operand 型は使わない)。命令列の取得には `ldmach.disasm_fn` (内部で capstone) を使う。台帳 (`fixes.json` の `site_detail[].src`) と引数単位で突き合わせ、一致・不一致を数えて `ledger_verify_rows.json` に全行を保存する。不一致があれば exit 1。

スクリプト名の理由: issue 本文の `m11_argrecover_verify.py` は既存の検算で、`set_const` の fix (18 件) だけを対象にする。set_other 系の台帳は対象外なので、本 PR では set_other 台帳用に `m11_setother_ledger_verify.py` を新設した。

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

**検算の独立性は限定的**: 代入元の判定は台帳と別の実装 (文字列照合) だが、(a) 命令列の取得 (`ldmach.disasm_fn`・capstone)、(b) call 位置の対応付け (`k` 番目の call)、(c) 窓の範囲 (分岐・call で打ち切り) は台帳と共通である。したがって検算が確かめるのは「代入元の分類」だけで、(a)〜(c) の誤りは検出できない。初版の判定修正は台帳の値を見た後に行った。修正は規則 (8/16bit 名・`al`/`xmm` を含める) の追加で、台帳の kind を個別に書き換えてはいない。

## 4. 既定出力の byte 一致 (測定)

測定 commit: `1d1b4f2f` (§1・§9 と同じ)。`m11_post.py` は `cb45c284` から `1d1b4f2f` まで差分 0 行。

`621c0d67` 時点の `m11_post.py` の出力と、現行 HEAD の `m11_post.py` の出力を比較した (HEAD `1d1b4f2f` で再実行した sha も同じ):

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

## 6. survey 退行検査 (受入 2・改訂版)

測定 commit: `dece0171` の worktree (`ws-1441`) で `work-m11` と `fl-win64` を展開し、以下の手順で測定した。
`dece0171` から HEAD までの `tools/m11` のコード差分 (`git diff dece0171 HEAD -- tools/m11 ':(exclude)*.md'`) は 0 行 (§9)。

**同じ IR での比較** (IR `c9308c98…`・`ir_conditions`: `ldfix=applied` / `qstore=applied`。`m11_e2e.sh` の既定経路):

| `M11_SIGFIX_RECOVER` | reached_stage | survey ok / trap / miss / clobber | IR sha256 (`ir_sha256`) | 所要 |
|---|---|---|---|---|
| 1 | 4 | 872 / 23 / 46 / 0 | `c9308c98…` | 1 分 34 秒 (load 0.66 → 1.01・build 含む) |
| 0 | 4 | 872 / 23 / 46 / 0 | `c9308c98…` | 43 秒 (load 1.01 → 1.08・build 増分) |

判定: 同じ IR で `=0` と `=1` の ok が一致 (872 = 872)。退行なし。

**`69c774…` の IR での survey は取れなかった** (受入 2 の改訂で求められた「同じ IR で 1 回試す」の結果):
- 展開直後の `boot_final.ll` の sha は `69c774ded8aaf717…` で、`work-m11` の展開物と一致した。
- しかし `ir_conditions.json` と `lift_pe.sha256` が展開物に無い。`m11_build.sh` は `ldfix=applied` の記録が無い IR を拒否する (`ERROR: ... ldfix=applied の記録無し`)。
- `m11_gen_ir2.sh` を 1 回走らせると (35 秒) IR は `2c68ce…` になり、`69c774…` は再現できなかった。
- `m11_e2e.sh` (`lift_pe.sha256` 無し) は全再生成の分岐に入り、`m11_bounds.py` が `m2/work/ghidra_dll/functions_dll.csv` (Ghidra 成果物・素材に無い) を読めず fail-closed で停止した。
- 残件: 全再生成 (Ghidra 再生成 9 分 47 秒を含む) の成立と、`69c774…` の IR を build 可能にする条件の特定。起票先は #1154。
- 本 PR では `lift_pe.sha256` を手で書いて IR 再生成を止め、`c9308c98…` の既定経路で測った。この指紋は lift 成果物の出自を検証していない (`m11_e2e.sh` の全再生成の代替ではない)。

**参考値 (別 IR)**: `69c774…` の IR での survey は未測定。`c9308c98…` の値 (ok 872 / trap 23 / miss 46) は、台帳の 1,049 site の IR とは別 IR の参考値である。

再生成 IR (`c9308c98…`) の値: 0 詰め site 1061・引数 2084、set_other 系 416 (384 + 32)。台帳と検算は `m11_setother_ledger_verify.py` で `match 416` / exit 0 (§5)。

## 7. 再現

- 素材: `work-m11` (`tools/m11/work/boot_final.ll`・`boot_final3.ll`) と `fl-win64` (`extracted/block00031_PE.bin`)。
- `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json`
- `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <PE> --out work/sigfix_stats/fixes.json`
- `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe <PE>` (exit 0 = 全件一致)

## 9. 再測定 (`69c774…` IR・受入 1 と 3 の根拠)

- 測定 commit: `1d1b4f2f` (台帳・検算。§1 と同じ)。survey (§6) の測定 commit は `dece0171` (以下の比較参照)。
- 入力 IR: 展開直後の `tools/m11/work/boot_final.ll` (sha256 `69c774ded8aaf717…`・`work-m11` 展開物と同一。HEAD で再確認)。
- 実行 (HEAD `1d1b4f2f`・すべて rc 0): `m11_post.py` (既定出力 sha `ecab191b…`) → `m11_argrecover.py` → `m11_setother_ledger_verify.py`。
- 台帳: 0 詰め site 1049・引数 1963・set_other 系 410 (set_other 378 + stack_set_other 32)。`resolved_sites` 31・const 復元 fixes 18。
- 台帳の kind 別件数は §1 と一致 (imm 61 / lea 76 / mem 150 / reg 123)。
- 検算 (`m11_setother_ledger_verify.py`): `match 410`・`mismatch 0`・exit 0。
- コード差分 (4 ファイル): `git diff cb45c284 1d1b4f2f -- tools/m11/m11_post.py tools/m11/m11_argrecover.py tools/m11/ldfix/ldmach.py tools/m11/m11_setother_ledger_verify.py` は 0 行。
- survey (§6) の範囲: `git diff dece0171 HEAD -- tools/m11 ':(exclude)*.md'` は 0 行 (`dece0171` 以降、`tools/m11` のコードは未変更)。
- 注: `work/` は gitignore 対象のため commit しない。`tools/m11/work/` の再生成物 (`boot_final.ll` の `c9308c98…` 版) は素材の既定 IR を上書きしている。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 410 引数の SSA 値接続による実値化 (現状 実値化 0 / 復元不能 0 / 未実装 410 / 未分類 0)。imm 61 件 (`const_of` の部分書込) を先行 | 0 詰め引数の意味が未保証 | #1524 ([M11-N98]・親 #1371) |
| lea 76 / mem 150 / reg 123 件の SSA 接続 (接続方式が未定) | 同上 | #1154 (親 #953) |
| inherit 側の呼出元 def 追跡 | 受入の inherit 分 | #1373 ([M11-N87]) |
| `69c774…` IR の build・survey (`ir_conditions.json` 無し・全再生成は `functions_dll.csv` 不足で停止) | 受入 2 が `c9308c98…` の参考値のみ | #1154 |
