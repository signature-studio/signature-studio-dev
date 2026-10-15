# freshair FA-39 (#3507) 付録: Filter の SC ⇄ KH 同一入力 native 差分

親: #2739 (FA-34)。判定基準の本体 `REPORT_APPENDIX_2739.md` (§1 C4〜C6・§3 VA 表) は main にも全 branch にも無い
(`git log --all -- tools/targets/freshair/REPORT_APPENDIX_2739.md` は空)。`ks_sc_native_smoke.sh` も無い。
本付録は issue 本文の基準 (同一 seed・L/R と処理後 state の bit 一致・許容差 0) を採った。

## 1. 結論

- KH 側 (HeartCore 0x1804655e0) の実機機械語 harness を新設した (`ks_semantic_filter_kh.c`)。
- SC (SlateCore 0x180b6f050) と同一のシナリオ 200 本 (598 call) で比べた結果、**最初の call (新規状態) は 200/200 で L/R が bit 一致**。
  **2 回目以降の call は 228/398 で L/R が不一致**。判定は「一致しない」。
- 差の起点は 2 本目の係数バッファ (slot 1)。最初の call の後にすでに食い違う。FMA 経路 (SC の fma=1) でも同じ数で、FMA の差ではない。
- 原因は未特定。子 issue に切り出す (本文の未解決表)。

## 2. 機械語の読み (根拠)

KH `0x1804655e0` (969 B。末尾は `jmp 0x1802ff250`)。`objdump -d` で読んだ。

- 呼出し形: ms_abi の `process(rcx=this, rdx=ctx, r8=aud)` (`mov %rcx,%rdi` / `mov %rdx,%r14` / `mov %r8,%rsi`)。
- aud: L @0、R @8 (float*)、n @0x28 (int)。L/R を 16 B/sample で `this+0x70` に interleave して格納し、処理後に L/R へ戻す。
- P = `*(ctx+0x3188)`: `+0` type (int)、`+4` freq (float、4 番目の引数 xmm3)、`+8` Q (float、5 番目 `[rsp+0x20]`)、`+0xc` gain (float、6 番目 `[rsp+0x28]`)、`+0x10` order (int、2 倍して `r8d` で渡す)。
- `this+0x60`: sr (float)。7 番目の引数 `[rsp+0x30]` として係数計算に渡す。
- `this+0x12c8`: 係数 slot の index。slot は `this+0xc70 + idx*0x320` の 2 本。`this+0x12cc` は変更フラグ、`this+0x12d0` は時間加算。
- `this+0x12d8`: 合算バッファのポインタ。末尾の `0x1802ff250` が `ptr+0x28` から書く (harness で確保が要る)。
- 呼出し先: `0x180469d00` (係数の変更判定、戻り値 al)、`0x180469d40` (係数計算、7 引数)、`0x180469ee0` (slot への per-sample 格納)、`0x181384040` (memmove 相当)、`0x180469c50` (slot のリセット)。closure 内に IAT 間接呼出しは無い。そのため Gain と同じく PE を ImageBase に敷設するだけで実行できる。

SC `0x180b6f050` (818 B) も同じ骨格。

- `0x180b802c0` が KH `0x180469d00` に対応 (`rcx`=slot、`edx`=type `P+0x9dc4`、`r8d`=2×order `P+0x9ee4`)。
- `0x180b7fa80` が KH `0x180469d40` に対応。引数の並びも同じ: `edx`=type `P+0x9dc4`、xmm3=freq `P+0x9e0c`、`[rsp+0x20]`=Q `P+0x9e54`、`[rsp+0x28]`=gain `P+0x9e9c`、`[rsp+0x30]`=`S+0x98` (sr)。
- 写像 (SC `P` ⇄ KH `P`): type `0x9dc4`⇄`+0`、freq `0x9e0c`⇄`+4`、Q `0x9e54`⇄`+8`、gain `0x9e9c`⇄`+0xc`、order `0x9ee4`⇄`+0x10`。
- state 写像 (差の位置の読みに使う): KH `this+0x60`⇄SC `S+0x98` (sr)、KH `0x70`⇄`S+0xa0`、KH `0x470`⇄`S+0x4a0`、KH `0xc70`⇄`S+0xca0` (`0x70`〜の 4 領域は +0x30 の一定ずれ)。

## 3. 実測

### 3-1 KH 単独 (乱数入力、seed 7、200 case)

- 実行: `bash tools/targets/freshair/ks_semantic_filter_kh.sh 200 7` (測定 commit は §5)
- 結果: cases=200、samples=12616、NaN/Inf=0、入力から変化=10738 サンプル (85.1%)。所要 0.23 s (user 0.12 s / sys 0.10 s)。
- 決定性: 同一 seed の 3 回の出力 sha256 が一致 (`29609aa0…`)。
- 補足: 初版は合算バッファを `calloc` で確保し、その ASLR 由来のポインタが state の 4 B を毎回変えた。固定アドレス (`0x200000000`) の mmap に変えて解消した。

### 3-2 SC ⇄ KH 同一シナリオ (`gen_filter_scen.py` 200 本、seed 0xF117E4、fma 0)

- 実行: `bash tools/targets/freshair/ks_semantic_filter_scen.sh 200 0xF117E4 0` (0.36 s、2 回の sha256 一致)。
- SC 側は `native_filter` を `FA_IAT_ALL=1` (PE の import テーブルから全 thunk を束縛) で起動した。`iat_slots.txt` (mlift 生成) は使っていない。stderr は空、ERR・GUARD は 0。
- 比較: `scenarios=200 calls=598`。
  - L/R 不一致 call: **228 / 598**。
  - call 0 (新規状態): 0/200 不一致 (全 type・全 order で一致)。
  - call 1 以降: 228/398 不一致。不一致は type 0〜7・order 0〜4 のどれにも現れる。
  - state 領域 (call ごと、4 領域): sr 0/598、`S+0x4a0` 系 0/598、`S+0xa0` 系 253/598、`S+0xca0` 系 598/598。
  - `S+0xca0` 系の最初の差は slot 1 (KH `0xf90`〜、SC `S+0xfc0`〜) の 0x10 以降。call 0 の直後 (200 シナリオの合計) で 3350 word が不一致で、そのうち 630 word は相対差 > 1e-3 (例: 相対差 8e-4)。
- fma=1 (SC): 同じ 228/598。FMA 分岐の差ではない。

## 4. 判定 (issue 本文の基準: bit 一致・許容差 0)

- 単一の新規呼出し: 一致 (200/200)。
- 連続呼出し (state を引き継ぐ 2 回目以降): **不一致** (228/398)。
- したがって「同じ seed の 200 case で L/R・state が bit 一致」は未達。判定は「差分あり・未解決」。Gain と同じ一致判定にはならない。

## 5. 測定 commit と差分

- 測定 commit: `df244c684` (scen 比較と SC 起動分岐を含む、コードを変えた最後の commit)。
- `git diff df244c684 HEAD -- tools/targets/freshair/ks_semantic_filter_kh.c tools/targets/freshair/ks_semantic_filter_kh.sh tools/targets/freshair/ks_semantic_filter_scen.sh tools/targets/freshair/ks_filter_scen_cmp.py tools/targets/freshair/lift2/native` の出力: 空 (本付録の追加だけ)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 本目の slot 係数差 (連続呼出しでの L/R 不一致 228/398) の原因切り分け | Filter の意味同一性の判定が出ない (#52 ① 受入 3) | 子 issue #3525 ([FA-40]) |
| 判定基準 `REPORT_APPENDIX_2739.md` (§1 C4〜C6・§3 VA 表) が main に無い | 判定の正本が欠ける (本付録は issue 本文の基準を採用) | #2739 |
| `ks_sc_native_smoke.sh` が main に無い | SC 側 ERR 0/20 の再確認ができない | #2739 |
