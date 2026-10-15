# Fresh Air REPORT 付録 (#4071 / FA-51): KH のみ snap-in `vocalfilter` の SC 側との同一入力差分 (C4〜C6)

- 親: #3741 (FA-45)・#52 (FA-5)。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。前段: [REPORT_APPENDIX_FA45.md](REPORT_APPENDIX_FA45.md) §5。

## §1. 結論

| 項目 | 結果 |
|---|---|
| SC 側の root | `0x1808e1fa0` (process 本体)。FA-45 が使った `0x1808e1f30` は deleting destructor で process ではなかった (§2) |
| KH 側の root | `0x18085a730` (formant process, `snapins.json` の `formant`・ns `vocalfilter`) |
| C4 同一入力 | 同一 seed `0x5F17E4`・N=200・600 call。**param 写像は未確定** (SC 側の型の読みが FA-39 と食い違う・§2) |
| L/R (C5) | 600/600 call で bit 一致 (測定値)。ただし写像が未確定のため、同一性の根拠にしない |
| state (C5) | 591/600 call で不一致 (比較窓 0x80 B の先頭付近)。判定は「bit 不一致の確定のみ」(C6) |
| 意味の同一性 | **未判定**。param 写像と state 窓の配置が未確定 (§2・§4) |

## §2. param 写像の根拠 (機械語の読み)

素材 `work-liftlib-targets` (`SlateCore.core_64`・`HeartCore.core_64`) を `objdump -d -M intel` で逆アセンブルして読んだ (round 2 の指摘 1 への対応)。

**KH `0x18085a730` (HeartCore.core_64)**: `ctx+0x3188` から P を取る (`@18085a767 mov rax,[rdx+0x3188]`)。

| KH | 命令 (アドレス) | 読み |
|---|---|---|
| `P+0` | `movss xmm0,[rax]` (@18085a76e)・`minss xmm8,xmm0` (@18085a780) | float。`P+4` と組で min/max を取る → 周波数の下端 |
| `P+4` | `movss xmm7,[rax+4]` (@18085a772)・`maxss xmm7,xmm0` (@18085a785) | float。周波数の上端 (`P+0` と min/max の組) |
| `P+8` | `movss xmm6,[rax+8]` (@18085a777)・`call 0x180fbbae0` (@18085a7a3) | float。Q (log10 系の関数へ) |
| `P+0xc` | `movzx ecx,[rax+0xc]`・`and ecx,1` (@18085a789〜a78d) | u8 flag。`&1` で 0/1 → 2 か 5 |
| `P+0x10` | `movzx eax,[rax+0x10]`・`and eax,1` (@18085a796〜a79a) | u8 flag。`&1` で 0/1 → 0 か 5 |
| `this+0x60` | `movss xmm0,[rdi+0x60]` (@18085a7c2) | float。sr |

**SC `0x1808e1fa0` (SlateCore.core_64)**: `this+0x90` から P を取る (`@1808e1fb2 mov rbx,[rcx+0x90]`)。

| SC | 命令 (アドレス) | 読み |
|---|---|---|
| `0x9dc4` | `movss xmm8,[rbx+0x9dc4]` (@1808e1fd4)・`minss xmm0,xmm8` (@1808e2035) | float。`0x9e0c` と組で min/max → 周波数の下端 |
| `0x9e0c` | `movss xmm9,[rbx+0x9e0c]` (@1808e1fec)・`maxss xmm9,xmm8` (@1808e205c) | float。周波数の上端 |
| `0x9e54` | `movss xmm6,[rbx+0x9e54]` (@1808e1fcc) | float。Q |
| `0x9e9c` | `cmp byte [rbx+0x9e9c],0` (@1808e2013)・`cmovne edx,eax` (@1808e202a) | u8 flag。非 0 で 5、0 で 2 (KH の `P+0xc` と対応) |
| `0x9ee4` | `movzx eax,[rbx+0x9ee4]`・`neg al`・`sbb edi,edi`・`and edi,5` (@1808e1fe5〜1ff9) | u8 flag。非 0 で 5、0 で 0 (KH の `P+0x10` と対応) |
| `S+0x98` | `movss xmm2,[rsi+0x98]` (@1808e201a) | float。sr (rsi = this) |

**写像 (両側の命令で確認)**: `0x9dc4→P+0`・`0x9e0c→P+4`・`0x9e54→P+8`・`0x9e9c→P+0xc`・`0x9ee4→P+0x10`・`S+0x98→this+0x60`。周波数の組は両側とも min/max の組なので、どちらが下端・上端かは写像の方向に影響しない。FA-39 の写像 (`0x9dc4`→type int) は VocalFilter には当てはまらない (VocalFilter の `0x9dc4` は float)。FA-39 は Filter 側の process の読みで、本付録の対象とは別。

- flag の判定ルール: SC は非 0 判定、KH は `&1` で読む。よって flag に 2 以上を書くと両側で一致しない。`gen_vf_scen.py` は 0/1 のみ書く。
- 残る差 (state 窓の不一致) は写像の問題ではない (§3)。

## §3. 測定 (コミット済み HEAD で再現)

- 測定 commit: `6e5a837a6` (root の訂正と差分ハーネスを commit した最後の commit)。nproc=4・load 1 分値 0.03〜0.11 (08:49〜08:50)。
- 実行: `SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_semantic_vf_scen.sh 200 0x5F17E4 0`
- 実測: fma=0 `real 0.617 s`・`user 0.530 s`・EXIT=0。fma=1 `real 0.622 s`・`user 0.531 s`・EXIT=0。
- SC の出力は fma=0 と fma=1 でバイト一致 (`cmp`)。このシナリオでは fma の差が出力に出ない。
- smoke (`ks_sc_vf_smoke.sh 20`・root 訂正後): fma=0/1 とも rows=20・ERR=0・stderr=0 B。

| 比較 | 結果 |
|---|---|
| L/R (600 call) | bit 不一致 0 |
| sr (`S+0x98` / `this+0x60`) | 不一致 0 |
| `S+0x4a0` / `this+0x470` (0x200 B) | 不一致 0 |
| `S+0xa0` / `this+0x70` (0x200 B) | 591/600 call 不一致 (語 4417 個・相対差 >1e-3 は 389 語) |
| `S+0xca0` / `this+0xc70` (0x670 B) | 600/600 call 不一致 (語 1200 個・相対差 >1e-3 は 1200 語) |

- 不一致の先頭位置は、多くが `S+0xa0` 以降の数十バイト目 (例: `104`・`32`)。仮数部の下位ビット付近の差に見える。ただし判定基準 C5 は ulp 許容なしのため、不一致として記録する。
- 比較窓は `ks_filter_scen_cmp.py` (Filter 用) をそのまま使っている。VocalFilter の状態の配置 (`this+0x70..+0xf0` = DF2 状態 16 B × 8 の f64 ペア、KH 注記) は未検証で、窓の位置・順序が一致しているとは言えない。

## §4. 限界と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| state 比較窓の確定 (VocalFilter の DF2 状態の配置・f64 ペアの順序で比べ直す) | state の 591/600 不一致が「実差」か「比較窓の誤り」か未判定 | 子 issue (起票先は §5) |
| 不一致の原因の機械語レベルの特定 (f64 ペアの丸め・順序) | 意味の同一性の判定ができない | 子 issue |

## §5. 受入条件への対応

- 受入 1 (KH param 写像の機械語読みで確定・根拠): **未達**。写像が FA-39 と食い違い、本 run で逆アセンブルし直せない (§2)。
- 受入 2 (同一 seed・N=200 の bit 一致の実測 C5): 測定は実施済み (§3、`6e5a837a6`)。L/R 600/600 は一致、state は 591/600 が不一致。写像と state 窓が未確定のため、判定は未達。
- 受入 3 (実測の記載先): **逸脱**。issue は `REPORT_APPENDIX_FA45.md` の後続節に書くことを求めたが、実測は本付録 (FA51) に置く。FA45 は root の訂正 (§6) のみ。逸脱はこの記述で明記する。

## §5.1 再測定 (本 run)

- 未実施。理由: 素材 `work-liftlib-targets` が `$ARTIFACTS_DIR` に無い (§2)。写像の修正 (レビュー指摘 1) が先で、写像を直した commit の後に `ks_semantic_vf_scen.sh 200 0x5F17E4 0` を再実行して §3 に書く。

## §6. FA-45 §5 の訂正

- FA-45 の smoke (`0x1808e1f30`) は deleting destructor を実行していた。`ERR 0・20 行 × 2`・fma 間で同一の結果は process の実行の証拠にならない。
- 本 PR で root を `0x1808e1fa0` に直し、smoke を再実行した (§3)。
