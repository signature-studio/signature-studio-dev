# Massive X MX-33 (#3032) 受入 1: xmm0〜3 だけの入口 livein (MX-6 の保留 17 件) の判定

- 解析日: 2026-10-15 / 担当: `tools/targets/massivex/dsp/` (親 #1123 MX-6 の残件。受入 1 の残件と受入 2〜5 は子 issue に分離)
- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` (1,870,391,792 B) を既存パーサで展開
  (`scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> <work> key`)。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (検収値と一致)。PE の置き場所は `$RUNNER_TEMP` 配下。
- **測定 commit = `1083467fe`** (コードを変えた最後の commit・前版 = `d9a2b7ec2`)。再現: `MX_PE='$RUNNER_TEMP/mx33/work/extracted/VST3/Massive X.vst3' MX6_WORK='$RUNNER_TEMP/massivex-mx33' bash tools/targets/massivex/dsp/mx6_e2e.sh`。

## 0. 結論 (先出し)

1. **受入 1 の結論 (#3774 後): 17 件のうち確定は 1 件。** scalar **1** (0x17b680) / 128 bit 0 / 判定不能 **16**。
   前版 (#3032) は scalar 0 / 128 bit 0 / 判定不能 17。残 16 件の内訳は §2 末尾。
   17 件の入口読み 21 本はすべて「reg-reg 複写」(9 件) か「VEX 3 オペランドの上位保持 (merge)」(8 件) で、
   前版 (#3032) では scalar 読みも packed 証拠も 1 本もなかった。#3774 後は scalar 1 件 (0x17b680) だけが確定した (§1・§2)。
2. **merge 8 件は引数の根拠にならない。** `vcvtsi2sd xmm0, xmm0, rax` 型は xmm の下位 32/64 bit を読まずに上書きし、
   上位だけを素通しする。仕様文言どおり「`cvtsi2ss` 等は scalar 読み」とすると 8 件が scalar に落ちるが、これは誤分類なので採らない (§3 感度)。
3. **複写 9 件のうち 8 件は転送先の後続読みが未確定。** `movaps xmm6, xmm2` 等の転送先の後続を追い切れていないため判定不能のまま (0x17b680 のみ scalar に確定)。
   受入 1 の確定にはこの追跡が要る (未解決 U3h・§6)。
4. **独立再計算 (線形): 範囲内に 128 bit 読みを持つ関数は 9 件**。ただし CFG で入口から未定義と判定された読みに 128 bit 型はなく、
   線形の 128 bit 読みは定義後 (または CFG 非到達) の読み。CFG 側の 128 bit 候補は 0 件のため包含検査 `CFG-P ⊆ 線形-P` は空真。構造上の上限確認にとどまる (§4)。
5. **NC 17/17 PASS** (MX-33 の合成列 17 件・§3。前版 9 件 + #3774 で 6 件 + MX-64 で vzeroupper 2 件)。MX-6 の `mx6_vectorcall.py --selftest` 5/5 は別集合 (§3・§5)。e2e `mx6_e2e.sh` は exit 0 (48 s・測定 commit `1083467fe`)。funclet は REPORT_MX6.md §4 と一致 (step 7/7 で assert・positive control PASS)。
6. **MX-6 の表示値は不変**: pdata 始点の xmm4/5 livein 0・保留 17 (seeds)・census・funclet の値は MX-6 §1 と一致。

## 1. 判定定義 (実装: `scripts/mx33_xmm03.py`・読み列挙は `scripts/mx6_vectorcall.py` の `analyze`)

- **対象**: pdata 始点かつ seeds (入口面) の関数のうち、`xmm4/5` の入口 livein が 0 で `xmm0〜3` の入口 livein が 1 つ以上ある 17 件。
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
| 10 | 0x17b680–0x17b7ed | 79 | 2 | 0x18017b6a5 `movaps xmm6, xmm2` (複写先 xmm6 の後続は全て scalar・#3774) | 0 | **scalar** |
| 11 | 0x7d38d0–0x7d3b05 | 127 | 2 | 0x1807d3937 `vcvtsi2ss xmm0, xmm2, dword ptr [rax+0xc]` (A: merge) | 0,1,2,3 | 判定不能 |
| 12 | 0x7d3b10–0x7d3d95 | 149 | 2 | 0x1807d3bb6 `vcvtsi2ss xmm0, xmm2, dword ptr [rax+0xc]` (A: merge) | 0,1,2,3 | 判定不能 |
| 13 | 0x7dcb60–0x7dcca8 | 71 | 0, 1 | 0x1807dcbad `vcvtsi2sd xmm0, xmm0, r9d`・0x1807dcbb2 `vcvtsi2sd xmm1, xmm1, r10d` (A: merge) | 0,1,2,3 | 判定不能 |
| 14 | 0x7dce90–0x7dd031 | 79 | 0, 1 | 0x1807dcec4 `vcvtsi2sd xmm0, xmm0, rax`・0x1807dcf78 `vcvtsi2sd xmm1, xmm1, rax` (A: merge) | 0,1,2,3 | 判定不能 |
| 15 | 0x7dd960–0x7ddaa8 | 71 | 0, 1 | 0x1807dd9ad `vcvtsi2sd xmm0, xmm0, r9d`・0x1807dd9b2 `vcvtsi2sd xmm1, xmm1, r10d` (A: merge) | 0,1,2,3 | 判定不能 |
| 16 | 0x7ddc90–0x7dde31 | 79 | 0, 1 | 0x1807ddcc4 `vcvtsi2sd xmm0, xmm0, rax`・0x1807ddd78 `vcvtsi2sd xmm1, xmm1, rax` (A: merge) | 0,1,2,3 | 判定不能 |
| 17 | 0x118d8b0–0x118d994 | 49 | 0 | 0x18118d8cc `vcvtsi2sd xmm0, xmm0, rax` (A: merge) | – | 判定不能 |

- 内訳: **scalar 1 / 128 bit 0 / 判定不能 16** (#3774 後。前版 #3032 は 0 / 0 / 17)。読みの型: 複写 9 件 (1 読み each・全て k=2・うち 0x17b680 のみ scalar 確定)、merge 8 件 (計 12 読み)。
- 0x17b680 の根拠: 複写先 xmm6 の後続読みが全て scalar (`follow()` の結果)。PR 本文の「関数末で stack から復元」は未確認。`follow()` は `ret` で xmm0 のみを見るため、xmm6 の stack 復元はコードで確かめていない。
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
| 10 | `movaps xmm1, xmm0; addss xmm1, xmm2; ret` (追加・複写 → scalar 読み) | scalar | PASS |
| 11 | `movaps xmm1, xmm0; addps xmm1, xmm2; ret` (追加・複写 → 128 bit 読み) | 128 bit | PASS |
| 12 | `movaps xmm1, xmm0; movaps xmm1, [rsp+8]; ret` (追加・全幅上書きで追跡停止) | 判定不能 | PASS |
| 13 | `vcvtsi2ss xmm0, xmm0, eax; addps xmm0, xmm1; ret` (追加・merge の上位 → 128 bit) | 128 bit | PASS |
| 14 | `vcvtsi2ss xmm0, xmm0, eax; addss xmm0, xmm1; ret` (追加・merge の後続 scalar は証拠にしない) | 判定不能 | PASS |
| 15 | `vcvtsi2ss xmm0, xmm0, eax; movddup xmm0, xmm0; ret` (追加・merge 上位の shuffle は下位 64 bit のみ) | 判定不能 | PASS |

- **NC 17/17 PASS** (`--selftest` 17 cases)。MX-6 の `mx6_vectorcall.py --selftest` (5 件) も PASS のまま。
- **感度 (分類規則の影響・前版 #3032 の計算。#3774 後は未再計測)**:
  - 仕様文言どおり `cvtsi2*` の xmm 入力を scalar 読みにする: **scalar 8 / 128 bit 0 / 判定不能 9** (前版)。増えた 8 件は上表の merge 8 件そのもので、
    入力を消費しないため採らない (§1 (a))。
  - bitwise `*ps`/`*pd` を 128 bit 証拠に含める: **変化なし** (前版。17 件に bitwise 読みはない)。
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
| NC (MX-33・17 件) | 17/17 PASS (MX-64 後。#3774 後は 15/15・前版 9/9) |
| RTTI + 入口面 | REPORT_MX6.md §1 と一致 (測定 commit の step 2/7 の出力) |
| vectorcall (MX-6) | seeds: pdata 始点 livein xmm4/5 = 0 (REPORT_MX6.md §2 と一致) |
| 受入 1 (MX-33) | 17 件: scalar 1 / 128 bit 0 / 判定不能 16 (§2・#3774 後。前版 #3032 は 0 / 0 / 17) |
| .pdata census | REPORT_MX6.md §3 と一致 (測定 commit の step 5/7 の出力) |
| funclet (positive control) | REPORT_MX6.md §1・§4 と一致 (step 7/7 で assert) |
| 判定 | PASS (step 6/7・7/7)。step 6/7 の「包含 OK」は空真 (CFG 側の 128 bit 候補 0 件・§4) |

- e2e: `mx6_e2e.sh` (7 工程) → **exit 0・elapsed 48 s** (#3774 後・測定 commit `1083467fe`)。load average: 開始 `0.08 0.06 0.09` → 終了 `0.64 0.21 0.14`。前版 (#3032・`d9a2b7ec2`) は 35 s。
- 本 HEAD (`docs` commit) の再実行は未実施: この run では `plugins-massivex` が `$ARTIFACTS_DIR` に無く、`mx6_e2e.sh` は回せなかった。上記は測定 commit の記録。
- 追加した assert: step 6/7 は `vectorcall` の livein 0・整合 OK に加え、受入 1 の件数 17 と内訳合計 17、包含 OK を要求。
  step 7/7 は `pdata_eh.json` の `funclets_fh3.seeds` の funclet 数を `mx6_e2e.sh` 内の固定値と比べ、不一致なら exit 1。

## 6. 検証範囲・範囲外と未解決

**検証範囲**: VST3 の pdata 始点 seeds 17 件 (1-round 側の pdata 始点保留 17 件も同じ RVA 集合)・xmm0〜3 の入口 livein の幅分類・NC 15 件 (MX-33・§3)・線形の構造上限。
**範囲外**: 受入 2〜5 (FH4 funclet 全数・unwind 残件・funclet 到達・取り込み設計)、xmm4/5 の判定の変更、lift 出力 (RetDec/x64c) への影響。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U3h: reg-reg 複写 (`movaps xmm6, xmm2` 等) の転送先 xmm_j の後続読みを追い切れていない (0x17b680 のみ確定) | 受入 1 の判定不能 8 件 (複写型) | 子 **[MX-37]** |
| U3d: 既存 must-def は部分書込 (merge) を全幅の定義として扱う。merge 後の上位保持の利用を見ない。MX-6 の xmm4/5 陰性 (livein 0) も、merge 先頭の入力を見落とす過小検出側の影響を受けうる (未測定) | 判定不能 8 件 (merge 型)・MX-6 の陰性の強さ | 子 **[MX-37]** |
| U3e: call/jmp の引数転送 (xmm を読まずに渡す形) は `regs_access` に現れず、母集合 (livein 17) に入らない | 母集合の外側の関数は未判定 | 子 **[MX-37]** |
| U3f: 包含検査が空真 (CFG の 128 bit 候補 0 件)・線形側と分類器を共有 | §4 の独立性は弱い | 本 PR の限界として記載 (追加起票なし) |
| U3g: 既知の非 vectorcall float 関数での感度確認 (任意) | scalar 落ちの実地確認なし | 未実施 (子 **[MX-37]**) |
| U3b (MX-6 から): 間接 jmp テーブルの残り (過大近似の件数は REPORT_MX6.md §6 U3b) | 陰性の保守性は保つが精度は未確定 | 子 **[MX-37]** |
| U3c (MX-6 から): 1-round の解析不能の件数 (REPORT_MX6.md §6 U3c) の由来 | vectorcall 判定の対象外 | 子 **[MX-37]** |
| 受入 2 (MX-6 U4a・FH4 funclet 全数) | FH4 の landing pad が一覧に入らない | 子 issue **[MX-38]** |
| 受入 3 (MX-6 U4b・U4c・unwind 残件) | 1 本目 .pdata 全体の数値は下界・読取不能の件数と原因は未確定 (REPORT_MX6.md §3) | 子 issue **[MX-38]** |
| 受入 4・5 (MX-6 U4d・U4e・funclet 到達と取り込み設計) | #228 同型の確定 (深い closure での到達) と x64c への取り込み | 子 issue **[MX-39]** |

- 起票先: **#3774 ([MX-37])** = 受入 1 の残件 (U3 系: 複写先の追跡・merge 扱い・引数転送・感度・間接 jmp・解析不能の件数 (U3c))。#3774 は本 PR で Closes せず、残件表 (下記) を #3774 の本文に追記した。
  **[MX-38]** = 受入 2・3 (FH4 funclet・unwind 残件)、**[MX-39]** = 受入 4・5 (funclet 到達・取り込み設計)。これらの子 issue 番号は本 REPORT では未確認 (起票番号の確認は PR 本文に記載)。

### 6.1 受入 1 の判定不能 16 件の残件 (#3774)

§2 の表 (行) から数えた内訳。

| 残件の型 | 件数 | 対象の行 | 扱い |
|---|--:|---|---|
| 複写 (`movaps` / `vmovaps` の転送先の後続が未確定) | 8 | 行 1・3〜9 | #3774 の残件 |
| merge (`vcvtsi2ss` / `vcvtsi2sd` の上位の後続が未確定) | 8 | 行 2・11〜17 | #3774 の残件 |

理由ごと (PE 再実行 `mx33_xmm03.py` の `reads` の理由文字列による実測・本 PR で記録):

| 型 | 理由 | 件数 | RVA |
|---|---|--:|---|
| 複写 | call 境界で追跡中の値が引数として渡りうる (間接 `call qword ptr [...]` を含む) | 6 | 0xccc0・0x105e0・0x1108c0・0x110960・0x1109b0・0x110a30 |
| 複写 | ret で xmm0 戻り値として渡る | 1 | 0x17b4e0 |
| 複写 | 3 オペランド `vcvtsd2ss` の下位 64 bit 読みを曖昧 (A) と扱う (規則の当てはめ要確認) | 1 | 0x11830 |
| merge | `vzeroupper` (上位の消去のみ) の後、ret で xmm0 戻り値として渡る (旧規則は全幅書込と誤判定・本 PR で修正) | 2 | 0x7d38d0・0x7d3b10 |
| merge | 上位の読みが `movddup` (下位 64 bit のみ読む shuffle・証拠にしない) | 2 | 0x7dce90・0x7ddc90 |
| merge | CFG 後続に幅の証拠なし | 2 | 0x7dcb60・0x7dd960 |
| merge | ret で xmm0 戻り値として渡る | 1 | 0x118d8b0 |
| merge | call 境界 (引数として渡りうる) | 1 | 0xef60 |

- 残件の未解決: 間接 call 先の引数幅 (解析外)・`vcvtsd2ss` 規則 (0x11830)・`movddup` 後の上位追跡 (0x7dce90 等)・ret の xmm0 戻り値の呼出側の幅 (0x7d38d0・0x7d3b10・0x17b4e0・0x118d8b0)。いずれも本 issue 範囲の追加実装が要る (呼出側の解析)。
- `follow()` の A 理由は分類結果を変えない。`classify_fn` は merge の A 理由を記録するように変えた (件数 scalar 1 / 128 bit 0 / 判定不能 16 は不変)。

- 受入 2〜4 (U3d・U3e・U3g) の感度測定 (#4989): 付録 `REPORT_APPENDIX_4989.md` (結論は同付録 §0)。

## 7. 既知類型との関係

- `docs/DEFECTS.md` の D1a〜D23 (lift の silent miscompile 類型) と `tools/icall/REPORT.md` §4 の D1〜D13 (ICALL 系) は別体系で、本件は解析モデルの問題 (merge と複写の扱い)。
  どちらにも行を足さない。
- 受入 2〜4 の landing pad 非到達は、`tools/icall/REPORT.md` §4 **D12** (Delphi landing pad 非到達) と同型 (MX-6 §4 と同じ)。MSVC 固有の差は子 issue で扱う。

## 9. 既知の非 vectorcall float 関数 (MX-55 #5030)

- 同定 (`0x18017b680`・scalar 読み・入口 xmm2)、scalar 落ちなし。呼出元 1 件 (`0x18017b4af`・xmm2 に float を載せて vtable slot 32 を呼ぶ) を確認。
- 非 vectorcall の確定は未了 (`rbx` の vtable 型)。詳細・実測は [REPORT_APPENDIX_5030.md](REPORT_APPENDIX_5030.md)。

## 8. 測定 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit = **`4840cc082`** (`feat(massivex): find vtable caller of 0x17b680 and check xmm2 arg (MX-55 #5030)`)。コードを変えた最後の commit (HEAD と同じ)。
  - 本 run の測定: `mx6_e2e.sh` exit 0・elapsed 59 s・load 0.50 0.56 0.27 → 0.82 0.64 0.31・PASS 32 件。`mx55_callers.py` exit 0 (§9 の呼出元の値)。
  - 前回 (実装 run・commit `d9edb0ad9`): 同じ `mx6_e2e.sh` で exit 0・elapsed 58 s。
  変更: `scripts/mx55_nonvec_float.py` (新規)・本 REPORT §9。前回の測定 commit = `d106f3c23` (MX-37 #3774)。
- 測定 (MX-55 実装 run・`mx6_e2e.sh`・MX_PE = 展開 `Massive X.vst3`・md5 `622993e7…` 一致): **exit 0・elapsed 58 s・load 0.24 0.41 0.22 → 0.70 0.51 0.27**。
  mx55 の候補は **14 行 = 一意 13 関数** (§9)。`mx6_e2e.sh` は `mx55` を呼ばないため、mx55 の件数は同じ素材での個別実行の値。
- **再現の状況**: 本 fix run (review 差し戻し対応) では `plugins-massivex` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、
  `Massive X.vst3` を展開できないため、上の e2e と mx55 は再実行していない。上の値は実装 run の記録。
  再測定は素材 `plugins-massivex` を付けて再起動した run で行う。
- 測定 commit から HEAD までのコード差分: `git diff d9edb0ad9 HEAD -- tools/targets/massivex/dsp/scripts` は `mx55_nonvec_float.py` の docstring の 1 行のみ (説明文の修正・判定ロジックは変えない)。
  `mx6_e2e.sh` は差分 0。
- 上の差分は docstring のみのため、測定値は測定 commit のコードに対するものとして扱う。
- MX-6 測定 commit (`fbc9971f`) からの変更 (`mx6_vectorcall.py` の +4/−1 行・`mx6_e2e.sh`) は、MX-6 の表示値を変えないことを e2e (§5) で確認した。

## 7. MX-54 (#5019): U3e (引数転送の xmm4/5) と U3g (非 vectorcall float の感度)

- 実装: `scripts/mx54_u3e.py` (`mx6_vectorcall` の `analyze`・`effects` を再利用)。入力は `mx6_e2e.sh` が生成する `surface_seeds_x64c.json`。`mx6_e2e.sh` は `mx54_u3e.py` を呼ばないため、§7.3 の e2e は本節の測定を含まない。
- 測定 commit = **`ee794bcc31952f75f41fe3ef9c32ed33e4a49268`** (`feat(massivex): MX-54 U3e probe ...`。コードを変えた最後の commit)。測定 commit から HEAD までのコード差分 `git diff ee794bcc3 HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は 0 行 (HEAD の差分は本 REPORT の docs 修正のみ)。
- 素材: `plugins-massivex` の `Massive X.vst3` (md5 `622993e76565f49c094063a2b717d6ca`)。

### 7.1 U3e: F が xmm4/5 を読まず direct call/jmp で G へ渡す形

- 母集団: seeds の pdata 始点 566 件 (`mx6_vectorcall` の rows と同じ)。F ごとに、F 内の direct call/jmp (即値) の site を数える。
- 判定 (script の実装どおり): site の直前で、いずれの経路でも xmm4/5 が F 内で定義されていない (may-def = 0) かつ、いずれの経路にも call が無い (call は xmm0〜5 を clobber しうるため、入口値との同一性を示せない) とき、G (転送先) の入口 livein xmm4/5 が 1 以上なら候補。転送前の全経路で xmm4/5 の定義がなく、かつ前段に call が無いことが、転送元の値が F の入口値と同一であることの根拠。

| 項目 | 件数 |
|---|--:|
| 解析した F (pdata 始点 seeds) | 566 |
| 直接 call/jmp (即値) を持つ F | 480 |
| 到達可能な direct site | 2,657 |
| うち転送前に F 内で xmm4/5 定義済み (いずれかの経路) | 821 |
| うち前段に call を含むため除外 (定義なし) | 1,453 |
| うち転送前に xmm4/5 未定義・前段に call なし | 383 |
| &emsp;うち G の入口 livein xmm4/5 ≠ 0 (候補) | **42 site / 42 F** |
| &emsp;うち G の入口 livein xmm4/5 = 0 | 315 |
| &emsp;うち G 解析不能 (画像外など) | 26 |
| G が pdata 始点 | 0 |

- 段の合計: 2,657 = 821 + 1,453 + 383 (到達可能 = 定義済み + call 除外 + 未定義)。383 = 42 + 315 + 26 (未定義の内訳)。
- 件数の差 (appendix の 47 との差): `REPORT_APPENDIX_4989.md` と `mx4989_probe.py` は main に無く、`origin/4989-massivex-xmm-merge-call` (commit `2fc5debe2`・`3146df45d`・`601a3ecc7`・`c0209641a`) にある。appendix の 47 (pdata 始点)・193 (全 F) は probe の `u3e` の値。`70b4b84db` の `mx4989_probe.py` (`plugins-massivex` の PE) で 193 (pdata 始点 47) を再現した。抽出方法の違い (コードの読みによる):
  1. 母集団: probe は seeds と one_round の行を対象にし、本 script は seeds の pdata 始点 566 のみ。
  2. F の入口 livein: probe は F の `livein45` = 0 で絞る。本 script は絞らない (注 a)。
  3. call 前段: probe は除外しない。本 script は除外する。
  4. 判定: probe は must-def に入らない site を F ごとに最初の 1 件で打ち切る。本 script は may-def = 0 の site を全件数える。
  向き: 1・3 は本 script の件数を小さくし、2・4 は大きくする。差し引きで 42 と 47 の大小が決まるため、切り分けは PE が要り未実施。
- 注 (未確認):
  - (a) 本 script は F の入口 livein = 0 のフィルタを掛けていない。`for F` ループに判定が無く、docstring の「入口 livein xmm4/5 = 0 の母集団」は実装と一致しない。よって 42 は F が入口で xmm4/5 を読む関数を含みうる。フィルタ付きの件数は未測定。
  - (b) 「42 件の G は全て pdata 範囲内」は script で判定していない (未確認)。G が pdata 始点でないことのみ `G_pdata_begin` で数えた (0)。
  - (c) G は線形・CFG 解析で入口 livein が立つと判定されたもので、G が実際の関数入口かは未確認 (例: `0x8020e3` は `or eax, ...` で始まる)。
  - (d) F→G の site 3 件 (`0xfb13`・`0x6ba2ba`・`0x6da2ae`) の E8/E9 と rel32 の照合は前 run の記録で、本 run では再確認していない。

### 7.2 U3g: 既知の非 vectorcall float 関数での scalar 落ち

- 本 PR の時点 (MX-54) では同定できず未実施。後続の MX-55 (#5030) で同定し、scalar 落ちなしを確認した (§9 → [REPORT_APPENDIX_5030.md](REPORT_APPENDIX_5030.md))。

### 7.3 e2e と再現 (前 run の記録。本 run では再実行していない)

- e2e `tools/targets/massivex/dsp/mx6_e2e.sh` (MX_PE = 展開 `Massive X.vst3`・md5 `622993e7…` 一致): **exit 0・elapsed 57 s・load 0.79 0.36 0.14 → 0.92 0.47 0.19** (測定 commit `ee794bcc3`)。出典は PR 本文の前 run の記録で、本 run は `plugins-massivex` が `$ARTIFACTS_DIR` に無く再実行できなかった。e2e は `mx54_u3e.py` を実行しない。
- `mx54_u3e.py` 単体の実行時間は 5.7 s (前 run の記録。e2e の 57 s とは別)。
- 再現: `python3 scripts/mx54_u3e.py "<Massive X.vst3>" <surface_seeds_x64c.json> <out.json>`。素材の展開: `plugins-massivex` (素材名の正本は `docs/WORKFLOW.md` §11) を `tar --zstd -xf` で展開 → `parse_setup_headers.py` → `extract_massivex.py <exe> <work> key`。
