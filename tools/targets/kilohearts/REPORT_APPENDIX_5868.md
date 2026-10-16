# REPORT 付録 (#5868 KH-178): `_DAT_1813a1d40` の型不一致 0 件化と Gain/Haas/Gate の `.o` 不変の確認

上位: `REPORT_APPENDIX_4671.md` §10-7y (FNPTR の規則)・`REPORT_APPENDIX_4911.md` (stereo の GTYPE)。

#### 結論

- **結論**: 関数ポインタ slot `_DAT_1813a1d40` の型不一致は、delay で 0 件、stereo で 2 件 (1300・1888) → 0 件になった。受入 3 (本 3 件の型不一致 0 件) は達成。
- 受入 4 (Gain/Haas/Gate の `.o` 不変) は達成。`origin/main` の規則で作った `.o` と `cmp` 一致 (3 本とも)。
- 変更: `patches.py` の `GTYPE['stereo']` に `'1813a1d40': 'FNPTR'` を 1 行足した (delay の規則と同じ型・同じ PE の同じ VA)。

#### 測定 commit

- 測定 commit (コードを変えた最後の commit): `500a6e024` (`fix(kilohearts): stereo の関数ポインタ slot を FNPTR で確定 (KH-178, #5868)`)。
- 基点: `origin/main` = `cf486ff00`。

#### 素材・環境

- `plugins-kilohearts` → Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B。REPORT と同サイズ)。
- `toolchain-emsdk` = emcc 6.0.12。Ghidra 12.1.4 (公式 release zip・sha256 先頭 `ddac49f9` 一致)。JDK 21 (temurin-21)。n=1。
- 作業場所: `$RUNNER_TEMP/kh` (repo 外)。

#### 測定 1: delay の census (`FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes`・`gtype_census.sh`)

| 項目 | 値 |
|---|---|
| delay の emcc error 行 | 277 |
| 演算・代入・ポインタの型不一致 | 81 |
| スロット呼出し 3 件 (生成 C の 4935・5947・6730) の error | 0 (4935 は `int` 代入でも error なし。5947・6730 は `-Wdeprecated-non-prototype` の warning のみ) |
| 測定の wall | 1 分 10 秒 (Ghidra 込み) |

- スロット 9 件の呼出し行 (生成 C の 2546・4034・4647・4768・4874・4935・4967・5947・6730) で、型不一致の error が出る行は 0 件。本 PR は delay の規則を変えていない (変更は stereo の GTYPE 1 行のみ) ので、delay の出力は origin/main と同一。本 PR で新たに消えたのは stereo の 1300・1888 のみ。

#### 測定 2: stereo の emcc (`stereo.c` 単体・`-w -O1 -Wno-error=...` 条件)

| 条件 | error 行 | 1300・1888 の error |
|---|---|---|
| GTYPE `stereo` に `1813a1d40` なし (前) | 42 | あり (`indirection requires pointer operand ('float' invalid)`) |
| GTYPE `stereo` に `1813a1d40: FNPTR` (後) | 40 | 消えた |

- 残り 2 件 (744・758): `longlong → void *` の `int-conversion`。今回の slot とは無関係の既存の癖 (`-Wno-error=int-conversion` 条件では error にならない)。

#### 測定 3: Gain/Haas/Gate の `.o` (`cmp`)

| 本 | 本 HEAD (`500a6e024`) の `.o` | `origin/main` の規則で作った `.o` | 判定 |
|---|---|---|---|
| gain | 1,435 B | 1,435 B | `cmp` 一致 |
| haas | 3,217 B | 3,217 B | `cmp` 一致 |
| gate | 3,756 B | 3,756 B | `cmp` 一致 |

- 比較の基点は `git archive origin/main tools/targets/kilohearts/ghidra_route` を展開した規則 (`gtype_census.sh` の第 2 引数)。
- gain・haas・gate の GTYPE は空なので、stereo の規則追加は効かない。

#### 差分 (`git diff 500a6e024 HEAD -- tools/targets/kilohearts/ghidra_route`)

- 測定 commit は HEAD と同一 (本節の commit が HEAD なら差分 0 行)。

#### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元の戻り値 int の bit-exact 検証 (5928 `FUN_180fd7f54` は読み手なし) | 型 int の正しさは未検証 | #4693 の未解決 (KH-112 の PR 本文) |
| stereo の数値突合 (1000 trial) | FNPTR を流用した stereo の値は未検証 | 親 #4911 のチェックリスト |
| stereo の残り error 40 行 (引数数不一致・`V128`・`longlong → void*` 等) | stereo の emcc は依然通らない | 親 #4911 のチェックリスト |

#### 再現

- `FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>` (第 2 引数に `origin/main` の `ghidra_route` を渡すと `.o` の `cmp` まで行う)。
- emcc は `PATH=<emsdk>/upstream/emscripten:<emsdk>/upstream/bin:$PATH EMSDK=<emsdk>` で直接通す (`toolchain-emsdk` の展開先は `emsdk/emsdk/` ではなく `emsdk/` 直下の `upstream/` だった)。
