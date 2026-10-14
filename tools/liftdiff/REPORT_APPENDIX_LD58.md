# liftdiff REPORT 付録: LD-58 (#1637) 1801c67a0 の m8_fail 発火条件と sample:800 の件数揺れ

親 issue #1313 (LD-44)。前提は `REPORT_APPENDIX_LD44.md` §2・§3・§5。heap 残りの検証 (case 後に heap 全域を比較する計測) は `REPORT_APPENDIX_LD96.md` §8 (測定 commit `7d434168`) で実施済みで、本付録は数値を複製せず参照する。

## 結論

- 本付録の数値はすべて**旧 commit** (`5b254578`・`7d15ceab`) の測定。HEAD (`ee6ad3dc`) での再測定は未実施 (§6・§8)。HEAD のコードは測定 commit と差分があり (§5)、以下の結論は HEAD の結論ではない。
- 受入 (a): 入口ガードを外した再 build で、`1801c67a0` の u16・vm0 の `m8_fail` (wasm abort) は**消えた** (両方 `equal`)。発火点は `m8_rt.c` の入口ガードで、LD-44 の仮説 (arena 範囲外で弾いている) は、この試験で方向として支持された。ただし arena ポインタ値そのものは記録していない。
- 受入 (a) の副作用: 同じ再 build で `qall` は `both_fault` (native segv・wasm trap) から `native_fault` (native segv・wasm ok) に変わった。ガードを外すと wasm 側は trap せず進むため。ガードを外した版を本流に入れるかは別判断 (本 PR は測定のみ・コード変更なし)。
- 受入 (b): sample:800 を旧 commit `5b254578` で n=4 測定した (全体 run 4 回・件数は **361 / 360 / 360 / 360** (一致 / 不一致 / 実行不能 = 361/229/210, 360/230/210 ×3))。`7d15ceab` の shard 追試 (§7) でも同じ揺れのパターンが出た。
  - 件数揺れは `0x959a40` 1 関数の verdict だけ (shard 12)。shard 1 では 19 関数が揺れる (n=1 の暫定・§7)。
  - 揺れた case は `p1`・`pall`・`qall` で、**timeout ではない** (native・wasm とも ok で戻り値だけ不一致。§3)。
  - 単独 run (`--set file:` で `0x959a40` のみ、4 回) は 4/4 `match`。全体 run (4 回) は 1/4 `match`。LD-96 §8.3 の 19 関数 solo (1 run) も 19/19 `match`。
  - 揺れの原因は**未特定**。heap の高水位外の残存は wasm 側だけに出るが、残存を持たない関数も揺れるため、残存だけでは説明できない (LD-96 §8.3)。残件は #2681・#2682 (いずれも #2258 (LD-96) の子) に移した (§6)。
  - 最初の run (r1) だけが一致し、r2〜r4 が不一致になるパターンは 2 session (`5b254578`・`7d15ceab`) で出た。ただし r1 は開始負荷が最低で、負荷と run の順序が交絡しているため判定できない (§7.3)。
- 受入 (c): 測定 commit と `git diff` は §5 に記載。

## 1. 測定条件

- 測定 commit: `5b254578` (origin/main 当時の HEAD。その後の HEAD との差分は非空。§5)
- 測定 runner: 4 vCPU。load は `/proc/loadavg` の 1 分値。「開始」はその run の直前、「終了」は直後 (§7 の表記)。4 を超えると過負荷。§3 の load は `uptime` で記録したのは r1 のみ (開始 0.9・終了 5.7)。r2〜r4 の load は未記録。
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

## 3. 受入 (b): sample:800 の n=4 測定 (旧 commit `5b254578`・直列実行)

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

- timeout (native・wasm どちらか) による件数揺れ: **該当なし**。`0x959a40` の verdict 変化は両側 ok の case による。
- 揺れの源: **未特定**。単独で `match` になり、全体 run でのみ `diff` になる。heap 残りの検証 (case 後に heap 全域を比較) は LD-96 §8 で実施済み。結論は次の通り (数値は LD-96 §8.3 を参照): 高水位外の残存は wasm 側だけに出る。残存を持たない関数も揺れるため、残存だけでは揺れを説明できない。残りの原因 (他関数の状態持ち越し・負荷など) の切り分けは #2681・#2682 (LD-96 の子) の範囲。
- shard 配置は関与する可能性がある (shard 1 で 19 関数、shard 12 で 1 関数が揺れる・§7)。ただし shard 1 は n=1 の暫定。
- 件数 361 と 360 の差は、r1 の 1 回だけ出た。以後は 360 が 3 回続く。

## 4. 前回測定 (`2626e445`・参考・§3 とは別 commit)

前回の n=3 測定 (commit `2626e445`) は件数 361 / 361 / 360 で、`0x959a40` は r3 だけ `mismatch` だった。この値は §3 の `5b254578` とは別 commit の測定で、直接比較はできない。両者の間の `git diff --stat 2626e445 5b254578 -- <§5 のパス>` は 72 files / +3502 / -57 (§5 の範囲)。

- 前回の生データ: `work/m11/batch_head_r{1,2,3}.jsonl` (gitignore)。r1 の所要は 1m48.2s、r2・r3 は未計測。
- 前回の揺れも、同じく `0x959a40` 1 関数の verdict に限られていた。

## 5. 測定 commit と差分

- 再測定 (§3) の測定 commit: **`5b254578`** (origin/main)。
- 本節の再確認 (HEAD `ee6ad3dc` 時点): `git diff 5b254578 HEAD --stat -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt` = **190 files changed, 19894 insertions(+), 228 deletions(-)**。
- §7 の測定 commit `7d15ceab` からの同じ範囲の差分: `git diff 7d15ceab HEAD --stat -- (同じ範囲)` = **151 files changed, 11252 insertions(+), 359 deletions(-)**。
- 差分の中で測定に効きうるもの (未検証): `tools/liftdiff/rt/ld_core.h` の仮 proc の VMT slot 域 (LD-48 の `ld_fakeproc_vmt_init`・`ld_fakeproc_valid`)。`ld_snapshot` (SSNAP) から呼ばれるため、仮 proc の解決に効きうる。`ldlib/cases.py` の fvm 用 blob (`vmt`) も同じ差分に入る。
- 本付録の文書だけを変える commit を後に積んでも、上の範囲のコード差分は変わらない。
- よって §3・§7 の測定値は HEAD のコードに対応しない。HEAD での再測定は未実施 (§6・§8)。
- 生データ: `results/ld58_m11_sample800_n3_5b254578.tsv` (case 揺れと件数。ファイル名は n=3 だが中身は r1〜r4 の 4 run を含む。case 行は r1〜r3)。JSONL は `work/m11/batch_head_r{1..4}.jsonl` (gitignore)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD での再測定 (§8 の手順) が未実施。本 run は素材不足 (fl-win64 のみ) で wasm を build できなかった | §3・§7 の数値が HEAD に対応しない | 本 PR #2693 (`oc_artifacts` 行を付けた次の run で実施) |
| 件数揺れの原因 (heap 残存か、他関数の状態持ち越しか) | 件数 360/361 と shard 1 の 19 関数の説明 | #2681 (LD-121)・#2682 (LD-122)。どちらも #2258 (LD-96) の子 (移し元は #2258) |
| shard 1 の 19 関数の揺れは n=1 (暫定) | §7.3 の shard 配置の判定 | HEAD 再測定で 2 回目を取る (上の行) |
| shard 1 の 19 関数の case 単位の native・wasm 記録が committed に無い (`shards_t1.tsv` は verdict のみ) | §7.3 の「native ok・wasm ok」の根拠 | HEAD 再測定で `results/` の TSV に残す (上の行) |
| ガード緩和の本流への反映方法 (ガード範囲の arena 合わせ・関数単位の除外) | `1801c67a0` の u16・vm0 は本流 wasm で abort のまま | 本 PR の未解決表で追跡 (子は起票しない) |
| `qall` の native_fault への変化の解釈 (ガード緩和で wasm が進んだ後の native segv) | 緩和版の判定の妥当性 | 同上 |
| arena ポインタ実値の記録 | 「範囲外」の判定の確定 | 同上 |
| OTT 8 関数のうち 1801c67a0 以外の 7 関数の再確認 | LD-44 §2 の未実施分 | LD-57 (#1636) |

## 7. shard 数による差 (旧 commit `7d15ceab`・追試)

§3 の 4 回は shard 12 のみだった。shard 数を変えると件数が変わるかを追試した。測定 commit は `7d15ceab` (origin/main)。`7d15ceab` から HEAD までのコード差分は §5 の通り (151 files)。

- コマンドは §3 と同一 (`--set sample:800 --nobuild --state auto`)。`--shards 12` を 4 回、`--shards 1` を 1 回 (n=1)。
- 所要 (wall): shard 12 は r1 1m50s・r2 1m52s・r3 1m47s・r4 1m51s。shard 1 は 6m25s。
- load (`/proc/loadavg` 1 分値, 開始→終了。定義は §1): r1 0.8→6.0・r2 5.1→7.1・r3 7.1→6.4・r4 6.4→6.9・shard 1 5.8→0.9。4 vCPU。shard 1 は直前の shard 12 r4 (終了 6.9) の直後に開始した (開始 5.8)。
- 件数 (一致/不一致/実行不能): shard 12 は r1 361/229/210、r2〜r4 360/230/210。**shard 1 は 342/248/210**。

結果 (`results/ld58_m11_sample800_shards_t1.tsv`。verdict が run 間で変わる関数。列は va・r1〜r4 (shard 12)・s1 (shard 1)):

- shard 12 の 4 回で変わったのは `0x959a40` だけ (r1 match、r2〜r4 mismatch)。`p1`・`pall`・`qall` の wasm 側で `wasm_extra_entry` (`0x956550`) または `ret` の差。timeout ではない (§3 の case 行)。
- shard 1 では **19 関数** の verdict が match から mismatch に変わった (`0x959a40` を含む)。shard 12 の r1 とは一致しない。
- shard 1 で変わった関数の差分は主に wasm 側の heap の値 (`0xccccccccccc35b20`・`0xff800000ff800000` など、native は `unchanged(0x0)`) と `ret`・`calls` (`GetDeviceCaps` の引数)。ただし shard 1 の case 単位の記録は committed になく、「全ケース native ok・wasm ok」は未検証 (§6)。
- 修正前の §3.1 の「shard 数の差 (1 vs 12) では説明できなかった」は、この追試で**修正が必要**になった。shard 1 の方が件数が多く揺れる。ただし shard 1 は n=1 の暫定。

### 7.1 読み取った範囲の仕組み (未検証の推測)

- `cmd_batch` (`liftdiff.py`) は 400 件 chunk ごとに `run_functions` を呼ぶ (LD-96 §2・§8.1 と同じ)。`run_functions` は関数を shard ごとに分け、shard の中では同じ runner で順に実行する (`ldlib/session.py`)。よって shard 1 でも 800 関数が 1 つの runner で流れるわけではなく、runner は chunk 境界で作り直される。
- `ld_core.h` の `ld_case_begin` は、`keep` でない case で `ld_restore_all` (img・arena・heap を pristine へ戻す) を行う。heap の復元は `ld_model_reset` が `ld_heap_hw` までの範囲で行う。
- 推測 (未検証): wasm 側で snapshot 時点の high-water を超えて書かれた heap 領域が、後続 case で消えずに残る。LD-96 §8 はこの残存を wasm 側だけに見出したが、残存を持たない関数も揺れるため、これだけでは揺れを説明できない。

### 7.2 結論 (旧 commit `7d15ceab`)

- shard 1 の 19 関数の揺れは n=1 の暫定。shard 配置が差に関わる可能性は残るが、断定しない (§7.3)。
- 負荷: shard 1 は開始 5.8・終了 0.9。shard 12 の r1 は開始 0.8・終了 6.0、r2〜r4 は開始 5.1〜7.1。4 vCPU のため、開始が 4 を超える run (shard 1・shard 12 の r2〜r4) は過負荷域から始まっている。負荷による説明の可否は §7.3 の通り判定不能。
- 原因 (heap 残存か、他関数の状態持ち越しか) は未特定。LD-96 §8 の heap 全域比較の結論は §3.1 の通り。残件は #2681・#2682 (#2258 の子)。

### 7.3 分類 (4 軸 + 順序・既存の測定結果の再集計。測定 commit `7d15ceab`・`5b254578`)

| 軸 | 判定 | 根拠 |
|---|---|---|
| native / wasm の timeout | **除外** (shard 12 の範囲) | `0x959a40` の揺れた case (p1・pall・qall) は shard 12 の committed 記録 (r1〜r3) で native ok・wasm ok (§3)。shard 1 の 19 関数は case 単位の記録が committed に無く未確認 (§6) |
| shard 配置 | **暫定: 関与する可能性 (n=1)** | shard 1 (342/248/210) で 19 関数が揺れる (n=1)。shard 12 (361 / 360×3) では `0x959a40` の 1 関数だけ。shard 12 の内部でも揺れるため、shard 配置だけでは決まらない |
| 負荷 (1 分値・開始→終了) | **判定不能** | shard 12 の r1 (開始 0.8) は一致、r2〜r4 (開始 5.1〜7.1) は不一致。shard 1 (開始 5.8) は 19 関数が揺れる。低い開始負荷で一致した run は r1 の 1 回だけで、n が少なく相関は判定できない |
| 順序 (session 内の run の位置) | **判定不能** | 2 session (`5b254578`・`7d15ceab`) とも r1 だけが一致し、r2 以降が不一致。r1 は開始負荷が最低で、負荷と順序を分けられない。n=2 session のため偶然の可能性も残る |
| 単独 run (`--set file:`) | **揺れない** (`0x959a40` の 4 回) | shards 1 ×2・12 ×2 の計 4 回とも `0x959a40` は `match` (p1・pall・qall は `equal`)。19 関数の solo (1 run) は LD-96 §8.3 で 19/19 `match`。全体 run の中でのみ出る |

- case 単位の `native_status`・`wasm_status` は `results/ld58_m11_sample800_n3_5b254578.tsv` (r1〜r3 の行。r4 は件数のみ) と、前回 n=3 の `0x959a40` の case 単位記録 `results/ld58_m11_sample800_0x959a40_case_status.tsv` (§4)。shard 1 の case 単位の記録は committed に無い (§6)。
- 他の関数の case 単位では hang/timeout が run ごとに揺れる (`ld58_m11_sample800_n3_5b254578.tsv`)。ただし verdict は変わらず、件数揺れの源ではない。

## 8. HEAD 再測定の手順 (未実施・次の run 用)

素材を指定して次の run で実行する。手順の素材展開と simd.c の扱いは `REPORT_APPENDIX_LD96.md` §8.7 と同じ (素材版 `simd.c` の sha256 は `d82e2759…`。`liftdiff.py build` は使わない)。

- 素材: PR 本文の `oc_artifacts:` 行 (`fl-win64 toolchain-retdec toolchain-emsdk plugins-ott analysis-ott-binaries work-m6-ott work-liftlib work-m11 work-liftdiff`)。
- wasm は HEAD で build し直してから測る (`--nobuild` は既存 wasm を使うため、HEAD の rt 差分が測定に入らない)。
- 測定: `sample:800 --shards 12` を 3 回以上 (§3 と同条件)、`--shards 1` を 2 回、`--set file:` の `0x959a40` 単独を shard 1・12 で各 1 回以上。
- 各 run の case 単位の `native_status`・`wasm_status` を `results/` の TSV に残す (JSONL からの変換を含む)。
- 旧数値 (`5b254578`・`7d15ceab`) は §3・§7 に測定 commit を付けて残す。結論は HEAD の数値で書き直す (全 run の完了後)。
- 測り終えない run は §6 の未解決表に残し、測り終えた run だけで結論を書く。
