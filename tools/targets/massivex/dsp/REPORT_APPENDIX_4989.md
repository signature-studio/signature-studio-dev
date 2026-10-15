# Massive X MX-52 (#4989): 受入 2〜4 の感度測定 (U3d・U3e・U3g)

- 解析日: 2026-10-15 / 担当: `tools/targets/massivex/dsp/` (親 #3774 → #4989 は MX-37 の受入 2〜4)
- 素材: `plugins-massivex` (Inno installer `Native Instruments Massive X v1.7.1.exe`) → `scripts/parse_setup_headers.py` → `scripts/extract_massivex.py <exe> <work> key`。
  `Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca` (REPORT_MX33 §0 と一致)。PE の置き場所は `$RUNNER_TEMP` 配下。
- 基準 e2e: `origin/main` (`1c98a13a7`) で `mx6_e2e.sh` → **exit 0・elapsed 48 s・load 0.77 0.46 0.20 → 1.22 0.63 0.28**。
  全判定 PASS (NC 5/5・MX-33 NC 15/15・受入 1 の内訳 scalar 1 / 128 bit 0 / 判定不能 16・funclet 533/529・MX-41 整合)。

## 0. 結論 (先出し)

1. **U3d (merge 上位保持の must-def): 修正前の定義では感度は 1 件 (0xefe0) のみ、後続の証拠は 0 件。** 部分書込の定義に取りこぼしがあった (メモリ元の `movlps` 等・VEX 3 オペランド形・legacy SSE の `addss` 等が部分書込に入らず、全幅の定義として扱われていた)。定義は修正済み (§1・selftest 22 件 PASS)。ただし修正後の probe 再実行は未実施 (本 run に `plugins-massivex` が無い)。以下の件数は修正前の値で、再実行まで暫定。0xefe0 の xmm5 の読みはすべて merge の上位で、後続は `call` 境界か `roundsd` で止まる (A)。新規 1 件 (0xefe0) は証拠 A のため入口 livein とは確定しない。MX-6 の xmm4/5 入口 livein 0 の陰性は、この 1 件と修正後の再実行の結果を待つ。
2. **U3e (call/jmp の引数転送): 未解決の候補が多い。** 呼出側 F が xmm4/5 を入口から読まず、direct call/jmp で G へ未定義のまま渡し、G の入口 livein に xmm4/5 が立つ F は **193 関数**。うち pdata 始点は **47 件** (seeds 側 46 件・one_round 47 件)。
   既存の livein (`must-def` で F 自身の読みだけを見る) はこの形を落とす。ただし G の livein が転送元の値を要求するかは未確認 (呼出後に G の入口面を定義し直す等の可能性が残る)。**MX-6 の「入口 livein 0」の陰性は、この 47 件については過小検出の疑いがある**。
3. **U3g (非 vectorcall の既知 float 関数での scalar 落ち確認): 未実施。** 既知の非 vectorcall 関数の RVA を VST3 内で特定できなかった (MSVC の `__std_smf_hypot3f` 等の import 名は 1 件のみ・内部呼出の対応付けが要る)。時間内に実施できなかったため、子 issue へ移す。

## 1. U3d の測定 (`scripts/mx4989_probe.py` の `livein_u3d`)

- 変種: 部分書込 (下記) を must-def に入れない。
  - 部分書込 (修正後): `movlps`/`movhps`/`movlpd`/`movhpd`/`movhlps`/`movlhps` は、メモリ元・レジスタ元・VEX 3 オペランドの全形。`movss`/`movsd` はレジスタ元のみ (`movss xmm0,[mem]` はゼロ拡張のため全幅の定義)。`addss` 等の scalar 演算・`cvtsi2*`・`cvtss2sd` 等の `ss`/`sd` 終端は 2 / 3 オペランド形とも。`ucomi*`/`comi*` は宛先に書かないので対象外。
  - 修正前の取りこぼし: メモリ元の `movlps` 等・VEX 3 オペランドの `movlps`/`movhps`・legacy SSE の `addss` 等の 2 オペランド形は部分書込に入らず、全幅の定義として扱われていた (レビュー指摘 blocking 1)。
  - 単体判定: `mx4989_probe.py --selftest` で上記 22 形を判定 (PE 不要)。修正後 **22/22 PASS**。
- 修正後の probe 本体の再実行は **未実施** (本 run に `plugins-massivex` が無く、`MX_PE` の PE が無い)。以下の件数は修正前の定義による値で、再実行まで暫定。
- 結果 (修正前の定義): pdata 始点 seeds 566 件・one_round 604 件のうち、xmm4/5 入口 livein が 0 → 1 に変わったのは **0xefe0 の 1 件**。
- 0xefe0 の xmm5 読み 6 件 (`vcvtsi2sd xmm0,xmm5,rdx` 等) の後続を `mx33_xmm03.follow(merge=True)` で追跡:
  - `call` 境界で追跡中の値が引数として渡りうる: 3 件 (A)
  - `roundsd` (3 オペランド scalar の上位保持): 3 件 (A)
  - P (128 bit 証拠): 0 件。
- 判定: 感度は 1 件で、証拠はどれも A。**0xefe0 を 128 bit / xmm5 の入口 livein とは確定しない。**

## 2. U3e の測定 (`scripts/mx4989_probe.py` の `u3e`)

- 形: F の入口から k (k∈4,5) を読まず (F の livein 0)、F 内の direct `call`/`jmp` (`0x...` 形) の前で k が must-def に入っていない (未定義のまま渡る) 命令で、宛先 G の入口 livein に k が立つ。
- 結果: **193 関数 (うち pdata 始点 47)**。
  - pdata 始点 47 件のうち seeds 側 46、one_round 側 47。
  - 代表例: `0x11895c0 → 0x86d66c [4,5]`、`0x118c280 → 0xbdde60 [4]`、`0x6da260 → 0x8020e3 [4]`。
- 注意: G の入口 livein が F の転送元を要求するとは限らない。呼出前の定義が F 内の後続で行われるなど、切り分け (転送元の値の同一性) は未実施。**未確定の候補として扱う。**

## 3. U3g (非 vectorcall の scalar 落ち確認): 未実施

- 理由: VST3 の import・export から既知の非 vectorcall float 関数 (`sinf` 等) を CFG 上で同定する手順が未確立。時間内 (run の残り約 40 分) に確実な候補を得られなかった。
- 子 issue へ移す (§5)。

## 4. 検証と測定 commit

- 基準 (測定 commit) = **`1c98a13a7`** (origin/main・基準 e2e の HEAD)。本 PR のコード変更は `scripts/mx4989_probe.py` (新規) と `scripts/mx6_vectorcall.py` (`analyze()` の返り値に `must` を追加・既存の値は不変)。
- 基準 e2e の測定 commit = `1c98a13a7` (origin/main)。本 PR の変更は `scripts/mx4989_probe.py` (新規) と `scripts/mx6_vectorcall.py` (`analyze()` の返り値に `must` を追加・既存の値は不変)。`mx6_e2e.sh` は `mx4989_probe.py` を呼ばないため、e2e の測定値は本 PR の変更の影響を受けない。
- e2e の測定値 (本 PR の正本・1 組のみ): commit `3146df45d` の `mx6_e2e.sh` = **exit 0・elapsed 49 s・load 0.19 0.59 0.50 → 0.65 0.65 0.53・判定 28 行のうち PASS 27・負例の FAIL 1 行 (期待どおり)**。`601a3ecc7` は docs のみの差分で、コードは同一。
- 測定 commit `3146df45d` から本修正 commit (HEAD) までのコード差分: `git diff 3146df45d HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx6_e2e.sh` (修正は `mx4989_probe.py` の `partial_dst`・`must_partial_off` の引数・`--selftest` の追加)。
- `mx4989_probe.py` の実行時間 (約 2 分 27 秒・修正前の定義) は HEAD `3146df45d` での実測。修正後の本体は未測定 (PE 不在)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U3e: 193 件 (pdata 始点 47 件) の「未定義のまま転送」の候補が、G の入口 livein の転送元 (値の同一性) を要求するかの切り分け | MX-6 の xmm4/5 入口 livein 0 の陰性が過小検出の疑い (47 件) | #5019 |
| U3g: 非 vectorcall の既知 float 関数の scalar 落ち確認 | scalar 判定の感度の実地確認なし | #5019 |
| U3d: 修正後の probe 本体の再実行 (`plugins-massivex` が必要) | §0・§1 の件数は修正前の定義による暫定値 | 本 PR の次の修正で再実行 (PE 取得後)。起票なし |
| U3d: 0xefe0 の xmm5 (A の 6 読み) の後続 (call 境界・roundsd) | 1 件の判定は未確定 | 本 PR で A として記録 (追加起票なし) |
