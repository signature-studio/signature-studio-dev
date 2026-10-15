# Fresh Air REPORT 付録 (#4071 / FA-51): KH のみ snap-in `vocalfilter` の SC 側との同一入力差分 (C4〜C6)

- 親: #3741 (FA-45)・#52 (FA-5)。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。前段: [REPORT_APPENDIX_FA45.md](REPORT_APPENDIX_FA45.md) §5。

## §1. 結論

| 項目 | 結果 |
|---|---|
| SC 側の root | `0x1808e1fa0` (process 本体)。FA-45 が使った `0x1808e1f30` は deleting destructor で process ではなかった (§2) |
| KH 側の root | `0x18085a730` (formant process, `snapins.json` の `formant`・ns `vocalfilter`) |
| C4 同一入力 | 同一 seed `0x5F17E4`・N=200・600 call。param 写像は両側の逆アセンブルで確認済み (§2) |
| L/R (C5) | 600/600 call で bit 一致 (測定値・写像確定後の再測定 §3) |
| state (C5) | §3 の旧窓では 591/600 (`S+0xa0`)・600/600 (`S+0xca0`)。§7 で窓を確定して再比較: DF2 は 591/600 不一致 (組 2・3・6・7、相対差 ≤3.4e-9)、ctx 本体は 600/600 一致 (`S+0xca0` の不一致はポインタ値のみ) |
| 意味の同一性 | **未判定**。bit 不一致の原因 (組 2・3・6・7 の丸め差) が未特定 (§7.3) |

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

- 測定 commit: `532617a68` (写像の読みと KH harness を直した最後の commit。以降のコード差分は無い)。nproc=4・load 1 分値 0.02〜0.09。素材は `work-liftlib-targets` を `$ARTIFACTS_DIR` から展開したもの (`SlateCore.core_64`・`HeartCore.core_64`)。
- 実行: `SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_semantic_vf_scen.sh 200 0x5F17E4 0` (fma=1 は末尾を `1`)。
- 実測: fma=0 `real 3.665 s`・`user 0.560 s`・EXIT=0 (初回のため clang の build を含む)。fma=1 `real 0.675 s`・`user 0.552 s`・EXIT=0。
- fma=0 と fma=1 の `cmp.txt` はバイト一致 (`cmp`)。
- 出力 (fma=0 と同一の `cmp.txt`): `scenarios=200 calls=600`・`L/R bit mismatch calls=0`・`S+0x98 0`・`S+0xa0 591/600`・`S+0x4a0 0`・`S+0xca0 600/600`。前回 (`6e5a837a6`) の報告値と一致した。
- smoke (`ks_sc_vf_smoke.sh 20`・root 訂正後): fma=0/1 とも rows=20・ERR=0・stderr=0 B (smoke は SC 単独で、この commit の写像変更の影響を受けない)。

`cmp.txt` (fma=0・fma=1 共通):

```
scenarios=200 calls=600
L/R bit mismatch calls=0
state field mismatch [sr S+0x98/KH+0x60]: calls=0 first(scen,byte)=None
state field mismatch [arr S+0xa0/KH+0x70]: calls=591 first(scen,byte)=('S0', 104)
state field mismatch [arr S+0x4a0/KH+0x470]: calls=0 first(scen,byte)=None
state field mismatch [ctx S+0xca0/KH+0xc70]: calls=600 first(scen,byte)=('S0', 1640)
state word mismatch [sr S+0x98/KH+0x60]: words=0 rel>1e-3 (|SC-KH|/|KH|)=0
state word mismatch [arr S+0xa0/KH+0x70]: words=4417 rel>1e-3 (|SC-KH|/|KH|)=389
state word mismatch [arr S+0x4a0/KH+0x470]: words=0 rel>1e-3 (|SC-KH|/|KH|)=0
state word mismatch [ctx S+0xca0/KH+0xc70]: words=1200 rel>1e-3 (|SC-KH|/|KH|)=1200
```

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

- 受入 1 (KH param 写像の機械語読みで確定・根拠): **達成**。両側の逆アセンブル行で §2 の表に書いた (`HeartCore.core_64` `0x18085a730`・`SlateCore.core_64` `0x1808e1fa0`)。
- 受入 2 (同一 seed・N=200 の bit 一致の実測 C5): 測定は実施済み (§3、`532617a68`、fma=0/1)。L/R 600/600 は一致。state は `S+0xa0` 591/600・`S+0xca0` 600/600 が不一致。state 窓の確定は #4417 (FA-54) に残す。よって受入 2 は「L/R の一致と state 不一致の記録まで」で、意味の同一性の判定は未達。
- 受入 3 (実測の記載先): **逸脱**。issue は `REPORT_APPENDIX_FA45.md` の後続節に書くことを求めたが、実測は本付録 (FA51) に置く。FA45 は root の訂正 (§6) のみ。逸脱はこの記述で明記する。
- 受入 3 (実測の記載先): **逸脱**。issue は `REPORT_APPENDIX_FA45.md` の後続節に書くことを求めたが、実測は本付録 (FA51) に置く。FA45 は root の訂正 (§6) のみ。逸脱はこの記述で明記する。

## §5.1 再測定 (本 run)

- 実施 (round 2 の指摘 2 への対応)。素材 `work-liftlib-targets` は `$ARTIFACTS_DIR` に存在した (展開して使用)。写像の読みを直した commit `532617a68` の head で `ks_semantic_vf_scen.sh 200 0x5F17E4` を fma=0/1 で実行し、§3 に測定 commit と `cmp.txt` を書いた。報告値 (L/R 0/600・`S+0xa0` 591/600・`S+0xca0` 600/600) と一致した。写像の読みは変えていないので、数値が変わらないのは想定どおり。

## §7. 後続 (#4417 / FA-54): DF2 状態の対応の確定と窓での再比較

§4 の「state 比較窓の確定」を解いた節。結論は次の表 (実測・測定 commit `faeb66ba4`・§7.2)。

| 項目 | 結果 |
|---|---|
| DF2 状態の対応 (機械語) | SC `S+0xa0`・KH `this+0x70` が起点。16 B の f64 ペア 8 組 (0x80 B)。SC 組 i と KH 組 i が同じ位置 (恒等写像)。根拠は §7.1 |
| 窓 (確定) | `S+0x98` (sr, 8 B)・`S+0xa0`〜`+0x120` (DF2, 0x80 B)・`ctx+0x000`〜`+0x668` (ポインタ以外)。`ctx+0x668`〜`+0x670` は合算バッファのアドレスなので状態として比べない (§7.2) |
| L/R (C5) | 600/600 call bit 一致 (§3 の再現) |
| sr (C5) | 600/600 call bit 一致 |
| DF2 (C5) | 591/600 call で bit 不一致。組 0・1・4・5 は 600/600 一致。組 2・3・6・7 が不一致 (577・565・578・564 call)。最大相対差 3.371e-09 (§7.2) |
| ctx 本体 (ポインタ以外) (C5) | 600/600 call bit 一致 |
| 判定 (C6) | bit 不一致の確定のみ。「意味が違う」とは断定しない。組 2・3・6・7 の差の原因は未特定 (§7.3) |

### §7.1 対応の根拠 (機械語の読み + 実測)

- SC (`SlateCore.core_64` `0x1808e1fa0`・`objdump -d -M intel`): `lea/movups/mulpd` の組で `[rsi+0xa0]`〜`[rsi+0x110]` の 8 組 (16 B 単位) を読み書きする。`rsi` は `this` (= `S`)。
- KH (`HeartCore.core_64` `0x18085a730`・同じ方式): `rax=this+0x70`・`rcx=+0x80`・`rdx=+0x90`・`r8=+0xa0`・`r9=+0xb0`・`r10=+0xc0`・`r11=+0xd0`・`rdi+0xe0` の 8 組 (16 B) を読み書きする。
- 実測の裏付け (`tools/targets/freshair/ks_vf_state_map.py`): 組 i 同士の bit 一致数の対角が 600 (組 0・1・4・5)。組 2・3・6・7 は対角が 23・35・22・36 で、同じ組の f64 値比較も同じ数 (hex 比較と struct の比較は独立に一致)。組 8 以降 (0x20 組) は両側ともゼロ。別の組との一致 (ずれ) は見つからない。
- 写像の確からしさ: 組 i の読み書きの位置 (SC `+0xa0+16i`・KH `+0x70+16i`) が一致することを命令の並びで読んだ。組の中身が同じ論理状態かどうかは、命令の読みだけでは確定しない (組 2・3・6・7 の差が残るのはこのため。§7.3)。

### §7.2 窓での再比較 (N=200・seed `0x5F17E4`・600 call・fma=0/1)

- 測定 commit: `faeb66ba4` (コードの最終 commit。REPORT の追記と 2 本の判定スクリプトだけを足した)。実行経路の 6 ファイル (`ks_semantic_vf_scen.sh`・`ks_semantic_vf_kh.c`・`ks_filter_scen_cmp.py`・`lift2/native/native_vocalfilter.c`・`lift2/gen_vf_scen.py`・`lift2/pokes.txt`) は §3 の `532617a68` から `faeb66ba4` まで差分 0 (`git diff 532617a68 faeb66ba4 -- <6 ファイル>` = 0 行)。`lift2/` 全体では `native/native_ctrl.c`・`native/native_stereo.c` が変わっているが、これらは実行経路の外。差分 0 の証跡 (6 ファイル・測定 commit から HEAD まで): `git diff faeb66ba4 HEAD -- tools/targets/freshair/ks_semantic_vf_scen.sh tools/targets/freshair/ks_semantic_vf_kh.c tools/targets/freshair/ks_filter_scen_cmp.py tools/targets/freshair/lift2/native/native_vocalfilter.c tools/targets/freshair/lift2/gen_vf_scen.py tools/targets/freshair/lift2/pokes.txt` の出力は 0 行 (REPORT の追記は測定の対象外)。nproc=4・load 1 分値 0.04〜0.32。
- 実行: `SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_semantic_vf_scen.sh 200 0x5F17E4 {0,1}`。
  実測 `real 0.63 s`・`user 0.52〜0.53 s`・EXIT=0 (fma=0/1 とも)。fma=0 と fma=1 の `cmp.txt` は `cmp` でバイト一致。
- 窓の判定 (`tools/targets/freshair/ks_vf_state_cmp.py`・fma=0/1 とも同じ出力):

```
calls=600
sr        S+0x98/KH+0x60        bit mismatch calls=0
DF2 f64x16 S+0xa0/KH+0x70 (0x80 B) bit mismatch calls=591
ctx 0x000..0x668 (excl. pointer)  bit mismatch calls=0
ctx 0x668..0x670 (pointer field)  mismatch calls=600 (harness address, not state)
per DF2 pair (f64): calls with diff / max |SC-KH|/|KH|
  pair 0 (S+0xa0 / this+0x70): calls=0 max_rel=0.000e+00
  pair 1 (S+0xb0 / this+0x80): calls=0 max_rel=0.000e+00
  pair 2 (S+0xc0 / this+0x90): calls=577 max_rel=2.444e-10
  pair 3 (S+0xd0 / this+0xa0): calls=565 max_rel=3.371e-09
  pair 4 (S+0xe0 / this+0xb0): calls=0 max_rel=0.000e+00
  pair 5 (S+0xf0 / this+0xc0): calls=0 max_rel=0.000e+00
  pair 6 (S+0x100 / this+0xd0): calls=578 max_rel=1.064e-09
  pair 7 (S+0x110 / this+0xe0): calls=564 max_rel=5.679e-10
```

- 「591/600」の数え方: `ks_vf_state_cmp.py` は DF2 の 0x80 B 全体を hex で比べ、差が 1 つでもある call を数える (591 call)。`ks_filter_scen_cmp.py` の 591 は arr 領域 (0x200 B) を hex で比べた call 数で、同じ call 集合を指すとは限らない。組ごとの内訳は `ks_vf_state_cmp.py` の値を使う。
- ctx の 0x668〜0x670 (600/600 不一致) は、ハーネスが `this+0x12d8` に置く合算バッファのアドレス (`0x200000000` 系の値。`ks_semantic_vf_kh.c` の `SUM_VA`) と、SC 側の対応位置が 0 のままであることによる。状態ではないので窓から外した。

### §7.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 組 2・3・6・7 の f64 丸め差 (相対 2.4e-10〜3.4e-9) の原因 (演算順・係数の精度のどちらか) | 591/600 call の bit 不一致の原因が未特定。意味の同一性の判定は未達 (C6: bit 不一致の確定のみ) | 親 #4071 への提案 (本 issue のコメント) |
| 組 0・1・4・5 と 2・3・6・7 で差が出る条件 (どの係数の経路か) | 上と同じ | 同上 |

## §6. FA-45 §5 の訂正

- FA-45 の smoke (`0x1808e1f30`) は deleting destructor を実行していた。`ERR 0・20 行 × 2`・fma 間で同一の結果は process の実行の証拠にならない。
- 本 PR で root を `0x1808e1fa0` に直し、smoke を再実行した (§3)。
