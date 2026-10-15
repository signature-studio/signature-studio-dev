# REPORT #3580 — 修復 cell の非 store 消費 (icmp) の 2 段 deref 脱落と audit の判定粒度 (LD-164)

親: #2910 (LD-137)。本 PR は受入条件のうち、受入 1 (機械語と IR の対応の確定) と、e2e の rc=0 を妨げていた既存の不整合の修正までを完了単位とする。受入 2 (icmp 3 読み出しの修復) と受入 3 (判定粒度の見直し案) は未達のため、`Refs #3580` とし、残りは PR 本文の未解決表に書く。

## 0. 結論

- ea7ae0 の icmp 3 読み出し (IR 461130・461142・461157) は、機械語では 2 段 deref (`mov rdx,[rip+X]` でセル内容を読み、`cmp dword ptr [rdx],0` で先の dword を比較) に対応する。IR は K を 1 段で `load i32` して `icmp slt` に渡している。**2 段の脱落は確定**した (#2910 の「未検証」は解消)。
- 同じ関数の store 側 3 本 (IR 460891・460910・460918) は #3586 (#2910) で修復済み。main の e2e は、この修復済み cell の icmp 読み出しを直していないので、audit 上は CELL_COLLAPSED のまま残る。
- 受入 2 (icmp 3 読み出しの修復) は未着手。理由は §3。
- main の `fix_d17_e2e.sh` は、#3753 (91d5c5ca4) で `results/spill178_1161.tsv` の 4 site が UNDETERMINED → TRUE_DROP に変わった後、派生 TSV (`results/spill37_1169.tsv`・`results/spill_repair_2794.tsv`) が再生成されておらず、step 4 の `cmp` で落ちていた (rc=1)。本 PR で生成元 (`spill37_1169.py`・`fix_spill_2794.py`) の実行結果から再生成して直した。

## 1. 測定条件

- 起点: `origin/main` = `47a76cf4b`。作業 worktree `ws-3580` (branch `3580-ld164-icmp-two-level-deref`)。
- 素材: `work-m11` を `$RUNNER_TEMP/m11x` に展開し、`M11_WORK=<その tools/m11/work>` で指定 (`tools/m11/work/` は gitignore されていないため、commit には含めない)。`work-m11` は #516 以前の snapshot なので、結論はこの IR に限る。
- 実行: `M11_WORK=... TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground)。
- 基準 (main のまま): rc=1 (step 4 の `cmp` で FAIL、real 25.73 s)。
- 修正後: rc=0、real 45.04 s、load average (1 分) 実行後 0.71。
- 修正後の件数: spill 宛 CELL_COLLAPSED 37 → 28、修復 13 (1 対 1 の 9 + callarg の 4)、TRUE_DROP 30 (#3753 の反映で 24 → 30。見送り 17)。修復件数は REPORT_2910 §3 と同じ。
- 測定 commit: コードを変えた最後の commit (本 PR の commit hash は push 後に §4 へ記録)。

## 2. icmp 3 読み出しの機械語と IR の対応 (受入 1)

| 機械語 (読み出し命令) | X / K | 消費 (機械語) | IR 行 | IR の読み出し | 消費 (IR) |
|---|---|---|---|---|---|
| ea7e6d `mov rdx,[rip+X]` → ea7e74 `cmp dword ptr [rdx],0` | 15e35c0 / 11e35c0 | cmp (dword・2 段目) | 461130 `%176` | `load i32 inttoptr (K)` (1 段) | `icmp slt i32 %176, 0` |
| ea7ea0 `mov rdx,[rip+X]` → ea7ea7 `cmp dword ptr [rdx],0` | 15e4a40 / 11e4a40 | cmp (dword・2 段目) | 461142 `%185` | 1 段 | `icmp slt i32 %185, 0` |
| ea7ed6 `mov rdx,[rip+X]` → ea7edd `cmp dword ptr [rdx],0` | 15e1f98 / 11e1f98 | cmp (dword・2 段目) | 461157 `%194` | 1 段 | `icmp slt i32 %194, 0` |

- 機械語は `ImageMachine.disasm_fn(0xea7ae0)` の逆アセンブルで確認 (`m11_image.bin`)。X = 機械語の rip 相対先、K = X − 0x400000。
- 同じ K の store 側 (機械語 ea7c58・ea7c8e・ea7cbf → IR 460891・460910・460918) は `mov eax,[rax]` の 2 段で、#3586 で修復済み。
- 同じ K に対して、IR の `load ptr` (1 段目 = セル内容) が使われている箇所は他にもある (459643・459783 など)。icmp の 3 本だけが `load i32` のまま。
- ゆえに icmp 側の 3 読み出しは、機械語では 2 段・IR では 1 段で、2 段の脱落と判定する。

## 3. 受入 2 が未達の理由

icmp 3 読み出しを直すには、次の 2 点が要る。

1. **根拠の型**: 既存の `1to1` (M=I=1) は M=I=2 (store 側と icmp 側の 2 本) のため使えない。`callarg` (引数 store → direct call) は cmp に当たらない。新しく「`mov rdx,[rip+X]` → `cmp dword ptr [rdx],0` の 1 組」を根拠の型として定義し、ネガコンを足す必要がある。
2. **対象の列挙**: 修復対象は audit の spill 宛 CELL_COLLAPSED の store の site 集合 (`spill_targets`) から来るため、icmp の読み出しは今の仕組みでは対象にならない。`audit_lsf_ssa.py` の拡張か、同じ K の非 store 消費を別に列挙する経路が要る。

上の 2 点を入れると、ネガコン・TSV・件数 assert の更新・e2e 再測定まで含めて 60 分に収まらないと判断した。受入 2 は子 issue に分割する (PR 本文の未解決表と issue コメントに起票先を書く)。

## 4. 修正の内容と根拠

- `results/spill37_1169.tsv`: `spill37_1169.py` を、現 main の `results/spill178_1161.tsv` (#3753 で更新) と現 main の audit (`audit_lsf_ssa.py`) に対して再実行して再生成。4 site (128c320 128cad6・128c320 128d007・128c320 128d495・128f9e0 12900c4、c343f0 c3460e、dcdde0 dcdeee の 6 site) が UNDETERMINED → TRUE_DROP。手で編集していない。
- `results/spill_repair_2794.tsv`: `fix_spill_2794.py` (`--gate both`) の出力で再生成。TRUE_DROP 30 のうち修復 13、見送り 17。
- `fix_d17_e2e.sh` の件数 assert を実測値に合わせた: ネガコン 2 (`--gate none`) `fixed=24` → `fixed=30`、ネガコン 3 (`--gate 1to1`) と 4 (argi ずらし) の `skipped=15` → `skipped=21` (`fixed=9` は不変)。
- 修復ロジック (`fix_spill_2794.py`) と判定 (`spill37_1169.py`) のコードは変えていない。

## 5. 判定粒度 (受入 3) の状態

`audit_lsf_ssa.cell_check` は site ごとでなく関数 × K で判定する。callarg の 4 site (100b8d0・ea7c61・ea7c97・ea7cc8) は修復後も、同じ K の i32 読み出しが残るために CELL_COLLAPSED のまま。見直し案は未作成。この PR では、修復済み cell の残存読み出しの有無を site 単位で数える案を書くだけにとどめる (実装は子 issue)。

## 6. 検証範囲 / 範囲外

- 範囲: `work-m11` の IR 1 本 (`boot_final3.ll`) に対する audit・修復・emcc 構文検証。
- 範囲外: 修復 IR を使ったビルド後の wasm の実行 (FLEngine の起動)。本 PR では修復を入れていないため、起動の影響は無い (製品 KPI は測っていない)。
