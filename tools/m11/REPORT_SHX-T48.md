# SHX-T48 (#5576): D23 301 site のうち unmatched 56・no_prologue 3 の site 単位判定

## 1. 結論

- 受入 2 (`unmatched` 56 site) と受入 3 (`no_prologue` 3 site・`function_517b50`) は site 単位で判定した (§3・§4)。
- `no_prologue` 3 site は、prologue の `add rsp, -0x80` を `sub` と同じに扱うと取れる。rbp の entry 基準は -152 で、親 IR の `stack_var_-152` (104 B) と一致する。callee が要る範囲は 128 B で、`ir_truncated` (真の D23 候補)。
- `unmatched` 56 のうち、IR に callee の call が**無い**のは 3 site (`function_40b620` → `function_40b290`・`0x40b8eb`・`0x40b938`・`0x40b963`)。これは call 欠落の疑いで、受入 2 が優先に挙げた箇所。
- 残りの 53 site は IR に call があるが、第 1 引数が alloca でなく SSA 値 (`%24` 等)。alloca 幅による `ir_truncated` / `ir_covers` の判定は当てはまらないので、判定不能として残す (§4)。
- 受入 1 (`write_local` 121・`read_local` 106 の制御フローを込めた走査) は未実施。既存の線型走査 (`detect.walk_callee`) は分岐を無視するため、本 run では置き換えない。
- `function_6905f0` → `function_690580` も、機械語 5 site に対して IR の call が 1 件。3〜4 site の call 欠落の候補として §4 に残す (未検証)。

## 2. 測定条件

- 測定 commit: `7306126a0` (origin/main 時点。本 PR で変えたのは `tools/m11/frame_share/unmatched_check.py` (追加) と本 REPORT のみ)。
- 素材: `fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。`work-m11.tar.zst` は worktree 直下に展開 (`tools/m11/work/`・gitignore)。`toolchain-retdec` は使わない (lift を再実行していない)。
- IR: `bash m11_gen_ir2.sh` (34 s・`boot_final.ll` 490,790 行)、`bash m11_build.sh` (18 s・`signature mismatch: 0, undefined symbol: 0`)。`boot_final3.ll` は HEAD の生成経路で作り直した。素材同梱の IR は使わない (REPORT_SHX-T44 §6 の注)。
- 負荷: 測定時の 1 分平均 load は 1.34 (nproc 4)。

## 3. 再現 (site 単位の判定)

| 工程 | 出力 | 結果 |
|---|---|---|
| `frame_share/detect.py --ir work/boot_final3.ll` | `work/frame_share.json` | mov・shared の site を抽出 |
| `frame_share/site_check.py --sites` | `work/site_check.json` | 301 件 `ok`。`write_local` 121 / `read_local` 106 / `arg_home_only` 74 (REPORT_SHX-T44 §6 と一致) |
| `frame_share/base_check.py` | `work/base_check.json` | 301 site: `ir_truncated` 204 / `unmatched` 56 / `ir_covers` 38 / `no_prologue` 3。組 94 (REPORT_SHX-T44 §6 と一致) |
| `frame_share/unmatched_check.py` (本 PR) | `work/unmatched_check.json` | 対象 59 site (`unmatched` 56 + `no_prologue` 3) を再判定 |

`unmatched_check.py` の判定 (site 単位):

- `no_ir_call`: 親 IR に callee の call が無い。
- `base_match` (`ir_truncated` / `ir_covers`): 第 1 引数が機械語の rbp 位置 `stack_var_X` と一致。
- `base_mismatch`: 第 1 引数が X と違う (SSA 値を渡している等)。

## 4. 判定結果 (59 site)

| 旧判定 | 新判定 | site 数 | 組 | 内訳 |
|---|---|---|---|---|
| `no_prologue` | `ir_truncated` | 3 | 2 | `function_517b50` → `function_517ac0` (2) と `function_517a40` (1)。X=-152・渡し先 `stack_var_-152` (104 B)・必要幅 128 B |
| `unmatched` | `no_ir_call` | 3 | 1 | `function_40b620` → `function_40b290`。機械語の call `0x40b8eb`・`0x40b938`・`0x40b963` (いずれも `mov rcx, rbp`) に対し、IR に該当 call が無い |
| `unmatched` | `base_mismatch` | 53 | 18 | IR に call はあるが第 1 引数が SSA 値。alloca 幅では判定しない (下表) |

`base_mismatch` 53 site の内訳 (組ごと。機械語の site 数 / IR の call 数):

| 親 | callee | site | IR call | 渡し先 (SSA) |
|---|---|---|---|---|
| `function_43f800` | `function_43f440` | 15 | 15 | `%24` |
| `function_43f800` | `function_43f490` | 2 | 2 | `%24` |
| `function_43f800` | `function_43f550` | 5 | 5 | `%24` |
| `function_441730` | `function_441500` | 3 | 3 | `%2` |
| `function_441730` | `function_441560` | 1 | 1 | `%2` |
| `function_d26460` | `function_d26430` | 5 | 5 | `%25` |
| `function_e4f310` | `function_e4f2d0` | 3 | 3 | `%7` |
| `function_6a25b0` / `6a2820` | `function_6a23d0` / `6a26e0` | 4 | 4 | `%0` |
| `function_977f50` | `function_977870` | 2 | 2 | `%17` |
| `function_441380` | `function_440d30` | 1 | 1 | `%2` |
| `function_441b20` | `function_441930` | 1 | 1 | `%4` |
| `function_11e7430` | `function_11e6c00` | 1 | 1 | `%48` |
| `function_1280530` | `function_1280170` | 2 | 2 | `%1035` |
| `function_13105d0` | `function_13104e0` | 1 | 1 | `%190` |
| `function_de43b0` | `function_de4120` | 1 | 1 | `%9` |
| `function_f40840` | `function_f3d5e0` | 1 | 1 | `%363` |
| `function_6905f0` | `function_690580` | 5 | 1 | `%27` |

- 組ごとに機械語の site 数と IR の call 数が一致するのは、`function_6905f0`→`function_690580` (5 対 1) を除く 17 組。`function_6905f0` の 4 site は IR で call が落ちている候補 (未検証)。
- `function_6905f0` の IR 本体には `call @function_690580` が 1 件だけある (`%31`)。機械語の 5 site (`0x6906ec`・`0x69073b`・`0x690804`・`0x6908b3`・`0x6909d4`) のうち、どれが IR に残っているかは site 単位で未確認。

## 5. 未了 (次の run へ)

| 未了 | 影響 | 起票先 |
|---|---|---|
| 受入 1: `write_local` 121・`read_local` 106 の site ごとの「call 直前の引数が親の rbp 由来か」の制御フロー付き走査 | 真の D23 の確定 | #5575 (既存の子。残り 291 site の突合) |
| `function_40b620` の 3 site (call 欠落の疑い) の IR 側の再確認と、欠落の原因 (lift 段の制御フロー) の特定 | 受入 2 の優先箇所。修復の対象 | #5576 (本 issue に残す) |
| `function_6905f0` → `function_690580` の 5 対 1 (4 site の call 欠落の候補) | 同上 | #5576 (本 issue に残す) |
| `base_mismatch` 53 site の判定 (SSA 値を渡す site は alloca 幅では決まらない) | 修復範囲の決定 | #5576 (本 issue に残す) |

## 6. 検証

- 測定 commit `7306126a0` (origin/main)。本 PR の差分は `tools/m11/frame_share/unmatched_check.py` (追加) と `tools/m11/REPORT_SHX-T48.md` のみ。既存の判定スクリプト・IR 生成・build の経路は変えていない。
- 既存の `site_check.py` / `base_check.py` の出力は、本 run の HEAD で REPORT_SHX-T44 §6 の値 (301 / 204 / 56 / 38 / 3・組 94) と一致した。
