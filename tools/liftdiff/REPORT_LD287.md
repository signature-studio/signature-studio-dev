# liftdiff LD-287 (#5886) — `40c420` の戻り型を double に確定し `m11.json` へ反映 (受入 1)

> 親 #4429 (LD-215)・移送元 #4423 (LD-238)。前回の停止報告 (run 38919389757) の前提 (`40c420` の wasm 戻り 0) は #5888 (LD-288・PR #5896) で解消済み。

## 1. 結論

- `40c420` の戻り型は **double** に確定 (`native_x0` が 64bit 全体で一致)。`targets/m11.json` の `ret_override` に入れ、入口の xmm0 修正 IR (LD-288) を同時に入れた。
- 同時に入れた理由: `ret_override` だけでは `wasm_x0=0` の mismatch になる (LD-288 実測 1)。型と IR 修正は対で反映する。
- 候補 6 件のうち `40c420` 以外は **型を確定できなかった**。double / float のどちらでも一致せず、`1311ea0` は `unsupported_sig` で判定不能。詳細は §3。
- 45e1a0 群 6 件は m11 route では `unexec unsupported_sig` で判定不能。前回 run の native segv (全 pattern) と合わせ、理由を §4 に残す。
- 未確定 13 件は残件。経路追跡 (`call` の深さ超過) は今回広げていない。

## 2. 測定 (`40c420` の型確定と `--m11-only`)

| 項目 | 値 |
|---|---|
| 測定 commit | `e4f07955d` (`fix(liftdiff): type 40c420 return as double and restore its entry xmm0 in m11 (#5886)`。コードを変えた最後の commit) |
| 環境 | `FL_WIN64_DIR=$RUNNER_TEMP/ld5886` (fl-win64 を展開)・`EMSDK=$RUNNER_TEMP/ld5886/emsdk` (toolchain-emsdk)・`work/m11`・`work/liftdiff` は素材 work-m11 / work-liftdiff を展開 |
| 負荷 | 測定開始時 load average 1.13 (4 コア) |
| 単体 (修正後 `m11.json`) `run --fn function_40c420` | `verdict=match`・11 case 全 `equal` |
| e2e (`liftdiff_e2e.sh --m11-only`) | **PASS** (rc 0)・所要 215.2 秒 (3m35.182s wall)・user 5m51.3s |
| closure sample:800 | 801 件: **一致 360 / 不一致 236 / 実行不能 205**。LD-288・LD-233 と同値 |

## 3. 候補 6 件の型判定 (受入 1 の残り)

一時 target (`work/ld5886/t_{double,float}.json`・commit しない) で double / float を別々に実行した結果。

| 関数 | double | float | 判定 |
|---|---|---|---|
| `40c420` | match (64bit 一致) | match (下位 32bit) | **double に確定** (float は下位 32bit のみの比較で判定力が無い) |
| `ba05f0` | mismatch (wasm `0x7ff0…` = inf) | mismatch (`0x8000000` vs `0x0`) | 型で説明できない。未確定 |
| `6a3ac0` | mismatch (wasm 常に `0x0`) | mismatch (同) | 型で説明できない。入口 xmm の落ちの疑い (D5)。未確定 |
| `40f210` | mismatch (値が近いが不一致) | mismatch | 未確定 |
| `677820` | mismatch (wasm `0x80000000`・native `0x3f800000`) | mismatch | 未確定 (`movss` で読む・float 寄り) |
| `1311ea0` | unexec `unsupported_sig` | unexec | 判定不能 (引数 i128) |

- 6 件のうち確定したのは `40c420` の 1 件。残り 5 件は `ret_override` に入れていない (型が無いまま入れると誤った型を焼き込む)。
- `ba05f0` `6a3ac0` `40f210` `677820` は、型を変えても結果が変わらないか、wasm 側の値が native と桁から違う。`40c420` と同じ入口 xmm 落ち (D5) の可能性が残る。LD-288 と同様に入口型の確認が要る。

## 4. 45e1a0 群 6 件 (受入 3)

| 関数 | m11 route の判定 (HEAD) | 前回 run (38919389757) の記録 |
|---|---|---|
| 45e1a0・45e280・45e2e0・45eb00・45ecc0・45ed20 | `unexec unsupported_sig` (6 件とも) | native が全 pattern で segv (`native_null_deref_all_patterns` / `native_fault_all_patterns`) |

- 判定できない理由: native 実行が全 pattern で segv し、戻り経路 (rax / rdx / xmm0) を比べられない。m11 route でも `unsupported_sig` で wasm 側の比較に入らない。
- LD-158 の『判定不能 (全実行が segv)』と同じ扱い。解消には segv 関数の実行可能化が要り、#4423 (LD-238) が担当する。受入 3 は『判定できない件は理由を REPORT に記録する』で満たす。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/ld5886 EMSDK=$RUNNER_TEMP/ld5886/emsdk TMPDIR=$RUNNER_TEMP
python3 tools/liftdiff/liftdiff.py run tools/liftdiff/targets/m11.json --fn function_40c420 -v   # → verdict=match
bash tools/liftdiff/liftdiff_e2e.sh --m11-only                                                      # → LIFTDIFF_E2E PASS
```

## 6. 測定 commit からの差分

`git diff e4f07955d HEAD -- tools/liftdiff` は `REPORT_LD287.md` の新規追加 (67 行) のみ。コードは変えていないため、測定値は再取得していない。`docs/DOC_MAP.md` は 1 行追加。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 候補 5 件 (`ba05f0` `6a3ac0` `40f210` `677820`・`1311ea0`) の戻り型が未確定 | `ret_override` に入れられない。入口 xmm の落ち (D5) の可能性も残る | #5886 (親に残す) |
| 未確定 13 件の `call` 追跡 (経路の深さ超過) | 戻り型が決まらない | #5886 (親に残す) |
| 45e1a0 群 6 件の動的判定 (native segv) | 判定不能。理由は §4 | #4423 (LD-238) |
