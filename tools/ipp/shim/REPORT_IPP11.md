# IPP-11 (#473): `ippsVectorSlope_64f` / `_32f` — 出力先が 16B 境界に揃わない場合の bit 再現 (2026-10-13)

既知類型との関係: `docs/DEFECTS.md` 該当なし (lift ではなく自前 C 実装の算法同定)。親: #276 (IPP-9)・#263。
`REPORT_IPP9.md` §4 の未解決 (misaligned) を解消する。本 branch は未マージの PR #306 (IPP-9) の head 上に積んである。

## 結論

実 `dsp_ippv2_x64.dll` の VectorSlope は **ポインタ値 `& 15` で head を peel する** 実装で、出力先アライメントが出力を変える仕組みを特定した。
自前実装に同じ head 処理を入れ、**`vslope_verify --mis K` は K=0..16 の全てで bad_cases=0** (変更前: K=1,5 → 1,312 / K=2,6 → 1,032 / K=3,7 → 643)。

| 受入条件 | 状態 |
|---|---|
| 仕組み (head/tail) を特定し `--mis K=0..16` の全てで bad_cases=0 | **達成** (§1・§2・§3) |
| FL の実呼出の出力先アライメント分布を実測 | **未達** (実行時の実測は不可。静的な呼出元分類のみ §4) |
| ネガコン (誤った head 処理で bad_cases が復帰) | **達成** (§3、5 種) |

## 1. 実 DLL の仕組み (逆アセの結果)

`objdump -D` で RVA を指定して読んだ (`adjust-vma` = RVA − ファイルオフセット)。

- export `ippsVectorSlope_32f/_64f` (RVA 0xc22a40 / 0xc22aa0) は CPU dispatch 表 (6 経路) への間接 jmp。
- 経路別ラッパ (RVA 0xcba100〜0xcba2e0 / 0xcbb5e0〜0xcbb7c0) が `pDst==NULL → -8`・`len<=0 → -6` を検査し、`offset` と `slope` をスタックへ置いて、カーネルに `(pDst, len, &offset, &slope)` を渡す。
- カーネル RVA (経路 0..5): 64f = 0x1ac0d90 / 0x1ac18b0 / 0x1ac23d0 / 0x1ac2f00 / 0x1ac3a40 / 0x1ac4600、32f = 0x1ac0c50 / 0x1ac1770 / 0x1ac2290 / 0x1ac2dc0 / 0x1ac3900 / 0x1ac44c0。
- **精読したのは経路 0 (SSE2) の 2 本のみ**。他 5 経路は逆アセ未精読で、出力が SSE2 と一致することを実測で確認した (§3)。経路 4,5 のラッパは VEX 符号化の `vmovsd` を使うため、AVX 系のカーネルと推定。

### 算法 (SSE2 カーネルから)

| 段 | 64f (2 レーン/ベクトル、ブロック 8 要素) | 32f (4 レーン/ベクトル、ブロック 16 要素) |
|---|---|---|
| 初期状態 | idx={0,1} | x={0·s, 1·s, 2·s, 3·s} (`cvtdq2ps` → `mulps`) |
| **head** | `rdi & 0xf` が 0 になるまで 1 要素ずつ: `dst = idx0·s + o` (積→加算)、`idx += 1`。64f の peel は 0 か 1 要素 | 同条件: `dst = x[0] + o`、`x[j] += s` (全レーン)。peel は 0〜3 要素 |
| body 前処理 | `x = {p·s, (p+1)·s}` (p = peel 数)。ベクトル m の値 = (x に 2s を m 回累積) + o (m=0..3) | ベクトル g の値 = (x[j] に 4s を g 回累積) + o (g=0..3) |
| body | 4 ベクトル = 8 要素を 64B 整列 store、各レーンに `step = 8s` を加算。`rem/8` ブロック (rem = len − p) | 4 ベクトル = 16 要素、`step = 16s`。`rem/16` ブロック |
| tail | `rem%8` 個: 先頭 = 次ブロックのレーン0 の累積値、以降は `直前 + s` の直列加算 | `rem%16` 個: 同左 |

- 乗算と加算は融合しない (`-ffp-contract=off` 必須)。
- 「peel 数」はポインタ値 `& 15` だけで決まる。そのため前 PR の観測 (64f は K 偶数で aligned と同一、32f は K%4 で 4 周期) と一致する。
- 前 PR の aligned 式は、この算法の p=0 の場合そのもの (例: 64f レーン5 = `o+((1·s+2s)+2s)` が旧 REPORT の `o+(3s+2s)`)。
- head の p 番目の値は p ≤ 3 では `p·s + o` と等しい (s の直列加算も p·s を 1 回丸めた値になるため)。head の式を `p·s` に差し替えても出力は変わらない (ネガコン候補から除外した理由)。
- 実装: 64f = `impl/ipp_sig_fill3.c`、32f = `src/ipp_min.c` (`VSLOPE==0`)。pDst の実アドレス `& 15` を使う。

## 2. 変更点

| ファイル | 内容 |
|---|---|
| `impl/ipp_sig_fill3.c`・`src/ipp_min.c` | head peel (`(uintptr_t)p & 15`) を追加し、body の初期状態を peel 後の状態から作る |
| `test/vslope_mis_run.sh` (新) | K=0..16 の実 DLL 突合・ネガコン 5 種・native/wasm ハッシュ・特殊値の 1 コマンド再現 |
| `test/vslope_model_check.py` (新) | 別言語・別実装の独立検算 (Python モデル vs 実 DLL の bit) |
| `test/vslope_verify.c` | `--special` (inf/NaN/-0/非正規数) を追加 |
| `test/vslope_hash.c` | 引数 K で出力先をずらす (既定 0 は従来と同一ハッシュ) |
| `test/fill3_oracle.c` | 環境変数 `IPP_CPU_MASK` で `ippSetCpuFeatures` の値を上書き可能に (既定は従来どおり `~0`) |
| `vslope_callsite_survey.py` (新) | FL win64 全モジュールの呼出元の出力先引数を静的に分類 (§4) |

## 3. 検証 (検証起点 commit `c9e3124` をクリーン worktree に展開して実行。`4e6c91b` = 変更前。`vslope_model_check.py` と本 REPORT は後続 commit で、独立検算は branch の作業ツリーで実行 (実装コードは `c9e3124` と同一))

実行環境: GitHub Actions runner (nproc=4、AVX2 まで・**AVX-512 なし**)、並列 1、素材は `fl-win64` の `block24356_PE.bin` のみ。

| 検査 | 実測 |
|---|---|
| `bash shim/test/vslope_mis_run.sh` (§1〜§4 全体) | **n=3: 6.96 / 7.02 / 6.96 秒、RESULT PASS**。開始時 load average (1 分) = 0.20 / 0.26 / 0.32、並列 1 |
| 実 DLL 突合 `vslope_verify --mis K` (K=0..16、64f+32f、cpu mask 6 通り × 400) | **17 本とも** `cases=4800 elements=1,347,350 bad_cases=0 bad_elements=0` |
| 同、変更前 (`4e6c91b`) | K=1,5: bad_cases=1,312 (bad_elements=16,239)・K=2,6: 1,032 (10,439)・K=3,7: 643 (6,448)・K=0,4,8,16: 0 |
| 特殊値 `--special` (inf/NaN/-0/±1e-310/±1e308 を 50% 混入、K=0..16) | 17 本とも `elements=1,218,296 bad_cases=0 bad_elements=0` |
| native と wasm (scalar / simd128) の自前出力 FNV-1a (K=0..16) | **17 本とも 3 者一致**。K%4 = 0/1/2/3 の値 = `ea554c7ef72ae86e` / `5446c7828c554e98` / `8eea0f53361a8c63` / `f01e6771a2d5aee3` (K=0 は前 PR と同値) |
| 独立検算 `vslope_model_check.py` (Python モデル、64f/32f × mask 6 × K=0..7 × 40 ケース) | `cases 3840 bad 0` (所要 44.4 秒、sys 時間が大半) |
| 既存 `ref/ipp_ref cmp` (mask 0x3f) VectorSlope_32f: 216 ケース / 2,665,224 要素 | `differ` (NaN 以外の値の不一致): 2,593 要素 / 23 ケース → **0 / 0** |
| `fill3_oracle_run.sh` (`IPP_CPU_MASK=0x3f`) | VectorSlope_64f `cases=9 st_mis=0 case_diff=0 byte_diff=0`・errgrid `mismatch=0`。wasm replay `records=297 mismatch=0 -> PASS`。所要 1.26 秒 |

数え方: 要素 = 出力 1 個 (64f と 32f を別計上)。`bad_cases` = 1 ケース (関数 × cpu mask × 乱数入力) で 1 要素でも byte が異なれば 1。
`nan_payload` = 実 DLL と自前の双方が NaN でビットだけ異なる要素 (bad には数えない)。

**`fill3_oracle` の SUM は `case_diff=8 byte_diff=1292` になる**。内訳は `ippsAddProductC_32f` の 1 行 (`cases=9 case_diff=8`) のみで、変更前 (`4e6c91b`) も同じ値。この runner に AVX-512 が無く、`~0` では SIGILL になるため `IPP_CPU_MASK=0x3f` で実行したことによる ISA 依存の差で、VectorSlope とは無関係。AVX-512 のある環境での SUM は未実行。

### ネガティブコントロール (`vslope_mis_run.sh` §2。本体は変更せず、コピーに誤りを注入。数値は `bad_cases`)

| 注入した誤り | K=1 | K=2 | K=3 | K=5 |
|---|---|---|---|---|
| 64f: head peel なし | 593 | 0 | 593 | 593 |
| 32f: head peel なし | 1,231 | 1,032 | 385 | 1,231 |
| 64f: peel を 32B 境界まで | 1,176 | 1,218 | 0 | 1,176 |
| 32f: peel を 32B 境界まで | 1,033 | 1,148 | 1,264 | 0 |
| 32f: head 後に x[j] へ s を加算しない | 2,108 | 2,108 | 2,105 | 2,108 |

0 になる列は、その誤りがその K で結果を変えない場合 (例: 64f は K=2 が 16B 揃い) で、想定どおり。5 種とも bad_cases が復帰する。
独立検算側のネガコン (`NEG=1`: モデルに K を無視させる): `cases 3840 bad 1128`、exit 1。

## 4. FL の実呼出の出力先アライメント (受入条件 2): 静的な呼出元分類のみ、実行時分布は未測定

**実行時の分布 (どの K が実際に使われるか) は測れていない**。FL win64 を実行する手段が Actions (Linux) 上に無く、FLEngine の boot lift もこの呼出まで到達していない (`docs/STATUS.md`)。
代わりに `python3 shim/vslope_callsite_survey.py` で、FL win64 の PE 313 モジュール (2 本は解析不能) の呼出元の第 1 引数 (rcx) の由来を静的に分類した。
母数は `scan_x64.analyze` が採る「関数 × モジュールあたり ≤3 箇所」の呼出箇所で、32f = 430 箇所 (144 モジュール)・64f = 85 箇所 (`shim/data/callsite_evidence.json` の `sites` と一致)。

| 出力先 (rcx) の由来 | 32f | 64f | 判定 |
|---|---|---|---|
| `lea rcx,[rbp+d]` (d%16=0): フレームのローカル配列 | 344 (80.0%) | 0 | rbp は Win64 規約で rsp (16B 整列) からの 16B 単位オフセットなので 16B 揃い、と推定 (UNWIND_INFO の実読は未実施)。K%4=0 の経路 |
| `mov rcx,[reg+d]`: オブジェクトのフィールドから読んだポインタ | 49 (11.4%) | 82 (96.5%) | **静的には不明** (割当元のアロケータ次第。`d` はフィールド位置で、指す先の整列ではない) |
| `rcx ← lea reg,[reg2+4]` (call をまたいで遡った由来): 配列先頭 +4B | 36 (8.4%) | 0 | base が 16B 揃いなら **K%4=1 (head 3 要素を peel する経路)** |
| `lea rcx,[rax+0x20]` (定数列を書いた直後の領域) | 0 | 1 | base 次第 |
| 窓内で rcx の設定が見つからない | 1 | 2 | 不明 |

分かること: **実 DLL の misaligned 経路 (head peel) を踏む呼出が FL の実コードに存在する** (32f で最大 8.4% の箇所が `base+4B`)。
分からないこと: フィールド経由 (32f 11.4%・64f 96.5%) の整列、各箇所の実行頻度 (静的なので重み無し)。

重要な性質: 自前実装は**渡されたポインタの実値 `& 15`** で挙動を決める。ゲストポインタ = wasm リニアメモリ番地 (恒等。`shim/REPORT.md` の「ゲストポインタ ↔ ホストポインタ」) なので、
分布が分からなくても、**ゲストが渡した整列のとおりに実 DLL と同じ出力になる**。ただしゲスト側アロケータが Win64 (HeapAlloc は 16B 整列) と同じ整列を返すことが前提 (§5 の未解決)。

## 5. 再現

```sh
export FL_WIN64_DIR=<fl-win64 展開先>   # extracted/block24356_PE.bin が必要。EMSDK_DIR は既定 /opt/emsdk
bash tools/ipp/shim/test/vslope_mis_run.sh                       # §3 の大半 (RESULT PASS で exit 0)
python3 tools/ipp/shim/test/vslope_model_check.py                # 独立検算 (NEG=1 でネガコン)
IPP_CPU_MASK=0x3f bash tools/ipp/shim/test/fill3_oracle_run.sh   # AVX-512 の無い host
python3 tools/ipp/shim/vslope_callsite_survey.py                 # §4 (numpy / pefile / capstone が必要)
```

## 6. 未解決・範囲外

検証範囲: 64f/32f、n=1..4097、cpu mask 6 通り、出力先 = 64B 境界から K=0..16 要素、特殊値入力 (NaN 以外の値)。範囲外は下表。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL 実行時の出力先アライメント分布 (K の実頻度) が未測定 | 受入条件 2 が未達。実装は実値で挙動が決まるため正しさには影響しないが、どの経路が支配的かは不明 | 新規子チケット案 `[IPP-12]` (番号は PM が採番): shim の thunk に `ptr & 15` のヒストグラム計装を入れ、FLEngine boot が VectorSlope に到達した時点で採取 |
| ゲスト側アロケータの整列が Win64 と異なると K が実機とずれ、最大 1 ULP の差が出る | `base+4B` 型 (§4 の 8.4%) で顕在化し得る | 同上 (アロケータ整列の確認を含める) |
| NaN の符号/ペイロード差 (両者 NaN): `--special` で 136〜193 要素/4,800 ケース (K=0 でも 156)。K 非依存 | 値は一致、NaN のビットのみ。C の演算順序に由来 (wasm の NaN は元々非決定) | 同上 |
| 他 5 ISA 経路のカーネルは逆アセ未精読 (出力一致のみ実測) | 現行 6 mask の範囲では差なし | 同上 |
| 64f の 8B 未満整列 (4B オフセット) の出力先 | 実 DLL の head ループは全要素を peel する構造。自前も同構造だが、実 DLL との突合は未実施 | 同上 |
| `ippsVectorSlope_32s` は stub のまま | — | 新規子チケット案 (IPP-9 §4 から継続) |
| AVX-512 環境での `fill3_oracle_run.sh` SUM の再確認 | この runner は AVX-512 なし | PR レビュー/手元環境で確認 |
