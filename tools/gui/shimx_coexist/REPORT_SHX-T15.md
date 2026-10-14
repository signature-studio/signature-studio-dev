# REPORT_SHX-T15 — save 反映契機の自動結線 (#958 SHX-T15)

親: `tools/gui/shimx_coexist/REPORT.md` §11 / §6。測定 commit: **`59c74ab5`** (コード変更の最後の commit。クリーン worktree `ws-958` で実測)。ベースライン: `eeca4ded` (main)。

## 1. 結論

- 契機を決めた: **書込み用 file handle の `CloseHandle`** (shimx)。FL が保存先を開いて書き、閉じた時点で host が `HostCallBridge` の保存待ち先へ反映する。手動の `flushSaves()` は残した。
- #169 (レジストリの IndexedDB flush: `onYield` / `onPageHide`) とは別の契機。レジストリと wvfs の flush は変更していない。
- node harness (coexist) で自動反映を確認。**本番の起動 glue は未結線** (#134 の stage 6/6 が前提)。**保存後の再読み込み復元は未達** → 子 [SHX-T38] #3131。

## 2. 設計 (変更点)

| 層 | 変更 |
|---|---|
| shimx (`tools/shimx/src/handles.c`) | `shimx_set_file_close_hook(fn)` を追加。`CloseHandle` で `OBJ_FILE` かつ `GENERIC_WRITE`/`GENERIC_ALL` の handle を閉じたとき、その POSIX path を hook へ渡す (shx_lock 外、`shx_unref` の前) |
| gui (`tools/gui/src/gui_core_ext.inc`) | `gui_shimx_attach()` が hook を登録 (戻り bit3)。`gui_file_close` は path が stage 配下のときだけ `GUI_HC_FILE_CLOSED` (op 6) を host へ送る (timeout 30 s) |
| host (`src/runtime/gui_hostcall.ts`) | op `fileClosed`: `pendingSaves` に path があれば `flushOne` (読み出し → `SaveTarget.write`)。対象外は result 0。`flushSaves()` は同じ `flushOne` を使う |
| 検証 (`tools/gui/shimx_coexist/`) | `t_main.c` は save を FL と同じ `CreateFileW` → `WriteFile` → `CloseHandle` で書く。`run.mjs` は手動 `flushSaves()` を外し、自動反映だけで `saved` が一致することを検査 |
| 生成物 | `tools/shimx/data/sigs.json` と `exports.txt` を `gen_sigs.py` で再生成 (新公開関数の分) |

## 3. 検証 (測定 commit `59c74ab5`)

環境: ubuntu runner、emcc 6.0.12 (`/opt/emsdk`)、node 22、Chrome 155.0.8059.39。素材 `work-m11` の `boot_final3.ll` (sha1 `4a4a5fa01e`)。開始時 load average 1 分値 0.41–0.52。

| 検査 | 結果 | 所要 |
|---|---|---|
| `bash tools/gui/shimx_coexist/coexist.sh` | ALL PASS。link duplicate 0 / warning 0 / undefined 0。C 側 **69 PASS / 0 FAIL**、host 側 **13 PASS / 0 FAIL** (うち自動反映の検査 PASS) | 11.870 s |
| 変更前 `eeca4ded` の coexist (比較) | ALL PASS。C 側 68 / host 13 | 11.373 s |
| NC1 (shimx から weak を外す) | link rc=1、duplicate symbol 7 (§4.1 と同値) | — |
| NC2 (host 無し) | exit=1、C 側 fail **13** (変更前 14。save の fopen 検査 1 件を CreateFileW 検査へ置換したため) | — |
| NC3 (新規: `handles.c` の CloseHandle から hook 呼出しを外す) | link rc=0、run exit=1、自動反映の検査 **FAIL=1** (期待どおり) | — |
| `bash tools/gui/test/selftest.sh` | **506 passed / 0 failed** | 10.929 s |
| `EMSDK_ENV=/opt/emsdk/emsdk_env.sh bash tools/gui/shimx_coexist/browser_e2e.sh` | **14 PASS / 0 FAIL** (実 Chrome で window.open・picker・save 反映) | 11.443 s |
| `bash tools/gui/e2e.sh` | ALL PASS。OffscreenCanvas readback・on-screen screenshot とも golden **EXACT MATCH (0 px 差)**。sigprobe mismatch 0 / unresolved 0。stress EXACT MATCH | 2 分 38.888 s |
| `bash tools/shimx/test.sh --quick` | rc 0、7/7 PASS (MT/ST・M4 互換・verify_sig m11 / m11_3 mismatch 0) | 53.101 s |
| `tsc --noEmit` (`tsconfig.json`) | rc 0 | — |

- 初回の `shimx/test.sh --quick` は `sigs.json が shimx ソースと不一致` で FAIL した (新公開関数の未再生成)。`python3 scripts/gen_sigs.py` で再生成して解消。quick 実行は OTT 素材が無いため `BACKLOG.md`・`inventory.*`・`coverage.json` も書き換えるが、これは本 PR に含めず HEAD の版へ戻した (§5 と同じ方針)。
- 差分確認: `git diff 59c74ab5 HEAD -- src tools/gui tools/shimx/src tools/shimx/data tools/shimx/exports.txt` の出力は 0 行 (測定後のコード差分なし)。

## 4. 限界 (検証範囲)

- **実 FL の save 手順は未実測**。harness の C テストは「FL が返した Win パスへ CreateFileW → WriteFile → CloseHandle」を模している。
- **browser e2e は CloseHandle 経路を通らない**。`browser_page` は main を走らせないため、自動反映は node harness でのみ確認した。
- **本番の起動 glue は未結線**。`gui_shimx_attach()` と `HostCallBridge.start()` を呼ぶ経路が無い (#134 の stage 6/6 待ち)。本番では契機が働かない。
- **30 秒の host 応答 timeout**: 長い FSA 書込みが 30 s を超えると gui 側は待たずに進む。host の書込みは続くが、戻り時点の完了は保証されない。
- 閉じた stage 配下の書込み file ごとに host 往復が 1 回増える (保存待ちでない path は即 0)。実 FL での頻度は未測定。

## 5. 再現

```
bash tools/gui/shimx_coexist/coexist.sh           # M11_IR 既定 tools/m11/work/boot_final3.ll (work-m11 を展開)、emsdk は /opt/emsdk
EMSDK_ENV=/opt/emsdk/emsdk_env.sh bash tools/gui/shimx_coexist/browser_e2e.sh   # node_modules (tsc) を要する
```

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本番起動 glue への `gui_shimx_attach()` / `HostCallBridge.start()` の結線と、実 FL の save 手順 (CreateFileW → CloseHandle か) の実測 | 本番では save 反映が働かない | #134 (前提) → [SHX-T38] #3131 |
| 保存後の再読み込みで保存ファイルが復元される確認 (復元の保存先の設計を含む) | 受入条件 2 未達 | [SHX-T38] #3131 |
| 実 Chrome で CloseHandle 経路 (page で main を走らせる) | 現状は node のみで確認 | [SHX-T38] #3131 |
