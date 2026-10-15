# Massive X DSP REPORT 付録 (#3776 MX-39・§9 分割移動)

本体 `REPORT_MX6.md` の 250 行上限のため、§9 (MX-39 #3776: funclet の深い closure 到達・E8/E9 候補の由来・取り込み方式 U4d・U4e) を分割移動した (節番号 §9 は維持)。

## 9. MX-39 (#3776): funclet の深い closure 到達・E8/E9 候補の由来・取り込み方式 (U4d・U4e)

- 測定 commit = **bb4ce18b2** (`dsp/mx39_e2e.sh` と `dsp/scripts/mx39_funclet_reach.py` を追加した commit)。再現: `MX_PE=<Massive X.vst3> MX6_WORK=<mx6 作業dir> bash tools/targets/massivex/dsp/mx39_e2e.sh` (前提: `mx6_e2e.sh` で RTTI json を作成済み)。
- 素材: `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` → `parse_setup_headers.py` / `extract_massivex.py` で `Massive X.vst3` (95,356,824 B、md5 `622993e7…`、§0 と一致)。展開先は repo 外 `$RUNNER_TEMP`。
- 実測 (e2e, bb4ce18b2): **所要 422 s**、load 1.00 0.94 0.83 (終了時)、exit 0。closure 2 本 (linear・flow) の固定点計算が大半 (flow 約 6.5 分)。

### 9.1 結論 (先出し)

1. **U4d(1) 由来**: `.text` の E8/E9 一致 (全 FH3 funclet 36,533 件が対象) は 213 件。命令境界で見ると **179 件は call/jmp rel32 (長さ 5、宛先一致)**、**34 件は別命令の途中** (境界判定で除外)。537 母数 (REPORT §4) に当たる **4 件は全て命令境界の call/jmp**。4 件の囲む関数 (pdata begin) は linear・flow いずれの closure にも入らず、由来は「closure 非到達の関数の中の直接辺」。
2. **U4d(2) 深い closure**: 2 round 以上で funclet は到達する (ただし少数)。537 母数では **2 件 (0x118c780・0x118d1f0) のみ**で、どちらも深さ 3 (元の入口は深さ 2)。残り 535 件は固定点でも到達しない。全 FH3 funclet 36,533 件では固定点で linear 119 件・flow 82 件のみ到達 (表 9.2)。
3. **U4e 取り込み**: §9.4 に方式を記録 (x64c の追加 root + #228 と同じ SjLj 形の呼出し)。実装は子 issue **[MX-43] (#3838)**。

### 9.2 closure の深さ別の到達 (測定 commit bb4ce18b2)

| 集合 | round 0 | round 1 | round 2 | round 3 | 固定点 |
|---|--:|--:|--:|--:|--:|
| linear 入口数 | 567 | 3,227 | 12,973 | 59,522 | 472,313 (round 17) |
| flow 入口数 | 567 | 2,456 | 6,748 | 18,533 | 507,258 (round 34) |
| funclet 到達 (linear・36,533 中) | 0 | 1 | 9 | 44 | 119 |
| funclet 到達 (flow・36,533 中) | 0 | 1 | 5 | 9 | 82 |
| 537 母数の到達 (linear = flow) | 0 | 0 | 0 | 2 | 2 |

- 母数: funclet を持つ FH3 関数 13,525 / funclet 36,533 (`mx39_funclet_reach.py`)。537 母数 = round 1 の FH3 親の funclet (REPORT §4 と一致)。
- 上限・下限: linear は全域を decode する過大近似 (固定点の入口が pdata 関数数 186,960 を超える)。flow は制御フローで到達する命令だけの下限 (間接 jmp は未解決 `indirect_unres` を含む)。
- 棄却: FH3 FuncInfo 355 件は上限 (maxState > 0x1000 / nTry > 0x1000 / nCatch > 0x100) で棄却。537 母数は棄却の影響なし (537 を再現)。棄却の値の妥当性は未確認 (U4f)。

### 9.3 E8/E9 一致 4 件 (537 母数) の由来

| site (RVA) | 命令 | 宛先 funclet (親) | 囲む関数 | 囲む関数の closure 深さ | 宛先の到達 |
|---|---|---|---|---|---|
| 0x10c8beb | call | 0x1190b30 (0x1190ad0) | 0x10c8b40 (FH3 親) | なし (入口から flow で未到達 = EH 専用の block と見られる) | 未到達 |
| 0x1c9a51b | call | 0x118c780 (0x118c3c0) | 0x1c99c51 (非 FH3・非 funclet) | なし | 深さ 3 |
| 0x1c9afeb | call | 0x118d1f0 (0x118cee0) | 0x1c99c51 | なし | 深さ 3 |
| 0x10c6dab | jmp | 0x118ceb0 (0x118c940) | 0x10c6cb0 | なし | 未到達 |

- 4 件とも囲む関数は closure に入らず、宛先 2 件 (0x118c780・0x118d1f0) は別の直接辺 (深さ 2 の入口 0x1c9a1cd・0x1c9aa25 から) で深さ 3 に到達する。
- 境界の判定は linear 逆アセンブル (囲む関数の pdata begin から) と flow 到達 (begin から制御フロー) の両方で行った。

### 9.4 U4e: MSVC funclet の取り込み方式 (記録・実装は [MX-43])

- **方式**: #228 の landing pad 方式 (`tools/icall/landing/REPORT.md` §6・§8) を MSVC に当てる。Delphi と異なり MSVC の funclet は親範囲の外の独立 .pdata entry で、FH3 FuncInfo (`mx6_pdata_eh.funclets_fh3`) から RVA を取る。
  1. **x64c の追加 root**: FH3 funclet を追加入口として lift する (親の CFG に scope を取り込む処理 (landing §8-2①) は不要)。対象は固定点で flow 未到達の funclet (36,451 件)。
  2. **呼出し**: pad は関数として呼ぶ SjLj 形 (`@__lp_icall` / `@__lp_resume` 相当)。例外 runtime は FH3 FuncInfo の walk を移植する。
  3. **既到達の funclet** (flow 82 件) は通常 lift で足りるので pad 経路を重ねない (二重 lift を避ける)。
- **根拠**: MSVC funclet は FuncInfo (unwind action と catch handler) からしか到達しない (537 母数は直接辺 0 件、round 1 で 0 件)。SjLj 形は landing §6 の推奨と同じ。
- **未確認 (前提)**: MSVC funclet の呼出し ABI (unwinder が RDX に establisher frame を渡す形) は実機で未確認。landing §9-2 (OTT funclet の実行検証) と同じ未解決。
- **検証の要件 (子 issue)**: funclet 1 本以上の native vs wasm 通し一致 (landing §7 型)、既到達の 82 件と root 追加分の lift 件数を分けて報告。

### 9.5 未解決 (起票先)

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U4f | FH3 FuncInfo 355 件の上限棄却 (maxState・nTry・nCatch) の妥当性 | 母数 36,533 の下界 | [MX-47] (#4192) |
| U4g | flow 到達 funclet の直接辺の元 82 件のうち 4 件 (FH3 親の関数) が funclet を通常フローで指す (ICF / tail-merge による共有か) | funclet と通常コードの境界 | [MX-47] (#4192) |
| U4h | 囲む関数 0x10c8b40 の EH 専用 block の位置 (親の pdata 範囲内か) | 親 pdata 範囲の定義 | [MX-47] (#4192) |
| U4i | MSVC funclet の呼出し ABI の実機確認 | §9.4 の前提 | [MX-47] (#4192) |

### 9.6 検証 (docs/WORKFLOW.md §6)

- 測定 commit = **3eefb3bab** (main 取り込みの merge。コードを変えた最後の commit)。§9.1〜9.3 の数値は bb4ce18b2 (main 取り込み前) の測定で、3eefb3bab で同じ値を再現した (下の実測)。
- コード差分 (`git diff --stat 3eefb3bab HEAD -- tools/targets/massivex/dsp/scripts tools/targets/massivex/dsp/mx39_e2e.sh tools/targets/massivex/dsp/mx6_e2e.sh`): **0 行** (本 PR の後続 commit は docs のみ)。
- 参考: bb4ce18b2 からの差分 (`git diff --stat bb4ce18b2 3eefb3bab -- 同範囲`): 6 files, 697 insertions(+), 28 deletions(-)。内訳は main 側の MX-33・MX-6 FH4 の変更 (`mx6_e2e.sh`・`mx33_xmm03.py`・`mx6_fh4.py`・`mx6_vectorcall.py`・`mx_closure.py`・`mx_flow_recheck.py`)。`mx39_e2e.sh` と `mx39_funclet_reach.py` は bb4ce18b2 から 0 行。
- 実測 (3eefb3bab・素材: `plugins-massivex` → `Native Instruments Massive X v1.7.1.exe` → `parse_setup_headers.py` / `extract_massivex.py` で `Massive X.vst3` = 95,356,824 B / md5 `622993e7…`):
  - `mx6_e2e.sh`: exit 0・**42.3 s**・8 step すべて完了 (log の PASS 行: step 4 受入1 PASS・step 6 判定 PASS・step 7 positive control 533 / 529 PASS・step 8 FH4 NC 3/3 PASS)。load 0.52 0.33 0.14 → 0.75 0.41 0.18。
  - `mx39_e2e.sh`: exit 0・**389 s**・load 0.69 0.40 0.18 → 1.03 0.91 0.50。FH3 funclet 母数 36,533 (棄却 355)・537 母数 = 537・linear 到達 119 (深さ≤2: 9、≤3: 44)・flow 到達 82 (深さ≤2: 5、≤3: 9)・E8/E9 一致 213 件 (命令境界 179)・537 母数への一致 4 件 (命令境界 4 件)。bb4ce18b2 の §9.1〜9.3 の値と一致。
- 境界判定による除外: E8/E9 一致 213 件のうち、命令境界でない 34 件 (別命令の途中) を除いた。これは負例ではない。負例の合成バイト列は §5 の 5/5 PASS。

### 9.7 MX-43 (#3838) 受入 1: 追加 root の lift 件数

- 測定 commit = **6f676dbb4** (コードを変えた最後の commit = `dsp/scripts/mx43_funclet_roots.py` の整数 VA 修正 + `dsp/mx43_e2e.sh`)。再現: `MX_PE=<Massive X.vst3> MX39_WORK=<mx39 作業dir> bash tools/targets/massivex/dsp/mx43_e2e.sh` (前提: `mx39_e2e.sh` 実行済み)。
- 母数: FH3 funclet universe 36,533 − flow 到達 82 = **36,451**。うち `.text` の外を指す **211 件を除外** (RVA 0〜0x188 のヘッダ部 8 件・`.text` より上 203 件。FH3 walk の誤読と見て lift 対象から外した。原因は未確認 → 下の表)。**root = 36,240**。
- 実測 (6f676dbb4・素材 `plugins-massivex` 展開 md5 `622993e7…`):
  - `mx39_e2e.sh` (前提・従来値): exit 0・**240 s**・FH3 universe 36,533・棄却 355・linear 到達 119・flow 到達 82・537 母数一致 4。
  - `mx43_e2e.sh`: exit 0・**46 s**・lift 関数 36,240 (blocks 36,240)・insns 1,764,126・`ott_unsup` を含まない関数 **35,221**・含む関数 **1,019** (unsup サイト 7,056)。
  - unsup の上位 (サイト数): `vbroadcastss` ymm 552・`vpextrd` 339・`vinsertps` 299・`in` 292・`out` 277・`vpslld` 227・`vpermilps` ymm 208・`vblendvps` ymm 196。x64c の既存語彙の外で、MX-43 の変更とは無関係。
- 受入 1 の判定: 未到達 36,451 件のうち `.text` 内の **36,240 件** を root として lift した (`.text` 外の 211 件は root にしていない → #4192)。成功・棄却の内訳は上の数字 (lift 成功 35,221 関数 / unsup を含む 1,019 関数)。「棄却」は `ott_unsup` を含む関数として数える (棄却と成功の区別は未実装)。
- 注意: `mx43_e2e.sh` の `--img 0x180000000` と `--img-size 0x6616000` は Massive X v1.7.1 (md5 `622993e7…`) の PE 固有の直書き値。別バージョンの PE では再現しない (PE から読む化は #4192 の範囲)。
- 注意: x64c の `--entries` は整数 VA を要求する (文字列だと `bytes_at` で TypeError)。`roots` は base 加算済みの VA。

### 9.8 MX-43 の未解決 (起票先)

- 下表の `.text` 外 211 件・U4f〜U4i は #4192 (MX-47) で確認済み。結果と §9.2・§9.3 の訂正は `REPORT_APPENDIX_4192.md` が正本。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` 外を指す FH3 funclet 候補 211 件 (RVA 0〜0x188 の 8 件・`.text` より上 203 件) の由来 | root から除外した。FH3 walk の誤読か、別の FuncInfo 形かは未確認 | [MX-47] (#4192) |
| SjLj 形の runtime と FH3 FuncInfo walk の C 実装 (受入 2 の残り) | funclet は lift されるが呼べない | [MX-45] (#4161) |
| native vs wasm の通し一致・ネガティブコントロール (受入 3 の残り) | 未実測 | [MX-46] (#4162) |
| U4f (上限棄却 355 件の妥当性)・U4g (4 件の共有)・U4h (EH 専用 block の位置)・U4i (呼出し ABI の実機確認) | §9.5 のとおり | [MX-47] (#4192) |
