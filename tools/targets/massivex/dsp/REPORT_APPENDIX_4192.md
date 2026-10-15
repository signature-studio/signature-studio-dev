# Massive X DSP REPORT 付録 (#4192 MX-47・§9.7〜9.8 の残件)

`REPORT_APPENDIX_3776.md` §9.7〜9.8 の残件 (`.text` 外の FH3 funclet 候補 211 件・U4f〜U4i) の確認結果。

## 1. 結論 (先出し)

1. **211 件は誤読と判定し、x64c の root には加えない** (受入 2 の (b))。候補の値は関数の入口ではなく、
   画像外 (208 件) または `.data` (3 件) の値で、FuncInfo の表を読んだ際の誤読。
2. **U4f の前提を訂正**: 棄却 355 件の内訳は上限 (maxState / nTry / nCatch) ではなく、大半 (339 件) が
   **FuncInfo の読取不能** (ポインタが画像外)。上限で棄却されたのは 9 件のみ。`REPORT_APPENDIX_3776.md` §9.2 の「上限で棄却」は誤り。
3. **U4g の前提を訂正**: E8/E9 の 4 件のうち、囲む関数が FH3 親なのは 1 件 (0x10c8b40) だけ。残り 3 件は FH3 親ではない。
4. **U4h**: 親の pdata 範囲 `[0x10c8b40, 0x10c8eff)` の中に EH 専用の call がある (`site_reached_by_flow_in_container` = False)。
5. **U4i**: 静的確認のみ。root の 90% (32,696 / 36,240) が `mov [rsp+disp8],rdx` で始まり、RDX 退避の形と整合する。
   実機の呼出し ABI は未確認 (native 実行を行っていない)。
   なお、root からの 211 件の除外の根拠は値の所在 (画像外・`.data`) だけで、同じ FH3 walk で得た `.text` 内 root 36,240 件の正しさは本付録では未検証 (§2.1 の限界と同じ)。

## 2. 測定 (再現: `MX_PE=<Massive X.vst3> MX39_WORK=<mx39 作業dir> bash tools/targets/massivex/dsp/mx43_e2e.sh`)

- 測定 commit = **a78696236** (`dsp/scripts/mx47_origin.py` と `mx43_e2e.sh` の 3 行を追加した commit)。
- 前提: `mx6_e2e.sh` (exit 0・37 s) → `mx39_e2e.sh` (exit 0・299 s、reach.json 作成)。素材 `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` → `parse_setup_headers.py` / `extract_massivex.py` で `Massive X.vst3` (95,356,824 B、md5 `622993e7…`、本付録と一致)。展開先は `$RUNNER_TEMP` (repo 外)。
- 実測 (a78696236): `mx43_e2e.sh` exit 0・**63 s**・load 0.01 0.14 0.32 → 0.67 0.31 0.37。
  - universe 36,533・flow 到達 82・未到達 36,451・`.text` 内の root **36,240**・`.text` 外 **211** (除外)。
  - lift: 関数 36,240・insns 1,764,126・`ott_unsup` を含まない関数 35,221・含む関数 1,019・unsup サイト **6,815**。
  - 注: §9.7 の unsup サイト 7,056 は本測定の 6,815 と一致しない (差の原因は未確認。lift の関数数・insns は一致)。

### 2.1 .text 外の 211 件の由来 (`scripts/mx47_origin.py`)

| 項目 | 件数 | 備考 |
|---|--:|---|
| 由来が unwind action | 193 | `disp_unwind` の欄 (`action` が 0 でない値) |
| 由来が catch handler | 18 | `disp_ha` の欄の `handler` |
| 値の出現 (handler 欄) | 230 | 最後の欄 145・途中の欄 85 (候補ごとの出現数。重複あり) |
| 値が画像外 | 208 | どの section にも入らない |
| 値が `.data` | 3 | 例: 0x515f150 (`.data` 内。何を指すかは未確認) |
| 値が 0x1000 未満 | 8 | 0x0 (null)・0x9・0x40・0x68・0x130・0x188・0x1e0・0x438 |

- 判定: 候補の値は `.text` の外にあり、画像外・`.data`・0x1000 未満の値である。FH3 の表の読みが値を取り違えたと見るのが妥当 (誤読)。
- 限界: 誤読の機構 (欄のずれ等) は推定で、未確認。個々の FuncInfo の正しい形 (`nCatch` 等) も未確認。0x0 を含む小さい値は、空の欄を読んだ結果と見られる。root から外した判断はこの範囲の証拠に基づく。

### 2.2 U4f: FH3 FuncInfo の棄却 355 件 (mx39 の数) の内訳

| 理由 | 件数 (pdata 行) | 件数 (FuncInfo 単位) |
|---|--:|--:|
| FuncInfo の読取不能 (ポインタが画像外) | 339 | 339 |
| magic が不正 | 6 | 6 |
| nCatch > 0x100 | 10 | 9 |
| maxState > 0x1000 | 0 | 0 |

- mx39 の「355 件」は pdata 行単位の数。FuncInfo 単位では 354 件 (`mx47_origin.py` の `fh3_funcinfo_rejected_total`)。
- 339 件はいずれも pdata の FH3 ハンドラ欄が指す FuncInfo が画像外で、上限ではなく pdata 解析の問題。この 339 件の中に本物の funclet があるかは未確認 (母数 36,533 は下界)。
- 未解決の扱い: 339 件の pdata 行の解析の確認は本 issue の範囲外 (PR 本文の未解決表)。

### 2.3 U4g: E8/E9 一致 4 件 (537 母数)

| site | 宛先 funclet | 宛先 flow 到達 | 囲む関数 | 囲む関数は FH3 親 | 囲む関数は funclet | site を囲む関数の flow で到達 |
|---|---|---|---|---|---|---|
| 0x10c8beb | 0x1190b30 | No | 0x10c8b40 | Yes | No | No |
| 0x1c9a51b | 0x118c780 | Yes | 0x1c99c51 | No | No | Yes |
| 0x1c9afeb | 0x118d1f0 | Yes | 0x1c99c51 | No | No | Yes |
| 0x10c6dab | 0x118ceb0 | No | 0x10c6cb0 | No | No | Yes |

- 前提の訂正: 「flow 到達 FH3 親 4 件が funclet を通常フローで指す」は 4 件中 1 件 (0x10c8beb) のみ成り立つ。
- 残り 3 件は、囲む関数が FH3 親でも funclet でもない。宛先 0x118c780・0x118d1f0 は flow で到達する。
- ICF / tail-merge による共有の判定は未実施。判定には funclet 本体の比較が要るため、本 issue の範囲外。

### 2.4 U4h: 囲む関数 0x10c8b40 の EH 専用 block の位置

- 囲む関数の pdata 範囲は `[0x10c8b40, 0x10c8eff)` (`.text` 内)。call (0x10c8beb) はこの範囲の中にある。
- site は囲む関数の入口から flow で到達しない (`site_reached_by_flow_in_container` = No)。よって EH 専用 block と見られる。
- 補足: 囲む関数は、範囲が重なる pdata 行が複数あるため、begin 一致で決めた。

### 2.5 U4i: MSVC funclet の呼出し ABI (静的確認のみ)

| 集合 | 件数 | `mov [rsp+disp8],rdx` で始まる | push / REX (0x55・0x53・0x40) で始まる | その他 |
|---|--:|--:|--:|--:|
| `.text` 内の root (flow 未到達) | 36,240 | 32,696 | 686 | 2,858 |
| flow 到達 | 82 | 65 | 未集計 | 17 |

- 区分の定義: 「mov」は先頭 4 バイトが `48 89 54 24`。「push / REX」は先頭 1 バイトが `0x55`・`0x53`・`0x40` (`mx47_origin.py` の `pro` 集計)。`0x40` (REX 接頭辞) は push ではないが、この集計では push 側に入っている。「その他」は上記のどちらでもない。
- flow 到達の列は `mx47_origin.py` が mov と other の 2 区分しか出さないため、push / REX は未集計。flow の「その他」17 には push / REX で始まる関数が含まれうる (内訳は未集計)。

- 大半が RDX を退避する形で始まる。RDX を使う形と矛盾はしないが、これだけでは establisher frame の受け渡しは確認できない。
- 静的な形の確認で、実行時の動作の確認ではない。native 実行の検証は本 run では行っていない (landing §9-2 と同じ未解決)。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FH3 pdata 行のうち 339 件の FuncInfo 読取不能 (画像外) の解析 | 母数 36,533 の下界。本物の funclet を取り落とす可能性 | PM 判断 (調査のみのため子 issue は起票しない) |
| U4g: 囲む関数が FH3 親でない 3 件の宛先 (2 件は flow 到達) の共有 | funclet と通常コードの境界 | PM 判断 (調査のみ) |
| U4i: MSVC funclet の呼出し ABI の実機確認 | §9.4 の前提 (SjLj 形) | [MX-46] (#4162) の起票先は未確定 (本 run では静的確認のみ) |
| 211 件の誤読の要因 (FH3 walk の欄ずれ) の特定 | 誤読の原因を確定できない。root からの除外は既に行った | PM 判断 |
