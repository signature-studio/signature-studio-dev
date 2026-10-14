# liftdiff REPORT 付録: LD-58 (#1637) 1801c67a0 の m8_fail 発火条件と sample:800 の件数揺れ

親 issue #1313 (LD-44)。前提は `REPORT_APPENDIX_LD44.md` §2・§3・§5。

## 結論

- 受入 (a): 入口ガードを外した再 build で、`1801c67a0` の u16・vm0 の `m8_fail` (wasm abort) は**消えた** (両方 `equal`)。発火点は `m8_rt.c` の入口ガードで、LD-44 の仮説 (arena 範囲外で弾いている) は、この試験で方向として支持された。ただし arena ポインタ値そのものは記録していない。
- 受入 (a) の副作用: 同じ再 build で `qall` は `both_fault` (native segv・wasm trap) から `native_fault` (native segv・wasm ok) に変わった。ガードを外すと wasm 側は trap せず進むため。ガードを外した版を本流に入れるかは別判断 (本 PR は測定のみ・コード変更なし)。
- 受入 (b): sample:800 を同一 commit `2626e445` で n=3 測定した。件数は **361 / 361 / 360** (一致 / 不一致 / 実行不能 = 361/229/210, 361/229/210, 360/230/210)。`0x959a40` の verdict は r1・r2 が `match`、r3 だけ `mismatch`。変化の原因は、この関数の変化した case が **native ok・wasm ok** (`p1`・`pall`・`qall` が r1・r2 は `equal`、r3 は `diff`) で、timeout ではない。同一 commit で揺れたため、LD-44 で観測した揺れ (92a145a5 の 361 と be017fb1 の 360) と同じ性質の run 間揺れと判断するが、**揺れの源 (native 側の非決定性・shard 配置・負荷のどれか) は切り分けていない**。
- 受入 (c): 測定 commit と `git diff` は §4 に記載。

## 1. 測定条件

- 測定 commit: `2626e445` (main HEAD。`git diff 2626e445 HEAD -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt` は空。§4)
- 測定 runner: 4 vCPU。load は測定中 0.0〜6.0 (`uptime`)。
- 素材: `fl-win64` (`FL_WIN64_DIR` = `[WIN64]`)・`work-m6-ott`・`work-m11`・`work-liftdiff`・`work-liftlib`・`analysis-ott-binaries` (`ANALYSIS_DIR` = `[ANALYSIS-DIR]`)・`plugins-ott` (`PLUGINS_DIR` = `[ANALYSIS-PLUGINS]`)・`toolchain-emsdk` (`[EMSDK]`)。全て展開を確認済み。
- 生データ (`work/` は gitignore): `work/m11/batch_head_r{1,2,3}.jsonl`・`work/m11/batch_head_r{1,2,3}.log`・`work/ott_noguard/run_1801c67a0.log`。

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

## 3. 受入 (b): sample:800 の n=3 測定

コマンド: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/batch_head_r{N}.jsonl` (commit `2626e445`, 3 回連続)。

| run | 一致 | 不一致 | 実行不能 | timeout を含むケース数 |
|---|---|---|---|---|
| r1 | 361 | 229 | 210 | 292 |
| r2 | 361 | 229 | 210 | 286 |
| r3 | 360 | 230 | 210 | 292 |

注: 所要時間は r1 のみ `time` で計測 (108 s・`real 1m48.192s`)。r2・r3 は計測していない。

- 件数揺れ (361 vs 360) の出所: `0x959a40` 1 関数の verdict (r3 だけ mismatch)。他の関数の verdict は 3 回とも同じ。
- `0x959a40` の case の変化: `p1`・`pall`・`qall` の 3 case。r1・r2 は `equal` (native ok・wasm ok)、r3 は `diff` (native ok・wasm ok)。**timeout ではない**。native と wasm が両方とも正常終了し、戻り値の比較だけが変わった。
- 分類 (case 単位の status は `results/ld58_m11_sample800_0x959a40_case_status.tsv`):
  - timeout (native・wasm どちらか) による件数揺れ: 該当なし (`0x959a40` の揺れた case は両側 ok)。
  - ただし timeout を含むケース数は 292 / 286 / 292 で run 間に揺れている。これは件数揺れの原因ではないが、揺れの存在は確認した。
  - 揺れの源 (native 側の非決定性、shard 配置、負荷のどれか): **未切り分け**。同一 commit で 361/360 が出ており、run 間の揺れとして扱う。
- 参考: 同一 commit `2626e445` の 3 回で件数が 361・361・360 と揺れたことは、LD-44 の `92a145a5` (361/360/360) と `be017fb1` (360/360/360) の差が commit 差分だけによるものではない可能性を示す。ただし 2 commit の比較は本 run では行っていない。

## 4. 測定 commit と差分

- 測定 commit: `2626e445`。
- `git diff 2626e445 HEAD -- tools/liftdiff/ldlib tools/m8 tools/ott tools/m11 tools/m6 tools/m9 tools/liftdiff/rt` = **空** (コード変更なし。本 PR は REPORT と `results/` のみ)。よって測定値は HEAD のコードに対応する。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ガード緩和の本流への反映方法 (ガード範囲の arena 合わせ・関数単位の除外) | `1801c67a0` の u16・vm0 は本流 wasm で abort のまま | 未起票。本 PR 対象外。`Refs #1637` の次 run で扱う |
| `qall` の native_fault への変化の解釈 (ガード緩和で wasm が進んだ後の native segv) | 緩和版の判定の妥当性 | 未起票。本 PR 対象外。`Refs #1637` の次 run で扱う |
| 0x959a40 の p1/pall/qall の native・wasm 値の差 (r3 のみ) の発生源 | 件数 361/360 の揺れの説明 | 未起票。本 PR 対象外。`Refs #1637` の次 run で扱う |
| arena ポインタ実値の記録 | 「範囲外」の判定の確定 | 未起票。`Refs #1637` の次 run で扱う |
| OTT 8 関数のうち 1801c67a0 以外の 7 関数の再確認 | LD-44 §2 の未実施分 | LD-57 (#1636) |
