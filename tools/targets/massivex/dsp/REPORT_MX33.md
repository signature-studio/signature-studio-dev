# Massive X MX-33 (#3032) 受入 1: xmm0〜3 だけの入口 livein (MX-6 の保留 17 件) の判定

- 解析日: 2026-10-15 / 担当: `tools/targets/massivex/dsp/` (親 #1123 MX-6 の残件。受入 1 の残件と受入 2〜5 は子 issue に分離)
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) を既存パーサで展開
  (`scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> <work> key`)。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (検収値と一致)。PE の置き場所は `$RUNNER_TEMP` 配下。
- **測定 commit = `d9a2b7ec2`** (コードを変えた最後の commit)。再現: `MX_PE='$RUNNER_TEMP/mx33/work/extracted/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx33' bash tools/targets/massivex/dsp/mx6_e2e.sh`。

## 0. 結論 (先出し)

1. **受入 1 の結論: 17 件は定義どおりには 1 件も確定しない。** scalar 0 / 128 bit 0 / 判定不能 **17**。
   17 件の入口読み 21 本はすべて「reg-reg 複写」(9 件) か「VEX 3 オペランドの上位保持 (merge)」(8 件) で、
   scalar 読みも packed 証拠も 1 本もない (§1・§2)。
2. **merge 8 件は引数の根拠にならない。** `vcvtsi2sd xmm0, xmm0, rax` 型は xmm の下位 32/64 bit を読まずに上書きし、
   上位だけを素通しする。仕様文言どおり「`cvtsi2ss` 等は scalar 読み」とすると 8 件が scalar に落ちるが、これは誤分類なので採らない (§3 感度)。
3. **copy 9 件は転送先の後続読みが未確定。** `movaps xmm6, xmm2` 等の転送先 (xmm6・xmm3) を追わないため判定不能のまま。
   受入 1 の確定にはこの追跡が要る (未解決 U3h・§6)。
4. **独立再計算 (線形): 範囲内に 128 bit 読みを持つ関数は 9 件**。ただし CFG で入口から未定義と判定された読みに 128 bit 型はなく、
   線形の 128 bit 読みは定義後 (または CFG 非到達) の読み。CFG 側の 128 bit 候補は 0 件のため包含検査 `CFG-P ⊆ 線形-P` は空真。構造上の上限確認にとどまる (§4)。
5. **NC 9/9 PASS** (MX-6 の 5 件 + 本件の 4 件)。e2e `mx6_e2e.sh` は exit 0 (35 s)。funclet は seeds 533 / pdata 始点 529 のまま (positive control PASS)。
6. **MX-6 の表示値は不変**: pdata 始点の xmm4/5 livein 0・保留 17 (seeds)・census・funclet の値は MX-6 §1 と一致。

## 1. 判定定義 (実装: `scripts/mx33_xmm03.py`・読み列挙は `scripts/mx6_vectorcall.py` の `analyze`)

- **対象**: pdata 始点かつ seeds (567 入口面) の関数のうち、`xmm4/5` の入口 livein が 0 で `xmm0〜3` の入口 livein が 1 つ以上ある 17 件。
  `vectorcall.json` の rows から抽出し、関数範囲 `[RVA, end)` を再解析して livein 集合が一致することを assert。
  1-round 側の pdata 始点保留 (17 件) も同じ RVA 集合 (`same set=True`)。
- **読み列挙**: `analyze` の must-def (全経路で書かれている集合) で、入口から未定義の xmm_k (k∈0..3) を読む命令を列挙する
  (`undef_reads03`。既存の livein 計算に 1 行足して位置を返すように最小拡張)。
- **幅の分類** (命令の mnemonic と オペランド役割。VEX の `v` 接頭辞は除く):

| 分類 | 命令 | 理由 |
|---|---|---|
| **S** (scalar) | `*ss`/`*sd` の算術・比較・変換 (`addss`・`comiss`・`cvtss2sd`・`cvtss2si` 等)、`movd`/`movq`、`movss`/`movsd` の src 読みと memory store、`movlpd` の store | 下位 32/64 bit のみ使う |
| **P** (128 bit 証拠) | `*ps`/`*pd` の算術・変換、`p*` 整数 SIMD、shuffle 族 (`shufps`・`unpck*`・`movhlps`/`movlhps` の src・`movddup`・`movsldup`/`movshdup`)、`movhps`/`movhpd` の store (上位 64 bit)、full-width store (`movaps`/`movups`/`movapd`/`movupd`/`movdqa`/`movdqu`/`movnt*` の memory 宛先) | packed 演算か上位 64 bit の利用 |
| **A** (曖昧) | reg-reg 複写 (`movaps` 等の xmm 宛先が reg)、部分書込の**保持側** (`movss`/`movsd` の dest、`movlps`/`movlpd`/`movhps`/`movhpd` の load、`movhlps`/`movlhps` の dest)、VEX 3 オペランド scalar の上位保持 (`cvtsi2*` を含む・算術 `add/sub/mul/div/min/max/cmp/fma` 以外)、bitwise `andps`/`xorps` 等、`movlps` の store、未分類 | 値を消費していない・幅の証拠がない |

- **関数の判定**: いずれかの k の読みが P → **128 bit 候補**。全 k が S のみ → **scalar**。それ以外 → **判定不能**。
- **仕様からの訂正 (理由付き・感度は §3)**: (a) 仕様文言の「`cvtsi2ss` 等の scalar 読み」は、xmm 入力が VEX 3 オペランドの
  上位保持としてのみ読まれる (下位は GPR から書かれる) ため A に変更。(b) bitwise `*ps`/`*pd` は、MSVC が scalar の符号反転・絶対値を
  定数マスクの `xorps`/`andps` で書くため、128 bit 証拠に含めず A。(c) 保持側の merge 読みは、値の幅の証拠にならないため A。

## 2. 17 件の一覧 (RVA・k・根拠の命令アドレスと mnemonic)

「線形 P」は線形走査で範囲内に見つかった P 読み (k) で、CFG の判定には使っていない (§4)。

| # | 関数 RVA–終端 | 命令数 | 入口 livein k | 根拠 (読み命令のアドレス・mnemonic・型) | 線形 P (k) | 判定 |
|--:|---|--:|---|---|---|---|
| 1 | 0xccc0–0xcd22 | 27 | 2 | 0x18000cccb `movaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 2 | 0xef60–0xefd5 | 23 | 0 | 0x18000ef80 `vcvtsi2ss xmm0, xmm0, rax` (A: merge) | – | 判定不能 |
| 3 | 0x105e0–0x1069a | 54 | 2 | 0x1800105fb `vmovaps xmm3, xmm2` (A: 複写) | 0 | 判定不能 |
| 4 | 0x11830–0x118ed | 62 | 2 | 0x18001183d `vmovaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 5 | 0x1108c0–0x11090d | 25 | 2 | 0x1801108ce `movaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 6 | 0x110960–0x1109a8 | 19 | 2 | 0x180110969 `movaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 7 | 0x1109b0–0x1109f8 | 19 | 2 | 0x1801109b9 `movaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 8 | 0x110a30–0x110a75 | 21 | 2 | 0x180110a3a `movaps xmm6, xmm2` (A: 複写) | – | 判定不能 |
| 9 | 0x17b4e0–0x17b63d | 76 | 2 | 0x18017b505 `movaps xmm6, xmm2` (A: 複写) | 0 | 判定不能 |
| 10 | 0x17b680–0x17b7ed | 79 | 2 | 0x18017b6a5 `movaps xmm6, xmm2` (A: 複写) | 0 | 判定不能 |
| 11 | 0x7d38d0–0x7d3b05 | 127 | 2 | 0x1807d3937 `vcvtsi2ss xmm0, xmm2, dword ptr [rax+0xc]` (A: merge) | 0,1,2,3 | 判定不能 |
| 12 | 0x7d3b10–0x7d3d95 | 149 | 2 | 0x1807d3bb6 `vcvtsi2ss xmm0, xmm2, dword ptr [rax+0xc]` (A: merge) | 0,1,2,3 | 判定不能 |
| 13 | 0x7dcb60–0x7dcca8 | 71 | 0, 1 | 0x1807dcbad `vcvtsi2sd xmm0, xmm0, r9d`・0x1807dcbb2 `vcvtsi2sd xmm1, xmm1, r10d` (A: merge) | 0,1,2,3 | 判定不能 |
| 14 | 0x7dce90–0x7dd031 | 79 | 0, 1 | 0x1807dcec4 `vcvtsi2sd xmm0, xmm0, rax`・0x1807dcf78 `vcvtsi2sd xmm1, xmm1, rax` (A: merge) | 0,1,2,3 | 判定不能 |
| 15 | 0x7dd960–0x7ddaa8 | 71 | 0, 1 | 0x1807dd9ad `vcvtsi2sd xmm0, xmm0, r9d`・0x1807dd9b2 `vcvtsi2sd xmm1, xmm1, r10d` (A: merge) | 0,1,2,3 | 判定不能 |
| 16 | 0x7ddc90–0x7dde31 | 79 | 0, 1 | 0x1807ddcc4 `vcvtsi2sd xmm0, xmm0, rax`・0x1807ddd78 `vcvtsi2sd xmm1, xmm1, rax` (A: merge) | 0,1,2,3 | 判定不能 |
| 17 | 0x118d8b0–0x118d994 | 49 | 0 | 0x18118d8cc `vcvtsi2sd xmm0, xmm0, rax` (A: merge) | – | 判定不能 |

- 内訳: **scalar 0 / 128 bit 0 / 判定不能 17**。読みの型: 複写 9 件 (1 読み each・全て k=2)、merge 8 件 (計 12 読み)。
- merge の読みは、同じ命令が xmm_k の下位を新しい値で上書きする。上書き後の xmm_k を後続の命令が使い
  (例 #2: `vdivss xmm0, xmm1, xmm0` は `vcvtsi2ss` の結果を使う)、入口の xmm_k の下位は計算に入らない。

## 3. ネガティブコントロール (NC) と感度

`mx33_xmm03.py --selftest` (合成バイト列・PE 不要・逆アセンブルの mnemonic を出力して符号化を確認):

| # | 合成列 (逆アセンブル結果) | 期待 | 結果 |
|--:|---|---|---|
| 1 | `addss xmm0, xmm1; ret` (必須) | scalar | PASS |
| 2 | `addps xmm0, xmm1; ret` (必須) | 128 bit | PASS |
| 3 | `movss dword ptr [rsp+8], xmm0; ret` (必須) | scalar | PASS |
| 4 | `movaps xmmword ptr [rsp+8], xmm0; ret` (必須) | 128 bit | PASS |
| 5 | `movaps xmm1, xmm0; ret` (必須・reg-reg 複写) | 判定不能 | PASS |
| 6 | `andps xmm0, xmm1; ret` (追加・bitwise) | 判定不能 | PASS |
| 7 | `paddd xmm0, xmm1; ret` (追加・整数 SIMD) | 128 bit | PASS |
| 8 | `movss xmm0, xmm1; ret` (追加・k0 は merge のみ・k1 は scalar) | 判定不能 | PASS |
| 9 | `vcvtsi2ss xmm0, xmm0, eax; ret` (追加・VEX merge のみ) | 判定不能 | PASS |

- **NC 9/9 PASS**。MX-6 の `mx6_vectorcall.py --selftest` (5 件) も PASS のまま。
- **感度 (分類規則の影響)**:
  - 仕様文言どおり `cvtsi2*` の xmm 入力を scalar 読みにする: **scalar 8 / 128 bit 0 / 判定不能 9**。増えた 8 件は上表の merge 8 件そのもので、
    入力を消費しないため採らない (§1 (a))。
  - bitwise `*ps`/`*pd` を 128 bit 証拠に含める: **変化なし** (17 件に bitwise 読みはない)。
  - 既知の非 vectorcall float 関数での scalar 落ちの確認 (任意項目): **未実施**。

## 4. 独立再計算 (線形走査・構造上の上限)

- 方法: CFG を使わず、各 17 件の `[RVA, end)` を先頭から線形に逆アセンブルし、xmm0〜3 の読みのうち P 型 (§1 の表) を数える。
- 結果: 範囲内に P 読みを持つ関数は **9 件** (#3, 9, 10, 11, 12, 13, 14, 15, 16。k は表の「線形 P」列)。
  CFG で入口未定義と判定された読み (§2) に P 型はないため、これらの P 読みは CFG の判定に現れない
  (定義後の読み、または CFG 非到達の読み。どちらかは個別に確認していない)。
- 包含検査 `CFG の 128 bit 候補 ⊆ 線形 P 関数`: CFG 側の 128 bit 候補が 0 件のため **空真**。
- **限界**: 線形側も CFG 側も同じ逆アセンブラ (capstone)・同じ読み集合 (`effects()`)・同じ分類 (`classify_read`) を使う。
  よって、ここで確認したのは「線形が CFG の上限になっている」という構造だけで、分類規則の独立な検証ではない。

## 5. 検証 (受入 6): e2e と positive control

| 工程 | 結果 (MX-6 §1 との比較) |
|---|---|
| NC (MX-6・5 件) | 5/5 PASS (MX-6 と同じ) |
| NC (MX-33・9 件) | 9/9 PASS |
| RTTI + 入口面 | seeds 567 / 1-round 3,226 / pdata 186,960 (MX-6 と同じ) |
| vectorcall (MX-6) | seeds: pdata 始点 livein xmm4/5 = 0 / 保留 17 (MX-6 と同じ) |
| 受入 1 (MX-33) | 17 件: scalar 0 / 128 bit 0 / 判定不能 17 (§2) |
| .pdata census | pdata 187,060 / chained 62,526 / EH 23,293 / 読取不能 160 (MX-6 と同じ) |
| funclet (positive control) | **seeds 533 / pdata 始点 529** (MX-6 と同じ・step 7/7 で assert) |
| 判定 | PASS (step 6/7・7/7) |

- e2e: `mx6_e2e.sh` (7 工程) → **exit 0・elapsed 35 s**。load average: 開始 `0.00 0.04 0.04` → 終了 `0.39 0.13 0.07`。
- 追加した assert: step 6/7 は `vectorcall` の livein 0・整合 OK に加え、受入 1 の件数 17 と内訳合計 17、包含 OK を要求。
  step 7/7 は `pdata_eh.json` の `funclets_fh3.seeds` から funclet 533 / pdata 始点 529 を読み、不一致なら exit 1。

## 6. 検証範囲・範囲外と未解決

**検証範囲**: VST3 の pdata 始点 seeds 17 件 (1-round 側の pdata 始点保留 17 件も同じ RVA 集合)・xmm0〜3 の入口 livein の幅分類・NC 9 件・線形の構造上限。
**範囲外**: 受入 2〜5 (FH4 funclet 全数・unwind 残件・funclet 到達・取り込み設計)、xmm4/5 の判定の変更、lift 出力 (RetDec/x64c) への影響。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U3h: reg-reg 複写 (`movaps xmm6, xmm2` 等) の転送先 xmm_j の後続読みを追わない | 受入 1 の判定不能 9 件 (複写型) | 子 **[MX-37]** |
| U3d: 既存 must-def は部分書込 (merge) を全幅の定義として扱う。merge 後の上位保持の利用を見ない。MX-6 の xmm4/5 陰性 (livein 0) も、merge 先頭の入力を見落とす過小検出側の影響を受けうる (未測定) | 判定不能 8 件 (merge 型)・MX-6 の陰性の強さ | 子 **[MX-37]** |
| U3e: call/jmp の引数転送 (xmm を読まずに渡す形) は `regs_access` に現れず、母集合 (livein 17) に入らない | 母集合の外側の関数は未判定 | 子 **[MX-37]** |
| U3f: 包含検査が空真 (CFG の 128 bit 候補 0 件)・線形側と分類器を共有 | §4 の独立性は弱い | 本 PR の限界として記載 (追加起票なし) |
| U3g: 既知の非 vectorcall float 関数での感度確認 (任意) | scalar 落ちの実地確認なし | 未実施 (子 **[MX-37]**) |
| U3b (MX-6 から): 間接 jmp テーブルの残り (seeds 12 / 1-round 14 の過大近似) | 陰性の保守性は保つが精度は未確定 | 子 **[MX-37]** |
| U3c (MX-6 から): 1-round の解析不能 118 件の由来 | vectorcall 判定の対象外 | 子 **[MX-37]** |
| 受入 2 (MX-6 U4a・FH4 funclet 全数) | FH4 の landing pad が一覧に入らない | 子 issue **[MX-38]** |
| 受入 3 (MX-6 U4b・U4c・unwind 残件) | 1 本目 .pdata 全体の数値は下界・読取不能 160 件の原因未確定 | 子 issue **[MX-38]** |
| 受入 4・5 (MX-6 U4d・U4e・funclet 到達と取り込み設計) | #228 同型の確定 (深い closure での到達) と x64c への取り込み | 子 issue **[MX-39]** |

- 子 issue の割当: **[MX-37]** = 受入 1 の残件 (U3 系: 複写先の追跡・merge 扱い・引数転送・感度・間接 jmp・解析不能 118 件)、**[MX-38]** = 受入 2・3 (FH4 funclet・unwind 残件)、**[MX-39]** = 受入 4・5 (funclet 到達・取り込み設計)。起票番号は PR 本文に記載。

## 7. 既知類型との関係

- `docs/DEFECTS.md` の D1a〜D23 (lift の silent miscompile 類型) と `tools/icall/REPORT.md` §4 の D1〜D13 (ICALL 系) は別体系で、本件は解析モデルの問題 (merge と複写の扱い)。
  どちらにも行を足さない。
- 受入 2〜4 の landing pad 非到達は、`tools/icall/REPORT.md` §4 **D12** (Delphi landing pad 非到達) と同型 (MX-6 §4 と同じ)。MSVC 固有の差は子 issue で扱う。

## 8. 測定 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit = **`d9a2b7ec2`** (`feat(massivex): classify xmm0-3 vectorcall candidates (MX-33 #3032)`)。
  変更: `scripts/mx6_vectorcall.py` (読み位置の返却: +4/−1 行)・`scripts/mx33_xmm03.py` (新規)・`mx6_e2e.sh` (step 4/7 と assert の追加)。
- `git diff d9a2b7ec2 HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` → **0 行** (コードの差分 0)。
  `tools/targets/massivex/dsp` 全体の差分は本 REPORT の追加 (docs commit `61e1aabbe`) のみで、測定対象外。
- MX-6 測定 commit (`fbc9971f`) からの変更 (`mx6_vectorcall.py` の +4/−1 行・`mx6_e2e.sh`) は、MX-6 の表示値を変えないことを e2e (§5) で確認した。
