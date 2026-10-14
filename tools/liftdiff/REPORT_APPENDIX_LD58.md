# liftdiff REPORT 付録: LD-58 (#1637) 1801c67a0 の m8_fail 発火条件と sample:800 の件数揺れ

親 issue #1313 (LD-44)。前提は `REPORT_APPENDIX_LD44.md` §2・§3・§5。heap 残りの検証 (case 後に heap 全域を比較する計測) は `REPORT_APPENDIX_LD96.md` §8 (測定 commit `7d434168`) で実施済みで、本付録は数値を複製せず参照する。

## 結論

- **HEAD (`33eef065`) で再測定した (§8)**。wasm は HEAD で build し直し、`work/m11/simd.c` は素材版 (sha256 `d82e2759…`) のまま使った。以下の件数は HEAD の数値が正本。旧 commit `5b254578`・`7d15ceab` の数値 (§3・§7) は測定 commit を付けた参考値として残す。
- 受入 (a): 入口ガードを外した再 build で、`1801c67a0` の u16・vm0 の `m8_fail` (wasm abort) は**消えた** (両方 `equal`)。発火点は `m8_rt.c` の入口ガードで、LD-44 の仮説 (arena 範囲外で弾いている) は、この試験で方向として支持された。ただし arena ポインタ値そのものは記録していない。
- 受入 (a) の副作用: 同じ再 build で `qall` は `both_fault` (native segv・wasm trap) から `native_fault` (native segv・wasm ok) に変わった。ガードを外すと wasm 側は trap せず進むため。ガードを外した版を本流に入れるかは別判断 (本 PR は測定のみ・コード変更なし)。
- 受入 (b): sample:800 の件数は、HEAD の shard 12 を 3 回で **361/232/207・361/232/207・360/233/207** (一致/不一致/実行不能)。旧 commit の 361/229/210・360/230/210 (×3) とは、実行不能が 210→207 に変わり、不一致が +2〜+3 になった (HEAD 側の変化。移った件の特定は未確認・§6)。
  - 件数揺れは `0x959a40` 1 関数の verdict だけ (HEAD の shard 12 でも同じ・r1・r2 は match、r3 は mismatch)。
  - HEAD の shard 1 (n=1): 342/251/207。旧 commit と同じ 19 関数が match→mismatch になった (§7.3・§8)。
  - 揺れの原因は**未特定**。heap の高水位外の残存は wasm 側だけに出るが、残存を持たない関数も揺れるため、残存だけでは説明できない (LD-96 §8.3)。残件は #2681・#2682 (いずれも #2258 (LD-96) の子) に移した (§6)。
  - **timeout の扱いを修正**: 旧 commit の shard 12 では `0x959a40` の揺れた case (p1・pall・qall) は native・wasm とも ok で、timeout ではなかった (§3)。HEAD の shard 1 では、verdict が flip した 19 関数の中に wasm の timeout 9 件・trap 3 件が出た (r1〜r3 では equal だった case のうち 12 件)。shard 1 の flip を timeout 無しで説明するのは誤り (§7.3・§8.3)。
  - 単独 run (`--set file:` で `0x959a40` のみ) は、旧 commit の 4 回と HEAD の 2 回 (shard 12・1 各 1 回) の計 6 回すべて `match`。
  - 「最初の run (r1) だけが一致し、r2〜r4 が不一致」というパターンは旧 commit の 2 session で出たが、HEAD の shard 12 では r1・r2 が一致し r3 が不一致で、再現しなかった (§8.2)。負荷と順序は判定不能のまま (§7.3)。
- 受入 (c): 測定 commit と `git diff` は §5 に記載。

## 1. 測定条件

- 測定 commit: 旧 n=4 は `5b254578` (origin/main 当時の HEAD)、旧 shard 追試は `7d15ceab`、HEAD 再測定 (§8) は **`33eef065`**。`5b254578`・`7d15ceab` から HEAD までのコード差分は非空 (§5)。HEAD 再測定ではコード差分 0 (§5)。
- 測定 runner: 4 vCPU。load は `/proc/loadavg` の 1 分値。「開始」はその run の直前、「終了」は直後 (§7・§8 の表記)。4 を超えると過負荷。§3 の load は `uptime` で記録したのは r1 のみ (開始 0.9・終了 5.7)。r2〜r4 の load は未記録。
- 素材 (旧測定): `fl-win64` (`FL_WIN64_DIR` = `[WIN64]`)・`work-m6-ott`・`work-m11`・`work-liftdiff`・`work-liftlib`・`analysis-ott-binaries` (`ANALYSIS_DIR` = `[ANALYSIS-DIR]`)・`plugins-ott` (`PLUGINS_DIR` = `[ANALYSIS-PLUGINS]`)・`toolchain-emsdk` (`[EMSDK]`)。全て展開を確認済み。
- 素材 (HEAD 再測定 §8): `fl-win64` の `extracted/block00031_PE.bin` (`FL_WIN64_DIR` に展開)・`work-m11`・`work-liftdiff` を展開した。emsdk は runner の `/opt/emsdk` (emcc 6.0.12 = `tools/m1/flags.sh` の pin) を使い、`toolchain-emsdk` は展開していない。`targets/m11.json` の batch は、これ以外の素材を展開しなくても rc 0 で完了した。PR 本文の `oc_artifacts:` 行の残りの素材は未使用。
- 生データ (`work/` は gitignore): 旧測定は `work/m11/batch_head_r{1..4}.jsonl`・`work/m11/batch_head_r{1..4}.log` (旧名。`5b254578` の生データ)・`work/ott_noguard/run_1801c67a0.log`。HEAD 再測定は `work/m11/batch_head_{r1,r2,r3,s1,solo1,solo12}.{jsonl,log}` と `work/m11/batch_head_runs.txt` (load・wall)。
- コミット済みの TSV (HEAD 再測定): `results/ld58_head_sample800_verdict.tsv` (800 関数の verdict・`#counts` 行)、`results/ld58_head_sample800_cases.tsv` (case 単位・8877 行・`outcome(native_status/wasm_status)`)、`results/ld58_head_0x959a40_solo{12,1}_{verdict,cases}.tsv`。JSONL からの変換は `ld58_head_summarize.py`。

## 2. 受入 (a): `1801c67a0` の m8_fail 発火条件

試験の方法: `tools/m8/m8_rt.c` の `m8_ptr_ok` を `a >= 0x1000 && a < 0x36000000` に緩めた版を使い、`targets/ott_old.json` の `extra_sources` の `m8_rt.c` だけを差し替えた (`work/ott_noguard/target.json`)。`liftdiff.py run ... --nobuild` は使わず、wasm を新規 build させた。リポジトリの `tools/m8/m8_rt.c` は変えていない。緩和版の差分は `tools/liftdiff/results/ld58_m8_ptr_ok_relax.patch` (原文 `a >= M8BASE` (`0x30000000`) を `-` 行、緩和後の `a >= 0x1000ull` を `+` 行で併記) に commit した。再現は `git apply tools/liftdiff/results/ld58_m8_ptr_ok_relax.patch` の後に build する。build ログは `results/ld58_1801c67a0_noguard_build.log` (パスは repo 相対と `[EMSDK]` に置換済み)。

| case | 基準 (`2626e445`・`ott_old` snapshot, `run --nobuild`) | ガード緩和 build |
|---|---|---|
| z, s, p0, p1, p01, pall | both_fault (native segv・wasm trap) | both_fault (同) |
| u16 | wasm_trap (native ok・wasm abort, `m8_fail`) | **equal** (native ok・wasm ok) |
| vm0 | wasm_trap (native ok・wasm abort, `m8_fail`) | **equal** (native ok・wasm ok) |
| qall | both_fault (native segv・wasm trap) | **native_fault** (native segv・wasm ok) |
| 関数 verdict | mismatch | match |

- 基準の `m8_fail` の呼び出し経路: `ld_wasm.wasm.m8_fail < ld_wasm.wasm.function_1801c67a0` (直接)。LD-44 §8.3 の `function_1801c721c` 経由は誤り (LD-44 §2 で訂正済み)。
- 結論: u16・vm0 の wasm abort は入口ガードで発火していたと**支持された**。ガード緩和で消えたが、緩和は全 `m8_ptr_ok` 呼び出しに効くため「入口ガードで確定」とは言えない。arena ポインタの実値は未記録のため、「範囲外」の部分は未確定。
- 仮説が外れた場合ではなく、支持された。ただしガード緩和は全 `m8_ptr_ok` 呼び出しに効くため、本流の修正方法 (ガードの範囲を arena に合わせるか、関数単位で外すか) は未決。

## 3. 受入 (b): sample:800 の n=4 測定 (旧 commit `5b254578`・直列実行)

旧 commit の参考値。HEAD の数値は §8。

コマンド: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/batch_head_r{N}.jsonl` (commit `5b254578`, 4 回連続)。

| run | 一致 | 不一致 | 実行不能 | 所要 (wall) | 備考 |
|---|---|---|---|---|---|
| r1 | 361 | 229 | 210 | 1m49.8s | load 0.9→5.7。`0x959a40` は `match` |
| r2 | 360 | 230 | 210 | 1m45.8s | `0x959a40` は `mismatch` |
| r3 | 360 | 230 | 210 | 1m48.2s | `0x959a40` は `mismatch` |
| r4 | 360 | 230 | 210 | 1m44.3s | `0x959a40` は `mismatch` |

- 件数揺れ (361 vs 360) の出所: `0x959a40` 1 関数の verdict のみ。他の 799 関数の verdict は 4 回とも同じ。
- `0x959a40` の揺れた case は p1・pall・qall。r1 は `equal` (native ok・wasm ok)、r2〜r4 は `diff` (native ok・wasm ok)。**timeout ではない** (`results/ld58_m11_sample800_n3_5b254578.tsv` の case 行で確認)。
- r2〜r4 の差分の中身 (p1): `ret` が native `0xffffd4e8` / wasm `0x2206ec00` で不一致、かつ `trace` に `wasm_extra_entry` (wasm が余分に関数 `0x956550` を通る)。
- 全 27 件の case 揺れ (3 回以上の run にまたがるもの) のうち、timeout・hang を含むものが大半 (native `hang`・wasm `timeout`/`crash`/`hang` の組)。`0x959a40` 以外の関数の verdict は揺れていない。
- 単独測定 (`--set file:` で `0x959a40` のみ、shards 1 ×2 / 12 ×2): 4 回とも `match` (p1・pall・qall は全て `equal`)。
  → **sample:800 の全体実行の中でのみ `diff` が出る**。単独では再現しない (4 回・n=4 の範囲)。

### 3.1 揺れの分類 (旧 commit の結論)

- timeout (native・wasm どちらか) による件数揺れ: **該当なし** (`0x959a40` の verdict 変化は両側 ok の case による)。ただし shard 1 の HEAD 測定では wasm timeout が出た (§8.3)。
- 揺れの源: **未特定**。単独で `match` になり、全体 run でのみ `diff` になる。heap 残りの検証 (case 後に heap 全域を比較) は LD-96 §8 で実施済み。結論は次の通り (数値は LD-96 §8.3 を参照): 高水位外の残存は wasm 側だけに出る。残存を持たない関数も揺れるため、残存だけでは揺れを説明できない。残りの原因 (他関数の状態持ち越し・負荷など) の切り分けは #2681・#2682 (LD-96 の子) の範囲。
- shard 配置は関与する可能性がある (旧 commit の shard 1 で 19 関数、shard 12 で 1 関数が揺れる・§7)。HEAD の shard 1 (n=1) でも同じ 19 関数が揺れたが、n=1 のため暫定。
- 件数 361 と 360 の差は、旧 commit の r1 の 1 回だけ出た。以後は 360 が 3 回続く。HEAD の shard 12 では 361・361・360 (§8)。

## 4. 前回測定 (`2626e445`・参考・§3 とは別 commit)

前回の n=3 測定 (commit `2626e445`) は件数 361 / 361 / 360 で、`0x959a40` は r3 だけ `mismatch` だった。この値は §3 の `5b254578` とは別 commit の測定で、直接比較はできない。両者の間の `git diff --stat 2626e445 5b254578 -- <§5 のパス>` は 72 files / +3502 / -57 (§5 の範囲)。

- 前回の生データ: `work/m11/batch_head_r{1,2,3}.jsonl` (gitignore)。r1 の所要は 1m48.2s、r2・r3 は未計測。
- 前回の揺れも、同じく `0x959a40` 1 関数の verdict に限られていた。

## 5. 測定 commit と差分

- 旧 n=4 (§3) の測定 commit: **`5b254578`** (origin/main)。HEAD 再測定 (§8) の測定 commit: **`33eef065`**。
- 本節の再確認 (HEAD `ee6ad3dc` 時点): `git diff 5b254578 HEAD --stat -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt` = **190 files changed, 19894 insertions(+), 228 deletions(-)**。`33eef065` は REPORT のみの変更で、この範囲の数値は変わらない。
- §7 の測定 commit `7d15ceab` からの同じ範囲の差分: `git diff 7d15ceab HEAD --stat -- (同じ範囲)` = **151 files changed, 11252 insertions(+), 359 deletions(-)**。
- 差分の中で測定に効きうるもの (未検証): `tools/liftdiff/rt/ld_core.h` の仮 proc の VMT slot 域 (LD-48 の `ld_fakeproc_vmt_init`・`ld_fakeproc_valid`)。`ld_snapshot` (SSNAP) から呼ばれるため、仮 proc の解決に効きうる。`ldlib/cases.py` の fvm 用 blob (`vmt`) も同じ差分に入る。
- HEAD 再測定 (§8) の測定 commit `33eef065` から、本 commit までのコード差分: `git diff 33eef065 HEAD -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt tools/liftdiff/liftdiff.py` = **0 行** (本 commit で増えるのは `tools/liftdiff/ld58_head_summarize.py`・`results/ld58_head_*` と本 REPORT だけで、測定の範囲の外)。
- よって §3・§7 の旧数値は HEAD のコードに対応しない。HEAD の数値は §8 だけが対応する。
- 生データ: `results/ld58_m11_sample800_n3_5b254578.tsv` (旧 case 揺れと件数。ファイル名は n=3 だが中身は r1〜r4 の 4 run を含む。case 行は r1〜r3)。HEAD の生データは `results/ld58_head_sample800_{verdict,cases}.tsv`。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shard 1 (HEAD) の 2 回目は未測定。HEAD の shard 1 は n=1 | §7.3・§8.3 の shard 配置の判定 | 本 PR #2693 内で追跡 (n=1 の暫定として残す。子は起票しない) |
| shard 1 (HEAD) で wasm timeout 9 件・trap 3 件が出た原因 (負荷による wall-clock 超過か、case の挙動か) | §8.3 の flip の解釈。timeout 除外の根拠 | 本 PR #2693 内で追跡 (子は起票しない) |
| 件数揺れの原因 (heap 残存か、他関数の状態持ち越しか) | 件数 361/360 と shard 1 の 19 関数の説明 | #2681 (LD-121)・#2682 (LD-122)。どちらも #2258 (LD-96) の子 (移し元は #2258) |
| HEAD で実行不能が 210→207 に減った 3 件 (不一致・一致のどちらに移ったか) の特定 | 旧 commit と HEAD の件数比較 | 本 PR #2693 内で追跡 (旧 per-function の verdict は未コミット) |
| ガード緩和の本流への反映方法 (ガード範囲の arena 合わせ・関数単位の除外) | `1801c67a0` の u16・vm0 は本流 wasm で abort のまま | 本 PR の未解決表で追跡 (子は起票しない) |
| `qall` の native_fault への変化の解釈 (ガード緩和で wasm が進んだ後の native segv) | 緩和版の判定の妥当性 | 同上 |
| arena ポインタ実値の記録 | 「範囲外」の判定の確定 | 同上 |
| OTT 8 関数のうち 1801c67a0 以外の 7 関数の再確認 | LD-44 §2 の未実施分 | LD-57 (#1636) |

## 7. shard 数による差 (旧 commit `7d15ceab`・追試)

§3 の 4 回は shard 12 のみだった。shard 数を変えると件数が変わるかを追試した。測定 commit は `7d15ceab` (origin/main)。`7d15ceab` から HEAD までのコード差分は §5 の通り (151 files)。HEAD での同じ比較は §8 (shard 12 を 3 回、shard 1 を 1 回)。

- コマンドは §3 と同一 (`--set sample:800 --nobuild --state auto`)。`--shards 12` を 4 回、`--shards 1` を 1 回 (n=1)。
- 所要 (wall): shard 12 は r1 1m50s・r2 1m52s・r3 1m47s・r4 1m51s。shard 1 は 6m25s。
- load (`/proc/loadavg` 1 分値, 開始→終了。定義は §1): r1 0.8→6.0・r2 5.1→7.1・r3 7.1→6.4・r4 6.4→6.9・shard 1 5.8→0.9。4 vCPU。shard 1 は直前の shard 12 r4 (終了 6.9) の直後に開始した (開始 5.8)。
- 件数 (一致/不一致/実行不能): shard 12 は r1 361/229/210、r2〜r4 360/230/210。**shard 1 は 342/248/210**。

結果 (`results/ld58_m11_sample800_shards_t1.tsv`。verdict が run 間で変わる関数。列は va・r1〜r4 (shard 12)・s1 (shard 1)。この TSV は verdict のみ):

- shard 12 の 4 回で変わったのは `0x959a40` だけ (r1 match、r2〜r4 mismatch)。`p1`・`pall`・`qall` の wasm 側で `wasm_extra_entry` (`0x956550`) または `ret` の差。timeout ではない (§3 の case 行)。
- shard 1 では **19 関数** の verdict が match から mismatch に変わった (`0x959a40` を含む)。shard 12 の r1 とは一致しない。
- shard 1 で変わった関数の差分は主に wasm 側の heap の値 (`0xccccccccccc35b20`・`0xff800000ff800000` など、native は `unchanged(0x0)`) と `ret`・`calls` (`GetDeviceCaps` の引数)。ただし旧 commit の shard 1 は case 単位の記録が committed に無かった。HEAD の shard 1 では記録を取り、§8.3 に示す (wasm の timeout・trap を含む)。
- 修正前の §3.1 の「shard 数の差 (1 vs 12) では説明できなかった」は、この追試で**修正が必要**になった。shard 1 の方が件数が多く揺れる。ただし shard 1 は n=1 の暫定 (HEAD でも同じ 19 関数が揺れた・§8)。

### 7.1 読み取った範囲の仕組み (未検証の推測)

- `cmd_batch` (`liftdiff.py`) は 400 件 chunk ごとに `run_functions` を呼ぶ (LD-96 §2・§8.1 と同じ)。`run_functions` は関数を shard ごとに分け、shard の中では同じ runner で順に実行する (`ldlib/session.py`)。よって shard 1 でも 800 関数が 1 つの runner で流れるわけではなく、runner は chunk 境界で作り直される。
- `ld_core.h` の `ld_case_begin` は、`keep` でない case で `ld_restore_all` (img・arena・heap を pristine へ戻す) を行う。heap の復元は `ld_model_reset` が `ld_heap_hw` までの範囲で行う。
- 推測 (未検証): wasm 側で snapshot 時点の high-water を超えて書かれた heap 領域が、後続 case で消えずに残る。LD-96 §8 はこの残存を wasm 側だけに見出したが、残存を持たない関数も揺れるため、これだけでは揺れを説明できない。

### 7.2 結論 (旧 commit `7d15ceab`・HEAD で追認)

- shard 1 の 19 関数の揺れは n=1 の暫定。HEAD の shard 1 (n=1) でも同じ 19 関数が揺れた (§8.3)。shard 配置が差に関わる可能性は残るが、断定しない (§7.3)。
- 負荷: shard 1 は開始 5.8・終了 0.9。shard 12 の r1 は開始 0.8・終了 6.0、r2〜r4 は開始 5.1〜7.1。4 vCPU のため、開始が 4 を超える run (shard 1・shard 12 の r2〜r4) は過負荷域から始まっている。負荷による説明の可否は §7.3 の通り判定不能。HEAD の shard 1 は開始 4.8 (§8.1)。
- 原因 (heap 残存か、他関数の状態持ち越しか) は未特定。LD-96 §8 の heap 全域比較の結論は §3.1 の通り。残件は #2681・#2682 (#2258 の子)。

### 7.3 分類 (4 軸 + 順序・既存の測定結果の再集計。測定 commit `7d15ceab`・`5b254578`・HEAD `33eef065` の結果を併記)

| 軸 | 判定 | 根拠 |
|---|---|---|
| native / wasm の timeout | **shard 12 では除外・shard 1 では除外できない** | shard 12 で `0x959a40` の揺れた case (p1・pall・qall) は committed 記録で native ok・wasm ok (§3)。HEAD の shard 1 では、19 関数の flip に wasm timeout 9 件・trap 3 件が混じる (§8.3)。負荷による wall-clock 超過かは未確認 (§6) |
| shard 配置 | **暫定: 関与する可能性 (n=1 ×2 session)** | 旧 commit の shard 1 (342/248/210) と HEAD の shard 1 (342/251/207) で、同じ 19 関数が match→mismatch。shard 12 では `0x959a40` の 1 関数だけ。shard 配置だけでは決まらない |
| 負荷 (1 分値・開始→終了) | **判定不能** | 旧 commit では shard 12 の r1 (開始 0.8) だけ一致。HEAD では shard 12 の r1 (開始 0.28) と r2 (開始 4.86) が一致、r3 (開始 6.30) が不一致。低い開始負荷と一致の対応は一貫しない |
| 順序 (session 内の run の位置) | **判定不能 (旧の「r1 だけ一致」は HEAD で不成立)** | 旧 2 session は r1 だけが一致。HEAD の shard 12 は r1・r2 が一致し r3 が不一致。順序の規則は再現しない |
| 単独 run (`--set file:`) | **揺れない** (`0x959a40` の 6 回) | 旧 commit の 4 回と HEAD の 2 回 (shard 12・1 各 1 回) の計 6 回とも `0x959a40` は `match` (p1・pall・qall は `equal`)。19 関数の solo (1 run) は LD-96 §8.3 で 19/19 `match`。全体 run の中でのみ出る |

- case 単位の `native_status`・`wasm_status` は、旧 commit の `results/ld58_m11_sample800_n3_5b254578.tsv` (r1〜r3 の行。r4 は件数のみ)、`results/ld58_m11_sample800_0x959a40_case_status.tsv` (§4)、HEAD の `results/ld58_head_sample800_cases.tsv` (全 run・全 case)。旧 commit の shard 1 の case 単位記録は committed に無い (§6)。HEAD の shard 1 では取った (§8.3)。
- 他の関数の case 単位では hang/timeout が run ごとに揺れる (`ld58_m11_sample800_n3_5b254578.tsv`・HEAD の `ld58_head_sample800_cases.tsv`)。ただし verdict は変わらず、件数揺れの源ではない (HEAD の shard 12 では 3 回とも同じ)。

## 8. HEAD 再測定 (`33eef065`)

### 8.1 方法と素材

- 素材と wasm build: §1 の通り。`sha256sum tools/liftdiff/work/m11/simd.c` は展開直後と wasm build の後で、どちらも `d82e27592c03a316`。`liftdiff.py build` は使わず、`build_wasm.build(load_target('targets/m11.json'), False)` で HEAD の rt を含む wasm を作った (link 3.6 s・全体 9.3 s)。
- 各 run は `liftdiff.py batch targets/m11.json --set <set> --shards <N> --nobuild --state auto --out work/m11/batch_head_<name>.jsonl`。run 名と load・wall は `work/m11/batch_head_runs.txt` (gitignore) に記録。
- 変換: `python3 ld58_head_summarize.py r1=... r2=... r3=... s1=... --verdict results/ld58_head_sample800_verdict.tsv --cases results/ld58_head_sample800_cases.tsv`。solo は同じ script を 1 run ずつ流した。

### 8.2 件数と verdict (HEAD)

| run | 設定 | 一致 | 不一致 | 実行不能 | `0x959a40` | load (開始→終了) | wall |
|---|---|---|---|---|---|---|---|
| r1 | sample:800・shard 12 | 361 | 232 | 207 | match | 0.28→5.74 | 106.8 s |
| r2 | sample:800・shard 12 | 361 | 232 | 207 | match | 4.86→6.85 | 109.1 s |
| r3 | sample:800・shard 12 | 360 | 233 | 207 | mismatch | 6.30→6.70 | 111.6 s |
| s1 | sample:800・shard 1 | 342 | 251 | 207 | mismatch | 4.80→1.03 | 390.1 s |
| solo12 | `file:` (`0x959a40`)・shard 12 | 1 | 0 | 0 | match (p1・pall・qall は equal) | 0.87→0.80 | 6.7 s |
| solo1 | `file:` (`0x959a40`)・shard 1 | 1 | 0 | 0 | match (p1・pall・qall は equal) | 0.32→0.29 | 6.5 s |

- HEAD で 800 関数の verdict が run 間で変わったのは 19 関数 (`results/ld58_head_sample800_verdict.tsv`)。このうち 18 関数は r1〜r3 で match・s1 で mismatch。`0x959a40` は r1・r2 match、r3・s1 mismatch。**19 関数は旧 commit の shard 1 の 19 関数と同じ**。
- 実行不能は 4 run とも 207。旧 commit の 210 とは 3 件違う (§6)。
- shard 12 の 3 回の中で、r3 だけ `0x959a40` が mismatch。旧 commit の「r1 だけ一致」の規則は HEAD では成立しない (§7.3)。

### 8.3 shard 1 の case 記録 (HEAD)

- 19 関数の shard 1 (s1) の case は 209 件: diff 81・native_fault 61・hang 26・both_fault 22・wasm_trap 12・equal 7。
- 同じ 19 関数の r1〜r3 では equal だった case のうち、s1 で `wasm_trap` になったのは 12 件: `0x6971f0` (p0・pall・u16・vm0)・`0xde10c0` (p0・p01・pall・u16・vm0) が `ok/timeout` の 9 件、`0x7850d0` (p0・pall)・`0x6cd900` (q0) が `ok/trap` の 3 件。
- よって shard 1 の flip は diff (81 件) だけでなく、wasm の timeout・trap を含む。旧 commit の「shard 1 の 19 関数は全ケース native ok・wasm ok」は未検証の推測だった (§7.3 で訂正)。
- 原因 (負荷による wall-clock 超過か、case の挙動か) は未確認。shard 1 の開始負荷は 4.80 (過負荷域から始まった)。

### 8.4 結論 (HEAD)

- shard 12 の件数は HEAD でも 361 付近 (3 回: 361・361・360)。揺れは `0x959a40` 1 関数のみ。
- shard 1 (n=1) は HEAD でも 19 関数が flip した。ただし flip には wasm の timeout・trap が混じるため、「timeout ではない」とは言えない。
- `0x959a40` の単独 run は HEAD の 2 回でも match。全体 run の中でのみ mismatch が出るという旧結論は、HEAD の shard 12 r3・shard 1 でも同じ向き。
- 受入 (b) の残り: shard 1 の 2 回目 (§6)。その他の HEAD 数値は本節で揃った。

### 8.5 観察: `liftdiff.py build` の simd.c 再生成

- `liftdiff.py build targets/m11.json` は `work/m11/simd.c` を再生成し、素材 (`work-liftdiff`) と内容が違った (sha256 `4c9ed1ff…` ≠ `d82e2759…`)。`ir_instr.ll`・`stubs.c`・`sigs.json`・`stubs.json` は素材と一致。
- 本測定 (HEAD) は素材版の `simd.c` を使った (`build_wasm.build(t, False)` は `work/m11/simd.c` が有れば再生成しない)。差の原因 (生成の非決定性か入力差か) は未確認。
