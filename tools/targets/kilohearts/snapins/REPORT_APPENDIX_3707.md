# REPORT_APPENDIX_3707 — KH-59 (#3707): emcc 段に RSS cap (rss_cap.py) を付けた実測

親 `REPORT.md` の付録。測定 commit は `bb4408cc4` (emcc を `tools/flelift/boot/rss_cap.py` 経由にした変更・コードを変えた最後の commit)。
環境: GitHub Actions runner (RAM 15,989MB・swap 3,071MB)。素材 `fl-win64` `plugins-kilohearts` `toolchain-retdec` `toolchain-emsdk` を展開して使用。
`work/winpkg` は Installer zip の Windows 側だけを展開した (`extract_installer.sh` の dmg 展開は省略)。

## 1. 変更内容

- `snapins/lift/build.py` と `license/lic_build.py` の emcc 呼び出しを `emcc_capped()` 経由にした。
  `python3 tools/flelift/boot/rss_cap.py --cap-mb ${KH_EMCC_RSS_CAP_MB:-11000} --interval 0.5 --log emcc_rss.log -- emcc ...`
- 上限超過時は子孫 PID だけ kill され (`rss_cap.py` の既存処理)、`[build] emcc RSS cap 超過: <name> peak=<MB>MB (cap=<MB>MB)` を出して非 0 で終わる。
- `stat.json` に `emcc_peak_rss_mb` を追加。`emcc` の引数・順序は変えていない (`source` の重複だけを外した。`sh()` が既に source する)。
- `.github/workflows/` は未変更。`rss_cap.py` は新規に書かず再利用した。

## 2. 出力不変 (受入条件 2)

入力 `gain` (`--path s0`) で、emcc の出力 5 本の sha256。変更前 (`origin/main` = `5ec4aef07` の同一コード) 1 回、変更後 2 回 (通常の `after`、`KH_EMCC_RSS_CAP_MB=200` の `negcap`)。すべて同一環境 (2026-10-15 03:33〜03:34 UTC)。

| ファイル | 変更前 (`base`) | 変更後 (`after`) | 変更後 (`negcap`・cap=200) |
|---|---|---|---|
| `final.ll` | d7980101e7f942c92ffd96f34de494b538dc0a276b34b2b431ebf7fdb953bb6b | d7980101e7f942c92ffd96f34de494b538dc0a276b34b2b431ebf7fdb953bb6b | d7980101e7f942c92ffd96f34de494b538dc0a276b34b2b431ebf7fdb953bb6b |
| `simd.c` | 751a8b41842fd75a0faab443ce0f92a9a6f9ef2bce47b33c834aeae1a9132506 | 751a8b41842fd75a0faab443ce0f92a9a6f9ef2bce47b33c834aeae1a9132506 | 751a8b41842fd75a0faab443ce0f92a9a6f9ef2bce47b33c834aeae1a9132506 |
| `globals.c` | 59ae076c50cb1a25e676c228951055e83d9ce8e9f453870ba33418488966c55d | 59ae076c50cb1a25e676c228951055e83d9ce8e9f453870ba33418488966c55d | 59ae076c50cb1a25e676c228951055e83d9ce8e9f453870ba33418488966c55d |
| `stubs.c` | 968f1f09bf792109dc4237741e6234f7632ab4d12a85eccbbc2ba029df078aa7 | 968f1f09bf792109dc4237741e6234f7632ab4d12a85eccbbc2ba029df078aa7 | 968f1f09bf792109dc4237741e6234f7632ab4d12a85eccbbc2ba029df078aa7 |
| `mod.wasm` | a8447893097d33b21f95c5ee52efa09bccdb94213fef8f991cec4d9c0dff16ed | a8447893097d33b21f95c5ee52efa09bccdb94213fef8f991cec4d9c0dff16ed | a8447893097d33b21f95c5ee52efa09bccdb94213fef8f991cec4d9c0dff16ed |

5 本すべて一致。RESULT 行は `mod.wasm` が同一なので同一 (gain の RESULT: `trials 200/200 bit-exact; calls 999/999`)。

## 3. ネガコン (受入条件 3) の結果

- `KH_EMCC_RSS_CAP_MB=200` で gain: **超過せず rc=0**。前提 (gain の emcc が 200MB を超える) は実測と合わない。
  gain の emcc は 0.5 秒未満で終わり、既定の 0.5 秒採取では fork 直後の 5MB しか取れない。
- 細かい採取 (`rss_cap.py --interval 0.02`、`emcc` の同一コマンドを 2 回・`work/gain/fine_{1,2}.rss.log`): **peak 82MB / 81MB**。よって gain は 200MB cap では超過しない。
- 超過経路の確認 (`KH_EMCC_RSS_CAP_MB=1` で gain): `[build] emcc RSS cap 超過: gain peak=6MB (cap=1MB)`、rc=1、`stat.json` 未出力、runner は生存。
- 実機の超過 (下表 4 本, cap=11000MB): 4 本とも同じ経路で非 0 終了 (rc=1)、runner は生存し、本付録まで届いた。受入条件 3 の「runner が生存して REPORT と PR まで届く」はこの 4 本で満たした。

## 4. 実測表 (`snapins/run_all.sh` の対象 14 本: matrix〜limiter の 13 本 + khbase、`--path s0`、`--trials 200 --seed 1`、compare 有り)

採取: emcc の RSS は `rss_cap.py` が 0.5 秒ごとに子孫の VmRSS 合計を採った最大値 (下限値)。0.5 秒より短い emcc は fork 直後の値しか取れないため、5〜6MB の行は実ピークではない (gain の実ピークは 82MB、§3)。`wall_s` は `build.py` 1 回の全体 (RetDec・lift・emcc・compare)。

| 入力 | rc | wall_s | emcc_sec | emcc peak (MB) | cap 超過 | final.ll (B) | globals.c (B) | defines | wasm (B) | compare |
|---|---|---|---|---|---|---|---|---|---|---|
| matrix | 0 | 13.4 | 0.7 | 5 (下限) | N | 31645 | 319 | 6 | 23206 | bit-exact 200/200 |
| gain | 0 | 2.2 | 0.7 | 6 (下限) | N | 42913 | 907 | 2 | 23054 | bit-exact 200/200 |
| haas | 0 | 14.1 | 1.2 | 72 | N | 107222 | 1636 | 10 | 35967 | bit-exact 200/200 |
| clipper | 0 | 14.0 | 1.2 | 82 | N | 89809 | 1999 | 6 | 37457 | bit-exact 200/200 |
| gate | 0 | 14.1 | 1.2 | 109 | N | 191040 | 1639 | 6 | 45754 | bit-exact 200/200 |
| quickeq | 0 | 18.9 | 3.2 | 955 | N | 779848 | 48759287 | 48 | 208237 | bit-exact 200/200 |
| resonator | 0 | 13.4 | 0.7 | 6 (下限) | N | 244640 | 7687 | 14 | 82697 | bit-exact 200/200 |
| stereo | 0 | 17.6 | 2.7 | 1132 | N | 336037 | 48729040 | 16 | 144986 | bit-exact 200/200 |
| disperser | 0 | 18.7 | 3.2 | 915 | N | 826147 | 48757286 | 48 | 209777 | bit-exact 200/200 |
| formant | 0 | 18.5 | 3.2 | 1069 | N | 602631 | 49401239 | 34 | 405390 | bit-exact 200/200 |
| **phaser** | **1** | 82.0 | — | **11237** | **Y** | 1461839 | **960709664** | 160 | — | 未実行 (kill) |
| **delay** | **1** | 97.7 | — | **11197** | **Y** | 2775052 | **1263683900** | 282 | — | 未実行 (kill) |
| **limiter** | **1** | 95.5 | — | **11122** | **Y** | 1817263 | **1255439321** | 216 | — | 未実行 (kill) |
| **khbase** | **1** | 96.9 | — | **11217** | **Y** | 2152241 | **1257571498** | 232 | — | 未実行 (kill) |

`emcc peak` の列は採取した最大値で、cap 超過 4 本は kill 時点の値 (11,000MB 超え)。

### module F (`license/lic_build.py --module F`)

- rc=0、wall 14.1 秒、emcc 1.2 秒、**emcc peak 112MB** (採取 0.5 秒の値。取り逃しの可能性あり)、cap 超過 N。
- `final.ll` 216127 B、`globals.c` 2524 B (9 globals)、wasm 54394 B、undefined imports 0。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| phaser・delay・limiter・khbase の emcc が cap 11000MB を超える (ピーク 11,122〜11,237MB)。`globals.c` が 0.96〜1.26GB。原因 (どの入力・どの global が支配するか) は未確定 | これら 4 本は cap で止まり、wasm が出ない。runner は落ちない | [KH-62] = #3756 (本 PR の子 issue) |
| 受入条件 3 の 200MB ネガコンは gain で成立しない (gain の実ピーク 82MB) | 文言の前提の誤り。超過経路は §3 の実機 4 本と KH_EMCC_RSS_CAP_MB=1 で確認済み | 本付録 §3 で記録。issue 文言の修正は PM 判断 |
| 0.5 秒未満の emcc の RSS は下限値 (fork 直後の値) | 表の 5〜6MB 行は実ピークでない。cap 判定も短い emcc では効かない | 採取間隔をさらに細かくするかは未決 (本 PR は 0.5 秒。短い入力は小さく、cap の目的である長い超過の検出には足りる) |

## 6. 測定 commit と差分 (WORKFLOW §6)

- 測定 commit: `bb4408cc4` (`snapins/lift/build.py` と `license/lic_build.py` の変更)。本付録の commit は測定値の記録だけ。
- 差分 0 の証跡: 本 PR の後続 commit (付録と DOC_MAP) のみ。`git diff bb4408cc4 HEAD -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/license` の出力は空であることを提出時に確認する。

## 7. main 取り込み後の再測定 (競合解消)

- 測定 commit: `25bb8c77b` (`origin/main` (`e13f1efd2`) の merge。競合は `docs/DOC_MAP.md` の索引表の 2 行追加のみで、コードは両側の自動マージ)。
- 差分 0 の確認: `git diff bb4408cc4 25bb8c77b -- tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/license tools/flelift/boot` の出力は 0 行。
- 環境は §2 と同じ runner。素材 `plugins-kilohearts` は `Kilohearts Offline Installer.zip` のみ取り出し、`scripts/extract_installer.sh` の Windows 側と同じ手順で `work/winpkg` を作った (dmg 側は省略)。

| 実行 | rc | wall (秒) | emcc (秒) | emcc peak (MB) | 結果 |
|---|---|---|---|---|---|
| gain (`--path s0 --trials 200 --seed 1`) | 0 | 13.8 | 1.2 | 30 (0.5 秒採取の値) | `RESULT trials 200/200 bit-exact; calls 999/999`・wasm 23054 B |
| gain (`KH_EMCC_RSS_CAP_MB=1`) | 1 | 1.4 | — | 5 | `[build] emcc RSS cap 超過: gain peak=5MB (cap=1MB)`・runner 生存 |
| module F (`license/lic_build.py --module F`) | 0 | 14.2 | 1.2 | 110 | wasm 54394 B・undefined imports 0 |
