# REPORT_APPENDIX_3188 — #3188 の LB=0 と LB=0x10000 の寛容起動の unit 差 8 件 (REPORT_N403.md §7 の全文)

分割移動 (REPORT_N403.md が 250 行を超えるため)。本文の内容は変えていない。

## 7. #3188: LB=0 と LB=0x10000 の寛容起動の unit 差 8 件の切り分け (Actions runner で実測)

測定 commit (merge 前の旧版): `6a20f8b1` (コード差分の最終 commit。1d9e2037 から PATH 行の削除だけ・再測定済み)。測定 runner: Actions (4 vCPU・RAM 15 GiB)。load average は未採取。merge 後の再測定は 7-0 のとおり未実施。
既知類型との関係: 該当なし (`docs/DEFECTS.md` の ID は未付与。NULL 源の memcpy は下 §7-3 の候補で、既存類型との対応は未確認)。
素材: `fl-win64` (`block00031_PE.bin` 22,227,016 B、展開 2.2 s)・`work-m11` (展開 2 s。`lift_pe.sha256` 無し)。
`m11_e2e.sh` の全再生成 (指紋検査) は使わず、後段だけ `m11_lb_tolerant_repro.sh` で回した (gen_ir2 → data/image → lb_check → build → `m11_tolerant.mjs`)。
`toolchain-emsdk` は展開せず runner 既存の emsdk ([EMSDK]、`docs/REFERENCES.md` §4) を使った。`toolchain-retdec`・`work-liftdiff` は使っていない (lift を走らせていない)。

### 7-0. merge 後の状態 (main 取り込み・数値は merge 前のまま)

- 本 PR の旧版と main (#3160) は同じ修正 (`fix_ld108.py`・`m11_fix912.py`) と同じ再現スクリプトを別の書き方で持っていた。競合は main 側を採用して解消した (merge commit `9c2bcd3a`)。解消後に本 PR が増やすのは `m11_lb_ir_fn_diff.py` と本節だけ。
- 以下 7-2〜7-3 の数値は merge 前の旧版 (`6a20f8b1`) で測ったもの。**merge 後の再測定は未実施**: 素材 `work-m11` (lift 成果物) と `toolchain-emsdk` (`[EMSDK]`) が未取得のため、`tools/m11/work/` が無く後段を回せない。再測定に要る `oc_artifacts` の行は PR 本文に書く。
- `6a20f8b1` から `f3841aa0` までの code 差分 (4 パス・§7-6 の出力): 8 files, +307 −88。main 由来の `fix_ld116.py`・`ld116_e2e.sh`・`dyn_ld115.mjs` と `REPORT_2513.md` を含む。
- 素材なしで確認した範囲 (merge 後の HEAD): `M11_LB_BASE=0` で `fix_ld108` の照合文字列は `i64 16404608`・`fix912` の VMT は `994072` (修正前の文字列と同一)。`M11_LB_BASE=0x10000` で `16470144`・`1059608`。`m11_lb_ir_fn_diff.py` は合成 .ll で定数変化量 `[65536]` を出した。main 版の `m11_lb_unit_diff.py` は合成 JSON で kind 差 1 件を検出した (差があっても exit 0。結果は `kind_diff=N` の行で読む)。

### 7-1. 再現スクリプト (main #3160 版を使う。本 PR で追加するのは `m11_lb_ir_fn_diff.py` のみ)

- `tools/m11/m11_lb_tolerant_repro.sh <LB> <出力先>`: 後段だけの再現。出力は `tools/m11/<出力先>/` (`tolerant_units.json`・`boot_final.ll`・ログ)。
- `tools/m11/m11_lb_unit_diff.py A.json B.json`: unit の index 単位で kind を突合 (VA は LB でずれるので比べない)。差は `kind_diff=N` で出る (exit 0 は差の有無と無関係)。
- `tools/m11/m11_lb_ir_fn_diff.py A.ll B.ll function_X ...`: 関数本体の行差分と、整数定数の変化量 (LB=0x10000 側 − LB=0 側) を出す。

### 7-2. 修正 (受入 2 の前段: LB 直書きの IR 書換え pass が LB=0x10000 で止まる)

下の修正は merge 前の本 PR 版。merge 後は main (#3160) の同じ修正が残り、定数は 7-0 のとおり同じ値になる。

修正前 (HEAD `24be607a`) は `M11_LB_BASE=0x10000` の IR も wasm も作れなかった (fail-closed)。原因は LB=0 の定数の直書き 2 件:

| pass | 直書き | 症状 (修正前・LB=0x10000) | 修正 |
|---|---|---|---|
| `ldfix/fix_ld108.py` (D20) | head 変数の store 先 `i64 16404608` (LB=0 の LVA = VA 0x13A5080) | gen_ir2 が `store 行が想定と違う` で停止 (IR の定数は 16470144 = +0x10000) | `HEAD_VA + VA_TO_LVA` |
| `fix912/m11_fix912.py` (#912) | VMT 参照 `i64 994072` (LB=0 の LVA = VA 0x4F2B18) | m11_build.sh が `対象行が無い (before=0 after=0)` で停止 (mode off でも検査する) | `0x4F2B18 + VA_TO_LVA` |

LB=0 の出力は不変: 修正前 (23:30 の実行) と修正後 (23:36・worktree の 23:41 の実行) で寛容起動の集計が同一 (下 §7-3 の LB=0 の記録)。

### 7-3. 寛容起動の結果 (修正後・同一 HEAD で各条件 2〜3 回)

- 集計 (units・ok・noproc・miss・skipped と skipped の内訳) は `REPORT_N403.md` §6-1 と一致 (差 0)。値の正本は §6-1 で、この節には値を書かない。
- 列の定義 (§6-1 と同じ): units = ok + noproc + skipped。skipped は `m11_tolerant.mjs` の SKIP 集合 (halt0・oob・unreachable・abort・other・oom・miss・clobber) の計で、miss を含む。内訳 (oob・halt0・unreachable・abort) の計は miss と別。
- 測定の記録: LB=0 は 2 回 (main 側 23:36・worktree 側 23:41)、repro 所要 70.3 s (main 側 23:36 の実行。worktree 側の 2 本合計は 143 s)。LB=0x10000 は 3 回 (main 側 23:35・23:38、worktree 側 23:42)、repro 所要 71.9 s (main 側 23:35 の実行)。
- 突合 (`m11_lb_unit_diff.py`): **kind 差 8 件**。unit の集合と kind は `REPORT_N403.md` §6-2 と一致。issue 本文の 8 件とも一致。
- ネガティブコントロール (決定性): LB=0 の 2 回 (main 側 23:36 と worktree 側 23:41) の突合は kind 差 0。差 8 件は実行の揺れではない。
- **issue の「現 HEAD で 8 件」は、修正前の HEAD では再現しなかった** (LB=0x10000 の IR が作れない)。修正後に初めて測れた。

### 7-4. 原因の切り分け (途中。未特定)

- **IR の再配置の漏れは見つからなかった** (`m11_lb_ir_fn_diff.py`): 関数 412770・4128b0・411d20・412e40・412c20・535c11 で、LB 由来の定数は全て +0x10000 (412c20 は 1 行のみ差・+65536)。構造 (行数) は同一で、0 でも +0x10000 でもない変化は無い。ただし測定時の版は定数を `iN 数値` の形でしか数えず、`add i64 %a, N` の形 (第 2 オペランド) の定数は数えていなかった。第 2 オペランドも数える版 (本 fix) での再確認は再測定の項目 (§7-0)。
- **image 側**: 線形 0 の NULL 領域は LB=0 で PE ヘッダ (`4d 5a 50 00 …`)、LB=0x10000 で全 0 (`lb_check` の `null_region_nonzero_bytes` = 0)。NULL を読む箇所の値が LB で変わる。
- **候補 (unit 40 の Halt0 経路)**: `function_412770` の memcpy の源が `ptr null` (IR 全体で `ptr null` 源の memcpy は 1 件だけ)。元の機械語 (VA 0x412790) は `mov rsi,[rax]` (arg1 の先頭 8 B を読む) → `rep movsq` 37 qword で、lift が load を脱落させ NULL に置換した silent miscompile の疑い。
  - 検証: 源を `[arg1+0]` の load に戻した IR (実験: `work/exp_null_src_*`・repo には入れていない) でも、kind 差 8 件・skipped の内訳は不変。**この NULL 読みは 8 件の原因ではない** (否定結果)。ただし lift の欠陥そのものは残る。
- **未検証の候補 (C 側)**: `m11_ov.c:194` の icall の `tkey = target + (0x400000 - M11_LB_BASE)` (LVA → VA 換算。VA 形式の target は fallback あり)。
- **未特定**: unit 153・158 (LB=0x10000 で OOB の読み先)、291・296・304・555・745 (LB=0 側の OOB。wasm 関数 `function_535c11`・`function_407e20__lifted`)、304・555 の abort の呼出元 (記録は最内の `abort` だけ)。

### 7-5. 検証範囲と限界

- 範囲: 寛容起動 (`m11_tolerant.mjs`) の unit 別結果のみ。strict (`m11_run.mjs`)・survey・`m11_e2e.sh` の gate は未実行 (指紋検査を迂回しないため)。
- LB=0 の既存 gate (`e2e_expect.env`) への影響は未確認。修正は LB=0 の文字列を変えない (`VA_TO_LVA = 0` で同じ定数) が、gate の再実行は未了。
- 回数: 修正後の実行は LB=0 が 2 回 (main 側 23:36・worktree 23:41)、LB=0x10000 が 3 回 (main 側 23:35・23:38、worktree 23:42)。突合の kind 差は全て 8 件・同じ unit。
- 未解決 (起票先は PR 本文の表): 8 件の原因特定 (上 §7-4 の未特定) → 子 issue。memcpy 源 NULL の lift 欠陥 (§7-4) → 同じ子 issue。

### 7-6. 測定 commit から HEAD までの差分 (4 パス)

- 測定 commit: `6a20f8b1` (§7-2・§7-3 の数値はこのコードによる)。差分の証跡 (fix commit 直前の HEAD `f3841aa0` まで): `git diff --stat 6a20f8b1 f3841aa0 -- tools/m11/ldfix tools/m11/fix912 tools/m11/m11_lb_tolerant_repro.sh tools/m11/m11_lb_unit_diff.py` の出力は次のとおり (全文の patch は同じ command で出せる。REPORT の行数上限のため stat のみ載せる)。

```
 tools/m11/fix912/m11_fix912.py     |  10 ++--
 tools/m11/ldfix/REPORT_2513.md     | 114 +++++++++++++++++++++++++++++++++++++
 tools/m11/ldfix/dyn_ld115.mjs      |  35 ++++++++++--
 tools/m11/ldfix/fix_ld108.py       |   7 +--
 tools/m11/ldfix/fix_ld116.py       |  68 ++++++++++++++++++++++
 tools/m11/ldfix/ld116_e2e.sh       |  59 +++++++++++++++++++
 tools/m11/m11_lb_tolerant_repro.sh |  52 +++++++----------
 tools/m11/m11_lb_unit_diff.py      |  50 +++-------------
 8 files changed, 307 insertions(+), 88 deletions(-)
```

- fix commit 以降 (`git diff --stat f3841aa0 HEAD -- <同じ 4 パス>`) の出力は空。この節の commit 以降も 4 パスは変えていない。
- 再測定 (HEAD で `m11_lb_tolerant_repro.sh 0` と `... 0x10000` を回す) は未実施。素材の取得が要る (上 §7-0)。
