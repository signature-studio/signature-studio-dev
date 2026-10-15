# tools/plugins/p0c REPORT 付録 H (§18)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本節は #197 (親 PLG-P0c) の出口条件
> 「80 kernel 全てが native 機械語と bit-exact」に対する**最終センサス**として新規追加。

## 18. #197: 80 kernel の最終センサス (測定 HEAD `6444b186`)

### 18.1 目的と数え方

- 出口条件の判定は、REPORT 内に確定値が無かった (付録 C §91 の status センサスは、その後の修復 #277 / #983 / #982 等を反映していない) ため、同一コマンドで再測定して一本化する。
- 数え方は `p0c4_abi_e2e.py` の定義 (付録 B/C と同一): `buf_diff` = native と IR の出力バッファの bit 不一致 cell 数 (f32 4 B 単位・NaN 同士は nandiff に分離)。
- **除外される kernel**: `k80_diff.py` は ABI 判定 (`k80abi` + `build_argmodel`) が `ok` 以外の kernel を CSV に出さない (driver の `if K['status'] != 'ok': continue`)。これは本付録で再現した仕様であり、測定から外す判断ではない。

### 18.2 測定

- 測定 HEAD: `6444b186` (origin/main 起点の branch `197-p0c-census`、`tools/plugins/p0c` / `lift` は無変更)。
- 素材: `fl-win64` (`extracted/block18983_PE.bin`、展開先 `$RUNNER_TEMP/fl-win64`)、`llvm-as` は PATH 上の llvm-18 のものを使用。
- 同一 HEAD での実行結果:

| 検証 | rc | 所要 | 結果 |
|---|---|---|---|
| `p0c_e2e.sh` (work/ 無し・クリーン) | 0 | 6 分 03 秒 | `== e2e OK ==` |
| `p0c4_abi_e2e.py 2000` (census) | 0 | 23.5 秒 | `run=67 ok=67 sig11=0`・冪等性 OK・llvm-as OK・45 変数 / 80 実装 / 10,886 B / x87 28 一致 |
| `p0c4_e2e.py 2000` (ext chain) | 0 | 1 分 40 秒 | 14 kernel 中 buf_diff=0 が 14 件 (下表 18.4) |

- 測定時の load average: p0c_e2e 開始時 1.39 (終了時 9.2)・census 直前 9.18 (並列 1, 4 コア runner)。

### 18.3 census の結果 (`p0c4_abi_e2e.py 2000`, 非 ext 鎖)

- 80 実装のうち CSV に出た kernel は **67** (全て status `ok`・sig11 0 件)。残る **13** は ABI 判定が ok でないため driver が CSV に出さない kernel (`k80_diff.py` の仕様)。
- そのうち **buf_diff = 0 は 49 / 67**。

#### buf_diff ≠ 0 の 18 kernel (非 ext 鎖・2000 case/kernel)

| kernel | buf_diff | maxulp (harness 出力) |
|---|---:|---:|
| 0x5de620 | 301,144 | 0.0000 |
| 0x5dea40 | 5,166,346 | inf |
| 0x5dec40 | 5,088,752 | inf |
| 0x5dedb0 | 2,583,215 | 535,560,460 |
| 0x5dee20 | 5,168,510 | 920,645,431 |
| 0x5dee50 | 5,168,510 | 224,174,645 |
| 0x5df340 | 1,283,847 | 0.0000 |
| 0x5dfae0 | 1,292,623 | 0.0000 |
| 0x5dfbe0 | 20,498 | 6,633.0000 |
| 0x5dfc90 | 110,434 | 51,082.000 |
| 0x5dfdb0 | 13,901 | 5,387.0000 |
| 0x5dffc0 | 4,000 | 441,131,124 |
| 0x5dfff0 | 4,000 | 159,985,194 |
| 0x5e0300 | 2,584,255 | 425,033,422 |
| 0x5e0350 | 5,168,510 | 425,493,409 |
| 0x5e03f0 | 5,168,510 | 0.0000 |
| 0x5e12c0 | 1,814,580 | 0.0000 |
| 0x5e1490 | 1,201,366 | 0.0000 |

- 注: `maxulp` の値が 10^8 台になるものは、比較対象の値がほぼ全域で異なる (符号・NaN・桁落ちによる無効比較) ことを示す。harness の `maxulp` を精度の指標として使うのは不適切で、本節では buf_diff のみで判定する。
- 0x5dfbe0 / 0x5dfc90 / 0x5dfdb0 は、ext 鎖 (18.4) で buf_diff = 0 になる kernel。非 ext 鎖では残る。

### 18.4 ext 鎖 (`p0c4_e2e.py 2000`) の結果

- 対象 14 kernel 全てで buf_diff = 0 (下表)。判定行 `bit-exact 7/14` は `ret_diff == 0` も要求する stricter 条件で、ret_diff は native が rax を放置する kernel で意味を持たない (付録 B/C の定義) ため、buffer 判定としては 14/14。

| kernel | class | buf_diff |
|---|---|---:|
| 0x5dfbe0 | rc_chop | 0 |
| 0x5dfc90 | rc_chop | 0 |
| 0x5dfd30 | f32chain | 0 |
| 0x5dfdb0 | rc_chop | 0 |
| 0x5de820 / 0x5dedf0 / 0x5dfb60 | f32chain | 0 |
| 0x5df210 / 0x5df240 | f32chain | 0 |
| 0x5e0760 / 0x5e0b70 / 0x5e0bb0 / 0x5e1590 / 0x5e1780 | sse | 0 |

### 18.5 出口条件への当てはめ

- **80 本全て bit-exact は未達**。判定に使える数は次のとおり:
  - 非 ext 鎖の census: 67 測定中 buf_diff=0 が 49。18 は未達。残り 13 は ABI 非 ok で未測定。
  - ext 鎖: 測定した 14 は全て buf_diff=0。ただし ext 鎖の対象は non-ext census の 18 件全体をカバーしない (交差は 18.3 の 3 件のみ)。
- Group B 12 本 (Delphi RTL / x87 helper 外部呼出) は付録 A §3 のとおり数値差分の対象外。本出口条件の扱いは PM 判断 (下表)。

## 18.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 非 ext 鎖 census の buf_diff≠0 が 18 kernel (18.3 表) | 80 本 bit-exact の未達の本体。ext 鎖では 3 件 (0x5dfbe0・0x5dfc90・0x5dfdb0) が buf_diff=0 になる | #2182 [P0c-17] (既存・新規起票なし) |
| 未測定 13 kernel (ABI 非 ok で CSV 対象外: 0x5de410 0x5de4b0 0x5de540 0x5de6a0 0x5de870 0x5deaa0 0x5df460 0x5df5a0 0x5dfa70 0x5e0380 0x5e11a0 0x5e12b0 0x5e1870) | 80 本の完全な判定ができない。内訳は Group B 12 + abi-mismatch 1 (0x5e12b0) で §20.3 に分類済み | §20.3 で記録。0x5e12b0 の旧担当 #938 は範囲外で closed (§20.4) → #3439 [P0c-21] |
| Group B 12 本を出口条件に含めるか | 判定基準そのもの | PM 判断 (#197 本文の更新) |
| harness の `maxulp` が 10^8 台を返す | 精度指標としては使えない (buf_diff のみで判定) | harness 修正は本 issue 外 |

## 19. #2182: 18 kernel の buf_diff 0 化 (修復と検証)

### 19.1 結果

- 修復前の値は §18.3 (同一 census)。修復の commit は `d2e4283a` (修復本体)・`46b908b9` (GLOBAL_INITS の不一致停止と件数検査)・`5d168e1e` (コメント修正)。
- **測定 commit は `5d168e1e`** (p0c_e2e と 10000 case の測定時点のコード)。その後 `1224865b` で `k80_hand_bodies.py` の冒頭コメント 1 行だけを直した (19.6)。
  素材は `fl-win64`・`toolchain-retdec`・`plugins-ott` を `$ARTIFACTS_DIR` から展開して使った (`FL_WIN64_DIR` と `PATH=/usr/lib/llvm-18/bin` を前置)。
  - `p0c4_abi_e2e.py 2000`: rc 0・27.9 秒 (開始 load 1.16)・`run=67 ok=67 sig11=0`・CSV 67 kernel 全てで buf_diff=0 (修復前は 49/67)。冪等性 OK・llvm-as OK。
  - `bash tools/plugins/p0c/p0c_e2e.sh` (`tools/plugins/p0c/work` 無しの状態から、kernel_matrix と k80 lift を含む全段を実行): rc 0・`== e2e OK ==`・8 分 35 秒 (開始 load 0.28、終了時の 1 分 / 5 分平均 7.79 / 10.09)。
  - `k80_diff.py --cases 10000 --only <修復 18 kernel>` (IR は `work/diff3/k80.hb.ll`): 完走・36.9 秒 (開始 load 2.95)。17 kernel は buf_diff=0。**0x5dffc0 だけ buf_diff=3** (maxulp 535)。2000 case では 0 だった。
  このため 0x5dffc0 は bit-exact と確定できない (19.3 の未解決)。
- 前回測定 (測定 commit `d2e4283a`、修復本体のみの版): `p0c4_abi_e2e.py 2000` 15.3 秒、`p0c_e2e.sh` 3 分 51 秒、10000 case 20.8 秒。
- 測定 commit までのコード差分 (`git diff --stat d2e4283a 5d168e1e -- tools/plugins/p0c ':!*REPORT*'` の出力):
  ```
   tools/plugins/p0c/k80_hand_bodies.py | 16 ++++++++++------
   tools/plugins/p0c/p0c4_abi_e2e.py    | 14 +++++++++++---
   2 files changed, 21 insertions(+), 9 deletions(-)
  ```
  BODIES の本体とシグネチャは変えていない。差分は GLOBAL_INITS の不一致停止・件数検査・コメント。

### 19.2 kernel 別の原因と修復

修復前の buf_diff は §18.3。原因は「機械語と IR の突き合わせで確認した差分」であり、RetDec 側の根本原因の特定までは行っていない。

| kernel | class | 修復後 (2000 / 10000) | 原因 (機械語との突き合わせ) | 修復 |
|---|---|---|---|---|
| 0x5dfff0 | f32chain | 0 / 0 | raw lift で xmm2 (a) と xmm3 (b) の参照が入れ替わる。(1±a)·b の中間精度が f64 では 80-bit と丸めがずれる | 本体を x86_fp80 で書き直し |
| 0x5de620 | f32chain | 0 / 0 | `fistp word` の範囲外 (|v|>32767・NaN) を 0x8000 にする処理が無い | rint + 範囲判定 |
| 0x5dee20 | f32chain | 0 / 0 | `fstp` が格納する値の x87 スタック参照がずれる (out += in) | 本体 (f32 add) |
| 0x5dee50 | f32chain | 0 / 0 | 同上 (fxch 列の参照ずれ) | 本体 (f32 add) |
| 0x5e0300 | f32chain | 0 / 0 | 同上。(in[2k]+in[2k+1])·c の 80-bit 中間値 | 本体 (x86_fp80) |
| 0x5e0350 | f32chain | 0 / 0 | 同上。0x6fc200 (0.5) 参照の 2 出力 | 本体 (x86_fp80) |
| 0x5dedb0 | f32chain | 0 / 0 | スケールが反復ごとに B+k·S と累積 (`fadd st(1)`) する部分を IR が落とす | 本体 (x86_fp80) |
| 0x5dea40 | f32chain | 0 / 0 | 上と同じ累積スケール (2 要素版) | 本体 (x86_fp80) |
| 0x5dec40 | f32chain | 0 / 0 | 2 本の累積スケール (C と F)。5 番目の引数の int bits を f32 として読む | 本体 (x86_fp80) |
| 0x5dfae0 | transc | 0 / 0 | `f2xm1`/`fscale` の指数計算を IR が別式にしていた。`(1-2^y)·Q+P` を 80-bit で再現 (2^y は `llvm.exp2.f80`) | 本体 (exp2 近似) |
| 0x5dfbe0 | rc_chop | 0 / 0 | fldcw (RC=chop) を含む 80-bit 中間値を f64 で近似していた | §18.4 と同じ ext pass (`f80_lower --ext`) を適用 |
| 0x5dfc90 | rc_chop | 0 / 0 | 同上 | 同上 |
| 0x5dfdb0 | rc_chop | 0 / 0 | 同上 | 同上 |
| 0x5dffc0 | f64mem | 0 / **3** | a/b の入替え + `(1+a)·K` → `fsincos` → sin/cos。sin/cos を `llvm.sin/cos.f80` (glibc) で近似。残差は大きい |t| での x87 fsincos の π 近似誤差と推定 (未確認) | 本体 (未解決: 19.3) |
| 0x5df340 | sse | 0 / 0 | 4 lane の乗数ランプ (vector ごとに +d)。端数は生の arg5 を加算。IR は乗数を定数化していた | 本体 (SIMD の加算順を再現) |
| 0x5e03f0 | sse | 0 / 0 | `@global_var_6fffb0` が 0 初期化。PE の 0x6FFFB0 は (0.5, 0.5) | GLOBAL_INITS で初期値を設定 |
| 0x5e12c0 | sse | 0 / 0 | in-place clip (|x| < C なら 0) の IR 誤り | 本体 |
| 0x5e1490 | sse | 0 / 0 | `llrint` 後の table 参照。`@global_var_70f568` は 0x6FC200 へのポインタだが IR は整数として読んでいた | 本体 (0.5 を直接参照) |

- 修復は `tools/plugins/p0c/k80_hand_bodies.py` (関数単位の本体差し替え・シグネチャ不変・冪等)。本体は機械語の読解に基づく手書きであり、一般の lift 修復ではない。
- `p0c4_abi_e2e.py` の鎖: `k80_deref_fix` → ext pass (p0c4_e2e.py と同じ引数) → `k80_hand_bodies.py` → 差分試験。冪等性を検査する。
- 受入の判定は buf_diff のみ (ret_diff は native が rax を放置する kernel で意味を持たない、既存定義どおり)。

### 19.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x5dffc0 の残差 (10000 case で buf_diff=3)。原因は大きい |t| の x87 fsincos 引数縮約と推定 (未確認) | 80 本の bit-exact の 1 本が未達。2000 case の標準では 0 | #3280 [P0c-19] |
| 手書き本体 (k80_hand_bodies.py) を lift 側の一般修正に置き換えていない。RetDec raw lift の x87 スタック参照・xmm2/xmm3 入替の根本原因は未特定 | 同型の誤りを他 kernel で自動検出できない。本体は関数単位で保守が必要 | #3281 [P0c-20] |

### 19.4 silent miscompile 類型の行案 (docs/DEFECTS.md 形式・PM 判断で採否を決める)

`docs/WORKFLOW.md` §5 に従い、DEFECTS.md は直接編集せず行案だけを書く。ID は仮置きで、採番は PM が行う。
類型の根拠は機械語との突き合わせ (19.2) で、RetDec のどの pass が原因かは未特定。

| 仮 ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| (案) xmm 引数の入替え | fe | 新規 | 同じ xmm 型の 2 引数 (a=xmm2, b=xmm3) の役割が入れ替わり、(1±a)·b が反転する | RetDec raw lift が xmm2/xmm3 の参照を入れ替える | 0x5dfff0: 修復前 buf_diff 4,000 (2000 case)、修復後 0 | 関数入口の xmm2/xmm3 の live-in と、後続の読み先 (機械語の movss 先) の対応が IR と一致しない | 関数単位の本体 (k80_hand_bodies)。D5 (xmm 引数の取り違え: 整数 reg と混同) とは別。D5 は xmm と整数 reg の取り違え、本件は xmm 引数どうしの入替え |
| (案) x87 スタック参照のずれ | fe | 新規 | fstp の格納値が別の入力に依存する (f32 出力が全域で不一致) | RetDec raw lift の st(i) 参照の番号がずれる (fxch 列・fstp 後の再参照) | 0x5dee20 (5,168,510)・0x5dee50・0x5e0300・0x5e0350・0x5dedb0・0x5dea40・0x5dec40 の 7 kernel、修復後 0 | 機械語の x87 push/pop 列と IR の fstp 参照先の対応が一致しない | 機械語の push/pop 列どおりの本体 (k80_hand_bodies) |
| (案) PE 定数の 0 初期化 | fe (未切り分け) | 新規 | グローバル定数が 0 として読まれ、その定数を使う出力が全域で不一致 | IR の `global i128 0` が PE の .data (VA 0x6fffb0 = (0.5, 0.5)) を取り込まない | 0x5e03f0: buf_diff 5,168,510 → 0 | PE の .data 値と IR の global 初期値の照合が無い | GLOBAL_INITS で初期値を設定。D16 (rdata 窓が縮む) とは別機構 (D16 は窓サイズ、本件は窓内の初期値)。D16 の gen_globals 経路で起きたかは未確認 |
| (案) fistp 範囲外の処理欠落 | fe | 新規 | \|v\|>32767 や NaN で 0x8000 を返すべき所が別の値になる | fistp word の範囲判定 (0x8000 を返す分岐) が IR に無い | 0x5de620: buf_diff 301,144 → 0 | 機械語の fistp 直後の範囲判定 (cmp/cmov) の有無 | rint と範囲判定 (k80_hand_bodies)。#982 (fistp qword の上位 dword store 欠落) と同じ fistp 系だが、store の欠落ではなく範囲外値の変換規則の欠落 |

### 19.5 負論対照 (新しい gate の FAIL 確認)

測定 commit `5d168e1e` の差分試験 IR (`work/diff3/k80.ext.ll`) から、`k80_hand_bodies.py` の `replace_bodies` で 2 通りの IR を作った (作業用の一時ファイルは repo 外。tracked file は変えていない)。

| 対照 | 置換件数 | 対象 kernel の buf_diff (`k80_diff.py --only <VA> --cases 2000`) | `p0c4_abi_e2e.py 2000` の出力 |
|---|---|---|---|
| (a) `function_5dfff0` の本体を BODIES から外す | 14 | 0x5dfff0: **4000** | `[FAIL] k80_hand_bodies 置換件数 14 (期待 15 = BODIES 14 + GLOBAL_INITS 1)` (rc≠0) |
| (b) GLOBAL_INITS を空にする | 14 | 0x5e03f0: **5168510** | 同上 |

- `p0c4_abi_e2e.py` の件数検査が先に止めるため、FIX18 の buf_diff gate と CSV 全 kernel の gate の FAIL 行は出ていない。両 gate が検査する buf_diff は、上の表のとおり 0 以外になる。
- `[FAIL]` 行を出すため、(a)(b) の時だけ `k80_hand_bodies.py` に 1 行 (`BODIES.pop(...)` / `GLOBAL_INITS.clear()`) を一時追加して p0c4 を実行し、直後に退避コピーから復元した (`git status` clean を確認)。
- 対照の後、`p0c4_abi_e2e.py 2000` を正常系で再実行し、`work/` を正常状態に戻した (`run=67 ok=67 sig11=0`・全 67 kernel buf_diff=0 を確認)。

### 19.6 検証範囲

- 測定 commit `5d168e1e` で実施: §19.1 の 3 本 (素材付き)、§19.5 の対照 2 本 (件数 gate の `[FAIL]` を含む)。
- `5d168e1e` から HEAD までのコード差分 (`git diff --stat 5d168e1e HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力):
  ```
   tools/plugins/p0c/k80_hand_bodies.py | 2 +-
   1 file changed, 1 insertion(+), 1 deletion(-)
  ```
  差分はコメント 1 行のみ。IR 出力は変わらない (`work/diff3/k80.hb.ll` を変更前の出力と `cmp` で byte 一致)。`1224865b` で `p0c4_abi_e2e.py 2000` を再実行: rc 0・27.8 秒・`run=67 ok=67 sig11=0`・全 67 kernel buf_diff=0。p0c_e2e.sh と 10000 case は `5d168e1e` の値をそのまま使う (実行される IR と実行コードは同一)。
- 未検証: 0x5dffc0 の 10000 case 残差の原因 (19.3 の未解決)。80 本の完全判定 (#2182 の §18.6)。

## 20. #197: 未測定 13 kernel と Group B 12 kernel の分類

### 20.1 目的と判定規則

- 目的: #197 の close 条件 (2026-10-15 の PM 改訂) のうち「未測定 13 本と Group B 12 本の分類が本付録に記録されていること」を満たす。
- 判定: `tools/plugins/p0c/k80_unmeasured.py` は `k80_diff.py` の `build_argmodel` (slot 判定) と `GROUP_B_HELPERS` (外部 helper 呼出判定) をそのまま import して使う。独自の判定規則は持たない。
  - `ok`: 差分試験の CSV に出る (census の対象)
  - `groupb`: `GROUP_B_HELPERS` の外部 helper を呼ぶ (数値差分の対象外)
  - `abi-mismatch`: 機械語が使う slot のうち IR 引数に割り当てられないものがある

### 20.2 測定

- 分類の測定 commit: `907c0c66e` (`k80_unmeasured.py` の追加。パイプラインのコードは無変更)。
- 前段 (`e59ca23b9` = origin/main 起点・同じコード): `p0c_e2e.sh` rc 0・7 分 36 秒 (開始 load 0.40)、`p0c4_abi_e2e.py 2000` rc 0・35 秒 (`run=67 ok=67 sig11=0`)。素材は `fl-win64` のみ (`FL_WIN64_DIR`)、`[RETDEC]` (`docs/REFERENCES.md` §4) は既存。
- 分類 (`python3 tools/plugins/p0c/k80_unmeasured.py`、入力は差分試験 IR `work/diff3/k80.hb.ll`): **`total 80 / ok 67 / groupb 12 / abi-mismatch 1 / no-ir 0`**。`ok` 67 は census の CSV 67 件と一致する。
- `907c0c66e` から HEAD までのコード差分: 本節を含む commit は REPORT のみを変える。`git diff --stat 907c0c66e HEAD -- tools/plugins/p0c ':!*REPORT*'` の出力は空。

### 20.3 分類結果

**未測定 13 本 = Group B 12 本 + abi-mismatch 1 本** (Group B 12 本は全て未測定 13 本に含まれる。重なり 12)。

Group B 12 本 (数値差分の対象外。外部 helper の呼出先は kernel 表 80 本の外にある):

| 外部 helper | kernel 数 | kernel |
|---|---:|---|
| `function_5de330` | 3 | 0x5de410 0x5de4b0 0x5de540 (f80 分類: cmpsel / f64mem) |
| `function_40d840` + `function_43c5e0` | 7 | 0x5de6a0 0x5de870 0x5deaa0 0x5df460 0x5df5a0 0x5dfa70 0x5e0380 |
| `function_5d10b0` | 1 | 0x5e11a0 |
| `function_408810` | 1 | 0x5e1870 |

- `k80_diff.py` の `HELPER_CIMPL` に C 実装があるのは `function_409d00` / `function_409df0` (cvtsd2si / cvttsd2si) だけで、上の 5 helper は生成物で fail-fast stub (呼ばれたら exit 9) になる。そのため差分試験は走らない。対象にするには 5 helper の C 実装 (Delphi RTL / x87 helper の意味論) が要る。
- 扱い: 数値差分の対象外のまま記録する。出口条件から外すか許容条件として残すかは PM 判断 (#197 本文)。

abi-mismatch 1 本:

| kernel | 区分 | 詳細 | 担当 |
|---|---|---|---|
| 0x5e12b0 | abi-mismatch (測定時点) | 未割当の使用 slot: xmm0, xmm1 (IR は `define i64 @function_5e12b0()` の引数ゼロ) | 修復済 (#3439 [P0c-21]・`REPORT_APPENDIX_I.md` §21 参照) |

### 20.4 担当と残件 (close 条件への当てはめ)

- **§18.6 の訂正**: 0x5e12b0 の旧担当 #938 (`[T-SH-22]`) は libkio の受入 (`Fix_RCSf` / `LimitFloat_RCSfff` 40/40) で 2026-10-14 に closed。0x5e12b0 はその受入範囲に含まれない。open の担当が無かったため #3439 [P0c-21] を起票した (親 #197)。#3439 で 0x5e12b0 は修復済み (`REPORT_APPENDIX_I.md` §21)。
- open のまま残る P0c 系 issue (PM の close 条件表には無いが、80 本の bit-exact に効く):
  - #3280 [P0c-19]: 0x5dffc0 の 10000 case で buf_diff=3 (2000 case は 0)
  - #3281 [P0c-20]: RetDec raw lift の x87 スタック参照・xmm 入替えの一般 pass 化 (手書き本体 `k80_hand_bodies.py` の削減)
  - #1283 [P0c-16]: ext 鎖の f80 2 本と hs_e2e の skip 原因 (依存: #2510・#2566 は open)
- Group B 12 本: §20.3 のとおり数値差分の対象外。扱いは PM 判断。
- 結論: 未測定 13 本の分類は本節で記録した。#197 の close は、上の open な担当 issue (#1283・#3280・#3281) の扱い (0x5e12b0 は #3439 で修復済み)と Group B 12 本の扱いを PM が決めてからになる。
