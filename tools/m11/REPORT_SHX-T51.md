# SHX-T51 (#5588): base_mismatch 53 site (SSA 値渡し・18 組) の修復範囲の決定

親: #5576 / 前提: PR #5583 (merge 済み・`REPORT_SHX-T48.md` §4)

## 1. 結論

- 18 組 (53 site) のうち、**alloca 拡幅 (R8) で覆えるものは 0 組**。全 18 組で、親の同じ関数内にある次の `stack_var` との間隔 (gap) が必要幅 E より小さい。
- 次の `stack_var` が無い 5 組 (`function_d26460`・`function_e4f310`・`function_977f50`・`function_441380`・`function_6905f0`) は、gap が測れていない (親の frame 境界までの間隔は未確認)。
- 修復範囲の決定 (暫定): **13 組は修復の対象外** (R8 で覆えない・§3)。残りの 5 組は gap を測れていないため、範囲は未確定。確定に要る測定は §4。
- 本 run では修復を実装していない。判定は既存 REPORT (`REPORT_SHX-T48.md` §4) の X・E を入力にした。
- 修復の対象外とした 13 組でも、親の frame の再配置 (次の stack_var を避けて callee 用の領域を確保する) で覆える可能性は残る。それは別の実装 issue の範囲で、本 REPORT では判定しない。

## 2. 測定条件

- 素材: `work-m11` (`tools/m11/work/boot_final3.ll`・529,468 行)。ただし §5 のとおり、前回の REPORT の測定時 (529,619 行) と一致しない。
- 判定: `tools/m11/frame_share/neighbor_gap.py` (新規)。入力は `REPORT_SHX-T48.md` §4 の表 (X・E)、IR は親関数内の `%stack_var_N = alloca` の集合。
- 負荷: 測定時の 1 分平均 load は取得していない (本 run では判定を IR の読み取りのみに限った)。

## 3. 組ごとの判定

| 親 | callee | X | E | 次の stack_var (gap) | 判定 |
|---|---|---|---|---|---|
| `function_43f800` | `function_43f440` (15 site) | -136 | 153 | -72 (64) | R8 で覆えない |
| `function_43f800` | `function_43f490` (2 site) | -136 | 153 | -72 (64) | R8 で覆えない |
| `function_43f800` | `function_43f550` (5 site) | -136 | 84 | -72 (64) | R8 で覆えない |
| `function_441730` | `function_441500` (3 site) | -120 | 136 | -52 (68) | R8 で覆えない |
| `function_441730` | `function_441560` (1 site) | -120 | 112 | -52 (68) | R8 で覆えない |
| `function_d26460` | `function_d26430` (5 site) | -104 | 48 | 無し | gap 未測定 |
| `function_e4f310` | `function_e4f2d0` (3 site) | -40 | 56 | 無し | gap 未測定 |
| `function_6a25b0` | `function_6a23d0` (2 site) | -88 | 121 | -52 (36) | R8 で覆えない |
| `function_6a2820` | `function_6a26e0` (2 site) | -88 | 121 | -44 (44) | R8 で覆えない |
| `function_977f50` | `function_977870` (2 site) | -88 | 160 | 無し | gap 未測定 |
| `function_441380` | `function_440d30` (1 site) | -40 | 84 | 無し | gap 未測定 |
| `function_441b20` | `function_441930` (1 site) | -168 | 284 | -104 (64) | R8 で覆えない |
| `function_11e7430` | `function_11e6c00` (1 site) | -136 | 88 | -64 (72) | R8 で覆えない |
| `function_1280530` | `function_1280170` (2 site) | -648 | 664 | -440 (208) | R8 で覆えない |
| `function_13105d0` | `function_13104e0` (1 site) | -120 | 136 | -76 (44) | R8 で覆えない |
| `function_de43b0` | `function_de4120` (1 site) | -136 | 172 | -80 (56) | R8 で覆えない |
| `function_f40840` | `function_f3d5e0` (1 site) | -18040 | 17992 | -17992 (48) | R8 で覆えない |
| `function_6905f0` | `function_690580` (5 site) | -152 | 176 | 無し | gap 未測定 (欠落候補は #5587) |

- 次の stack_var 無しの 5 組は、親 IR の alloca 名だけでは上限が決まらない (IR に rbp 基準の frame 境界が無い)。上限は機械語の prologue と親の frame 境界から測る必要があり、本 run では未測定。

## 4. 残り (次の run / 子 issue)

| 未了 | 影響 | 起票先 |
|---|---|---|
| gap 無し 5 組の親の frame 境界 (関数末尾までの間隔) の測定 | R8 の範囲の確定 | 本 issue の次の run (親 #5576 の未了) |
| 再生成 IR (HEAD の `m11_gen_ir2.sh` → `m11_build.sh`) での X・E の再測定 | §5 の差分の解消 | 本 issue の次の run |
| `function_6905f0` → `function_690580` の欠落候補 4 site | 同上 | #5587 |
| `function_40b620` → `function_40b290` の call 欠落 3 site | `no_ir_call` のため本表の対象外 | #5586 |

## 5. 素材の IR との差

- 素材の `boot_final3.ll` は 529,468 行。REPORT_SHX-T48 §4.1 の 529,619 行と一致しない。
- `function_6905f0` は、REPORT の 244892〜244958 行に対し、この IR では 244791 行で定義される。call (`%31`) は 244849 行で、約 100 行ずれている。
- `function_43f800` の `stack_var_-136` (49 箇所) は、X が一致する。構造は REPORT と整合する一方、行の対応は取れていない。
- したがって §3 の gap は親の alloca 集合から直接読んだ値で、REPORT の表の X・E は前 run の値を使っている。再生成 IR で測り直すまでは、表の値を確定値とは扱わない。
