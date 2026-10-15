# Massive X MX-52 (#4989): 受入 2〜4 の感度測定 (U3d・U3e・U3g)

- 解析日: 2026-10-15 / 担当: `tools/targets/massivex/dsp/` (親 #3774 → #4989 は MX-37 の受入 2〜4)
- 素材: `plugins-massivex` (Inno installer `Native Instruments Massive X v1.7.1.exe`) → `scripts/parse_setup_headers.py <exe> <work>` → `scripts/extract_massivex.py <exe> <work> key`。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (REPORT_MX33 §0 と一致)。PE は `$RUNNER_TEMP` 配下 (repo 外)。
  展開ログの `md5-ok 0/125` は付随ファイルの checksum 不一致。検証対象の PE は一致。
- 基準 e2e: `origin/main` (`1c98a13a7`) で `mx6_e2e.sh` → **exit 0・elapsed 48 s・load 0.77 0.46 0.20 → 1.22 0.63 0.28** (本 PR 導入前の基準値)。

## 0. 結論 (先出し)

1. **U3d (merge 上位保持の must-def): 修正後の定義で感度 18 件 (seeds・one_round で同一集合)。** 内訳は P 17 関数・A 1 関数 (0xefe0)。
   - P 17 関数: 入口 xmm4/5 の読みが packed 演算 (`*ps`/`*pd`) と full-width store で、MX-33 §1 の規則では 128 bit の証拠 (P)。
   - A 1 関数 (0xefe0): 6 読みが `call` 境界 (3)・`roundsd` (3) で、幅の証拠にならない (A)。
   - **MX-6 の「xmm4/5 入口 livein 0」の陰性は、この 17 関数について覆る候補になった** (P の証拠あり)。ただし P の読みは 256 bit 形の上位 128 bit が多く、入口から流入するかは未検証 (§1 の注記)。確定はしない。
2. **U3e (call/jmp の引数転送): 未解決の候補が多い。** 呼出側 F が xmm4/5 を入口から読まず、direct call/jmp で G へ未定義のまま渡し、G の入口 livein に xmm4/5 が立つ F は **193 関数**。うち pdata 始点は **47 件**。既存の livein (F 自身の読みだけを見る) はこの形を落とす。G の livein が転送元の値を要求するかは未確認。**MX-6 の「入口 livein 0」の陰性は、この 47 件については過小検出の疑いがある。**
3. **U3g (非 vectorcall の既知 float 関数での scalar 落ち確認): 未実施。** 既知の非 vectorcall 関数の RVA を VST3 内で特定できなかった (import 名は 1 件のみ・内部呼出の対応付けが要る)。子 #5019 へ移す。

## 1. U3d の測定 (`scripts/mx4989_probe.py` の `livein_u3d`)

- 変種: 部分書込を must-def に入れない。
  - 部分書込: `movlps`/`movhps`/`movlpd`/`movhpd`/`movhlps`/`movlhps` は、メモリ元・レジスタ元・VEX 3 オペランドの全形。`movss`/`movsd` はレジスタ元のみ (`movss xmm0,[mem]` はゼロ拡張のため全幅の定義)。`addss` 等の scalar 演算・`cvtsi2*`・`cvtss2sd` 等の `ss`/`sd` 終端は 2 / 3 オペランド形とも。`ucomi*`/`comi*` は宛先に書かないので対象外。
  - 単体判定: `mx4989_probe.py --selftest` で 22 形を判定 (PE 不要)。**22/22 PASS**。
- 読みの分類: 部分書込の後に残る入口 xmm_k の読み (must-def で未定義のもの) を、`mx33_xmm03.classify_read` (MX-33 §1 の規則) で S / P / A に分類する。`merge` の上位素通し (`upper_flow_dst`) に当たる読みは `follow` で後続を追う。
  - 修正前の probe は、この分類を通さず一律に「merge 形でない読み (A)」とした。その結果、P に当たる 77 読みが A として数えられていた。`70b4b84db` で分類を揃えた。
- 結果 (修正後の定義・HEAD `70b4b84db`・`plugins-massivex` の PE):
  - pdata 始点 seeds 566 件・one_round 604 件のうち、xmm4/5 入口 livein が 0 → 1 になったのは **各 18 件** (同一集合)。
  - 18 件の一覧と読みの分類 (読み数 83: P 76・A 7。A の 7 は 0xefe0 の 6 と 0x1623f50 の複写 1)。
    - P 17 関数 (`0x6e3f80`・`0x6e6470`・`0x6e6b30`・`0x7cd680`・`0x7cdc00`・`0x7d38d0`・`0x7d3b10`・`0x7d3da0`・`0x14db930`・`0x14dc160`・`0x15d4620`・`0x15d7fa0`・`0x161b760`・`0x161e310`・`0x1620590`・`0x1621000`・`0x1623f50`): 読みは `vmulps`/`vaddps`/`vsubps`/`vdivps`/`vminps`/`vmaxps`/`vcmpltps` (packed 演算 74 件)・`vmovaps` の full-width store (2 件)・`vmovaps ymm0, ymm5` の複写 (A 1 件、同じ関数に P が併存)。
    - A 1 関数 `0xefe0` (xmm5 の読み 6 件、すべて `vcvtsi2sd` の入力): `call` 境界で追跡中の値が引数として渡りうる (3)・`roundsd` (3 オペランド scalar の上位保持、3)。
  - 注記 (P の範囲): P の読みの多くは `ymm` 形 (256 bit)。上位 128 bit (bits 128〜255) が入口から流入するかは未検証。VEX 形の scalar 書込は宛先の bits 128〜255 をゼロにするため、部分書込の後の上位読みは入口の値ではない可能性がある。P は MX-33 の規則上の 128 bit 証拠であり、ビット単位の流入はこの測定では確かめていない。
- 判定: 感度 18 件。証拠 P 17 関数 (ビット単位の流入は未検証)・A 1 関数 (0xefe0)。**MX-6 の xmm4/5 入口 livein 0 の陰性は、P 17 関数について覆る候補。** 確定は流入の検証 (後続作業) による。

## 2. U3e の測定 (`scripts/mx4989_probe.py` の `u3e`)

- 形: F の入口から k (k∈4,5) を読まず (F の livein 0)、F 内の direct `call`/`jmp` (`0x...` 形) の前で k が must-def に入っていない (未定義のまま渡る) 命令で、宛先 G の入口 livein に k が立つ。
- 結果: **193 関数 (うち pdata 始点 47)**。
  - 代表例: `0x11895c0 → 0x86d66c [4,5]`、`0x118c280 → 0xbdde60 [4]`、`0x6da260 → 0x8020e3 [4]`。
- 注意: G の入口 livein が F の転送元を要求するとは限らない。呼出前の定義が F 内の後続で行われるなど、切り分け (転送元の値の同一性) は未実施。**未確定の候補として扱う。**

## 3. U3g (非 vectorcall の scalar 落ち確認): 未実施

- 理由: VST3 の import・export から既知の非 vectorcall float 関数 (`sinf` 等) を CFG 上で同定する手順が未確立。確実な候補を得られなかった。
- 子 #5019 へ移す (§5)。

## 4. 検証と測定 commit

- 測定 commit (コードを変えた最後の commit) = **`70b4b84db`**。e2e と probe は HEAD `70b4b84db` で実測。
- e2e (`mx6_e2e.sh`・HEAD `70b4b84db`): exit 0・elapsed 56 s・load 0.27 0.53 0.36 → 0.78 0.63 0.40。全判定 PASS (funclets 533/529 PASS・負例 "one corrupted IP pointer" の FAIL は期待どおり)。
- probe 本体 (`mx4989_probe.py`・HEAD `70b4b84db`): exit 0・2 分 25 秒。`--selftest` 22/22 PASS。
- 測定 commit から HEAD までのコード差分: なし (`git diff 70b4b84db HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` は空)。以降に変えるのは本 REPORT のみ。
- 基準 (`1c98a13a7`) からの差分: `scripts/mx4989_probe.py` (新規)・`scripts/mx6_vectorcall.py` (`analyze()` の返り値に `must` を追加・既存の値は不変) ・main 取り込み分。`mx6_e2e.sh` は `mx4989_probe.py` を呼ばない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U3e: 193 件 (pdata 始点 47 件) の「未定義のまま転送」の候補が、G の入口 livein の転送元 (値の同一性) を要求するかの切り分け | MX-6 の xmm4/5 入口 livein 0 の陰性が過小検出の疑い (47 件) | #5019 |
| U3g: 非 vectorcall の既知 float 関数の scalar 落ち確認 | scalar 判定の感度の実地確認なし | #5019 |
| U3d: P 17 関数の 256 bit 読みの上位 128 bit が入口から流入するかの検証 (VEX scalar 書込によるゼロ化を考慮) | 18 件の入口 livein の確定可否。MX-6 の陰性の扱い | 本 PR で未確定として記録 (追加起票なし) |
| U3d: 0xefe0 (xmm5・A 6 読み: call 境界 3・roundsd 3) | 1 関数の判定は A のまま | 本 PR で A として記録 (追加起票なし) |
