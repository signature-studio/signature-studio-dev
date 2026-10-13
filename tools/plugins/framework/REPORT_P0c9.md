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
  3. `pefile` / `capstone` 未導入 (WORKFLOW §11 の注記どおり) → system python3 では `pip install --user` 後も import できなかったため `tools/plugins/framework/work/venv` に導入して PATH 先頭に置いた。`llvm-as` が emsdk 同梱に無く `/usr/lib/llvm-18/bin` を PATH に追加 (IR 検証用。emcc は emsdk の clang 24 のまま)。
- **実測 (検証 HEAD = 739a4fe1。3bdb1d74 に origin/main 570bcb73 を merge し REPORT を更新した commit。空の W から stage-2 全再構築、素材 fl-win64 + toolchain-emsdk + work-fw-stage1、2026-10-13 runner)**:
  - `fw_269_verify.sh`: rc=0, `fw_stage2.sh` 253 s (load 0.42 0.77 0.60 → 2.62 1.78 1.04), smoke ×3 PASS (81/81/81 ms, dispatch=38 units_done=0 va=1 heap=1 ff=0)、smoke 同値 差分行=0/0、wasm 15,062,169 B (`--size` 未指定のため照合は警告止まり)。
  - `hs_e2e.sh --fresh`: rc=0, 88 s (load 0.64 1.30 0.94 → 1.34 1.32 0.98), `E2E PASS`。Phase B は `Phase B 例外: memory access out of bounds` を出し、emcc 側の実行ログにも `Aborted(Runtime error: The application has corrupted its heap memory area (address zero)!)` が出る。判定 (hs.mjs §判定) は `plug===0` 時の ID prefix 照合のみで、GOLDEN 6 ID すべて一致 → `E2E PASS`。`plug != 0` の完全生成は REPORT §7.1 の次段扱い。
  - Phase B 例外の切り分け (レビュー指摘 2): 当初は「origin/main は `KeyError: 'g224'` で停止し baseline 取得不可」と記したが、**現 main (`99b87bc2`) では `fw_stage2.sh` は完走する** (下記 §#884)。`_params` の `CT.get` 修正 (382c345a) は main に入っている。
- **#884 切り分け (HEAD `99b87bc2` = origin/main、素材 fl-win64 + toolchain-emsdk + work-fw-stage1、runner 2026-10-13)**:
  - `fw_stage2.sh` (空の `tools/plugins/work/fw` から全再構築): rc=0, 433 s, load 0.21 0.53 0.28 → 2.33 2.28 1.17, smoke `dispatch=38 units_done=0 va=1 heap=1 ff=0` PASS。
  - `hs_e2e.sh --fresh`: rc=0, 159 s, load 2.05 2.22 1.16 → 1.08 1.72 1.13, Phase A smoke PASS, Phase B `memory access out of bounds` (`status=0xffffffff plug=0x0 rec=7`), `E2E PASS` (判定は plug===0 の ID prefix のみ)。同一バイナリで再実行 (`hs_route.cjs` は再ビルド不要のため 1 s) も同一の Phase B 例外を再現。
  - **`_params` の CT.get フォールバックの寄与**: `fw_flat4.ll` の `__asm_` 宣言 295 件を gen 入力で集計したところ、`CT` に無いタグは 0 件 (フォールバックは現入力で未使用)。フォールバックを外して (`CT[t]`) `gen.py` を再実行した `fw_simd.c` は既存出力と**バイト一致** (`cmp` 差分 0)。よって Phase B の OOB は CT.get 修正の副作用ではない。
  - Phase A の `RestoreContext` 直後にも同種の `Aborted(... corrupted its heap memory area (address zero)!)` が出るが、Phase A の smoke 判定は PASS (`dispatch=38 ff=0`)。
  - 結論: **回帰ではない** (origin/main 上で再現し、本 PR 由来の変更を外しても生成物が変わらない)。原因は REPORT.md §6・§7 の RTL fold deref (RetDec の引数定数折畳み) で、#985 `[PLG-P0b-1]` が追跡する。#884 の受入 1・2 はここで満たす。
  - 残件: `hs_e2e.mjs` の判定が Phase B 例外時に PASS となる点は #985 受入 2 で扱う (本件では未変更)。
  - `_stub` (指摘 1 対応): `d0e15d52` の `_stub` 書き換えを元に戻した。未知タグ `?` を含む形と既知型形を含む 8 形で 56aa8795 と出力一致 (diff 0)。`['g224']` / `['x','g224']` の `_params` 経路は `u128` にフォールバックして正常生成 (旧版は KeyError)。`gen.py` の PR 差分は `_params` の 1 行のみ。
- 副作用の確認: `liftlib/simd/gen.py` の既知型 (x/d/q/b/y 等) の `_stub` 出力は origin/main と一致 (5 形で diff 0)。`tests/test_unit.py` は `m6/work` 等の素材が無く実行不可 (既存の前提)。
- **#610 再検証 (HEAD = b37d20ac、素材 fl-win64 + toolchain-emsdk + work-fw-stage1、runner 2026-10-13)**:
  - 既定経路 (FW_EXT_FUNCS 未指定): `fw_269_verify.sh` ALL PASS (空の W から, `fw_stage2.sh` 318 s, load 0.44 0.68 0.58 → 2.57 1.81 1.07, smoke ×3 PASS, 差分行 0/0, wasm 15,062,169 B)。`hs_e2e.sh --fresh` E2E PASS (97.9 s)。Phase B `memory access out of bounds` は本節 1 段上と同一。
  - ext 指定 (`FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0`): `fw_269_verify.sh` ALL PASS (`fw_stage2.sh` 319 s, load 0.81 1.16 1.02 → 2.63 1.98 1.36, smoke ×3 PASS, 差分行 0/0)。`fw_f80.ll.ext.json` で `ext_functions: 4`・skip 0 を確認。ただし wasm サイズは既定と同一 15,062,169 B で、ext 化が最終 wasm に反映されたかは未確認。
  - ext 指定 (`function_5dfbe0,5dfc90,5dfd30,5dfdb0,5de820,5dedf0,5dfb60` の 7 関数): **fail**。`function_5dfb60` / `5dfbe0` / `5dfc90` が `skip:no-ext-values` で ext 化されず、`fw_f80.py` が exit 1 (fail-fast 設計どおり)。
  - `hs_e2e.sh` の ext 指定版: `FW_EXT_FUNCS=...` 付きで E2E PASS (97.9 → 99.2 s)。ただし hs は既定経路で生成済みの `fw_flat4_canon3.ll` を読むため、ext 版の中間生成物を経由していない。
  - 修正: `fw_269_verify.sh` の snapshot に `tools/plugins/p0c` を追加 (ext 指定時の `f80_lower.py` 不在を解消)。
  - 環境: `pefile` が runner の python3 に無く、venv (`uv pip install pefile capstone numpy`) を PATH 先頭に置いて実行。
- **未達 (受入 3 の FW_EXT_FUNCS 指定経路)**: 7 関数指定は 3 関数が ext 化不可。`fw_flat4_canon3.ll` を ext 版で再生成した e2e は未実施。ext 対象の選定根拠 (x87 関数の一覧) は未作成。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FW_EXT_FUNCS 指定 (ext 対象関数あり) 時の fw_269_verify.sh / hs_e2e.sh 再検証 | #311 受入条件 3 の残り | #197 (選定後に再 run) |
| FW_EXT_FUNCS 対象 x87 関数の一覧と選定根拠 | 未決 | #197 |
| Phase B `memory access out of bounds` の原因 | 回帰ではない (下記 #884 切り分け)。原因の RTL fold deref は #985 で追跡 | #985 (#884 は切り分け済み) |
| `tests/test_unit.py` の素材依存 (`m6/work/ott.drc.ll` 等) | 単体テストが素材無しで実行不可 | 別途 (未起票・次 PM 判断) |

## P0c-15 (#1253 / PR #1284): f80_lower --ext の RE_EXT_* をメタデータ付き行へ拡張

- 対象: `tools/plugins/p0c/f80_lower.py` のみ。測定 commit `7d8b7d51` (コードを変えた最後の commit)。
  `git diff 7d8b7d51 HEAD -- tools/plugins/p0c tools/plugins/framework` の出力は 0 行 (差分 0)。
- 旧版 (`7d8b7d51^` = `fff76e97`) の挙動: `RE_EXT_*` が行末 `\s*$` で止まるため、`, !insn.addr !N` 付き行に一致しない。
  `function_5dfd30` は `skip:no-ext-values` で ext 化されず、fw_f80.py は ext 指定で fail-fast する。
- 新版: 各 RE_EXT の行末を `(?:,\s*![\w.]+\s*!\d+)*\s*$` (メタデータ列許容) にし、行末前提だった 4 箇所も同様に直す。
  書換えが 0 件の関数は `status: skip:no-rewrite` (従来は `ext` で通っていた)。書換え件数は `rewritten` として出す。

### 書換え行のメタデータ (`!insn.addr`) の扱い (指摘 2 への判断)

`plans` は書換え行を組み直すため、書換えた行のメタデータは落ちる。判断は **「落としたままにする (コードは変えない)」**。根拠:

1. 後段で `insn.addr` を読む箇所は無い。`fw_stage2.sh` の f80 後段 (`base.normalize` → `fw_cleanup` → `fw_cefix` → `ir5_patch` 8 way → `fw_sigfix` → `fw_entry_fix` → `fw_cab129` → `ir_flatten` → `fw_canon` → `fw_ovpass` → `fw_table` → emcc) で、`insn` を読む処理は `base.normalize` (保持のみ) と `ir5_patch` の A7 (全 `, !name N` を除去) だけ。
   `fw_entry_fix.py:18` のコメント「ir5 の A7 が !insn.addr を除去する」と整合する。
2. 実測 (再現: `bash tools/plugins/p0c/p0c15_meta_ab.sh`): 書換え行にメタデータを付けた入力と付けない入力を `ir5_patch --keep-all` に通すと出力は byte 一致 (`[C] PASS`)。よって書換え行のメタデータは ir5 より後の出力に影響しない。
3. 落としたままの IR も `llvm-as` を通る (`[D] PASS`)。

書換え行の `!insn.addr` を残す案は、`plans` の全組み直し箇所に `, !insn.addr !N` を再付与する実装が要るが、読み手が無いため採らない。将来 f80 の後段で機械語 VA を読む処理が入る場合は、この節の根拠 1 が崩れるので再判断する。

### 実測 (測定 commit `7d8b7d51`、HEAD と差分 0)

- `p0c15_meta_ab.sh` (素材不要・合成 IR): old=`skip:no-ext-values` / new=`ext` (`rewritten` 3)。書換え無し入力は old==new (`cmp` 一致)。ir5 出力・llvm-as すべて PASS (exit 0)。
- 素材依存の実測 (作成者 run の記録。**本 fix run では再実行していない**。`$ARTIFACTS_DIR` に fl-win64 しか無く、toolchain-emsdk / work-fw-stage1 が無いため。再測定は #1283):
  - ext 指定 (`FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0`): fw_stage2 exit=0、所要 333 s、load avg 0.45 → 2.37。smoke ×3 dispatch=38 units_done=0 va=1 heap=1 ff=0 (3 回同値)。wasm 15,075,739 B。`fw_f80.ll.ext.json` の `rewritten` 26 / 10 / 49 / 71、全 4 関数 `ext`。
  - 既定 (FW_EXT_FUNCS 未指定): fw_stage2 exit=0、所要 326 s、load avg 2.16 → 2.43。smoke 同値。wasm 15,062,173 B。
  - `cmp` (ext と既定): DIFF (byte 94 から)。ext 経路が既定と異なる。
  - 受入条件 2 (書換え 0 件の関数は FAIL): `skip:no-rewrite` になり `fw_f80.py` の `status != 'ext'` 判定で FAIL。
  - `fw_269_verify.sh` の ALL PASS と `rewritten` 件数は、この fix run では再実行していない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 4: `hs_e2e.sh` の ext 版 E2E | 既定と ext 版の E2E 同等性が未確認 | #1283 (P0c-16, 親 #1253) |
| 受入条件 5: `skip:no-ext-values` 3 件の原因確定 | ext 化されない関数の原因が未特定 | #1283 |
| 素材依存の `rewritten` 件数・`fw_269_verify.sh` の再実行 | 本節の再測定が未実施 | #1283 |
