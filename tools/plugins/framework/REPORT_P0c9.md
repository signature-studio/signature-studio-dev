# P0c-9 付録 — stage-1 成果物の素材化 (#610)

> **正本**: `tools/plugins/framework/REPORT.md`。本書は同 REPORT の P0c-9 節を 250 行上限のため分割移動したもの (内容の削除なし・元の節は Git 履歴にある)。

## P0c-9 (#610): stage-1 成果物の素材化 (部分達成・未完)

検証起点 commit: `8f55002` (origin/main)。既知類型との関係: DEFECTS.md の D1〜D16 に該当なし (インフラ変更)。

- 追加: allowlist に `work-fw-stage1` (`.github/scripts/prepare-event-context.sh`)・`fw_pack_stage1.sh` (pack/verify)・WORKFLOW §11 の記載。展開先は `tools/plugins/work/fw/` (= `fw_269_verify.sh` / `hs_e2e.sh` の既定 SRC)。pack 既定 OUT は `artifacts/work-fw-stage1.tar.zst` (`.gitignore` の `/artifacts/**/*` 対象)。
- 検証 (合成 12 ファイルで実施。実成果物ではない)。旧 (`55e5cb6`) と新の `verify` を同一入力で比較:

| ケース | 旧 verify (`55e5cb6`) | 新 verify |
|---|---|---|
| 正常 12 件 | rc=0 | rc=0 |
| 重複 (同一ファイルを 2 回格納。tar は 2 回目を hardlink で格納) | rc=0 (誤受理) | rc=1 (`出現 2 回`) |
| 重複 (内容の異なる実体を 2 回格納) | rc=0 (誤受理) | rc=1 (`出現 2 回`) |
| ディレクトリエントリ混入 | rc=0 (誤受理) | rc=1 |
| 空白入りの名前 `fw0.restored.ll x` | rc=0 (誤受理) | rc=1 |
| symlink (`fw0.restored.ll` → `fw1.restored.ll`) | rc=1 | rc=1 |
| r3 欠落 | rc=1 | rc=1 |
| r3 が 0 byte | rc=1 | rc=1 |
| 想定外エントリ (`extra.txt`) | rc=1 | rc=1 |
| fw_map.json 不正 JSON | rc=1 | rc=1 |

- 新 verify は名前を tar の 6 列目以降から切り出す (旧は `$6` で、空白入り名を誤って切っていた)。hardlink の `link to` 表記は名前から外して同名として数える。
- 想定外エントリ検査は `verify` に検査対象 tarball を渡した場合の結果。`pack` は `$FILES` のみを tar に入れるため pack 経路では発生しない。
- pack 既定 OUT (`artifacts/work-fw-stage1.tar.zst`) で生成 → `verify` rc=0 を確認済み (合成入力)。
- allowlist: `work-fw-stage1` を通し、`work-fw-bogus` と `work-fw-stage1x` を rc=1 で拒否。
- e2e (`fw_269_verify.sh` / `hs_e2e.sh`): 未実行。`$HOME/artifacts` には `fl-win64.tar.zst` と `toolchain-emsdk.tar.zst` のみで、`work-fw-stage1` は無い。
- **未達**: 実 stage-1 成果物はこの runner に無く (`tools/plugins/work/fw` 不在)、R2 への upload 権限も無いため、素材の実体・`fw_269_verify.sh` / `hs_e2e.sh` の PASS (FW_EXT_FUNCS 未指定/指定)・ext 対象関数一覧は未作成。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 stage-1 の梱包と R2 upload (`fw_pack_stage1.sh pack` → `artifacts/work-fw-stage1.tar.zst`) | 素材が無いと `oc_artifacts: work-fw-stage1` は `missing R2 object(s)` で失敗 | #610 (依頼者作業) |
| fw_269_verify.sh / hs_e2e.sh の FW_EXT_FUNCS 未指定・指定での再検証 | #311 受入条件 3 | #610 (素材 upload 後に再 run: `oc_artifacts: fl-win64 toolchain-emsdk work-fw-stage1`) |
| FW_EXT_FUNCS 対象 x87 関数の一覧と選定根拠 | 未決 | #197 / #610 |
