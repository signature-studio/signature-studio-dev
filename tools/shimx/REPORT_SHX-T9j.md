# tools/shimx REPORT 付録 — SHX-T9j (#2533) unit 23 の GetLastError を両版で読む

> 本体: `tools/shimx/REPORT_SHX-T9.md` §3.3.4 (親 #2489・#1985)。probe: `tools/m11/shimx_link/probe_lasterr_1985.mjs`。
> 証跡: `tools/shimx/evidence_2533/`。素材: `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-retdec toolchain-emsdk`。

## 1. 結論

- 受入 1 (probe): `probe_lasterr_1985.mjs` は commit `af6115db` (#1985) で追加済み。引数形式は `probe_flag_1985.mjs` と同じ。issue 本文の「repo に存在しない」は古い前提だった。
- 受入 2 (GetLastError を両版で読める export): `_GetLastError` を baseline (`tools/m11/m11_build.sh` の `EXPORTS`) と shimx (`tools/m11/shimx_link/build.sh` の `EXPORTS`) に 1 語ずつ追加 (測定 commit `0bdd046d`)。`-Wl,--export-all` だけでは `Module._GetLastError` にならないため必要だった。C 側の変更は無し。
- 受入 3 (両版で実測): 現行 `m11_ov.c` から baseline を再生成 (`m11_gen_ir2.sh` → `m11_build.sh`) し、shimx は `--trace --soft --fix` の clean rebuild で unit 23 を 1 回実行した。両版とも `ret=2`・icall-miss `0x457860` (2 件) で経路は一致した。unit 23 終了時の GetLastError は **baseline 0 / shimx 126**。
- 旧 snapshot 由来の `af6115db` の値 (baseline 1 / shimx 0) とは一致しない。unit 18・unit 22 の振る舞いが IR 再生成の後で変わっており、原因は IR 再生成と推定する (未切り分け・§4)。
- shimx 版の GetLastError=126 (`ERROR_MOD_NOT_FOUND`) が unit 22 で立つ呼出しは、後続の SHX-T9k (#2593) で特定済み: GetProcAddress の 1 回目の呼出し (hModule `0x56670`)。詳細は `tools/shimx/REPORT_SHX-T9k.md` §1 (§2.4 は本 PR 時点の記録として残す)。

## 2. 測定

### 2.1 受入条件の確認

| 受入 | 状態 | 根拠 |
|---|---|---|
| probe を追加 (`<m11_*.cjs 絶対パス> [idx 既定 22]`) | 達成 (af6115db) | `tools/m11/shimx_link/probe_lasterr_1985.mjs`。unit 1〜idx → idx+1 を 1 回 (trace) |
| GetLastError を両版で読める最小 export | 達成 (0bdd046d) | `EXPORTS` に `_GetLastError` を追加。両 build が `OK` |
| 両版で unit 23 の GetLastError を実測 | 達成 (本節) | §2.2・§2.3。両版とも clean rebuild |

### 2.2 unit 1〜22 と unit 23 (測定 commit `0bdd046d` の worktree で clean rebuild → probe)

| 項目 | baseline (再生成 `m11_boot.cjs`) | shimx `--trace --soft --fix` (clean rebuild) |
|---|---|---|
| unit 1〜17 の GetLastError | 0 (全て `ret=1`) | 0 (全て `ret=1`) |
| unit 18 | `ret=1 lasterr=0` | `exc=halt0 lasterr=0` |
| unit 19〜21 | `ret=1 lasterr=0` | `ret=1 lasterr=0` |
| unit 22 | `ret=1 lasterr=0` | `ret=1 lasterr=126` |
| unit 23 直前の gate | `P=0x11f10e0 slot=0x457860 flag=0` | 同左 |
| **unit 23 の結果** | **`ret=2` / GetLastError `0`** | **`ret=2` / GetLastError `126`** |
| unit 23 の trace | `icall 0x67f00` → `icall 0xf960` → `icall-miss 0x457860` ×2 | 同左 |

- 証跡: `evidence_2533/probe_lasterr_baseline_regen.txt`・`evidence_2533/probe_lasterr_shimx_trace_soft_fix.txt` (`UStrAsg` 行は一部省略せず全文)。
- unit 23 で GetLastError は変わらない (unit 22 の後の値をそのまま持つ)。差は unit 22 の時点で生じている。

### 2.3 旧 evidence (af6115db) との対照

| 版 | IR の出所 | unit 18 | unit 22 後 | unit 23 の結果・GetLastError |
|---|---|---|---|---|
| baseline 旧 snapshot (`evidence_1985/probe_lasterr_baseline_snapshot.txt`) | `work-m11` 同梱 `m11_boot.cjs` (2026-10-12) | `exc=OOB lasterr=0` | 0 | `halt0` / `1` |
| shimx `--fix` 旧 (`evidence_1985/probe_lasterr_shimx_fix_fresh.txt`) | 旧 `boot_final3.ll` | `exc=OOB lasterr=87` (unit 19〜21 も 87) | 0 | `ret=2` / `0` |
| baseline 再生成 (本 PR) | `m11_gen_ir2.sh` 再生成 (2026-10-14) | `ret=1 lasterr=0` | 0 | `ret=2` / `0` |
| shimx `--fix` clean rebuild (本 PR) | 同上 | `halt0 lasterr=0` | 126 | `ret=2` / `126` |

- 旧 IR の値 (af6115db) は、今回の再生成 IR では再現しない。baseline 側も unit 18 が OOB → ok に変わっており、IR 差が両版に効いている。
- 旧 IR で shimx を再ビルドして切り分けはしていない (旧 `boot_final3.ll` は上書き済み。sigs.h 等も同時に変わる)。「IR 再生成が原因」は**推定**。

### 2.4 unit 22 で GetLastError が 126 になる発生元 (未特定)

- shimx で `ERROR_MOD_NOT_FOUND` (126) を立てる箇所は `tools/shimx/src/module.c` の 197・207・228・240・289・330 行 (LoadLibrary / GetModuleHandle 系)。
- unit 22 だけ `shimx_set_trace(1)` と `SHIMX_TRACE=1` で走らせても shim の trace 行は出なかった (一時スクリプトはリポジトリ外。出力は空)。発生元 API は**未特定**。
- REPORT_SHX-T9 §3.3.1 の「unit 22 の `GetModuleHandleW("oleaut32.dll")` は非 NULL」とは別の呼出しと見るのが自然だが、未確認。
- 起票先: #2491 (`[SHX-T9i]`・unit 22〜23 の呼出し記録を拡張する作業) に合流。

## 3. 再現性 (WORKFLOW §6)

- 測定 commit: `0bdd046d` (コードを変えた最後の commit。`tools/m11/m11_build.sh` と `tools/m11/shimx_link/build.sh` の `EXPORTS` 各 1 語)。
- 検証: `0bdd046d` の worktree で clean rebuild → probe。main 側の先行測定 (同じ差分の作業ツリー) と同じ結果。
  - baseline: `rm -rf work/obj` → `FL_WIN64_DIR=… bash tools/m11/m11_build.sh` → `[m11build] OK` (`evidence_2533/build_baseline_regen.log`)。
  - shimx: `rm -rf work/shimx_link/obj work/shimx_link/gen_fix` → `bash tools/m11/shimx_link/build.sh --trace --soft --fix` → `[sxlink] OK trace_soft_fix: signature mismatch=1 undefined symbol=0 duplicate=0` (`evidence_2533/build_shimx_trace_soft_fix.log`)。
  - 両 build は同じ入力 (`work/` 配下の再生成物) で 30 秒程度 (15:05:46〜15:06:16)。`uptime` load 0.11〜0.27 (4 CPU)。
- 再生成 (IR): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_gen_ir2.sh` → `[gen_ir2] OK: work/boot_final.ll (490735 行)` (34 秒、rc 0)。PE は `fl-win64` の `extracted/block00031_PE.bin` (22227016 bytes) だけを展開して使用。
- image: `python3 tools/m11/m11_image_gen.py <PE>` を再実行して `work/m11_image.bin` を作り直したところ、sha256 は snapshot と一致 (`2d10d6926f3fd2b5…`)。PE 由来の成果物は現行 PE と整合。
- `llvm-nm work/obj/ov.o` の T シンボル: `function_410320`・`function_40f960`・`function_40fb40`・`function_467c40` の 4 つを確認 (`evidence_2533/ov_symbols_regen.txt`)。`#2489` の受入 1 に相当する確認。
- 生成物の sha256 (先頭 16 桁。順に `m11_boot.cjs`・`m11_sx_trace_soft_fix.cjs`): `49e6cce219f84655`・`66181f8fb2e3edea` (`evidence_2533/cjs_sha256.txt`)。
- `git diff 0bdd046d HEAD -- tools/m11 tools/shimx/src` の出力: 0 行 (本 PR の差分は REPORT・DOC_MAP・evidence のみ)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 22 で shimx 版の GetLastError が 126 になる発生元 → **特定済み** (GetProcAddress・`REPORT_SHX-T9k.md` §2.1)。hModule `0x56670` の出所 (`function_457c70` の未初期化 alloca の残存値) は未特定 | unit 22・23 の GetLastError 比較の解釈 | #1607 (`[SHX-T9e]`) |
| 旧 IR (`af6115db`) と再生成 IR で unit 18・22 の結果が変わった原因 (IR 再生成と推定・未切り分け) | 旧 evidence の値を根拠にできない | #2489 (`[SHX-T9h]`) の残り。PM が close 判断 |
| shimx 版 unit 18 `halt0` と baseline `ret=1` の差 (再生成 IR 上) | 両版の unit 単位差分 | 未起票 (`#1465` は CLOSED・`#2489` の比較に含める) |
