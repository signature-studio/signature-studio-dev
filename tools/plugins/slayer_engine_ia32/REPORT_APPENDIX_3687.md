# REPORT_APPENDIX_3687 — x87 の超越関数・剰余 (fsin/fcos/f2xm1/fyl2x/fprem 32 件) の ia32 lowering (#3687 PLG-G2-29)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は付録 2966 §3 と同じ類型 (ADR D28 の帰結) で、`DEFECTS.md` は未編集。

- 親 REPORT: `REPORT_APPENDIX_2966.md` §6 (残り unsup 36 件の内訳。超越・剰余 32 件を本 issue に送った)。 方式: `docs/DECISIONS.md` D28 (f80→f64)。 本付録が本 issue の測定値の正本。
- 測定 commit: `7694f4bdd` (`feat(ott): lower x87 fsin/fcos/f2xm1/fyl2x/fprem for ia32 (PLG-G2-29)`)。 この後の HEAD は docs だけの commit。 コード差分の確認は §8。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (`lift_text.py`) と、生成した試行のみ。
- 環境: x86-64 Linux (Ubuntu 24.04・gcc 13.3・capstone 5.0.7・python3)。 native = 実 x87 (機械語を `.byte` / inline asm で実行)、 lowered = gcc -O1 の SSE double。 実行時の 1 分 load は 0.28〜0.88、 CPU 4。

## 1. 結論

- **x87 unsup (`lift_text.py` pass1): 36 → 4**。 本 issue の 5 命令 (fsin 15・fcos 2・f2xm1 8・fyl2x 2・fprem 5 = 32 件) は 0。 残り 4 件 (fnsave 1・frstor 1・fnstenv 1・fldenv 1) は [PLG-G2-30] (#3688) の範囲で、 本 issue の範囲外 (issue 本文の範囲外に明記済み)。
- **lift の被覆は before/after で同じ**: pass2 で 472 関数・21,354 命令・被覆 62,320 / 73,002 B (85.37%)。 pass1 の被覆 61,654 B (84.46%) も同じ。 unsup 命令の起点は被覆に入るので、被覆数は変わらない (前任 2966 §4 と同じ)。
- **x64 の生成 C は不変**: `x64_regress_1099.py <origin/main の tools/ott> 8` で `same 8/8`。
- **命令単体の一致 (`x87_trans_direct.c`、n=200,000 × seed 1・2)**:
  - fprem 完全剰余 (e<64) 100%・部分剰余 (e≥64、d∈[64,255]) 100%。 値も FSW (C0〜C3) も一致。
  - fsin: |a|≤π/4 99.80%、π/4<|a|≤2^10 98.27%、|a|≤2^20 11.3%、2^20<|a|<2^63 0.09%。 **大きい引数で一致が落ちる** (§5)。 生成 C は |a|≤π/4 の外を fail-fast にする (§2)。
  - f2xm1 (|x|≤1) 66.2% (ulp は 0・1・2 のみ)。 定義域外 (1<|x|≤8) 0%。 生成 C は |x|≤1 の外を fail-fast にする (§2)。
  - fyl2x (x>0) 73.5% (ulp 0・1)。 x≤0 (NaN・−inf 経路) 100%。
- **差分試験 (`x87_diff.py`、10 万試行、seed 1)**: op 表は 83 template・251 instance (従来 78・246)。 主試行 bit 一致 **93,984 (93.98%)** (変更前の HEAD `7b5c75b3f` でも 93,984 で、本 PR の変更による差はない)。 定義域外の fsin/fcos/f2xm1 呼び出しは 6,415 件 (計算を続けて比べる。 製品ビルドでは fail-fast)。 従来 op 表の再現 (`--skip` で新 5 命令を外す) は **96,510 (96.51%)** で、従来の REPORT_APPENDIX_2966 §3 の値と一致。
- **ネガティブコントロール (`--nega-trig`: fyl2x の log2 を自然対数に取り違える)**: 93,984 → **93,893 (−91)** で検出。
- **fscale の指数域外 (受入 4、§4)**: f80 では有限・f64 では無限になる結果が 200,000 件中 **21,036 件 (seed 1)・20,804 件 (seed 2)**。 f64 出力は両方 inf で一致して見えるため、bit 一致は 100% と出る (§4 の注)。

## 2. lowering

| 命令 | 生成 C (x64c `ia32_only`) | runtime (`tools/ott/rt/ott_x87.h`) | 注 |
|---|---|---|---|
| `fsin` `fcos` | `x87_trig_at(0|1, addr)` → `x87_trig` | 定義域 \|ST0\|≤π/4 の外 (有限・<2^63) は `ott_unsup` (fail-fast・runtime)。 `x87_trig`: 有限で \|ST0\|≥2^63 は ST0 不変・C2=1。 ±inf は C2=0 で default NaN | 定義域の上限は PM 判断待ち (既定案 π/4)。 ≥2^63 と ±inf は native 実測 (§5) |
| `f2xm1` | `x87_f2xm1_at(addr)` → `x87_f2xm1` | 定義域 \|x\|≤1 の外は `ott_unsup` (fail-fast・runtime)。 `expm1(x·ln2)`。 ln2 は hi/lo に分ける | 静的 unsup にしない (pass1 の unsup 0 を保つ) |
| `fyl2x` | `x87_fyl2x()` | `ST1 = ST1·log2(ST0)` を計算して pop。 ST0<0 は default NaN。 NaN は伝播 | |
| `fprem` | `x87_fprem()` | 完全: 商の |Q| mod 8 を C0(Q2)・C3(Q1)・C1(Q0)。 部分 (e≥64): C2=1・商のビット 0・除数を `2^(32·(floor(e/32)−1))` 倍して `fmod` | 部分の s は native 実測 (§5)。 ST1=0 か ST0=inf は default NaN |

- default NaN は `x87_indef()` (負の quiet NaN・f80 の `0xFFFF C000…` に対応)。
- C1 は fprem の商ビットだけ模型化。 trig・f2xm1・fyl2x の C1 (丸め方向) は未模型化 (ADR D28 制限 6 と同じ)。
- 定義域外は計算値を返さない。 生成 C の入口 (`x87_trig_at`・`x87_f2xm1_at`) が `ott_unsup` で停止する (runtime の fail-fast。 静的 unsup ではない)。 差分試験だけ `-DOTT_X87_DOMAIN_SOFT` で計算を続け、定義域外の呼び出し数 (主試行 6,415 件) を別に出す。
- 停止の確認 (gcc で `ott_x87.h` を直接実行): fsin 0.5 は値を返し、fsin 0.9・1.0・3.0・1e4 は `[ott] UNSUPPORTED instruction` で停止。 f2xm1 0.5 は値、f2xm1 3 は停止。
- 試験の FSW 比較で、native 側は `fninit` で試行ごとに初期化する (x87_diff は既存、 x87_trans_direct は命令ごと)。 native の FSW は持ち越されるため、初期化しないと未定義の C0/C3 が前の命令から混ざる (§5)。

## 3. 命令単体の実測 (`x87_trans_direct.c`)

コマンド: `gcc -O1 -I ../../ott/rt -o work/x87/trans/x87_trans_direct x87_trans_direct.c ../../ott/rt/ott_cpu.c -lm && ./work/x87/trans/x87_trans_direct 200000 1` (seed 2 も同じ)。 入力は f64 だけ (`fld m64` で正確に載る)。 差は命令の計算だけによる。 「一致」は値の bit 一致。 FSW は C0/C2/C3 (trig・f2xm1・fyl2x・fscale は C1 を除く、fprem は C1 も)。

| 類 (n = 200,000) | seed 1 一致 | seed 2 一致 | ulp 0/1/2/≥3 (seed 1) | FSW 不一致 (seed 1) |
|---|---:|---:|---|---:|
| fsin \|a\|≤π/4 (定義域内・生成 C が計算) | 99.80% | 99.82% | 199,604/396/0/0 | 0 |
| fsin π/4<\|a\|≤2^10 | 98.27% | 98.28% | 196,540/3,086/146/228 | 0 |
| fsin \|a\|≤2^20 | 11.29% | 11.30% | 22,583/30,567/22,675/124,175 | 0 |
| fsin 2^20<\|a\|<2^63 | 0.09% | — | 174/321/345/199,160 | 0 |
| fsin \|a\|≥2^63 (C2 経路) | 100% | — | 200,000/0/0/0 | 0 |
| fcos \|a\|≤2^20 | 11.51% | 11.36% | 23,018/30,664/22,319/123,999 | 0 |
| fcos 2^20<\|a\|<2^63 | 0.08% | — | 168/338/327/199,167 | 0 |
| fcos \|a\|≥2^63 (C2 経路) | 100% | — | 200,000/0/0/0 | 0 |
| f2xm1 \|a\|≤1 | 66.29% | 66.12% | 132,577/66,647/776/0 | 0 |
| f2xm1 1<\|a\|≤8 (定義域外) | 0% | — | 0/0/0/200,000 | 0 |
| fyl2x x>0 (指数 −20〜20) | 73.51% | 73.41% | 147,012/52,988/0/0 | 0 |
| fyl2x x≤0 (NaN・−inf) | 100% | — | 200,000/0/0/0 | 0 |
| fprem e<64 (完全) | 100% | 100% | 200,000/0/0/0 | 0 |
| fprem e≥64 (部分, d∈[64,255]) | 100% | 100% | 200,000/0/0/0 | 0 |
| fscale (指数 ±1100・n ±70,000) | 100% | 100% | 200,000/0/0/0 | 0 |

- ulp の検算 (nextafter の歩進、cap 3) は全類で `bad 0`。
- fprem の部分剰余の規則は、d=64〜103 は全 d (各 300 件)、d=64〜256 は 8 刻み (各 200 件) で native と突き合わせて決めた。 `fmod(|a|, |b|·2^s)` が全件一致し、s=32·(floor(d/32)−1)。 試験本体の部分類 (d=64〜255 の一様乱数) は、この規則のまま全件一致。
- fscale の「f80 有限・f64 無限」件数 (seed 1): overflow 21,036・f64 の正規範囲より小さい 20,641 (seed 2: 20,804・20,756)。 lowered は overflow の 21,036 件すべてで inf。

## 4. 差分試験 (`x87_diff.py`、10 万試行)

コマンド: `python3 x87_diff.py --n 100000 --seed 1` (主)、`--skip fsin,fcos,f2xm1,fyl2x,fprem` (従来 op 表)、`--nega-trig`、`--no-e`、`--only fld,fld1,fldz,fscale,fst,fstp,fchs,fxch`。

| 試験 | bit 一致 | FSW 不一致 試行 (うち m80 なし) | 命令別の一致 (一致/含む試行) |
|---|---:|---:|---|
| 主 (seed 1) | 93,984 (93.98%) | 166 (45) | fsin 2,750/3,531 (77.9%)・fcos 2,670/3,426 (77.9%)・f2xm1 1,971/3,492 (56.4%)・fyl2x 396/444 (89.2%)・fprem 346/432 (80.1%)・fscale 389/419 (92.8%) |
| 主 (seed 2) | 94,111 (94.11%) | — | — |
| 従来 op 表 (`--skip` 5 命令) | 96,510 (96.51%) | 77 (0) | 従来 REPORT_APPENDIX_2966 §3 の値と一致 (試行列が同じ) |
| ネガコン `--nega-trig` (fyl2x を自然対数に取り違え) | 93,893 (93.89%) | 166 (45) | fyl2x 305/444 (主は 396/444)。 主との差 −91 件 |
| `--no-e` (m80 と 80bit 格納を外す) | 95,252 (95.25%) | 76 (76) | fsin 2,887/3,635・fcos 2,818/3,578・f2xm1 1,932/3,490・fyl2x 418/461・fprem 333/412・fscale 363/391 |
| `--only` fscale 系 | 98,107 (98.11%) | 0 | fscale 5,277/5,376 |

- m80 を含む試行 (主): 14,149 件中 12,148 件 (85.86%)。 従来 op 表は 14,269 中 12,525 (87.78%)。
- 主の FSW 不一致の最初の op: fxam 54・ftst 30・fcom 25・fcomp 20・fprem 15・fcos 11・fsin 8・fcompp 3。 比較命令 (fcom・fcomp・ftst・fxam の和 129 件。 fcompp の 3 件は含まない) が 129 件を占める。
- 注: fscale の指数域外は f64 出力では両方 inf で一致して見える (§3 の 21,036 件)。 f80 のまま比べる出力を持たないので、この harness では f80 の差を直接は測れない。

## 5. 読み方・原因の見立て

- **fsin/fcos の大引数 (推定・未確認)**: 一致率は |a| とともに単調に落ちる (π/4 以下 99.8% → 2^10 で 98.3% → 2^20 で 11%)。 x87 の fsin は π を 66 bit で還元するため、|a| が大きいほど還元誤差が大きくなる、と見るのが自然 (|a|=2^20 で絶対誤差 ≈ 2^−46 の見積もり。 推定)。 double 側 (libm) は還元を正確に行うので、この差は模型化していない。 模型化すれば一致は上がると推定するが、未実装。
- **native の FSW の挙動 (実測・`pre` 試験)**: fsin・f2xm1・fyl2x・fscale は C0/C2/C3 を変えず前の値を持ち越す (前の状態を ftst で 3 種類作って確認)。 fprem は完全で商ビットを設定し、部分で C2=1 のみ。 fsin(±inf) は C2=0・負の default NaN (C2=1 とは限らない)。 これを model に入れ、 ±inf の経路を直した (主試行の FSW 不一致: fprem 部分の商ビットを直す前 217 → 216 → ±inf を直した後 166)。
- **f2xm1・fyl2x の 1 ulp 級の差 (原因未確認)**: 引数の ln2 の丸めを hi/lo に分けても一致率は動かなかった (66.39% → 66.29%)。 引数の丸めは原因ではない。 libm 側の 1 ulp 誤差と、native の f80 中間精度の差の両方が候補。
- **非 m80 の FSW 不一致 45 件 (主) / 76 件 (`--no-e`) (推定)**: 1 ulp 級の値の差が後続の比較・fprem の商ビットに出た、と推定する。 未確認。
- **m80 の FSW 不一致 121 件 (主)**: 従来 op 表の 77 件と同じ性質 (f80 の指数域外の入力。 ADR D28 の帰結)。

## 6. 検証範囲・範囲外

- 範囲内: 5 命令の lowering・runtime・差分試験 (主・seed 2・従来 op 表・ネガコン・no-e)・命令単体試験 (seed 1・2)・lift の unsup (pass1/pass2)・x64 回帰 (8 本)。
- 範囲外: x87 の状態保存 (fnsave・frstor・fnstenv・fldenv: [PLG-G2-30] #3688)。 x87 を含む関数の native と wasm の差分 (#2989)。 f2xm1 の定義域外 (1<|x|≤1 以外は SDM で未定義・FL が呼ぶかは未確認)。 f80 の出力を持つ harness。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| fsin/fcos の大引数 (\|a\|>π/4) の x87 還元 (66 bit π) を模型化していない。 一致は 98.3% 以下・\|a\|>2^10 で 11% 以下 (§3)。 本 PR は \|a\|>π/4 を fail-fast にする | 定義域外は停止する (無言の誤値は出さない)。 定義域内 (≤π/4) の一致は 99.8% | PM agent の判断待ち: fsin/fcos の計算域の上限・既定案: π/4 (子 issue の候補。 本 PR では起票しない) |
| f2xm1 (\|x\|≤1) の 1 ulp 級の差 (一致 66%)・fyl2x (x>0) の 1 ulp 級の差 (一致 73%) | 差分試験の一致率を下げる。 原因未確認 (§5) | 本 PR の未解決 (原因の特定は未実施) |
| f2xm1 の定義域外 (1<\|x\|≤8、一致 0%) | 定義域外は fail-fast (本 PR)。 FL の呼び出しが定義域内か未確認 | PM agent の判断待ち: f2xm1 の計算域の確認・既定案: \|x\|≤1 (本 PR の既定) |
| 非 m80 の FSW 不一致 45 件 (no-e 76 件) | 1 ulp 級の差の伝播と推定 (§5)。 比較・fprem の商ビット | PM agent の判断待ち: 非 m80 の FSW 不一致の原因の調査を子 issue にするか・既定案: 起票しない (PM 判断まで未解決表に残す) |
| fscale の「f80 有限・f64 無限」21,036 件 (seed 1) | f64 出力では見えない (§4)。 f80 出力の harness が要る | PM agent の判断待ち: fscale の harness を f80 出力に拡張するか・既定案: 拡張しない (件数のみ本 PR で実測) |
| x87 fnsave・frstor・fnstenv・fldenv (4 件) | lift の unsup 4 件が残る | [PLG-G2-30] (#3688) |
| C1 の丸め方向 (trig・f2xm1・fyl2x・fst m32 等の直後) | FSW の C1 を比べる箇所では違う | `ott_x87.h` 制限 (6)・ADR D28 制限 6・#3749 (既存) |

## 8. 検証手順 (再現)

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=$RUNNER_TEMP/bin:$PATH   # emcc 名の gcc ラッパ (lift_text.py 用)
cd tools/plugins/slayer_engine_ia32
python3 lift_text.py                                      # §1 の unsup 4 件・被覆 85.37%
python3 x87_diff.py --n 100000 --seed 1                   # 主
python3 x87_diff.py --n 100000 --seed 1 --skip fsin,fcos,f2xm1,fyl2x,fprem   # 従来 op 表
python3 x87_diff.py --n 100000 --seed 1 --nega-trig       # ネガコン
python3 x87_diff.py --n 100000 --seed 1 --no-e
gcc -O1 -w -I ../../ott/rt -o work/x87/trans/x87_trans_direct x87_trans_direct.c ../../ott/rt/ott_cpu.c -lm
./work/x87/trans/x87_trans_direct 200000 1                # §3
mkdir -p $RUNNER_TEMP/before && git archive origin/main tools/ott | tar -x -C $RUNNER_TEMP/before
python3 x64_regress_1099.py $RUNNER_TEMP/before 8         # §1 (same 8/8)
```

- 差分確認 (測定 commit 以降のコード差分): 定義域判定 (fail-fast) の追加により、`tools/ott` の runtime・生成 C と差分試験の lowered 側にコード差分が入った。 差分試験の主試行の値 (93,984) は変更前後で同じ。 `git diff 7694f4bdd HEAD -- tools/ott tools/plugins/slayer_engine_ia32` の範囲を §8 に記録する。
- 大物: `find tools/plugins/slayer_engine_ia32 -type f -size +20M -not -path '*/work/*'` は 0 件。 生成物は `work/` (gitignore)。
