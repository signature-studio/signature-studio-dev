# REPORT #4418 — icmp 側の読み出しに残る 2 段 deref の脱落を spill 修復 gate で直す (LD-213)

既知類型との関係: #2794 (`REPORT_2794.md`) と同じ機構。`docs/DEFECTS.md` の D4 (disp=0 の 1 段 deref の脱落) に近いが、同一とは確定しないため ID は付けない。

親: #3580 (LD-164)。本 issue は受入条件のうち icmp 側の修復 (受入 1・2・3) を満たし、audit 粒度の見直し案 (受入 4) を §6 に書く。

## 0. 結論

- ea7ae0 の icmp 読み出し 3 本 (IR 461130・461142・461157 ↔ 機械語 ea7e6d・ea7ea0・ea7ed6。K = 11e35c0・11e4a40・11e1f98) を修復した。機械語は `mov rdx,[rip+X]` → `cmp dword ptr [rdx],0` で、store 側の 2 段 deref と同じ X を 2 段目で読む。修復は `%cellps.K` の 2 段分割。
- 根拠の型 `cmp` (`judge_cmp`) を `fix_spill_2794.py` に追加した。M = I = 2 の K で、機械語の読み出し 1 本だけが `mov rD,[rip+X]; cmp dword ptr [rD],0` の組、IR の i32 読み出し 1 本だけが `icmp ... i32 %v, 0` の被演算子、という条件を全て満たすときだけ直す。
- 100b890 の cell 11e27f0 (受入の対象) は cmp の型に当たらない (M = 3)。見送り。§5。
- e2e (`fix_d17_e2e.sh`) は、修復前の main (`6441decbb`) で既に FAIL していた (§1)。原因は `results/` の stale な TSV で、これを再生成して直した。
- 修復後の spill 宛 CELL_COLLAPSED は **28 → 25** (cmp 修復の 3 site 分。callarg 修復 4 のうち、同じ (関数, K) が全て直った 3 site は audit から消えた)。

## 1. 測定条件 (受入の再現)

- 測定 commit: `be7fefb4a` (コードを変えた最後の commit: `fix(m11): repair icmp-consumed 2-level deref drop via cmp gate (#4418)`)。起点 `origin/main` = `6441decbb`。作業 worktree `ws-4418` (branch `4418-icmp-deref-repair`)。
- 素材: `work-m11` を `$RUNNER_TEMP/m11art` に展開し、`M11_WORK=<その tools/m11/work>` で指定 (`tools/m11/work/` への展開は行わない)。emcc は runner の `[EMSDK]`。`work-liftdiff` と `toolchain-retdec` は本 e2e では未使用。`work-m11` は #516 以前の snapshot なので、結論はこの IR に限る。
- 実行: `M11_WORK=... TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground)。
- 実測 (測定 commit `be7fefb4a`、n=2): real **56.74 s / 56.13 s**、rc **0 / 0**、load average (1 分) 実行前 0.45 / 0.56、終了後 0.78 / 0.83。
- 修復前の基準 (`6441decbb`、修復 pass を変える前の script で同じ e2e を 1 回): step 4 で FAIL (`spill37_1169.tsv が results と不一致`、rc=1)。step 4 までの実行時間は 24.5 s。FAIL の原因は §7。
- 測定後のコード差分 (測定 commit から HEAD まで。この REPORT を追加する commit 以外は無い):

  ```
  git diff be7fefb4a HEAD -- tools/m11/ldfix/fix_d17.py tools/m11/ldfix/fix_d17_e2e.sh tools/m11/ldfix/audit_lsf*.py tools/m11/ldfix/ldmach*.py tools/m11/ldfix/spill37_1169.py tools/m11/ldfix/fix_spill_2794.py tools/m11/ldfix/check_spill_2794.py tools/m11/ldfix/results tools/m11/lb_base.py
  (空: 差分 0)
  ```

## 2. 機械語と IR の照合 (受入 1)

M = `rip_touches` で数えた、X に触れる rip 相対命令の数。I = IR 関数内の `i64 K to ptr` の出現数。

| fn | K | X | M / I | 機械語の読み出し (命令アドレス) | 2 段目の命令 | IR の K の load (行) | 判定 |
|---|---|---|--:|---|---|---|---|
| ea7ae0 | 11e35c0 | 15e35c0 | 2 / 2 | ea7c58 (`mov rax,[rip+..]`→`mov eax,[rax]` の store 側), ea7e6d | `mov rdx,[rip+..]` → `cmp dword ptr [rdx],0` | 461130 (icmp slt), 460891 (callarg) | **修復 (cmp)** |
| ea7ae0 | 11e4a40 | 15e4a40 | 2 / 2 | ea7c8e (store 側), ea7ea0 | `mov rdx,[rip+..]` → `cmp dword ptr [rdx],0` | 461142 (icmp slt), 460910 (callarg) | **修復 (cmp)** |
| ea7ae0 | 11e1f98 | 15e1f98 | 2 / 2 | ea7cbf (store 側), ea7ed6 | `mov rdx,[rip+..]` → `cmp dword ptr [rdx],0` | 461157 (icmp slt), 460918 (callarg) | **修復 (cmp)** |
| 100b890 | 11e27f0 | 15e27f0 | 3 / 3 | 100b8c7 (store 側 callarg), 他 2 本 | 型に当たらない (M = 3) | `%15`・`%23` (mul) | **見送り** (§5) |

- 3 site の機械語の形は、`mov rdx,[rip+X]` の直後の命令が `cmp dword ptr [rdx], 0` (disp 0、即値 0) で一致した (probe で確認)。
- ea7ae0 の icmp の IR (461130 付近): `%176 = load i32, ptr inttoptr (K)` → `%177 = icmp slt i32 %176, 0`。他の 2 本も同じ形。

## 3. 修復 (受入 2) と判定の型

- 修復は `fix_d17.py`・`fix_spill_2794.py` の既存パターンと同じ 2 段分割。`%v = load i32, ptr inttoptr K` を `%cellps.K = load ptr, ptr inttoptr K` と `%v = load i32, ptr %cellps.K` に置き換える。修復後の IR の差分 (`boot_spill.ll` と `boot_d17.ll` の比較) は 3 組 (6 行の追加・3 行の置換)。`emcc -c -O0 -g1` は rc=0。
- 根拠の型 `judge_cmp` の条件:
  1. K の機械語の読み出しが X 上にちょうど 2 本 (M = 2)。
  2. そのうちちょうど 1 本が `mov rD,[rip+X]` (reg 読み出し) で、直後の命令が `cmp dword ptr [rD], 0` (幅 4、disp 0、即値 0、index 無し)。
  3. IR の K の i32 load (幅 32) のうち、`icmp <pred> i32 %v, 0` の被演算子になるものがちょうど 1 本。
  4. IR の K の出現数 I = 2 (M = I)。
- 修復件数: `--gate both` で 13 (1 対 1 の 9 + callarg の 4)。icmp 側は別に 3 (`cmp fixed=3 skipped=25`)。`--gate 1to1` は 9 のまま (cmp は gate 'both' でのみ働く)。

## 4. audit 上の件数と突合 (受入 3)

| 項目 | 修復前 | 修復後 (cmp 無し: `--cmp off`) | 修復後 (cmp 有り: 既定) |
|---|--:|--:|--:|
| spill 宛 CELL_COLLAPSED site (`audit_lsf_ssa.py`) | 37 | 28 | **25** |
| うち TRUE_DROP 30 site の残数 | 30 | 21 | **18** |
| audit から消えた site (修復前との差) | - | 9 | **12** |
| 修復した IR 上の site (`--gate both`) | - | 13 | 13 (うち cmp 根拠で同じ (関数, K) が全て直った callarg が 3) |

- `--cmp on` で消える 3 site は、同じ (関数, K) の i32 読み出しが全て直った callarg の site (ea7ae0 の 11e35c0・11e4a40・11e1f98)。修復件数 (13) は両方で同じで、audit に現れるのが違う。

- 突合 `check_spill_2794.py`: **RESULT: PASS** (cmp 有り・無しの両方)。
- 突合の C2 を拡張した: callarg 根拠の修復 site のうち、同じ (関数, K) の i32 読み出しが全て直った group は audit から消える。これを `cmp_groups` で明示的に扱う。C2b は「直ってない callarg は audit に残る」だけを見る。
- ネガコン 5 (`--cmp off`): 突合は **両方 PASS する**。C2 は cmp 無しでも成立するため、突合だけでは cmp gate の有無を区別できない。そこで e2e は audit の件数の差 (28 と 25) を直接 assert する。

## 5. 見送りの内訳と 100b890 cell 11e27f0

- TRUE_DROP 30 のうち修復 13、見送り 17。見送りの理由は callarg の `callarg_site_not_rsp`・`callarg_m_ne_i` 等 (既存の gate) で、今回の変更による新規の見送りは無い。
- 100b890 の cell 11e27f0 は、受入 1 の対象だが cmp の型に当たらない。機械語の読み出しが 3 本 (M = 3) で、store 側 (100b8c7) を含む。IR の i32 読み出し `%15` (`%17 = mul i32 %16, %15`) と `%23` (`%28 = mul i32 %27, %23`) は mul の被演算子で、icmp ではない。下流が mul のため、M = I = 2 の型の条件を満たさず、見送った。この K は既に callarg で `%6` を直している (同じ cell)。mul 側の残存読み出しは、audit 粒度 (関数 × K) の見直し (§6) と同じ問題として扱う。

## 6. audit の判定粒度 (受入 4): 見直し案

- 現状の audit (`audit_lsf_ssa.cell_check`) は **関数 × K** で判定する。同じ K の i32 const load が 1 本でも残ると CELL_COLLAPSED とする。そのため、修復した site の数と audit 上の件数が一致しない (callarg 4 site のうち 1 本が 100b890 の mul の読みで残る)。
- site 単位で数える見直し案: 各 site について、「その site の値を使う読み出しが全て直っているか」を判定し、直っていれば CELL_COLLAPSED から外す。関数 × K の集約は、そのまま残してよい (件数だけ site 単位にする)。
- 本 issue では audit を変えない。変えると `results/` の全 TSV と e2e の全 assert が変わるため、別 issue で扱う (§7 の起票先)。

## 7. e2e が修復前の main で FAIL していた件 (受入の前提)

- `fix_d17_e2e.sh` は、`6441decbb` (main) の時点で step 4 の `cmp` で FAIL する (`spill37_1169.tsv が results と不一致`)。
- 原因: `results/spill37_1169.tsv` が stale。#3752 (`f592bd2aa`) と #3753 (`91d5c5ca4`) が `results/spill178_1161.tsv` の判定を変えた (UNDETERMINED → TRUE_DROP 等 6 site)。`spill37_1169.py` は spill178 を参照して TSV を作るが、その再生成が main に入っていなかった。
- 対応: `spill37_1169.py` で再生成した TSV を `results/` に入れた (TRUE_DROP 24 → 30)。この変更で、既存の件数 assert (`fixed=24`・`fixed=9`) が変わったため、`fixed=30` (`--gate none`) と `fixed=9 skipped=21` (`--gate 1to1` と argi ネガコン) に直した。`spill_repair_2794.tsv` も再生成した (6 行の追加。修復の集合は変わらない)。
- これは本 issue の修復とは別の、既存の不整合の修正である。`spill37_1169.tsv` の再生成は本 PR に含めた (`results/` だけで、e2e の `cmp` を通すため)。

## 8. 検証範囲 / 範囲外

- 範囲: `work-m11` の IR 1 本 (`boot_final3.ll`) に対する audit と修復・emcc 構文検証。
- 範囲外: 修復 IR を使ったビルド後の wasm の実行 (FLEngine の起動・boot の挙動)。本 issue ではやっていない。修復の正しさは機械語との照合による。
- 起動・GUI に関わらない IR 修復のため、製品 KPI (FLEngine 起動の dispatch 数・通過 unit 数) は測っていない。

## 9. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 100b890 cell 11e27f0 の mul 側の残存 i32 読み 2 本 (M = 3 のため cmp の型に当たらない) | 同じ関数の残存 miscompile の疑い (未検証) | 本 PR の範囲外。#3580 (LD-164) の残件として §5 に記録 |
| audit の判定粒度 (関数 × K → site 単位) の見直し | audit の件数と修復数が一致しない | 本 PR では変えない。§6 の案で別 issue |
| 修復 IR の実行検証 (FLEngine 起動) | 意味の正しさは機械語照合のみ | PM 判断 (本 issue の範囲外) |
| `work-m11` が #516 以前の snapshot | 結論はこの IR に限る | REPORT_1169 §5 と同じ扱い |

## 10. 再現

```
M11_WORK=<work-m11 展開先>/tools/m11/work TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/fix_d17_e2e.sh
```

素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff` (`work-m11` が必須。emcc は runner の `[EMSDK]`)。
