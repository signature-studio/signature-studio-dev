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

## 5a. 制御フローを考慮した site 確定 (#5575 / SHX-T48)

- 検出器 `tools/m11/frame_share/cfg_check.py` (新規)。301 site (`base_check.json`) を site ごとに判定する。
- **呼び出し側の確定** (条件 3 つ): (a) 直前の `mov rcx, rbp` から call までの区間 (`(mov, call]`) に分岐先 (合流点) が無い、(b) その区間で rcx (ecx/cx/cl を含む) が書き換えられない、(c) 親の rbp が prologue の `mov rbp, rsp` 以外で書かれない (エピローグの `pop rbp` は除く)。
- **callee 側**: `walk_callee_flow` で callee を基本ブロックに分け、rcx の別名を流れに沿って追う (合流では一致する別名だけ残す)。線型走査 (`site_check`) との比較。
- 判定の実測 (測定 commit `ad0f8e100`・IR は `m11_gen_ir2.sh` → `m11_build.sh` で再生成。PE は `block00031_PE.bin` 22,227,016 B):

| 項目 | 件数 |
|---|---|
| 301 site の呼び出し側判定 `confirmed` | **301** |
| うち分岐をまたぐ site (`label_between`) | 0 |
| callee の流れ感知走査が追えた site (`flow_ok`) | 301 |
| 流れ感知と線型走査の読み先が一致 | 295 |
| 一致しない site (分類は全て変わらず) | 6 |

- 不一致 6 site: `function_40f210→function_40f160` (0x40f412)・`function_441b20→function_441930` (0x441bb3)・`function_6a25b0→function_6a23d0` (2 site)・`function_977f50→function_977870` (2 site)。線型走査が分岐の反対側の別名を含めていた。`0x40f412` だけ判定が変わる: 線型走査の E=116 > S=88 で `ir_truncated`、流れ感知の E=64 ≤ S=88 で `ir_covers`。残りの 5 site は判定 (`ir_truncated`/`unmatched`) を変えない。
- 判定ロジックの検証: 陽性対照として、実 site `0x448588` の `mov` と `call` の間 (`0x448580`) に合流点を人工的に置くと `label_between` になった。`mov` 自身 (`0x44857d`) を置いたときは `confirmed` のままで、区間が半開区間 `(mov, call]` であることを確認した。
- **受入 3 の注意 (access_class の定義)**: `arg_home_only` は `off >= 0x70` で定義している。実測では 74 site のうち `+0x70` のみを読むのは **6 site**、`+0x70` より上 (`+0x8c`・`+0xb0`・`+0x15c`・`+0x1004f` など) を読むのが **68 site**。「引数 home (`+0x70`) だけを読む」という受入の前提は、このままでは 6 site しか満たさない。`+0x70` 超の読みは親の引数 home より上の領域への読みで、親の局所とは限らない (親 IR の alloca 外)。これは site 単位の確定の対象のまま残す。

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
- 残り 291 site を `frame_share/site_check.py --sites` で機械語から一括抽出した (301 件すべて取得)。callee の rbp 基準アクセスを 3 区分に分けた (線型走査の粗い分類・真の D23 の確定ではない): `write_local` 121 (callee が親の局所 `+0x70` 未満へ書く)・`read_local` 106 (読むだけ)・`arg_home_only` 74 (`+0x70` 以上の引数 home だけ)。site 単位の表は `REPORT_SHX-T44_APPENDIX.md` と `REPORT_SHX-T44_APPENDIX_2.md`。
- IR 突合との関係: `ir_truncated` 204 のうち `arg_home_only` は 67。引数 home だけを読む site は親の局所の書換えを示さないので、alloca 幅だけで D23 とみなすと過大に数える。`ir_covers` 38 のうち `write_local` は 8 で、偽陽性とは言い切れない。
- 前回 run (#4189 の停止) の `ir_truncated 242 / ir_covers 0` は、素材 `work-m11` を `-C tools/m11` で展開したことによる誤配置が原因と推定する (誤配置での再現は未確認)。`-C .` (リポジトリ直下) で展開すると §10 と一致する (204/38/56/3)。
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

## 5b. function_6905f0 → function_690580 の call site 突合 (#5587 / SHX-T50)

- 対象: `function_6905f0` (0x6905f0〜0x690763) の中で `call function_690580` の site。
  `function_690763` 所属の site (`0x690804`・`0x6908b3`・`0x6909d4`) は対象外で、子 SHX-T57 に移す。
- 判定スクリプト: `tools/m11/frame_share/callsite_audit.py`。画像全体の `e8 rel32` を走査して callee を指す site を抽出し、所属関数を `objdump` で線形逆アセンブルする。site を含む基本ブロック B の入口は、(a) B の直前命令が `ret`・`jmp`・`ud2`・`hlt` でなければ fall-through で到達しうる、(b) B と site への直接分岐・絶対参照の件数、の 2 点で判定する。
- 状態: **関数内からは到達しない** (SHX-T56 / #5640 で、関数内の間接 jmp 0 件により確認。関数外の表からの到達は画像全体の表復元をしておらず未排除。下の「SHX-T56 追加検証」を参照)。前版の「入口なし → 機械語として到達しない」の結論は、その時点では直接分岐・絶対参照の範囲に限られていたため撤回した (レビュー指摘 1)。
- 測定 commit: `b50c10552` (実行コードは `0c3aa8431` と同一。`git diff b50c10552 0c3aa8431 -- tools/m11/frame_share` は 0 行)。
- 素材: `work-m11.tar.zst` を `tools/m11/work/` 相当へ展開し、`m11_image.bin`・`boot1.drc.ll`・`boot_final3.ll` を使って測定 commit で実行した (下記の実出力)。
- IR 側: `boot1.drc.ll` の `@function_690580(` の call は 2 件 (`!14278` = `0x69073b`・`!14369` = `0x6909d4`)。`0x69073b` のみが `function_6905f0` 内。`boot_final3.ll` の `@function_690580(` の call は 3 件で、所属は次のとおり。244849 行 = `function_6905f0` (site `0x69073b` に対応)、245171 行 = `function_690763` (対象外)、513910 行 = trampoline wrapper `@m11_tr_function_690580` 内 (site ではない)。

### 再現 (`oc_artifacts: work-m11` で取得した素材を使う)

```
python3 tools/m11/frame_share/callsite_audit.py tools/m11/work/m11_image.bin 0x690580 0x6905f0:0x690763
```

実出力 (本 head で実行、画像全体の `e8 rel32` で callee `0x690580` を指す site は 5 件):

| site | 所属関数 | 呼び出し命令 | ブロック先頭 B | B の直前命令 | 直接参照 B/site | 絶対参照 B/site | 判定 |
|---|---|---|---|---|---|---|---|
| 0x6906ec | 0x6905f0 | `call 0x290580` | 0x6906d7 | jmp | 0/0 | 0/0 | 入口なし (直前 jmp は無条件転送・直接参照 0) |
| 0x69073b | 0x6905f0 | `call 0x290580` | 0x6906fc | nop | 2/0 | 0/0 | 到達しうる (fall-through または参照あり) |
| 0x690804 | (範囲外) | - | - | - | - | - | 範囲指定に含まれない |
| 0x6908b3 | (範囲外) | - | - | - | - | - | 範囲指定に含まれない |
| 0x6909d4 | (範囲外) | - | - | - | - | - | 範囲指定に含まれない |

結論: `0x6906ec` は直接分岐・絶対参照 0 件かつ直前が無条件 `jmp` で、入口なしと判定された。switch テーブル経由の確認 (下記 SHX-T56 追加検証) の結果、関数内からは `0x6906d7` に到達しない。`0x69073b` は fall-through で到達しうる。

### SHX-T56 追加検証 (switch テーブル経由の到達性, #5640)

- 測定 commit: 本 PR のコード変更は REPORT のみ (実行コードは `2c423ea2f` の `tools/m11/frame_share` と同一)。
- 直前ブロックの形: `0x6906d5` の `jmp 0x6906fc` が無条件転送で、`0x6906d7` (`nop; nop`) は直後に続く。`0x6906d7` を指す直接分岐 (rel8/rel32/jcc) は画像全体で 0 件、絶対参照 (4/8 byte LE) も 0 件。
- switch 経由の飛び先: 関数 `0x6905f0`〜`0x690c00` の線形逆アセンブルに間接 `jmp` (`jmp reg`・`jmp [mem]`) は 0 件。したがって、この関数内に switch テーブルを読んで飛ぶ分岐は無く、テーブル本体の相対オフセット復元の対象も無い。関数内の間接 `call` は 6 件あるが、ジャンプではなく、`0x6906d7` を飛び先にしない。
- 画像全体の `jmp reg` は 629 件。`movsxd` の近くにあるものも、`0x5e5eb6`〜`0x157b0a4` の関数外の位置だけだった。この範囲は個別に表の復元をしていない。
- 再現: `python3 tools/m11/frame_share/callsite_audit.py tools/m11/work/m11_image.bin 0x690580 0x6905f0:0x690763` の出力 (上表) は本検証と一致。
- 限界: 関数外の `jmp reg` が `0x6906d7` を飛び先にする可能性は、画像全体の表復元をしていないため完全には排除していない。関数 `0x6905f0` 内からの到達は、間接 jmp 0 件により無い。

### 検証 (本 run・合成バイナリ)

- 入力: `as` / `ld` で作った 0x400000 配置の小さな ELF (call 4 件、直前が `jmp`・`ret` の入口なしケースと、直接 `jmp` で入る入口ありケースを含む)。
- 出力: 4 site のうち `0x400009` (直前 `jmp`・参照 0) と `0x40001a` (直前 `ret`・参照 0) は「入口なし」、`0x400014` (直接分岐 1 件) は「到達しうる」と判定。`0x400000` は関数先頭で「到達しうる」。
- 本 run で直したもの: `objdump` の分岐先が `0x` 接頭辞の形で、call の確認が常に失敗していた。

### 限界

- switch テーブル (相対オフセット方式) による飛び先は走査していない (SHX-T56)。「到達しない」は直接分岐・絶対参照・無条件転送の範囲での結論に過ぎず、結論は「未確定」のまま。
- 線形逆アセンブルはデータ混在で同期がずれうる。ずれの有無は実画像の出力で確認する。

未解決 (起票先):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x6906ec` の switch テーブル経由の到達性 | 「入口なし」の結論の根拠 (実画像の表の判定を含む) | #5640 (SHX-T56) |
| `function_690763` 所属の 3 site (`0x690804`・`0x6908b3`・`0x6909d4`) の判定 | 欠落の有無 (本 PR の対象外) | #5641 (SHX-T57) |

