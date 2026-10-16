# SHX-T44 (#4189): 入れ子手続 function_448490 の親フレーム site の機械語判定 (D23)

## 1. 結論

- 受入 1 (`function_448490` → `function_4483f0` の 8 site と `function_448430` の 2 site の機械語判定) を満たした。10 site すべてで、親が `mov rcx, rbp` で親フレームを静的リンクとして渡す。`function_4483f0` の 8 site は callee が親の `[rbp+0x48]` (IR `-32`・count)・`[rbp+0x4c]` (IR `-28`・loop 変数) を読み書きする。`function_448430` の 2 site は `[rbp+0x4c]` の読みと `[rbp+0x70]` のみで、`[rbp+0x48]` には触らない (§3)。
- 判定の結論は「通常の rbp 渡しではなく、親の局所を callee が書き換える入れ子手続の形」。ただし IR の親 `function_448490` は、この書き換えを親の SSA に戻さない。D23 の機構と整合する。
- 受入 2 (修復 pass の実装)・3 (OFF/ON 実測)・4 (D23 の「修復」列) は本 run では未実施。前回 `[SHX-T40]` (#3234) は修復 ON で hang・OOB となり既定 OFF のまま main にある (`tools/m11/REPORT_SHX-T40.md`)。修復の設計 (call 前後の同期) は別 issue `[SHX-T45]` #4459 に移す (§5)。
- 受入 4 のうち、D23 の修復列は未達のため更新しない (`docs/DEFECTS.md` は変えない)。

## 2. 測定条件

- 測定 commit: `319b01a80` (origin/main。baseline・site 判定はこの commit のコードで行った)。本 PR の差分は `tools/m11/REPORT_SHX-T44.md` と `tools/m11/frame_share/site_check.py` (解析スクリプトの追加のみ・既存のコードは変えない)。`git diff 319b01a80 HEAD -- tools/m11/ldfix tools/m11/frame_share/detect.py tools/m11/frame_share/classify.py tools/m11/m11_gen_ir2.sh` は 0 行。
- 素材: `fl-win64.tar.zst` の `extracted/block00031_PE.bin` (22,227,016 B)・`work-m11.tar.zst` (`tools/m11/work/`・gitignore)。`toolchain-emsdk` は runner 既存。`toolchain-retdec` は使わない (lift を再実行していない)。
- IR: `FL_WIN64_DIR=/tmp/opencode/fl bash tools/m11/m11_gen_ir2.sh` (52 s・`[gen_ir2] OK: work/boot_final.ll (490761 行)`)。`m11_build.sh` 25 s・`signature mismatch: 0, undefined symbol: 0`。
- baseline (既定 OFF・修復なし): `shimx_link/build.sh --trace --soft` 15 s・`mismatch=0 undefined=0 duplicate=0`。実 boot `run_trace.mjs` 0.49 s・`units_run=17`・`dllmain_done=true`・`total_calls=106`・`va_calls=2`・`icall_ok=24`・`icall_miss=1`。前回 REPORT_SHX-T28 §7 と一致。
- 負荷: 測定時の 1 分平均 load は 0.59〜0.95 (nproc 4)。

## 3. site 単位の判定 (受入 1)

検出器の出力 `frame_share/site_check.py` (機械語の線型 disasm・`detect.py` の `call_site_base` と `walk_callee` を流用)。

| call (VA) | callee | call 直前の引数設定 (機械語) | callee の rbp 基準アクセス (off:size:kind) |
|---|---|---|---|
| `0x448588` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rax]` | `0x48:4:rmw`・`0x4c:4:load/rmw`・`0x70:8:load` |
| `0x4485c6` | `function_4483f0` | `mov rcx, rbp`・`mov dx, 0x6e` | 同上 |
| `0x44864a` | `function_448430` | `mov rcx, rbp`・`lea rdx, [rip+0x1ae]` | `0x4c:4:load/rmw`・`0x70:8:load` |
| `0x44865b` | `function_448430` | `mov rcx, rbp`・`lea rdx, [rip+0x1b1]` | 同上 |
| `0x448692` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rdx+rax*2-2]` | `0x48:4:rmw`・`0x4c:4:load/rmw`・`0x70:8:load` |
| `0x4486ca` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |
| `0x4486e0` | `function_4483f0` | `mov rcx, rbp`・`movzx rdx, word [rdx+rax*2-2]` | 同上 |
| `0x448708` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |
| `0x448720` | `function_4483f0` | `mov rcx, rbp`・`mov dx, 0x3a` | 同上 |
| `0x44872c` | `function_4483f0` | `mov rcx, rbp`・`mov edx, eax` | 同上 |

- 第 2 引数 (rdx) は、文字・長さ・即値のいずれか。第 1 引数 (rcx) はすべて親の `rbp`。
- callee `function_4483f0` の先頭: `mov rbx, rcx` で親の `rbp` を保持し、`mov rcx, [rbx+0x70]` (親の引数 home) を `function_413760` へ渡す。続けて `[rbx+0x4c]` を符号拡張して書込み先の添字にし、`[rbx+0x4c]` と `[rbx+0x48]` を +1 する。
- `0x448578`・`0x448754` は `call` 命令で、`mov rcx, rbp` の渡しではないので本節の対象外。直前の引数設定は `0x448570` が `lea rcx, [rbp+0x38]`、`0x44874b` が `lea rcx, [rbp+0x30]` で、局所の番地を渡す。`0x44873f` の `mov edx, [rbp+0x4c]` は親の読みで、callee へ渡す形ではない。

## 4. 親 IR との突合 (判定の補足)

- 親の機械語: `0x4484d3` `mov dword [rbp+0x48], 1`・`0x4484e4` `mov dword [rbp+0x4c], 1` (初期化)。IR の親には `store i32 1` が `-32` (`%stack_var_-32.0.reg2mem`) の 1 本だけで、`-28` (`[rbp+0x4c]`) の初期 store は無い (REPORT_SHX-T28 §6 と一致)。
- 親 IR の `%stack_var_-104` は `alloca [6 x i64]` (48 B)。callee が触る `+0x70`・`+0x78` を覆わず、`function_4483f0` / `function_448430` の呼出しは `ptr nonnull %stack_var_-104` (48 B) を渡している。
- 親 IR で `-32` は `reg2mem` の SSA 分解で扱われ、callee の書込み (`+0x48` の +1) が親 IR の以降の読みに届かない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 親フレームを callee の view に結線する修復 pass の実装 (`function_448490` の `-28` store の補完、`this` object の 120 B 拡幅、call 前後の count・length・arg1 の同期)。既定 OFF | unit 18 を越えられない (`VirtualAlloc(0x76910000)` の不発) | `[SHX-T45]` #4459 (親 #4123) |
| 修復 OFF/ON の before-after 実測 (`units_run ≥ 18`・`VirtualAlloc` 不発・`MessageBoxA` 不発・ネガコン) と、`docs/DEFECTS.md` D23 の「修復」列 | 修復の受入 | `[SHX-T45]` #4459 |
| `function_448430` 本体の機械語確認 (2 site)。本 REPORT は callee の読み先のみ確認 | 2 site の判定の裏付け | `[SHX-T45]` #4459 |
| 真の D23 かどうかの site 単位の確定 (IR 幅による分類は REPORT_SHX-T28 §10 で実施済み) | 修復範囲の決定 | `[SHX-T45]` #4459 |

## 6. 301 site の機械語突合 (REPORT_SHX-T28 §10 の残り・#4189 の再開分)

- 追加: `tools/m11/frame_share/base_check.py` (commit `8222772c9`)。親の prologue を機械語で読んで rbp の entry 基準位置 X (`push` 数と `sub rsp, imm` から計算) を求め、親 IR が callee へ渡す alloca 名が `stack_var_X` と一致するかを site ごとに見る。一致しない site は `base_mismatch`。
- 判定: `ir_truncated` (base 一致・callee の最大端 E > alloca 幅 S)・`ir_covers` (E ≤ S)・`unmatched` (IR に該当 call が無い)・`no_prologue` (prologue のパターンに合わず未判定)。`base_mismatch` は 0 件。
- 注: 「IR の `stack_var_N` は entry rsp 基準の N」という対応は §6 の推定 (REPORT_SHX-T28 §6) をそのまま使う。`base_check.py` はこの推定を site 全体に当てはめただけで、推定そのものは未確認。
- 機械語で確認したのは「親の rbp の位置」と「IR の alloca 名」の一致だけ。call 直前の引数と callee の読み先の site 単位の突合は、`function_448490` の 10 site (§3) だけ行った。残り 291 site は base の一致のみ。
- 残り 291 site を `frame_share/site_check.py --sites` で機械語から一括抽出した (301 件すべて取得)。callee の rbp 基準アクセスを 3 区分に分けた (線型走査の粗い分類・真の D23 の確定ではない): `write_local` 121 (callee が親の局所 `+0x70` 未満へ書く)・`read_local` 106 (読むだけ)・`arg_home_only` 74 (`+0x70` 以上の引数 home だけ)。site 単位の表は `REPORT_SHX-T44_APPENDIX.md`。
- IR 突合との関係: `ir_truncated` 204 のうち `arg_home_only` は 67。引数 home だけを読む site は親の局所の書換えを示さないので、alloca 幅だけで D23 とみなすと過大に数える。`ir_covers` 38 のうち `write_local` は 8 で、偽陽性とは言い切れない。
- 前回 run (#4189 の停止) の `ir_truncated 242 / ir_covers 0` は、素材 `work-m11` を `-C tools/m11` で展開して誤配置したことが原因。`-C .` (リポジトリ直下) で展開すると §10 と一致する (204/38/56/3)。
- 未了 (本 issue で追跡): `write_local` と `read_local` の site ごとの「call 直前の引数が親の rbp 由来か」の確定 (線型走査の分岐無視を解消する必要がある)・`unmatched` 56 と `no_prologue` 3 の判定。

### 実測 (測定 commit `8222772c9`・IR は HEAD で再生成)

| 分類 | site 数 | (親, callee) 組 | 意味 |
|---|---|---|---|
| `ir_truncated` | 204 | 70 | base 一致・IR の alloca が callee の触る範囲より小さい (真の D23 の候補) |
| `ir_covers` | 38 | 3 | base 一致・alloca が範囲を覆う (偽陽性の候補) |
| `unmatched` | 56 | 19 | IR に該当 call が無く判定不能 |
| `no_prologue` | 3 | 2 | prologue が取れず判定不能 (`function_517b50`) |
| 合計 | 301 | 94 | `base_mismatch` 0 |

- `function_448490` の 10 site は全て親の rbp 位置 `-104`・IR の渡し先 `stack_var_-104` (48 B)・callee の必要幅 120 B で `ir_truncated`。
- `ir_covers` の 38 site の渡し先は `stack_var_-56` (22)・`stack_var_-104` (8)・`stack_var_-72` (8)。
- `classify.py` の `ir_frame_too_small` 207 は、`base_check.py` の `ir_truncated` 204 と `no_prologue` 3 の合計で、件数は一致する。

### 再現と注意 (実測時に見つかった事項)

- 素材 `work-m11.tar.zst` の `work/boot_final3.ll` (10-10 作成) は、この PR の HEAD の生成経路の IR と一致しない。その IR で `classify.py` を実行すると `ir_frame_too_small` 245・`unmatched` 56・`ir_frame_covers` 0 となり、§10 の 207 / 38 / 56 と合わない。`function_448490` の alloca も `[6 x i64]` ではなく `i64` (8 B) として見える。HEAD で `m11_gen_ir2.sh` と `m11_build.sh` を再実行すると、§10 の値 (207 / 38 / 56・組 72 / 3 / 19) と一致した。素材の IR は古く、§10 の測定には使えない。
- 手順: `FL_WIN64_DIR=<展開先> bash m11_gen_ir2.sh` → `bash m11_build.sh` → `python3 frame_share/detect.py --ir work/boot_final3.ll --out work/frame_share.json` → `python3 frame_share/classify.py --ir work/boot_final3.ll --sites work/frame_share.json` → `python3 frame_share/base_check.py --ir work/boot_final3.ll --sites work/frame_share.json --out work/base_check.json`。PE は `fl-win64.tar.zst` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 測定時の 1 分平均 load は 0.2〜0.9 (nproc 4)。
- 測定 commit から HEAD までのコード差分: `git diff 8222772c9 HEAD -- tools/m11/frame_share tools/m11/ldfix tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh` は 0 行 (測定は HEAD 上で実施。IR 生成・build の経路は 3da603ce6 から変えていない)。

### 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 301 site のうち 291 site の call 直前の引数と callee の読み先の site 単位の機械語突合 (`base_check` は base の一致だけ) | 真の D23 の確定 (`ir_truncated` 204 の中身) | #4189 (open のまま追跡) |
| `unmatched` 56 site (19 組) と `no_prologue` 3 site (`function_517b50`) の判定 | 修復範囲の決定 | #4189 |
| 素材の `work-m11` の `boot_final3.ll` が HEAD の生成経路と一致しない件 | 素材の再作成が必要か | #4189 (本節の注) |
