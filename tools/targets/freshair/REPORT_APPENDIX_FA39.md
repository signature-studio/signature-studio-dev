# freshair FA-39 (#3507) 付録: Filter の SC ⇄ KH 同一入力 native 差分

親: #2739 (FA-34)。判定基準の本体 `REPORT_APPENDIX_2739.md` (§1 C4〜C6・§3 VA 表) は main にも全 branch にも無い
(`git log --all -- tools/targets/freshair/REPORT_APPENDIX_2739.md` は空)。`ks_sc_native_smoke.sh` も無い。
本付録は issue 本文の基準 (同一 seed・L/R と処理後 state の bit 一致・許容差 0) を採った。
判定基準の正本 (#2739 側) は PM 判断待ち。既定案は issue 本文の基準を採用し、#2739 で差し替える。

## 1. 結論

- KH 側 (HeartCore 0x1804655e0) の実機機械語 harness を新設した (`ks_semantic_filter_kh.c`)。
- SC (SlateCore 0x180b6f050) と同一のシナリオ 200 本 (598 call) で比べた結果、**最初の call (新規状態) は 200/200 で L/R が bit 一致**。
  **2 回目以降の call は 228/398 で L/R が不一致**。判定は「一致しない」。
- 差の起点は 2 本目の係数バッファ (slot 1)。最初の call の後にすでに食い違う。
- fma=1 (SC) でも L/R 不一致は同じ 228/598 (集合も同じ)。state は 4 call だけ変わる。Filter の範囲と KH 側に FMA 命令は無く、L/R 不一致の起源として FMA 分岐は除外する (§3-3)。
- 原因は未特定。子 issue #3525 (FA-40) に切り出す (§6)。

## 2. 機械語の読み (根拠)

### 2-1 KH `0x1804655e0`

969 B。末尾は `jmp 0x1802ff250`。`objdump -d` で読んだ。

- 呼出し形: ms_abi の `process(rcx=this, rdx=ctx, r8=aud)` (`mov %rcx,%rdi` / `mov %rdx,%r14` / `mov %r8,%rsi`)。
- aud: L @0、R @8 (float*)、n @0x28 (int)。L/R を 16 B/sample で `this+0x70` に interleave して格納し、処理後に L/R へ戻す。
- P = `*(ctx+0x3188)`: `+0` type (int)、`+4` freq (float、4 番目の引数 xmm3)、`+8` Q (float、5 番目 `[rsp+0x20]`)、`+0xc` gain (float、6 番目 `[rsp+0x28]`)、`+0x10` order (int、2 倍して `r8d` で渡す)。
- `this+0x60`: sr (float)。7 番目の引数 `[rsp+0x30]` として係数計算に渡す。
- `this+0x12c8`: 係数 slot の index。slot は `this+0xc70 + idx*0x320` の 2 本。`this+0x12cc` は変更フラグ、`this+0x12d0` は時間加算、`this+0x12c4` は補間フラグ、`this+0x12b0`〜 は補間の状態。
- `this+0x12d8`: 合算バッファのポインタ。末尾の `jmp 0x1802ff250` が `ptr+0x28` から書く (harness で確保が要る)。
- 呼出し先は §2-2 の表の通り。closure 内に IAT 間接呼出しは無い。そのため Gain と同じく PE を ImageBase に敷設するだけで実行できる。

### 2-2 SC `0x180b6f050` と KH `0x1804655e0` の呼出し先 (全件)

`objdump -d` で両側の本体を全件読んだ (SC 818 B・KH 969 B)。SC は call 9 箇所、KH は call 7 箇所と末尾 jmp 1 箇所。
括弧内はその命令のアドレス。

| SC (0x180b6f050) | KH (0x1804655e0) | 対応 | 根拠 (引数・実行条件) |
|---|---|---|---|
| `0x180b802c0` ×1 (`0x180b6f0f2`) | `0x180469d00` ×1 (`0x18046566f`) | 対応 | rcx=slot、edx=type、r8d=2·order。係数の変更判定 (戻り値 al) |
| `0x180b7fa80` ×1 (`0x180b6f1a3`) | `0x180469d40` ×1 (`0x180465711`) | 対応 | 係数計算。edx=type、xmm3=freq、`[rsp+0x20]`=Q、`[rsp+0x28]`=gain、`[rsp+0x30]`=sr。実行条件は両側同じ: 変更なし、または変更ありでフラグ 0 のとき (SC `S+0x12fc`・KH `0x12cc`) |
| `0x181030490` ×1 (`0x180b6f200`) | `0x181384040` ×1 (`0x180465761`) | 対応 (memmove 相当) | dst=`S+0x4a0` / KH `this+0x470`、src=`S+0xa0` / KH `this+0x70`、r8=n·16 B。呼出し先アドレスは別 |
| `0x180b7fc60` ×1 (`0x180b6f228`) | `0x180469ee0` ×1 (`0x18046577e`) | 対応 | rcx=slot(idx)、rdx=`S+0x4a0` / KH `this+0x470`、r8d=n。補間の経路 (フラグ 1) |
| `0x180b7fc60` ×1 (`0x180b6f250`) | `0x180469ee0` ×1 (`0x1804657a3`) | 対応 | rcx=slot(1−idx)、rdx=`S+0xa0` / KH `this+0x70`、r8d=n。補間の経路 (フラグ 1) |
| `0x180b7fc60` ×1 (`0x180b6f2fe`) | `0x180469ee0` ×1 (`0x180465817`) | 対応 | rcx=slot(idx)、rdx=`S+0xa0` / KH `this+0x70`、r8d=n。フラグ 0 (補間なし) の経路 |
| `0x180b80260` ×1 (`0x180b6f2db`) | `0x180469c50` ×1 (`0x180465944`) | 対応 | rcx=slot(1−idx) のリセット。フラグを 0 にした後。時間値が定数を超えたとき (両側) |
| `0x1806b0f20` ×1 (`0x180b6f2a6`) | 呼出し無し。インライン `0x180465821`〜`0x180465916` (補間フラグ `0x12c4` の分岐・状態更新・lerp ループ) | SC のみ (役割の対応は推定) | SC は rcx=`S+0x12e0` (KH `this+0x12b0` 相当)、rdx=`S+0xa0`、r8=`S+0x4a0`、`[rsp+0x20]`=クランプ値。KH は同じ形の補間 `cur + t·(prev−cur)` をインラインで行う |
| `0x180ac5230` ×1 (`0x180b6f376`) | 呼出し無し。末尾 `jmp 0x1802ff250` (`0x1804659a4`) が rcx=`this+0x12d8` (合算バッファ)・rdx=aud で無条件に呼ぶ | 未対応 | SC は `aud+0x60` ≠ 0 のときだけ rcx=this で呼ぶ。KH は無条件で、rcx が合算バッファ。呼出し条件と第 1 引数が違うので同一とは言えない |

- 対応は 7 組 (SC 7 箇所 ⇄ KH 7 箇所)。SC のみ 2 箇所 (`0x1806b0f20` は KH のインライン補間に相当・推定、`0x180ac5230` は未対応)。KH の末尾 jmp `0x1802ff250` は SC 側に対応する呼出しが無い。
- 骨格 (係数変更判定 → 係数計算 → 状態の退避 → 格納 → 補間 → 末尾の出力) は両側に在る。ただし呼出し単位で一致するのは 7 組で、「同じ骨格」とは言えない。
- 写像 (SC `P` ⇄ KH `P`): type `0x9dc4`⇄`+0`、freq `0x9e0c`⇄`+4`、Q `0x9e54`⇄`+8`、gain `0x9e9c`⇄`+0xc`、order `0x9ee4`⇄`+0x10`。
- state 写像 (差の位置の読みに使う): sr KH `this+0x60`⇄SC `S+0x98`、arr KH `0x70`⇄`S+0xa0`、arr KH `0x470`⇄`S+0x4a0`、ctx KH `0xc70`⇄`S+0xca0`、補間状態 KH `0x12b0`⇄`S+0x12e0`。

## 3. 実測

### 3-1 KH 単独 (乱数入力、seed 7、200 case)

- 実行: `bash tools/targets/freshair/ks_semantic_filter_kh.sh 200 7` (測定 commit は §5)。
- 結果: cases=200、samples=12616、NaN/Inf=0、入力から変化=10738 サンプル (85.1%)。
- 決定性: 同一 seed の 3 回の出力 sha256 が一致 (`29609aa0…`)。
- 補足: 初版は合算バッファを `calloc` で確保し、その ASLR 由来のポインタが state の 4 B を毎回変えた。固定アドレス (`0x200000000`) の mmap に変えて解消した。

### 3-2 SC ⇄ KH 同一シナリオ (`gen_filter_scen.py` 200 本、seed 0xF117E4、fma 0)

- 実行: `bash tools/targets/freshair/ks_semantic_filter_scen.sh 200 0xF117E4 0` (0.55 s)。
- SC 側は `native_filter` を `FA_IAT_ALL=1` (PE の import テーブルから全 thunk を束縛) で起動した。`iat_slots.txt` (mlift 生成) は使っていない。stderr は空、ERR・GUARD は 0。
- 比較: `scenarios=200 calls=598`。
  - L/R 不一致 call: **228 / 598**。
  - call 0 (新規状態): 0/200 不一致 (全 type・全 order で一致)。
  - call 1 以降: 228/398 不一致。不一致は type 0〜7・order 0〜4 のどれにも現れる。
  - `S+0xca0` 系の最初の差は slot 1 (KH `0xf90`〜、SC `S+0xfc0`〜) の 0x10 以降。
- state の語単位の不一致 (語 = 4 B、全 598 call の合計。`ks_filter_scen_cmp.py` の出力)。相対差は `|SC−KH|/|KH|` (float32 として読んだ値)。

  | 領域 | 不一致 call | 不一致語 | うち相対差 > 1e-3 の語 |
  |---|---:|---:|---:|
  | sr `S+0x98` / KH `+0x60` | 0 | 0 | 0 |
  | arr `S+0xa0` / KH `+0x70` | 253 | 1,144 | 0 |
  | arr `S+0x4a0` / KH `+0x470` | 0 | 0 | 0 |
  | ctx `S+0xca0` / KH `+0xc70` | 598 | 11,104 | 2,959 |

  - arr 領域の不一致語は全て相対差 1e-3 以下。意味のある相対差はこの領域で見る。
  - ctx 領域は整数・ポインタ語を含むため、相対差は float として読み直した値 (参考値)。
  - 旧版の「630 語 (相対差 > 1e-3)」は、どの語を数えるかの定義が無く再現できなかったため削除した。上表は `ks_filter_scen_cmp.py` が出力する値。
- fma=1 (SC): L/R 不一致は同じ 228/598。SC の出力が fma=0 と変わる call は 4/598。state の語数は ctx 11,181 (相対差 > 1e-3: 2,979)。

### 3-3 FMA の確認 (objdump)

- SC Filter 範囲 `0x180b6e000`〜`0x180b8a000` の命令に FMA (`vfmadd`/`vfmsub`/`vfnmadd`/`vfnmsub`) は 0 件。対照として同じ範囲で `mulss` を 2 件検出し、grep が機能していることを確認した。
- KH 本体 `0x1804655e0`〜+969 と係数計算の範囲 `0x180469c00`〜`0x180469fff` (`0x180469d00`・`0x180469d40`・`0x180469ee0`・`0x180469c50` を含む) に FMA は 0 件。
- SC 全体には FMA 命令が 460 件ある。fma フラグ `0x1813070f8` の参照は 15 箇所 (14 箇所は `cmpl $0x0` の読み、残り 1 箇所は別形)。fma=1 で SC の state が 4 call 変わるのは、Filter 範囲から呼ばれる先でこのフラグが効くためと推定する (呼出し経路は未確認)。
- 結論: L/R 不一致 228/598 は FMA 分岐の差ではない。Filter 範囲と KH 側に FMA 命令が無く、fma=0/1 で L/R 不一致の集合が同じだから。state の 4 call の差の起源は未特定 (§6)。

## 4. 判定 (issue 本文の基準: bit 一致・許容差 0)

- 単一の新規呼出し: 一致 (200/200)。
- 連続呼出し (state を引き継ぐ 2 回目以降): **不一致** (228/398)。
- したがって「同じ seed の 200 case で L/R・state が bit 一致」は未達。判定は「差分あり・未解決」。Gain と同じ一致判定にはならない。

## 5. 測定 commit と差分

- 測定 commit: `747bab931` (`ks_filter_scen_cmp.py` に語単位の出力を足した、コードを変えた最後の commit)。§3 の数値はすべてこの commit で測定した。
- `git diff 747bab931 HEAD -- tools/targets/freshair/ks_semantic_filter_kh.c tools/targets/freshair/ks_semantic_filter_kh.sh tools/targets/freshair/ks_semantic_filter_scen.sh tools/targets/freshair/ks_filter_scen_cmp.py tools/targets/freshair/lift2/native` の出力: 空 (以降の追加は本付録と DOC_MAP だけ)。

## 6. 係数計算の入出力の比較 (FA-65 / #5042)

係数計算関数 (SC `0x180b7fa80` ⇄ KH `0x180469d40`) の呼出し引数・入口ブロック・出口ブロックを両側で記録した (`lift2/native/coef_probe.c`・`ks_coef_scen.sh`・`ks_coef_cmp.py`)。
同一シナリオ 200 本 (seed 0xF117E4、fma 0)。

**再測定の状態 (未実施)**: 前版の §6 の数値は、現在の `ks_coef_cmp.py` の出力から再現できなかったため削除した。
再測定には `work-liftlib-targets` (`tools/targets/{freshair,kilohearts}/work/`) が要るが、この run で取得できた素材 (`fl-win64`) には SlateCore / HeartCore が無い。
新しい数値は、再測定後に `ks_coef_cmp.py` の出力をそのまま転記する (2×2 表・o2 別・|KH| 区分・first mismatch を含む)。

- 入力 (type / order×2 / freq / Q / gain / sr): 前版では全 call で一致。`ks_coef_cmp.py` は再測定時に再確認する。
- 入口ブロック (係数 slot の呼出し前内容): 前版で不一致 call があった (数値は未再現)。state 側 (写像) の差の候補。
- 出口ブロック: 入口一致でも出力が違う call の有無は、2×2 表 (入口一致/不一致 × 出口一致/不一致) で判定する。

**判定 (現時点)**: 引数は一致。係数 slot の入口状態の不一致 (写像候補) と、入口一致でも出力が違う係数計算側の差の両方がある。
どちらが支配的かは、再測定の 2×2 表で決める。式の特定は未了 (係数計算の呼出し先 `0x180d22850`・`0x180d235b0`・`0x18100c1e0` の入出力は未記録)。

- 決定性: `ks_coef_scen.sh` が SC・KH それぞれを 2 回実行して `cmp` し、`SC_DETERMINISTIC=` / `KH_DETERMINISTIC=` を出す (再測定で確認する)。
- 測定 commit: 再測定後に更新する (現版の harness の最後の変更 commit)。再現: `bash tools/targets/freshair/ks_coef_scen.sh 200 0xF117E4 0`。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 本目の slot 係数差 (連続呼出しでの L/R 不一致 228/398) の原因切り分け。まず §2-2 の未対応 2 箇所 (`0x1806b0f20`・`0x180ac5230`) と末尾 jmp の対応を確定する | Filter の意味同一性の判定が出ない (#52 ① 受入 3) | 子 issue #3525 ([FA-40]) |
| fma=1 で SC の state が 4 call 変わる原因 (フラグ `0x1813070f8` の読み手の呼出し経路) | FMA は L/R の原因ではないが、state の差の原因は未特定 | 子 issue #3525 ([FA-40]) の範囲 |
| 判定基準 `REPORT_APPENDIX_2739.md` (§1 C4〜C6・§3 VA 表) が main に無い | 判定の正本が欠ける (本付録は issue 本文の基準を採用) | #2739 |
| `ks_sc_native_smoke.sh` が main に無い | SC 側 ERR 0/20 の再確認ができない | #2739 |
