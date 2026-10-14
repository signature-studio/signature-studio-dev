# liftdiff REPORT 付録: LD-58 (#1637) 1801c67a0 の m8_fail 発火条件と sample:800 の件数揺れ

親 issue #1313 (LD-44)。前提は `REPORT_APPENDIX_LD44.md` §2・§3・§5。

## 結論

- 受入 (a): 入口ガードを外した再 build で、`1801c67a0` の u16・vm0 の `m8_fail` (wasm abort) は**消えた** (両方 `equal`)。発火点は `m8_rt.c` の入口ガードで、LD-44 の仮説 (arena 範囲外で弾いている) は、この試験で方向として支持された。ただし arena ポインタ値そのものは記録していない。
- 受入 (a) の副作用: 同じ再 build で `qall` は `both_fault` (native segv・wasm trap) から `native_fault` (native segv・wasm ok) に変わった。ガードを外すと wasm 側は trap せず進むため。ガードを外した版を本流に入れるかは別判断 (本 PR は測定のみ・コード変更なし)。
- 受入 (b): sample:800 を同一 commit `5b254578` で n=4 測定した (全体 run 4 回・件数は **361 / 360 / 360 / 360** (一致 / 不一致 / 実行不能 = 361/229/210, 360/230/210 ×3))。
  - 件数揺れは `0x959a40` 1 関数の verdict だけ (r1 のみ `match`、r2〜r4 は `mismatch`)。他 799 関数の verdict は 4 回とも同じ。
  - 揺れた case は `p1`・`pall`・`qall` で、**timeout ではない** (native・wasm とも ok で戻り値だけ不一致)。timeout を含むケース数は run 間で揺れるが、件数揺れの原因ではない。
  - 単独 run (`--set file:` で `0x959a40` のみ、4 回) は 4/4 `match`。全体 run (4 回) は 1/4 `match`。**全体 run の中でのみ diff が出て、単独では再現しない**。
  - 全体 run でのみ出ることから、同じ worker・プロセスで先に走った他関数の状態の持ち越しが疑わしい。shard 配置は関与する (shard 1 で 19 関数、shard 12 で 1 関数が揺れる・§7)。ただし **原因は未特定** で、切り分けは子 #2682 に移した (§7.3 で分類まで)。
- 受入 (c): 測定 commit と `git diff` は §5 に記載。

## 1. 測定条件

- 測定 commit: `5b254578` (origin/main 当時の HEAD。その後の HEAD との差分は非空。§5)
- 測定 runner: 4 vCPU。load は `uptime` で記録したのは r1 のみ (開始 0.9・終了 5.7)。r2〜r4 の load は未記録。
- 素材: `fl-win64` (`FL_WIN64_DIR` = `[WIN64]`)・`work-m6-ott`・`work-m11`・`work-liftdiff`・`work-liftlib`・`analysis-ott-binaries` (`ANALYSIS_DIR` = `[ANALYSIS-DIR]`)・`plugins-ott` (`PLUGINS_DIR` = `[ANALYSIS-PLUGINS]`)・`toolchain-emsdk` (`[EMSDK]`)。全て展開を確認済み。
- 生データ (`work/` は gitignore): `work/m11/batch_head_r{1..4}.jsonl`・`work/m11/batch_head_r{1..4}.log`・`work/ott_noguard/run_1801c67a0.log`。

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

## 3. 受入 (b): sample:800 の n=4 測定 (HEAD `5b254578`・直列実行)

コマンド: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/batch_head_r{N}.jsonl` (commit `5b254578`, 4 回連続)。

| run | 一致 | 不一致 | 実行不能 | 所要 (wall) | 備考 |
|---|---|---|---|---|---|
| r1 | 361 | 229 | 210 | 1m49.8s | load 0.9→5.7。`0x959a40` は `match` |
| r2 | 360 | 230 | 210 | 1m45.8s | `0x959a40` は `mismatch` |
| r3 | 360 | 230 | 210 | 1m48.2s | `0x959a40` は `mismatch` |
| r4 | 360 | 230 | 210 | 1m44.3s | `0x959a40` は `mismatch` |

- 件数揺れ (361 vs 360) の出所: `0x959a40` 1 関数の verdict のみ。他の 799 関数の verdict は 4 回とも同じ。
- `0x959a40` の揺れた case は p1・pall・qall。r1 は `equal` (native ok・wasm ok)、r2〜r4 は `diff` (native ok・wasm ok)。**timeout ではない**。
- r2〜r4 の差分の中身 (p1): `ret` が native `0xffffd4e8` / wasm `0x2206ec00` で不一致、かつ `trace` に `wasm_extra_entry` (wasm が余分に関数 `0x956550` を通る)。
- 全 27 件の case 揺れ (3 回以上の run にまたがるもの) のうち、timeout・hang を含むものが大半 (native `hang`・wasm `timeout`/`crash`/`hang` の組)。`0x959a40` 以外の関数の verdict は揺れていない。
- 単独測定 (`--set file:` で `0x959a40` のみ、shards 1 ×2 / 12 ×2): 4 回とも `match` (p1・pall・qall は全て `equal`)。
  → **sample:800 の全体実行の中でのみ `diff` が出る**。単独では再現しない。

### 3.1 揺れの分類 (現時点の結論)

- timeout (native・wasm どちらか) による件数揺れ: **該当なし**。`0x959a40` の verdict 変化は両側 ok の case による。
- 揺れの源: **未特定** (§7.3 で 4 軸の分類まで)。単独で `match` になり、全体 run でのみ `diff` になるため、他の関数を同じ worker で先に走らせたときの状態の持ち越し (ld_wasm の共有 arena・heap の残り) が疑わしい。shard 配置は関与する (§7)。load は §7 で記録したが、相関は判定できない。切り分けには同一プロセス内で関数順を変える実験が要り、子 #2682 の範囲。
- 件数 361 と 360 の差は、r1 の 1 回だけ出た。以後は 360 が 3 回続く。

## 4. 前回測定 (`2626e445`・参考・§3 とは別 commit)

前回の n=3 測定 (commit `2626e445`) は件数 361 / 361 / 360 で、`0x959a40` は r3 だけ `mismatch` だった。この値は §3 の `5b254578` とは別 commit の測定で、直接比較はできない。両者の間の `git diff --stat 2626e445 5b254578 -- <§5 のパス>` は 72 files / +3502 / -57 (§5 の範囲)。

- 前回の生データ: `work/m11/batch_head_r{1,2,3}.jsonl` (gitignore)。r1 の所要は 1m48.2s、r2・r3 は未計測。
- 前回の揺れも、同じく `0x959a40` 1 関数の verdict に限られていた。

## 5. 測定 commit と差分

- 再測定 (§3) の測定 commit: **`5b254578`** (origin/main)。
- 本節の再確認 (本 PR 作成時・HEAD `d90b3220`): `git diff 5b254578 HEAD --stat -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt` = **190 files changed, 19894 insertions(+), 228 deletions(-)**。
- §7 の測定 commit `7d15ceab` からの同じ範囲の差分: `git diff 7d15ceab HEAD --stat -- (同じ範囲)` = **151 files changed, 11252 insertions(+), 359 deletions(-)**。
- よって §3・§7 の測定値は HEAD のコードに対応しない。HEAD での再現は本 PR では行っていない (ビルドと素材を伴うため)。再現は子 #2682 の範囲。
- 生データ: `results/ld58_m11_sample800_n3_5b254578.tsv` (case 揺れと件数。ファイル名は n=3 だが中身は r1〜r4 の 4 run を含む)。JSONL は `work/m11/batch_head_r{1..4}.jsonl` (gitignore)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x959a40 の全体 run だけで diff が出る原因 (他関数との状態持ち越し・負荷のどちらか) | 件数 360/361 の揺れの説明 | #2682 (前提: #2681) |
| shard 1 で 19 関数の verdict が変わる原因 (§7) | 全体 run の件数揺れの説明 | #2681 (前提) → #2682 |
| 測定 commit から HEAD までのコード差分 (§5: 190 files) | §3・§7 の分類が HEAD で再現するか未確認 | #2682 (HEAD 再測定を含める) |
| ガード緩和の本流への反映方法 (ガード範囲の arena 合わせ・関数単位の除外) | `1801c67a0` の u16・vm0 は本流 wasm で abort のまま | 本 PR の未解決表で追跡 (子は起票しない) |
| `qall` の native_fault への変化の解釈 (ガード緩和で wasm が進んだ後の native segv) | 緩和版の判定の妥当性 | 同上 |
| arena ポインタ実値の記録 | 「範囲外」の判定の確定 | 同上 |
| OTT 8 関数のうち 1801c67a0 以外の 7 関数の再確認 | LD-44 §2 の未実施分 | LD-57 (#1636) |

## 7. shard 数による差 (HEAD `7d15ceab`・追試)

§3 の 4 回は shard 12 のみだった。shard 数を変えると件数が変わるかを追試した。測定 commit は `7d15ceab` (origin/main。`git diff 7d15ceab HEAD` は本 PR のみ)。

- コマンドは §3 と同一 (`--set sample:800 --nobuild --state auto`)。`--shards 12` を 4 回、`--shards 1` を 1 回。
- 所要 (wall): shard 12 は r1 1m50s・r2 1m52s・r3 1m47s・r4 1m51s。shard 1 は 6m25s。
- load (`/proc/loadavg` 1 分値, 開始→終了): r1 0.8→6.0・r2 5.1→7.1・r3 7.1→6.4・r4 6.4→6.9・shard 1 5.8→0.9。4 vCPU。
- 件数 (一致/不一致/実行不能): shard 12 は r1 361/229/210、r2〜r4 360/230/210。**shard 1 は 342/248/210**。

結果 (`results/ld58_m11_sample800_shards_t1.tsv`。verdict が run 間で変わる関数):

- shard 12 の 4 回で変わったのは `0x959a40` だけ (r1 match、r2〜r4 mismatch)。`p1`・`pall`・`qall` の wasm 側で `wasm_extra_entry` (`0x956550`) または `ret` の差。timeout ではない。
- shard 1 では **19 関数** の verdict が match から mismatch に変わった (`0x959a40` を含む)。shard 12 の r1 とは一致しない。
- shard 1 で変わった関数の差分は主に wasm 側の heap の値 (`0xccccccccccc35b20`・`0xff800000ff800000` など、native は `unchanged(0x0)`) と `ret`・`calls` (`GetDeviceCaps` の引数)。全ケースが native ok・wasm ok で、timeout の差ではない。
- 修正前の §3.1 の「shard 数の差 (1 vs 12) では説明できなかった」は、この追試で**修正が必要**になった。shard 配置が差に関わる (shard 1 の方が件数が多く揺れる)。

### 7.1 読み取った範囲の仕組み (未検証の推測)

- `session.run_functions` は関数を shard ごとに `vas[i::shards]` で割り、shard の中では同じ `(nat, was)` の runner で順に実行する。shard 1 は全 800 関数を 1 つの runner で走らせる。
- `ld_core.h` の `ld_case_begin` は、`keep` でない case で `ld_restore_all` (img・arena・heap を pristine へ戻す) を行う。heap の復元は `ld_model_reset` が `ld_heap_hw` までの範囲で行う。
- 推測: wasm 側で snapshot 時点の high-water を超えて書かれた heap 領域が、後続の case で 0 クリアされず残る。shard 1 は同じ runner で多くの関数が走るため、この残りが後続関数に効く。ただしこれは読んだ範囲からの推測で、未検証。

### 7.2 結論 (本 run)

- 受入 (b) の「件数揺れと `0x959a40` の verdict 変化の出所を分類する」は、§7.3 の 4 軸 (timeout・shard 配置・負荷・単独 run) の判定までで完了とする。
- 原因 (他関数の状態持ち越しか負荷か) の特定は本 issue の範囲から外し、子 #2682 (前提 #2681) に移した。原因の確定には、heap の残りを検出する実験 (case 後に heap を全域比較) または関数順を変える実験が要る。
- 負荷は shard 1 で load が高くない (0.9〜5.8) ため、負荷だけでは説明しにくい (§7.3)。

### 7.3 分類 (4 軸・既存の測定結果の再集計。測定 commit `7d15ceab`・`5b254578`)

| 軸 | 判定 | 根拠 |
|---|---|---|
| native / wasm の timeout | **除外** | `0x959a40` の揺れた case (p1・pall・qall) は測定したすべての run で native ok・wasm ok。§3 |
| shard 配置 | **関与する (単独要因ではない)** | shard 1 (342/248/210) で 19 関数が揺れる。shard 12 (361 / 360×3) では `0x959a40` の 1 関数だけ。shard 12 の内部でも揺れるため、shard 配置だけでは決まらない |
| 負荷 (loadavg 1 分値) | **判定不能** | shard 12 の r1 (0.8→6.0) は一致、r2〜r4 (5.1〜7.1) は不一致。shard 1 (5.8→0.9) は 19 関数が揺れる。低負荷でも揺れ、高負荷の r1 は一致するため相関は見えない。n=5 のため否定もできない |
| 単独 run (`--set file:`) | **揺れない** | shards 1 ×2・12 ×2 の計 4 回とも `0x959a40` は `match` (p1・pall・qall は `equal`)。全体 run の中でのみ出る。状態の持ち越しが疑わしい (未検証) |

- case 単位の `native_status`・`wasm_status`: `results/ld58_m11_sample800_n3_5b254578.tsv` (r1〜r3 の行。r4 は件数のみ) と、前回 n=3 の `0x959a40` の case 単位記録 `results/ld58_m11_sample800_0x959a40_case_status.tsv` (§4)。
- 他の関数の case 単位では hang/timeout が run ごとに揺れる (`ld58_m11_sample800_n3_5b254578.tsv`)。ただし verdict は変わらず、件数揺れの源ではない。
