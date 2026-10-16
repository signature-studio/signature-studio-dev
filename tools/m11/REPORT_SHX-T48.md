# SHX-T48 (#5576): D23 301 site のうち unmatched 56・no_prologue 3 の site 単位判定

## 1. 結論

- 受入 2 (`unmatched` 56 site) と受入 3 (`no_prologue` 3 site・`function_517b50`) は site 単位で判定した (§3・§4)。
- `no_prologue` 3 site は、prologue の `add rsp, -0x80` を `sub` と同じに扱うと取れる。rbp の entry 基準は -152 で、親 IR の `stack_var_-152` (8 B) と一致する。callee が要る範囲は 128 B で、`ir_truncated` (真の D23 候補)。
- `unmatched` 56 site は、現コード・実データの判定で **全 56 site が `ir_truncated` または `no_ir_call`**。53 site (`base_mismatch`) の大半は、第 1 引数が `ptrtoint ptr %stack_var_X to i64` の SSA 値 (`%24` 等) で、alloca 名に解決すると `stack_var_X` (rbp 基準の X と一致) になる。旧判定 (SSA 名のまま照合) の誤りである。
- `no_ir_call` の 3 site (`function_40b620` → `function_40b290`) は、生 grep で IR 上の直接 call が 0 件と確定した (§4.1)。親 IR に call 欠落がある。
- 受入 1 (`write_local` 121・`read_local` 106 の制御フローを込めた走査) は未実施。既存の線型走査 (`detect.walk_callee`) は分岐を無視するため、本 run では置き換えない。

## 2. 測定条件

- 測定 commit: 本 PR の HEAD (`unmatched_check.py` の修正を含む)。コード差分は §6 を参照。
- 素材: `fl-win64` (`FL_WIN64_DIR`)・`work-m11` (`tools/m11/work/`)・`toolchain-retdec` を展開。`work-m11` の旧 `boot_final3.ll` は使わず、`m11_gen_ir2.sh` (`boot_final.ll` 490,790 行・`ir_conditions.json` `ldfix=applied`) と `m11_post.py` で `boot_final3.ll` (529,619 行) を作り直した。
- 負荷: 測定時の 1 分平均 load は約 1.3 (nproc 4)。

## 3. 再現 (site 単位の判定)

| 工程 | 出力 | 結果 |
|---|---|---|
| `frame_share/detect.py --ir work/boot_final3.ll` | `work/frame_share.json` | mov・shared の site を抽出 |
| `frame_share/site_check.py --sites` | `work/site_check.json` | 301 件 `ok`。`write_local` 121 / `read_local` 106 / `arg_home_only` 74 |
| `frame_share/base_check.py --sites work/frame_share.json` | `work/base_check.json` | 301 site: `ir_truncated` 242 / `unmatched` 56 / `no_prologue` 3。組 94 |
| `frame_share/unmatched_check.py` (本 PR) | `work/unmatched_check.json` | 対象 59 site を再判定: `ir_truncated` 56 / `no_ir_call` 3 |

§3 の注: `base_check` の `ir_truncated` / `ir_covers` は、現コードの実測で **242 / 0** (全 242 site の alloca 幅が 8 B、需要幅の最小が 48 B)。旧 REPORT の 204 / 38 は現コードでは再現しない。差の原因は未確認。

`unmatched_check.py` の判定 (site 単位):

- `no_ir_call`: 親 IR に callee の `call` 行が 0 件。
- `ir_truncated`: 第 1 引数 (`ptrtoint` を辿った後の alloca 名) が `stack_var_X` (X = 機械語の rbp 位置) と一致し、需要幅 E > alloca 幅 S。
- `base_mismatch`: 第 1 引数が X と違う。
- `no_rbp_entry` / `no_callee_access` / `arg_type_unmatched`: 該当なし (本データでは 0 件)。

## 4. 判定結果 (59 site)

| 旧判定 | 新判定 | site 数 | 組 | 内訳 |
|---|---|---|---|---|
| `no_prologue` | `ir_truncated` | 3 | 2 | `function_517b50` → `function_517ac0` (2) と `function_517a40` (1)。X=-152・渡し先 `stack_var_-152` (8 B)・必要幅 128 B |
| `unmatched` | `no_ir_call` | 3 | 1 | `function_40b620` → `function_40b290`。IR に該当 call が無い (§4.1) |
| `unmatched` | `ir_truncated` | 53 | 18 | 第 1 引数が `ptrtoint ptr %stack_var_X` の SSA 値。alloca 名に解決すると `stack_var_X` で一致 |

- `unmatched` 53 site の旧 `base_mismatch` 判定は、SSA 名 (`%24` 等) のまま照合したための誤り。解決後は全 site が `ir_truncated` になった。
- 組の内訳 (機械語の site 数 / IR の call 数 は全組で一致):

| 親 | callee | site | 渡し先 (解決後) | X | alloca S | 需要 E |
|---|---|---|---|---|---|---|
| `function_43f800` | `function_43f440` | 15 | `stack_var_-136` | -136 | 8 | 153 |
| `function_43f800` | `function_43f490` | 2 | `stack_var_-136` | -136 | 8 | 153 |
| `function_43f800` | `function_43f550` | 5 | `stack_var_-136` | -136 | 8 | 84 |
| `function_441730` | `function_441500` | 3 | `stack_var_-120` | -120 | 8 | 136 |
| `function_441730` | `function_441560` | 1 | `stack_var_-120` | -120 | 8 | 112 |
| `function_d26460` | `function_d26430` | 5 | `stack_var_-104` | -104 | 8 | 48 |
| `function_e4f310` | `function_e4f2d0` | 3 | `stack_var_-40` | -40 | 8 | 56 |
| `function_6a25b0` | `function_6a23d0` | 2 | `stack_var_-88` | -88 | 8 | 121 |
| `function_6a2820` | `function_6a26e0` | 2 | `stack_var_-88` | -88 | 8 | 121 |
| `function_977f50` | `function_977870` | 2 | `stack_var_-88` | -88 | 8 | 160 |
| `function_441380` | `function_440d30` | 1 | `stack_var_-40` | -40 | 8 | 84 |
| `function_441b20` | `function_441930` | 1 | `stack_var_-168` | -168 | 8 | 284 |
| `function_11e7430` | `function_11e6c00` | 1 | `stack_var_-136` | -136 | 8 | 88 |
| `function_1280530` | `function_1280170` | 2 | `stack_var_-648` | -648 | 8 | 664 |
| `function_13105d0` | `function_13104e0` | 1 | `stack_var_-120` | -120 | 8 | 136 |
| `function_de43b0` | `function_de4120` | 1 | `stack_var_-136` | -136 | 8 | 172 |
| `function_f40840` | `function_f3d5e0` | 1 | `stack_var_-18040` | -18040 | 8 | 17992 |
| `function_6905f0` | `function_690580` | 5 | `stack_var_-152` | -152 | 8 | 176 |

注: 上の表は `unmatched_check.json` の 59 site の内訳 (`function_517b50` 3 site は `no_prologue` 由来で、`ir_truncated` 側に含む)。`unmatched` 53 site の組数は 18 組 (`function_40b620` の 1 組は `no_ir_call` の 3 site)。

- `function_6905f0` → `function_690580`: 機械語 5 site (`0x6906ec`・`0x69073b`・`0x690804`・`0x6908b3`・`0x6909d4`) に対し、IR 本体の `call` は 1 件 (`%31`・244950 行)。欠落候補の 4 site は未検証のまま残る (§5)。5 site とも解決後は `stack_var_-152` (8 B) を指す。

## 4.1 生 grep による確定 (素材で再生成した `boot_final3.ll`・529,619 行)

- `function_40b290` の出現 (`grep -n '@function_40b290' work/boot_final3.ll`):
  - 112301: `define weak i64 @function_40b290(...)` (定義)
  - 112320〜112485: `%ce0n11_function_40b290` 等 6 行 (`inttoptr i64 4240912` の load。call ではない)
  - 502054: `%r = call i64 @function_40b290(ptr %c0, i64 %a1)` (`@m11_tr_function_40b290` の中)
  - 529619: `@m11_disp_tab` のトランポリン表
- 親 `function_40b620` (112529〜112552) の本体に `call @function_40b290` は**無い**。よって `no_ir_call` は正しい。直接の呼出元は `@m11_tr_function_40b290` の 1 件のみ。
- `function_690580` の出現 (`grep -n '@function_690580(' work/boot_final3.ll`):
  - 244812: `define weak i64 @function_690580(...)` (定義)
  - 244950: `%31 = call i64 @function_690580(i64 %27, i32 %30)` (`function_6905f0` 本体 244892〜244958 の中)
  - 245272: `%143 = call i64 @function_690580(i64 %3, i32 %142)` (`function_690763` 244960〜 の中。`function_6905f0` の外)
  - 514061: `%r = call i64 @function_690580(i64 %a0, i32 %c1)` (トランポリンの中)
- よって `function_6905f0` 本体の call は 1 件 (244950)。`function_690763` の 245272 は別の親の call である。

## 5. 未了 (次の run へ)

| 未了 | 影響 | 起票先 |
|---|---|---|
| 受入 1: `write_local` 121・`read_local` 106 の site ごとの「call 直前の引数が親の rbp 由来か」の制御フロー付き走査 | 真の D23 の確定 | #5575 (既存の子。残り 291 site の突合) |
| `function_40b620` → `function_40b290` の call 欠落 3 site (`0x40b8eb`・`0x40b938`・`0x40b963`) の原因 (lift 段の制御フロー) | 修復の対象 | #5586 |
| `function_6905f0` → `function_690580` の機械語 5 site と IR の call 1 件の site 単位の突合 (欠落候補 4 site) | 同上 | #5587 |
| `ir_truncated` 56 site (alloca 8 B に対し需要 48〜17992 B) の修復範囲の決定 | 修復範囲の決定 | #5588 |

- 子 issue 3 件 (#5586・#5587・#5588) はいずれも親 #5576 を `親:` で指す。親の blocker にはしない。
- #5576 は closed 済みのため、本 PR の `Closes #5576` は範囲を縮めた完了として扱う。

## 6. 検証

- 測定 commit: `7306126a0` (origin/main)。本 PR の変更は `tools/m11/frame_share/unmatched_check.py` (`ptrtoint` 解決・書式化の修正) と本 REPORT。
- 実データ run: `m11_gen_ir2.sh` → `m11_post.py` → `detect.py` → `site_check.py` → `base_check.py` → `unmatched_check.py` の順に、本 PR の HEAD で実行した。
- `ptrtoint` 解決は、呼出し行より前で最も近い同名 SSA の定義を使う。同じ名前が複数の定義を持つ IR では誤る余地がある。本データの 59 site では、解決先が全て alloca 名 (`stack_var_X`) に一致した。
- 既存の `site_check.py` (301 ok) は REPORT_SHX-T44 §6 と一致。`base_check.py` の `ir_truncated` / `unmatched` / `no_prologue` は 242 / 56 / 3 (旧 204 / 38 とは不一致。§3 の注)。
