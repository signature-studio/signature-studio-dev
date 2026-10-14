# FA-13 (#905): rep movsb / stosw の実行到達の探索 (実測, 2026-10-14)

前回までの結論 (`REPORT_APPENDIX.md` §11) の後続。受入 1 (実行到達 scenario) と 2 (ネガコン FAIL) を
この run で再探索した。結論: **未達のまま**。受入の判定は変えない。

## 測定条件

- 測定 HEAD: `ec58d54b` (origin/main)。このコミットのコードは変更していない (一時 trap は元に戻し `cmp` 一致)。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk plugins-freshair`。`plugins-freshair` を
  `$RUNNER_TEMP/pf` に展開し `fetch.sh` で factory `.epf` 8 本を確認 (`win: 17 files, factory .epf: 8`)。
- `build_ctrl.sh` (trap 無し): exit 0, real 35.5 s, `lifted 1256 funcs / failed 0`。
- 一時版: `mlift/mlift_ops.py` の `h_rep_str` 先頭で `kind == 'movsb'` のとき `llvm.trap` + `unreachable` (movsb 39 サイト全体)。
  `build_ctrl.sh` exit 0, `lifted 1165 funcs / failed 0`, `ctrl build ok`。

## 実測

| 入力 | wasm 側 `unreachable` | native 側 | 判定 |
|---|---|---|---|
| 既定 `run_ctrl.sh 2 5` (seed `0xFA2C0001`) | 1 件 (S2001) | `ERR S2001 sig=5` (SIGTRAP) | 両側 ERR のため `run_ctrl.sh` は **PASS** (15/15) |
| seed `0xFA2C0002` | 0 | rc=134 (Aborted) | 判定外 |
| seed `0xFA2C0003` | 1 | rc=99, ERR 1 | 判定外 (両側 ERR) |
| seed `0x1` | 1 | rc=134, ERR 1 | 判定外 (両側 ERR) |
| seed `0x2` | 1 | rc=134, ERR 1 | 判定外 (両側 ERR) |
| seed `0x3` | 2 | rc=134, ERR 2 | 判定外 (両側 ERR) |
| seed `0xFA2C0010` | 1 | rc=134, ERR 1 | 判定外 (両側 ERR) |
| seed `0xFA2C0011` | 0 | rc=134, ERR 1 | 判定外 |
| epf 8 本のみ (乱数なし, seed `0x1`) | 0 | rc=0, ERR 0, 8/8 行 | 届かない |
| epf 8 本を 1 本ずつ | 0 (全 8 本) | — | 届かない |

- `run_ctrl.sh 2 5` の一時版は exit 0・PASS だった。ただし wasm の trap を踏んだ scenario (S2001) は
  native 側も同じ scenario で SIGTRAP しており、`run_ctrl.sh` は「両側で同一 scenario の ERR」を許容する。
  このため、movsb 経路に届いてもネガコンは FAIL にならない。

## 結論

- 受入 1 (movsb/stosw の実行到達 scenario): **未達**。movsb は structured / random scenario で wasm に届くが、
  その入力では native 側も ERR で落ちる (既知限界の乱数 OOB と同根)。native が正常終了する入力では届かない。
- 受入 2 (ネガコン FAIL): **未達**。native が ERR で落ちない入力は movsb に届かないため、
  「両側 ERR を許容しない」判定でも FAIL を作れない。
- stosw: 本 run では trap 版を作っていない (movsb の調査が先)。未確認。

## 受入 4: HEAD `ec58d54b` での lift2_e2e.sh (trap 無し, 実測)

- 実行: `TMPDIR=$RUNNER_TEMP FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/targets/freshair/lift2/lift2_e2e.sh` (foreground, rc=0)。
- 実測: `RESULT: lift2_e2e ALL PASS`, rc=0, real 1m14.228s, user 1m9.847s, load 0.38→0.98 (nproc 4)。
- 結果: comp 400/400 BIT-EXACT (non-grow 206/206・grow 194/194)・filter 400/400・fuzz 4 系統 mismatch 0 (各 1200, ERR 0/0)・ABI violations 0・ctrl 15/15 (fma0/fma1 とも `ERR native/wasm 1/1 同一 scenario: yes`)・ablation 5 種すべて検出 (comis_noflags 200/200, xmm_args_drop 200/200, xmm_ret_drop 200/200, icall_drop 80/200, cmov_drop 172/200)。
- 測定 commit: `ec58d54b` (コードを変えた最後の commit)。`8bc34ed9..ec58d54b` の lift2 コード差分は 218 行 (`git diff 8bc34ed9 ec58d54b -- tools/targets/freshair/lift2/ ':!*REPORT*'`)。
- 測定 commit から現 head までの鮮度 (WORKFLOW §6): `git diff ec58d54b HEAD -- tools/targets/freshair/lift2/ ':!*REPORT*'` の出力は 0 行 (差分 0)。`ec58d54b` 以降の変更は、lift2 配下が本ファイル (追記) のみ、リポジトリ全体では `docs/DOC_MAP.md` の索引 1 行。実行コードは不変。このため現 head で再測定はしていない。
- 素材の実在 (現 head での再測定を試みた run): `$ARTIFACTS_DIR` には `fl-win64.tar.zst` のみ。`toolchain-retdec` / `toolchain-emsdk` / `plugins-freshair` は無く、`/opt/retdec` も無いため、現 head での `lift2_e2e.sh` 再実行はできなかった。

## 追記 (stosw 単独 trap の到達確認, origin/main `60932d35`)

- 素材: `plugins-freshair` を展開し `fetch.sh` で factory `.epf` 8 本を確認。`build_ctrl.sh` (trap 無し) exit 0, real 36.9 s, `lifted 1256 / failed 0`。
- 一時版: `mlift_ops.py` の `h_rep_str` 先頭で `kind == 'stosw'` のとき `llvm.trap` (env `PROBE_STOSW` 指定時のみ)。`ctrl_full.ll` に `llvm.trap` 1655 件。`cmp` で元に戻し、`git status` 差分 0 を確認。
- 既定 `run_ctrl.sh 2 5` (seed `0xFA2C0001`): wasm / native とも `S2002` (または S2001) で ERR。両側同一 scenario のため PASS 扱い。
- seed 走査 (`gen_ctrl_scen.py 2 5 <seed>`、native 単独 rc と ERR 行を個別に計測):

| seed | native rc | native 行数 | native ERR 行 | wasm の trap 命中 |
|---|---|---|---|---|
| `0x1` / `0x2` / `0x3` / `0x4` / `0x5` | 134 (Abort) | 8〜10 / 15 | 0 | 1〜2 |
| `0x6` | 99 | 9 / 15 | 0 | 2 |
| `0x7` | 0 | 15 / 15 | `S2002` 1 件 | 1 |
| `0x8` | 134 | 8 / 15 | 0 | 2 |
| `0xFA2C0002` | 134 | 11 / 15 | 0 | wasm rc=1 (行 0) |
| `0xFA2C0003` / `0xFA2C0010` / `0xFA2C0011` | 99 / 134 / 134 | 8 / 8 / 8 | 0 | 1 / 1 / 0 |

- 注意: 前回までの ERR 集計 (`^ERR`) は行頭が `S… |ERR` の形を取りこぼしていた。seed `0x7` も native 側は `S2002 |ERR` (native の stderr も `ERR S2002 sig=5`) で、ERR 行は両側同一 scenario。
- 結論: stosw に届いた scenario は、いずれも native 側が ERR で落ちるか、native が途中で abort して行数が欠ける。native が 15 行正常終了し、かつ stosw の trap に届く入力は、今回の seed 走査では得られなかった。
- 受入 1 (stosw 実行到達 scenario): 未達。受入 2 (stosw 単独ネガコン FAIL): 未達。

## 次の作業 (起票先 #692 FA-11 に併記, 子 issue は起票しない)

1. native が ERR で落ちない structured 入力の設計 (意味 field への注入を制限する)。乱数 OOB を避ける生成条件を決める。
2. その入力で movsb / stosw trap が FAIL になることの実測。
3. 判定規則: 「両側で同一 scenario の ERR」は PASS に数えない版を別途検討 (現行 `run_ctrl.sh` の仕様変更は別 issue)。
