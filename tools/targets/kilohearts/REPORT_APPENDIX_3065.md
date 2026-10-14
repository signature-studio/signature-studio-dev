# REPORT APPENDIX 3065 — KH-38 (#3065): 対照 Gain closure の unsup (VEX/FMA 系) を flelift x64c で被覆

> 本付録は KH-38 の新規実測節。本体の導線は `REPORT_KH19.md` §11。issue が挙げた `REPORT_KH19D.md` と `lift_closure_x64c.sh` は main に存在しなかったため、実測は本付録に置き、スクリプトは `scripts/lift_closure_x64c.sh` として新設した。

## 0. 結論

- 対照 Gain の before 160 関数 closure (`gain_before_160.tsv`・root 27) を flelift `x64c` で lift すると、**unsup 48 種 / 285 箇所** が残っていた (origin/main `718e90fb`)。
- 測定 commit `ac58a874` で **0 種 / 0 箇所** に減った。関数数 158・命令数 9,513 は before / after で同じ。
- 差し戻し後の修正で `i_rcr` を実機の rcr に合わせた (§4)。実機 rcr との照合 4000/4000 一致、差分テスト 35/35 PASS (HEAD `236a63c9`)。
- **修正後の HEAD で closure を再測定していない** (`plugins-kilohearts` 素材が本 run に無い)。after の 0 は `ac58a874` の値。§4 の理由で rcr の unsup 件数は変わらない見込みだが、実測は未実施 (§4 未解決)。

## 1. 測定条件

- 測定 commit: `ac58a874` (コードを変えた最後の測定)。before は origin/main `718e90fb` の `tools/flelift/x64c.py` を `X64C=` で指定して同じスクリプトを実行。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` を repo 外に展開 → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (76,642,304 B)。REPORT_KH19 §9 と同じ手順 (mac 側は不要)。
- 入力: `gain_before_160.tsv` の 160 行 (roots 27)。`func_rva` を calltgt、`root_class` が空でない行を roots とする。lift 対象は thunk (`jmp [IAT]`) の 2 行を除く 158 関数。
- 実行: `X64C=<lifter> bash scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>`。4 vCPU、各 1 回、各 13.8 s。`--closure 0` (直接 call の閉包は 0 件)。
- 測定 commit から HEAD (`236a63c9`) までの差分 (測定入力のパス): `git diff ac58a874 HEAD --stat -- tools/flelift tools/targets/kilohearts/scripts/lift_closure_x64c.sh tools/targets/kilohearts/gain_before_160.tsv`

```
 tools/flelift/tests/rcr_native_check.py | 86 +++++++++++++++++++++++++++++++++
 tools/flelift/tests/x64c_vex_diff.py    | 85 +++++++++++++++++++++++++-------
 tools/flelift/x64c.py                   | 15 ++++--
 3 files changed, 164 insertions(+), 22 deletions(-)
```

差分の中身は `x64c.py` の `i_rcr` (§4) と差分テスト・実機照合。lift の入力 (`gain_before_160.tsv`・`lift_closure_x64c.sh`) は不変。

## 2. before / after 実測

| 版 | unsup 種 | unsup 箇所 | 関数 | 命令 |
|---|--:|--:|--:|--:|
| before (origin/main `718e90fb`) | 48 | 285 | 158 | 9,513 |
| after (`ac58a874`・修正前の `i_rcr`) | 0 | 0 | 158 | 9,513 |

- `int 0x29` の 3 箇所 (fail-fast) は件数の外 (§3)。after の表の 0 はこの 3 箇所を含まない。
- 修正後 HEAD (`236a63c9`) の再測定は未実施 (§4)。

before の内訳 (箇所数の多い順・種名 件数):

vmovsd 32 · vmovntdq 30 · vmovd 29 · vmulsd 25 · vaddsd 23 · vmovq 17 · vfmadd213sd 16 · vsubsd 13 · vorpd 9 · vpshufd 7 · rcr 6 · vldmxcsr 6 · vcomisd 5 · vcvtdq2pd 5 · vpor 4 · int 3 · vcvtsi2ss 3 · vcvtss2si 3 · vmulpd 3 · vorps 3 · vpand 3 · vpsrlq 3 · vpxor 3 · vstmxcsr 3 · vucomiss 3 · movsldup 2 · vcvtpd2dq 2 · vfnmadd231sd 2 · vpsubq 2 · vucomisd 2 · cmpleps 1 · movshdup 1 · vaddpd 1 · vandpd 1 · vcvtps2pd 1 · vcvtsd2ss 1 · vdivsd 1 · vfmadd231sd 1 · vfmsub213sd 1 · vinsertf128 1 · vmovss 1 · vpaddq 1 · vpsllq 1 · vpsrad 1 · vpsubd 1 · vpunpckldq 1 · vunpcklpd 1 · vxorpd 1

(issue の列挙 vmovntdq 30・vmovsd 32・vmovd 29・vmulsd 25・vaddsd 23・vmovq 17・vfmadd213sd 16 と一致)

## 3. 被覆の方法 (`tools/flelift/x64c.py`)

- **VEX.128 の 3-op** (`d, s1, s2|imm`): `d = s1` をコピーして legacy (d, s2) を適用し、`YL[d] = 0` (VEX.128 の上位 0 化)。
  - 可換な `d == s2` 形は s1 と s2 を入れ替える。スカラ形 (sd/ss) は上位ビットが s1 由来なので、legacy 適用後に s1 から上位を写す。最初の版はこの写しが無く、差分テストの `vaddsd xmm2, xmm1, xmm2` で不一致になり、修正した。
  - 非可換な `d == s2` 形は Unsup のまま (本 closure には出ない)。
- **VEX.128 の 2-op** (+imm): legacy handler を適用し、xmm 宛先なら上位を 0 化。`vucomisd`・`vcomisd`・`vucomiss`・`vstmxcsr`・`vldmxcsr` は flags か mem 宛てだけなので上位には触らない。
- **VEX FMA** (`vfmadd/fmsub/fnmadd/fnmsub` × 132/213/231 × sd/ss): OTT 版 (`tools/ott/lift/x64c.py`) と同式 (1 回丸め + NaN payload 補正)。runtime の `ott_fma_d/s` を `tools/flelift/rt/fle_cpu.h` に移植した。
- **新規 legacy**: `rcr` (実機の規則。§4)、`movsldup`・`movshdup`、`cmpeqps`〜`cmpordps` (predicate 0〜7)、`vinsertf128` (ymm)、`movntdq`・`movntps`・`vmovntdq` (ymm 格納は既存 `STY`)。
- **`int 0x29` (3 箇所)**: OTT 版と同じく `ott_unsup(...)` の fail-fast 出力にした。Unsup 例外ではないので件数の unsup には数えない。実行時は従来どおり fail-fast で止まる (件数が減ったのは分類の変更であり、実行時の挙動は変えていない)。

## 4. 検証 (実施・未実施)

### 実施

1. `python3 -m py_compile` ✓。生成 C (`fle_lifted.c`・約 1.1 MB) を `gcc -std=gnu11 -c` (`-I tools/flelift/rt`) で ✓ (`ac58a874` 時点、rc 0)。HEAD (`236a63c9`) では差分テストの生成 C (35 ケース) を `-Wshift-count-overflow` 付きでコンパイルし、shift 系の警告は 0 件 (残りは生成器の既存の `unused-label` 等)。
2. 差分テスト `tools/flelift/tests/x64c_vex_diff.py` **35/35 PASS** (HEAD `236a63c9`)。GNU as で機械語にし、x64c の FnLift で C に落として runtime と共に実行し、参照値と全 X/YL/R/フラグを比較。初期フラグは乱数 (従来は全 0 で「保存」と「0 に設定」を区別できなかった)。
   - 直接検証した mnemonic は 48 種のうち 16 種: vaddsd・vmulpd・vfmadd213sd・vfnmadd231sd・vfmsub213sd・vpsrlq・vpshufd・vmovq・vmovd・vinsertf128 (k=1 のみ)・rcr・movsldup・cmpleps・vucomisd・vmovsd・vsubsd。
   - 残り 32 種 (`int 0x29` を含む) は生成 C の目視のみ (#850)。`vinsertf128` は k=1 のみ検証、k=0 と `vmovntdq` は未検証。
3. **rcr の規則は実機で確定** (`tools/flelift/tests/rcr_native_check.py`、x86-64 + gcc):
   - 手順: インライン asm で `pushfq`/`popfq` により入力フラグを与え、`rcr` の結果と出力フラグ (CF/OF/ZF/SF/PF) を取る。乱数 4000 件 (w = 8/16/32/64、count 0〜255、フラグ乱数) を参照式 `rcr_ref` と照合。
   - 結果: **4000/4000 一致**。
   - 実機で確かめた規則: (a) count & マスク (8/16/32bit は 0x1F、64bit は 0x3F) が 0 なら flags 不変。(b) 8bit は回転量を MOD 9、16bit は MOD 17 で決める。マスク後が 9・17 の倍数 (回転 0) でも OF は更新され、CF は不変。(c) OF = MSB(結果) ^ MSB-1(結果)。count>1 でも同式 (scratch 検証で各 6000 件 × 2 回、count 0〜255、4 幅で全件一致)。(d) 32bit の書き込みは count 0 でも上位をゼロ拡張 (`rcr edx, cl` で cl=0 のとき rdx = 1)。(e) ZF/SF/PF は変えない。
   - SDM 原文は本 run から取得できなかった (felixcloutier.com が 404)。上の規則は実機測定を根拠とする。
4. 旧 `i_rcr` の検出力: 旧式で差分テストを流すと rcr 19 件がすべて FAIL (非 rcr 16 件は PASS)。旧式は 64bit の `(uint64_t)fCF << 64` を含み、`rcr rax, 1` の CF が誤った (gcc `-Wshift-count-overflow`)。修正後はこの警告が出ない。

### 未実施 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後 HEAD (`236a63c9`) での closure 再測定 (unsup 285 → 0 の再実行・`fle_lifted.c` の再生成と `gcc -c`) は未実施。`plugins-kilohearts` 素材が本 run の `$ARTIFACTS_DIR` に無く (fl-win64 のみ)、`HeartCore.core_64` を得られなかった。rcr の Unsup 経路 (`rd`/`wr` の型判定) は変えていないので件数の変化は見込まないが、実測はしていない | after 0 は `ac58a874` の値 | 次 run で `oc_artifacts: fl-win64 plugins-kilohearts` を付けて再測定 (#850) |
| Gain closure の native 実行との bit 一致 (e2e) は未実施。差分テストの 16 種以外 (32 種) は生成 C の目視のみ。`vinsertf128` は k=1 のみ、k=0 と `vmovntdq` は未検証 | 被覆した handler の意味は 16 種でのみ確定 | #850 (親) |
| FLEngine 起動の e2e (`tools/flelift/fle_e2e.sh`・boot) 未実施。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) は **動かしていない** | 製品 KPI の前後値が無い | #850 (親) |
| vtable 規則の closure (nogui 555 関数 / all 1,995 関数) の unsup 未測定。`vtable_closure.py` は関数一覧を出さず件数のみ | 対照 closure の残りの unsup は不明 | #850 (親) |
| OTT 版 `tools/ott/lift/x64c.py` の `i_rcr` は旧式 (SETZSP・OF = MSB ^ 新CF・`% (W+1)`・64bit の `<< 64`) のまま | OTT の rcr site (0x1801bc890 の FP 制御) の挙動が誤りうる | #3125 (KH-47) |

## 5. 再現

```sh
# 素材を展開し HeartCore.core_64 を得る (REPORT_KH19.md §9)
X64C=<origin/main の x64c.py> bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>   # before: 285 site
bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>                               # after: 0 site (修正後 HEAD は未測定)
python3 tools/flelift/tests/x64c_vex_diff.py                                                                       # 35/35
python3 tools/flelift/tests/rcr_native_check.py                                                                    # rcr vs 実機 4000/4000 (x86-64)
```
