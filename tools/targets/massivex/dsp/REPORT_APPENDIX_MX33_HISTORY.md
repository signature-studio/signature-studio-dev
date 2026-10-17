# Massive X MX-33 (#3032) REPORT の旧測定記録 (分割移動)

- 本付録は `REPORT_MX33.md` §8 にあった MX-55 (#5030) 以前の測定記録を、内容を削らず移したもの。現行の測定値の正本は `REPORT_MX33.md` §5・§8。

## 1. 測定 commit 4840cc082 (MX-55 #5030) までの記録 (旧 REPORT_MX33 §8)

- 測定 commit = **`4840cc082`** (`feat(massivex): find vtable caller of 0x17b680 and check xmm2 arg (MX-55 #5030)`)。コードを変えた最後の commit (HEAD と同じ)。
  - 本 run の測定: `mx6_e2e.sh` exit 0・elapsed 59 s・load 0.50 0.56 0.27 → 0.82 0.64 0.31・PASS 32 件。`mx55_callers.py` exit 0 (REPORT_APPENDIX_5030 の呼出元の値)。
  - 前回 (実装 run・commit `d9edb0ad9`): 同じ `mx6_e2e.sh` で exit 0・elapsed 58 s。
  変更: `scripts/mx55_nonvec_float.py` (新規)・REPORT_APPENDIX_5030 §9。前回の測定 commit = `d106f3c23` (MX-37 #3774)。
- 測定 (MX-55 実装 run・`mx6_e2e.sh`・MX_PE = 展開 `Massive X.vst3`・md5 `622993e7…` 一致): **exit 0・elapsed 58 s・load 0.24 0.41 0.22 → 0.70 0.51 0.27**。
  mx55 の候補は **14 行 = 一意 13 関数** (REPORT_APPENDIX_5030 §9)。`mx6_e2e.sh` は `mx55` を呼ばないため、mx55 の件数は同じ素材での個別実行の値。
- **再現の状況**: 本 fix run (review 差し戻し対応) では `plugins-massivex` が `$ARTIFACTS_DIR` に無く (`fl-win64` のみ)、
  `Massive X.vst3` を展開できないため、上の e2e と mx55 は再実行していない。上の値は実装 run の記録。
  再測定は素材 `plugins-massivex` を付けて再起動した run で行う。
- 測定 commit から HEAD までのコード差分: `git diff d9edb0ad9 HEAD -- tools/targets/massivex/dsp/scripts` は `mx55_nonvec_float.py` の docstring の 1 行のみ (説明文の修正・判定ロジックは変えない)。
  `mx6_e2e.sh` は差分 0。
- 上の差分は docstring のみのため、測定値は測定 commit のコードに対するものとして扱う。
- MX-6 測定 commit (`fbc9971f`) からの変更 (`mx6_vectorcall.py` の +4/−1 行・`mx6_e2e.sh`) は、MX-6 の表示値を変えないことを e2e で確認した。
