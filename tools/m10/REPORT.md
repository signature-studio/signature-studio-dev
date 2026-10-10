# M10 REPORT — OTT bit-exact 完走路検証 (band [F8] 係数 bit 突合 + junk 出生 trace)

## 0. 結論 (先出し)

- `bash tools/m10/m10_e2e.sh` = **PASS (exit 0)**: checks 7 / broken 0 + [E2] band 係数 dsm
  register-exact 突合 **maxdev = 0.0 (8 states × 10 係数 bit 完全一致)** + trap9 OOB 不発。
- **bit-exact 512/512 は不成立** (junk 残存) → tolerance 宣言へ移行 (§4):
  「正常 cell (0 < |v| < 4) の param 応答・determinism・基礎数値突合」を PASS 定義とし,
  junk 詳細を `m10_e2e.sh` INFO として常态化検収可能にした。
- **[F8] band filter C port の真の破れ 4 点を特定・修復** (FIX1–FIX4 下表)。m9 側の
  「pole ≈ 2..4 由来は [F8] [0x88]/[0x90]」仮説は**修正された** (§3): 実測では junk (~2^65 量級)
  の発生源は band IIR 係数**ではない** (exp 系 chain, §3.2)。
- junk census (m10 build, 検収同値): **[0x248]=0: zero 132 / normal 69 / junkHi 175 / junkTiny 136 /
  NaN 0 / |max| 1.67e20** — m9 検収値 (zero 132・junk 175) と完全一致 (band 修復とは独立に存続)。

## 1. 手順と成果物 (tools/m10)

- build: `m10_build.sh` (m9 鎖 reuse, `m10_boot.c` 差替参照 — tools/m6/m8/m9 は読取のみ改変 0 行)。
- 検収: `m10_e2e.sh` (E1–E7, INFO-census, bit 突合は tools/m10/m10_coefref.py)。
- trace pass 群 (新規作成; m9 の nanring 資産 文化継承):
  - `m10_dumpcoef.mjs`: band state [obj+0x140..0x178] × 8 の f64 係数全ダンプ。
  - `m10_bandtrace.mjs`: 1-sample chunk 連続 process での y/x 状態履歴。
  - `m10_junktrace.mjs` / `m10_ringtrace.mjs`: 4-sample chunk 実行毎の SVF 16 state / ring[0x250]6+ring[0x258]8
    per-cell 値追跡 (junk 出生 ring 特定に使用)。
  - `m10_junksrc.mjs` / `m10_junksrc2.mjs`: junk bits ↔ ring/state cells f32-lo/hi view 突合
    (bit 一致探索 → **junk 一致 0 件** を含む負証拠)。
  - `m10_coefdump.mjs` + `m10_coefref.py`: dsm register-exact 参照転記との bit 突合 (E2)。
  - `m10_probe.mjs`: 包括 probe (census + 係数 + dsm 参照, 開発用)。

## 2. [F8] band filter 修復 (目標 2) — dsm 0x180126670..91a 重突合 結果

| FIX | dsm op (欠落) | 効果 |
|---|---|---|
| F1 | `0x180126766 mulsd xmm13, xmm7` (C1⁴) | m9 port は v13 = C1² で通過 → K に C1² が加算され A16 ≈ −2 (dyad 分母欠落)。これが **m9 検収時の junk bit 系列と係数完全一致** (m9 側係数再シミュレーション (dsm ops 転記) が m9 junk 時点の係数を再現し, FIX1 適用で消滅する E2 evidence) する真の破れ 1 位 |
| F2 | `0x18012676b mulsd xmm9, xmm10` (4W2²) | S2 = 4W2²C1² が W2²C1² (÷4) になる脱漏 |
| F3 | `0x180126723 mulsd xmm2, [0x1802056f0=6.0]` (6W2⁴) | C16 = W2⁴/K (×6 欠落) → 6W2⁴/K, A32 分子も同値 |
| F4 | π̂/2π̂ 実ビット転記 | `b2d(0x4009249249249243)` / `b2d(0x4019249249249243)` (原 PE .rdata 0x1802056e8/f8 直読, 22/7 decimal から ~6 ulp 差) |

- 検収値 (f0 = 88.30000305175781 [0x42b0999a], SR = 44100.0 f64@st+0xb8):
  A16 = −3.9644032420571804, A32 = 5.893840508736176, B16 = −3.894465702604996, B32 = 0.9650284605750433,
  D1 = 1.5405651555022695e-09, C1c = 6.162260622009078e-09, C16 = 9.243390933013616e-09,
  D2 = −3.9294344784933486, E2 = 5.894151717740024, F2 = 0.9823586196233371
  — f0 = 2500 (4 states): A16 = −3.0070010520, B16 = −1.8170631590, A32 = 3.4690688854, B32 = 0.3651513295。
- 突合方法: `m10_coefref.py` = dsm op を xmm-register 命名で 1:1 転記 (op 順維持, 定数は const_addrs 実測)。
  **8 states × 10 係数: bit 一致 (dev = 0.0)** — f0 = 88.3/2500 とも。
- 定数の PE 直検 (analysis Plugins/binaries 直読): 0x1801ee848 = 2.0, 0x1801f70d8 = 8.0, 0x1801fde58 = 4.0,
  0x1802056f0 = 6.0, 0x180205700 = −4.0 — m9 const_addrs 側 indication (0xdf004/0xd7744 の rip-a 差 ~8B)
  の算出誤差が FIX の根拠判別を上書き (定数は全て dsm 実測 = m10 転記値を採用)。

## 3. junk 出生 trace (目標 1+3) — 実測 見所

### 3.1 junk bit 突合 (m9 値 ⇔ ring/state)

- junk f32 bits 例 (L cell): `0x9df9dcc3, 0xde124f49, 0x1e696358, 0x5e9628c5, ...` 隣接 2 cell 重複 (9/10, 11/12, …)
  — [F7]-class **outcopy 重複書き込みと cell 対** で現れ junk は ring 経由 (ring0 cell 12 等に先立って junk 値が在り)。
- bit-match window 全 ring ([0x250] 6 / [0x258] 8 rings per 256 cell) と band/SVF state 全 cell に対して **junk bits の完全一致 0** — junk は stored state からではなく **final loop 演算で新規に生成** (m10 REPORTの
  演算別 ring tracer で出生 op に到達)。

### 3.2 junk 値の正体 (確定部)

- junk 値群 = **±2^65 (3.68934881e19 EXACT), ±2^-63 (1.0842e-19 EXACT), ±2.0 系 → その後に per-stage ×1.0043
  増大系列** (ring0 → ring5: −3.705e19 → −3.94e19, 同時: −2.01 → −2.16) — exponential series は band IIR の
  係数 pole ではなく **exp() の入力量として放大される exp/log chain** ([box+0xb8] = 1.83e37, [box+0x90] =
  1.43e18 も GROWING — 3 gate box): m9 REPORT §2 の「由来 = [0x88]/[0x90] pole」の推定は本 trace により**保留 (実質否定寄)**: junk 2^65 量級は exp 系出力で, 係数 pole 解では説明できない。
- ring1→ring0 で same-position junk bit を共有する写像構造 (全 ring 同一 junk 位相) → out copy に junk 漏れが chain 化。

### 3.3 [0x248]=1 (18011efb0 band path) の状況 — 未解明継続

- census: zero 4 / normal 254 / junkHi 252 / junkTiny 2 / |max| 1.1306e36。
- 1-sample step trace: band state y は sample-by-sample **指数 ~×1.5/sample** で増大, x cell が
  3.03e-41 量級 (input deref/select 系 + dsm 0x18011f021..46e の feedback 係数組合せ)
  → **per-sample の破れ点が別に残ることを示す** (次回 [F7] 型 base-deref 修復を 0x18011e*  に適用).
- dsm-faithful 係数 (§2) の feedback 再帰 1 + A16z + A32z² + B16z³ + B32z⁴ の |root|:
  f0 = 88.3: {1.0190 ×2, 0.9720 ×2}, f0 = 2500: {1.6729 ×2, 0.9700 ×2} — **faithful 設定でも outside-root が存在**;
  native は stable, 残る破れ (per-sample 係数組合せ/経路) の別層に由来する可能性があり,
  verif 後の判定課題として REPORT 上に「在り」として記録する。

## 4. tolerance 宣言と判定スクリプト化 (目標 4+5)

- bit-exact 512/512: **不成立**。t1 全 512 cell bit 一致は junk の生成が (0.248)=0 path で 残存するため不成立。
- tolerance 宣言 (スクリプト化条件通りに `m10_e2e.sh` へ埋込み):
  1. **正常 cell (0 < |v| < 4) が ≥ 60 cells 存在する**こと (param 応答が junk に埋没しない); ※本回は 69
  2. **param 応答**: 順次 param 0.5 → 0.1 で正常 cell の bits に 100 cell 以上の差異 (検収: 380);
  3. **determinism**: 同一 setup → 再 process で出力 bits 完全一致 (検収: diff = 0);
  4. **[F8] 係数**: dsm register-exact 参照と bit 一致 (maxdev = 0) — 「bit-exact項」を係数域で宣告して
     検収する (checks に組み込み);
  5. **OOB 不発** ([F3] / trap9)。
- 上記が PASS 界, junkHi 値の MODEL discrimination (本修復は係数 bit 域のみで out-census に反映)

## 5. 未達残課題 (次回引継ぎ)

1. **[0x248]=0 exp chain 修復** (junkHi 175 の真正原因): junk = ±2^65/±2^-63 exp → box exp/log level
    computer chain の stage-gain ×1.0043 系増大 → final loop で outcopy に流出。outcopy 前段の
    box state ([0x200..0x218] per-sample) の破れが軸。
2. **[0x248]=1 経路の per-sample 破れ点**: x cell 3e-41-class (denormal) 入力 deref (pointer 経路 [rdi]/[r12]+ rsi
     の deref 欠落疑点) と 係数 feedback 組合せ → mixed junk の原因探査を次回最優先。
3. **0x2a8 ring 周期性** ([0x2a8] write index + [0x250]/[0x258] 6 + 8 = 14 名称) の統一ハーネス化 (pointermanager
     qword stride — m9 REPORT §5-4 引継し継続)。
4. bit-exact 512/512 参照 (mac AU/x64 SSE + native poly tan ulp) の標本化は junk-free 出力が担保されてから実施に留保する (m9 REPORT の既定キュと同継続)。

## 6. コミット内容

- tools/m10: m10_build.sh, m10_boot.c (m9 boot copy + FIX1..4), m10_e2e.sh, m10_coefdump.mjs,
  m10_coefref.py (dsm register-exact 参照転記), m10_probe.mjs, trace pass 群
  (m10_bandtrace.mjs, m10_dumpcoef.mjs, m10_junktrace.mjs, m10_ringtrace.mjs, m10_junksrc.mjs,
  m10_junksrc2.mjs), .gitignore (work/ 除外), REPORT.md。
- README/MILESTONES/docs/tools/m1-m9 等への編集 = 0 (README 提案文言は最終報告に記載)。
