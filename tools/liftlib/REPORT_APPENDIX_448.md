# liftlib 付録 — CI-8 (#448): work-* 絶対 symlink の張り直しと lowbase_e2e [3] の素材 .so 不整合

親 #294 / 元報告 #440 (PR #445 の run)。本体の要約は [`REPORT.md` §24](REPORT.md)。

- **測定 commit**: `2f1b76fc` (コードを変えた最後の commit)。基準は origin/main `54bacdc0`。
- **作業場所**: worktree `$RUNNER_TEMP/ws-448` (branch `448-relink-workdir`)。main チェックアウトは触っていない。
- **素材**: `$ARTIFACTS_DIR` (`/home/runner/artifacts`) で fl-win64 / plugins-ott / toolchain-retdec / toolchain-emsdk / work-m6-ott / work-liftlib / analysis-ott-binaries の実在を ls で確認。

## 1. 受入 1・2: agent-setup の relink と張り直し件数

- 実装: `.github/actions/agent-setup/action.yml` L162〜184 (commit 81b0283a / 06b22b73、PR #449)。`/home/ubuntu/work/webstudio/*` を指す絶対 symlink を `$GITHUB_WORKSPACE` 内へ `ln -sfn` で張り直す。find は `tools/*/work/*` に限定し、失敗は `extract_failed` に計上する。
- 実測 (main チェックアウト、素材展開後):

| 項目 | 件数 |
|---|---|
| `tools/*/work/*` 配下の絶対 symlink (全て `$GITHUB_WORKSPACE` 内を指す) | 201 |
| 旧パス `/home/ubuntu/work/webstudio/*` を指す symlink | 0 |
| dangling (`tools/liftlib/work/wt_cab238/tools/targets/{kilohearts,freshair}/work`) | 2 |

- dangling 2 本は nested worktree (`wt_cab238`) 内の参照で、張り先 `tools/targets/{kilohearts,freshair}/work` は素材に含まれない。旧パスは 0 のため受入 2 は満たす。
- 同じ件数を worktree (`cp -a` で work/ を複製) でも再現 (201 / 0 / 2)。

## 2. 受入 3: `lowbase_e2e.sh` を手当てなしで通す

### 2.1 修正前: 素材の `libottnative.so` のまま → [3] が全 FAIL

- 素材 `work-m6-ott` の `tools/ott/work/libottnative.so` (mtime 2026-10-12 18:21) は `nm -D` で `ott_enc_slots` が 0 件。
- HEAD の `tools/ott/native/ott_native.c` は `ott_enc_slots` を定義する。この関数を追加したのは 214df2d6 (ICALL-51, 2026-10-14 08:05 UTC) と 4c69d5db (#2120, 2026-10-14 09:11 UTC)。素材はそれより前に作られている。
- 結果: `rc=1` / 193 s。[1] (audit_va) と [2] (liftlib ott 0x10000 / 0x1230000) は PASS。[3] は 3 構成とも 89 scenario 全 failed、cells 0。原因は `ottnat.py` の `CDLL` ロード時の `AttributeError: ... undefined symbol: ott_enc_slots`。
- 前回 run (3418333a, 2026-10-13) は素材 .so と HEAD が整合していたため PASS した。

### 2.2 修正 (commit 2f1b76fc)

- `tools/liftlib/lowbase_e2e.sh` の [3] の先頭で `bash tools/ott/native/build.sh` (`gcc -shared`) を実行し、`chk` で PASS/FAIL 判定する。`tools/ott/work/libottnative.so` は素材の物を使わず、HEAD ソースから作り直す。
- 差分: `tools/liftlib/lowbase_e2e.sh` 3 行追加 / 2 行削除 (前提コメントの libottnative 記述も更新)。

### 2.3 実測 (commit 2f1b76fc = HEAD、素材の古い .so を戻した状態)

- 実行: `bash tools/liftlib/lowbase_e2e.sh` (foreground、worktree で実行)。
- 結果: **rc=0 / 103 s / load avg (実行後 1 分) 0.96 / ALL PASS**。
  - [1] audit_va: 補正漏れ候補 0 → PASS
  - [2] liftlib ott `--lb-base 0x10000` / `0x1230000`: 両方 PASS (checks 8 / broken 0 / band maxdev 0.0)
  - [3] libottnative.so を HEAD から再ビルド → PASS。x64c 3 構成 (0x10000/16MiB, 0x1230000/40MiB, 0x10000/8MiB) × 89 scenario = **150,708 cell 全一致** (各構成 50,236 cell、max_ulp 0、state_diff_qwords 0)
- 手当ての有無: DLL は `ANALYSIS_DIR=/home/runner/analysis` (agent-setup が環境に設定) 経由で `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll` (sha256 `ecd51e05…`) を解決。手配置 0 件。Python 依存は `~/.local/agent-py` (#893) の venv が PATH 先頭。
- 先行確認: 修正前の検証で、素材 .so を手で `build.sh` 再ビルドした状態でも同じ結果 (rc 0 / 150,708 cell) だった。本測定は素材を戻した状態でスクリプト単独に通した結果。

### 2.4 測定 commit 以降のコード差分

`git diff 2f1b76fc HEAD -- tools/liftlib/lowbase_e2e.sh tools/ott/native tools/hostbridge/lowbase` は REPORT と付録の追加コミットのみで、コード範囲の差分は 0 行 (実行結果は PR 本文に記載)。

## 3. 未解決

- 素材 `work-m6-ott` の `libottnative.so` は HEAD と不整合。本修正は `lowbase_e2e.sh` の [3] だけを回避する。`tools/ott/native/ottnat.py` を読む他の経路は未確認。素材の再 pack は R2 の更新を伴うため本 run では行わない (起票先は PR 本文の未解決表)。
- 再現: `bash tools/liftlib/lowbase_e2e.sh` (素材 fl-win64 / work-m6-ott / work-liftlib / analysis-ott-binaries が必要、約 100 秒)。
