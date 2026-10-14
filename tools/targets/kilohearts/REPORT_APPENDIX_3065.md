# REPORT APPENDIX 3065 — KH-38 (#3065): 対照 Gain closure の unsup (VEX/FMA 系) を flelift x64c で被覆

> 本付録は KH-38 の新規実測節。本体の導線は `REPORT_KH19.md` §10。issue が挙げた `REPORT_KH19D.md` と `lift_closure_x64c.sh` は main に存在しなかったため、実測は本付録に置き、スクリプトは `scripts/lift_closure_x64c.sh` として新設した。

## 0. 結論

- 対照 Gain の before 160 関数 closure (`gain_before_160.tsv`・root 27) を flelift `x64c` で lift すると、**unsup 48 種 / 285 箇所** が残っていた (origin/main `718e90fb`)。issue の 285 site / 48 種 と一致。
- 本 PR で **0 種 / 0 箇所** に減った。関数数 158・命令数 9,513 は before / after で同じ (lift 対象は同一)。
- 受入 1 (unsup の mnemonic を x64c に追加して被覆): 達成。48 種すべてに handler を追加した。ただし `int 0x29` の 3 箇所は OTT 版と同じく fail-fast の出力に変えた (§3)。
- 受入 2 (被覆後に再実行し before / after を実測): 達成 (§2)。
- 検証の範囲: 生成 C の `gcc -c` コンパイル、と代表 17 命令の差分テスト (`tools/flelift/tests/x64c_vex_diff.py`)。**Gain closure の native 実行との bit 一致 (e2e) は未実施** (§4)。

## 1. 測定条件

- 測定 commit: `ac58a874` (コードを変えた最後の commit)。before は origin/main `718e90fb` の `tools/flelift/x64c.py` を `X64C=` で指定して同じスクリプトを実行。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` を repo 外に展開 → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (76,642,304 B)。REPORT_KH19 §9 と同じ手順 (mac 側は不要)。
- 入力: `gain_before_160.tsv` の 160 行 (roots 27)。`func_rva` を calltgt、`root_class` が空でない行を roots とする。lift 対象は thunk (`jmp [IAT]`) の 2 行を除く 158 関数。
- 実行: `X64C=<lifter> bash scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>`。4 vCPU、各 1 回、各 13.8 s。`--closure 0` (直接 call の閉包は 0 件 = before 集合は直接 call で閉じている)。

## 2. before / after 実測

| 版 | unsup 種 | unsup 箇所 | 関数 | 命令 |
|---|--:|--:|--:|--:|
| before (origin/main `718e90fb`) | 48 | 285 | 158 | 9,513 |
| after (`ac58a874`) | 0 | 0 | 158 | 9,513 |

before の内訳 (箇所数の多い順・種名 件数):

vmovsd 32 · vmovntdq 30 · vmovd 29 · vmulsd 25 · vaddsd 23 · vmovq 17 · vfmadd213sd 16 · vsubsd 13 · vorpd 9 · vpshufd 7 · rcr 6 · vldmxcsr 6 · vcomisd 5 · vcvtdq2pd 5 · vpor 4 · int 3 · vcvtsi2ss 3 · vcvtss2si 3 · vmulpd 3 · vorps 3 · vpand 3 · vpsrlq 3 · vpxor 3 · vstmxcsr 3 · vucomiss 3 · movsldup 2 · vcvtpd2dq 2 · vfnmadd231sd 2 · vpsubq 2 · vucomisd 2 · cmpleps 1 · movshdup 1 · vaddpd 1 · vandpd 1 · vcvtps2pd 1 · vcvtsd2ss 1 · vdivsd 1 · vfmadd231sd 1 · vfmsub213sd 1 · vinsertf128 1 · vmovss 1 · vpaddq 1 · vpsllq 1 · vpsrad 1 · vpsubd 1 · vpunpckldq 1 · vunpcklpd 1 · vxorpd 1

(issue の列挙 vmovntdq 30・vmovsd 32・vmovd 29・vmulsd 25・vaddsd 23・vmovq 17・vfmadd213sd 16 と一致)

## 3. 被覆の方法 (`tools/flelift/x64c.py`)

- **VEX.128 の 3-op** (`d, s1, s2|imm`): `d = s1` をコピーして legacy (d, s2) を適用し、`YL[d] = 0` (VEX.128 の上位 0 化)。
  - 可換な `d == s2` 形は s1 と s2 を入れ替える。スカラ形 (sd/ss) は上位ビットが s1 由来なので、legacy 適用後に s1 から上位を写す。最初の版はこの写しが無く、差分テストの `vaddsd xmm2, xmm1, xmm2` で不一致になり、修正した。
  - 非可換な `d == s2` 形は Unsup のまま (本 closure には出ない)。
- **VEX.128 の 2-op** (+imm): legacy handler を適用し、xmm 宛先なら上位を 0 化。`vucomisd`・`vcomisd`・`vucomiss`・`vstmxcsr`・`vldmxcsr` は flags か mem 宛てだけなので上位には触らない。
- **VEX FMA** (`vfmadd/fmsub/fnmadd/fnmsub` × 132/213/231 × sd/ss): OTT 版 (`tools/ott/lift/x64c.py`) と同式 (1 回丸め + NaN payload 補正)。runtime の `ott_fma_d/s` を `tools/flelift/rt/fle_cpu.h` に移植した。
- **新規 legacy**: `rcr` (OTT 版と同式)、`movsldup`・`movshdup`、`cmpeqps`〜`cmpordps` (predicate 0〜7)、`vinsertf128` (ymm)、`movntdq`・`movntps`・`vmovntdq` (ymm 格納は既存 `STY`)。
- **`int 0x29` (3 箇所)**: OTT 版と同じく `ott_unsup(...)` の fail-fast 出力にした。Unsup 例外ではないので件数の unsup には数えない。実行時は従来どおり fail-fast で止まる (件数が減ったのは分類の変更であり、実行時の挙動は変えていない)。

## 4. 検証 (実施・未実施)

実施:

1. `python3 -m py_compile` ✓。生成 C (`fle_lifted.c`・約 1.1 MB) を `gcc -std=gnu11 -c` (`-I tools/flelift/rt`) で ✓ (rc 0)。
2. 差分テスト `tools/flelift/tests/x64c_vex_diff.py`: 17 命令 (vaddsd (d≠s2 / d==s2)・vmulpd・vfmadd213sd・vfnmadd231sd・vfmsub213sd・vpsrlq・vpshufd・vmovq・vmovd・vinsertf128・rcr・movsldup・cmpleps・vucomisd・vmovsd・vsubsd)。GNU as で機械語にし、x64c の FnLift で C に落として runtime と共に実行し、Intel SDM の意味から求めた参照値と全 X/YL/R/フラグを比較。**17/17 PASS** (commit `ac58a874`)。参照値の FMA は Python `math.fma` (正確丸め)。
3. 再測定 (§2)。before / after を同一スクリプトで取得。

未実施 (未解決):

- Gain closure の native 実行との bit 一致 (e2e): 未実施。VEX/FMA は差分テストの 17 命令でのみ確認。`vinsertf128`・`vmovntdq` (ymm) は差分テストの対象外で、生成 C の目視のみ。
- FLEngine の起動 e2e (`tools/flelift/fle_e2e.sh`・boot): 未実施。x64c は FLEngine の lift にも使われるため、製品 KPI (FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウの有無) は **動かしていない**。
- vtable 規則の closure (nogui 555 関数 / all 1,995 関数, `REPORT_KH19.md` §2): 未測定。`vtable_closure.py` は関数一覧を出さず件数だけを出すため、lift の入力にできない。一覧の出力は別 issue が必要。

## 5. 再現

```sh
# 素材を展開し HeartCore.core_64 を得る (REPORT_KH19.md §9)
X64C=<origin/main の x64c.py> bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>   # before: 285 site
bash tools/targets/kilohearts/scripts/lift_closure_x64c.sh <HeartCore.core_64> <out>                               # after: 0 site
python3 tools/flelift/tests/x64c_vex_diff.py                                                                       # 17/17
```
