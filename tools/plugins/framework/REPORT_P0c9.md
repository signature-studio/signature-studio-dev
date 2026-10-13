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
- e2e (2026-10-13, runner): `$ARTIFACTS_DIR` に `work-fw-stage1.tar.zst` (23,640,747 B) が実在。`fw_pack_stage1.sh verify` 12/12 OK → `tools/plugins/work/fw/` に展開。
- 初回 `fw_269_verify.sh` は三段で落ちた (いずれも既存コードの不備。修正して後段へ進んだ):
  1. snapshot が `tools/shared/env.sh` を含まず `fw_stage2.sh` が 0 s で exit 1 → `git archive` に `tools/shared` を追加。
  2. `liftlib/simd/gen.py` の `_params` が `CT[t]` で落ちる (`KeyError: 'g224'`)。`fw_stage2.sh` の DynTag が `iN` を `gN` に変換し `CT` に無いキーを渡す (b8e6855f #241 で `_stub` が `_params` 経由になった回帰)。→ `CT.get(t, "u128")` の寛容化。
  3. `pefile` / `capstone` 未導入 (WORKFLOW §11 の注記どおり) → `pip install --user`。`llvm-as` が emsdk 同梱に無く `/usr/lib/llvm-18/bin` を PATH に追加 (IR 検証用。emcc は emsdk の clang 24 のまま)。
- **実測 (commit d0e15d52 → 382c345a を含む HEAD、空の W から stage-2 全再構築)**:
  - `fw_269_verify.sh`: rc=0, `fw_stage2.sh` 428 s (load 2.78 2.22 1.35 → 継続), smoke ×3 PASS (dispatch=38 units_done=0 va=1 heap=1 ff=0)、smoke 同値 差分行=0/0、wasm 15,062,176 B (HEAD 参照 15,061,227 B に対し +949 B。`--size` 未指定のため照合は警告止まり)。
  - `hs_e2e.sh`: rc=0, 137 s。Phase B は `Phase B 例外: memory access out of bounds` を出すが、判定 (hs.mjs §判定) は `plug===0` 時の ID prefix 照合のみで、GOLDEN 6 ID すべて一致 → `E2E PASS`。`plug != 0` の完全生成は REPORT §7.1 の次段扱い (既存仕様)。
  - Phase B 例外の切り分け (レビュー指摘): origin/main の `gen.py` では `fw_stage2.sh` が `KeyError: 'g224'` で停止し `fw_image.bin` を生成できない。したがって origin/main では Phase B に到達せず、同素材の baseline は取得不可。本 PR の `_params` 修正 (`CT.get(t, "u128")`) が Phase B の例外を導入したかは未切り分け。修正後 HEAD の Phase B 挙動は本 run では未再実行 (素材 `work-fw-stage1` 未展開)。追跡 issue は未起票 (起票先: PM 判断)。
  - `_stub` (指摘 1 対応): `d0e15d52` の `_stub` 書き換えを元に戻した。未知タグ `?` を含む形と既知型形を含む 8 形で 56aa8795 と出力一致 (diff 0)。`['g224']` / `['x','g224']` の `_params` 経路は `u128` にフォールバックして正常生成 (旧版は KeyError)。
- 副作用の確認: `liftlib/simd/gen.py` の既知型 (x/d/q/b/y 等) の `_stub` 出力は origin/main と一致 (5 形で diff 0)。`tests/test_unit.py` は `m6/work` 等の素材が無く実行不可 (既存の前提)。
- **未達 (受入 3 の FW_EXT_FUNCS 指定経路)**: 本 run は既定経路 (FW_EXT_FUNCS 未指定) のみ検証。ext 指定時の e2e は未実施。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FW_EXT_FUNCS 指定 (ext 対象関数あり) 時の fw_269_verify.sh / hs_e2e.sh 再検証 | #311 受入条件 3 の残り | #197 (選定後に再 run) |
| FW_EXT_FUNCS 対象 x87 関数の一覧と選定根拠 | 未決 | #197 |
| `tests/test_unit.py` の素材依存 (`m6/work/ott.drc.ll` 等) | 単体テストが素材無しで実行不可 | 別途 (未起票・次 PM 判断) |
