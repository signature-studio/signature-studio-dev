# shimx REPORT — SHX-T37 (#3070): HeapReAlloc・GlobalLock/GlobalUnlock/GlobalFree の不正入力の戻り値・errcode 判断

既知類型との関係: 該当なし (lift 欠陥ではなく shim の API 応答契約。`docs/DEFECTS.md` の類型には当たらない)。
親: #3023 (SHX-T35・closed)。関連: #2821 (native/wasm 応答表の統一)・#3056 (SHX-T35 の PR。HeapFree の TRUE 応答と blk_ok 範囲検査・merge 済み)。

## 結論

- **`tools/shimx/src` は変えない (直さない)**。不正入力の戻り値は M4 契約 (`tools/shim/test/test_main.c`) と MSDN の記載に一致する。errcode は M4 が検査せず、MSDN と一部食い違う (§2) が、値を変える根拠 (実機データ・アプリの依拠経路) が無いため、HeapFree と同じ errcode 契約の PM 判断に残す。
- **native 参照 (`tools/liftdiff/rt/ld_core.h`) は基準にできない**。GlobalLock・GlobalUnlock・GlobalFree の戻り値が MSDN・M4 と異なり、errcode を設定しないスタブである (§1)。
- **HeapFree は変更しない** (受入 3)。main の SHX-T35 (#3056・merge 済み) で HeapFree の範囲外は TRUE・ERROR_SUCCESS に揃い、`test.sh` step 5 (M4) は PASS する (§4.1)。HeapFree の errcode 契約は PM 判断として残る (§2.3)。
- **範囲外の 4B 整列値 (0xFFFFFFF0) の wasm trap は、SHX-T35 の範囲検査で消えた**。新しい HEAD の表本体で trap は 0 件。範囲検査を外した対照では 4 関数すべてが再び trap する (§3)。本 PR は heap.c に触れない。

## 1. 不正入力の戻り値と GetLastError (実測と文書の対照)

shimx の値は `tools/shimx/evidence_3070/run.sh` (ST ビルド・1 ケース 1 プロセス) の実測。errcode は呼び出し前に 0 へ戻した GetLastError で、0 は「呼び出しが設定しなかった」。M4 の行番号は `tools/shim/test/test_main.c` (測定 commit `5cca7cb4`。test_main.c は `875eba29` から変わっていない)。native は `tools/liftdiff/rt/ld_core.h` の `ld_model_call` (:245 から) の読み取り。GlobalLock :313・GlobalUnlock :314・GlobalFree :436 は明示分岐、HeapReAlloc は既定 :460 の 0。`ld_stub` (:462) は `ld_model_call` を呼んで記録するラッパ。

| 関数 | 入力 | shimx 戻り値 / errcode | M4 契約 | native 参照 | MSDN 記載 |
|---|---|---|---|---|---|
| HeapReAlloc | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (NULL) / 87 | NULL (:206。errcode 未検査) | 既定 0 (errcode 不変) | 失敗時 NULL。**失敗時は SetLastError を呼ばない** |
| GlobalLock | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (NULL) / 6 | NULL (:205。errcode 未検査) | **a0 をそのまま返す** (errcode 不変) | 失敗時 NULL。errcode の値は規定なし |
| GlobalUnlock | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (FALSE) / 6 | 未検査 | **1 (TRUE)** (errcode 不変) | 失敗時は 0 かつ NO_ERROR 以外 (値は規定なし) |
| GlobalFree | NULL | 0 (NULL) / 0 | 未検査 | 0 | 成功時 NULL |
| GlobalFree | 0x1・0x3・0x10・0x1000・0xFFFFFFFC | 入力値 / 6 | 入力値 (:207) | **0** (errcode 不変) | 失敗時は hMem を返す (errcode の値は規定なし) |
| 4 関数 | 0xFFFFFFF0 (4B 整列・範囲外) | 範囲内の不正入力と同じ応答 (上の行と同値)。trap なし (SHX-T35 後・§3) | — | — | — |
| 4 関数 | 解放済み (GlobalFree 後のポインタ) | HeapReAlloc 0/87・GlobalLock 0/6・GlobalUnlock 0/6・GlobalFree 入力値/6 | 未検査 | — | — |
| GlobalUnlock | 確保直後 (未ロック) | 0 / **158** (ERROR_NOT_LOCKED) | 未検査 | 1 | 未ロックは FALSE・ERROR_NOT_LOCKED (一致) |
| GlobalUnlock | Lock 1 回の後の Unlock (正常入力) | **1 (TRUE)** / 0 | TRUE (:165) | 1 | 解放後は 0・NO_ERROR (**MSDN と異なる。M4 が pin**) |

- 「一致」は shimx の戻り値・errcode が MSDN の記載と矛盾しないこと。値が規定されていない errcode は推定 (87 / 6)。
- 解放済みブロックの行は、解放後に header を読む経路を含む (shimx の `HeapFree` は magic を消してから free する)。結果は範囲内の不正入力と同じ応答だった。

## 2. 判断: 直さない

1. **戻り値は M4 と MSDN に一致する** (不正入力の全行)。shimx を native 側 (GlobalLock→入力値・GlobalUnlock→1・GlobalFree→0) に揃えると、M4 の :205・:207 と MSDN の記載に反する。
2. **native 参照は基準にできない**。`ld_core.h` は未対応の import に既定 0 を返すスタブ (HeapReAlloc はこれ) で、errcode を設定しない。GlobalLock・GlobalUnlock・GlobalFree は既定 0 ではなく明示分岐 (:313・:314・:436) で、戻り値は MSDN・M4 と異なる。native 側の直しと応答表の統一は #2821 の論点。`GlobalFree`・`LocalFree` の範囲外の応答 (native 0・shim は入力値) は #2821 側の未解決として残す。
3. **errcode は M4 が検査せず、値を変える根拠が無い**。HeapReAlloc の 87 は MSDN の「失敗時 SetLastError を呼ばない」と食い違う。ただし文書上アプリは GetLastError で詳細を読めず、観測可能な差は M4 でも native でも検査されていない。値の統一は HeapFree の errcode 契約と一括で PM 判断 (§6)。Global 系の 6 は MSDN が値を規定しないため推定で、実機未検証。
4. **GlobalUnlock の「Lock→Unlock で TRUE」は MSDN と異なる** (解放後は 0・NO_ERROR)。`heap.c` 冒頭の M4 互換の注記と M4 (:165) が pin しているため変更不可。

## 3. 範囲外 trap (0xFFFFFFF0) と負の対照

- 旧 main (`875eba29`) では 4 関数すべてが `RuntimeError: memory access out of bounds` で止まった。`blk_ok` が範囲検査の前にヘッダを読むため (0xFFFFFFF0 は 16B 整列で `(user & 15) == 0` を通る)。
- SHX-T35 (#3056・merge 済み) の `blk_ok` は範囲検査 (`u < HEAP_HDR || u > memory 長`) を先に行う。積は `uint64_t` で計算する。本 HEAD の表本体 (`work/probe.tsv`・34 行) で TRAP は 0 件。0xFFFFFFF0 の結果は `HeapReAlloc 0/87`・`GlobalLock 0/6`・`GlobalUnlock 0/6`・`GlobalFree 0xfffffff0/6` (範囲内の不正入力と同じ応答)。
- 負の対照: `run.sh` が `work/src_rc/` に範囲検査を外した複製 (`heap.c` の範囲検査行を旧版の 1 行に戻す) で同じ probe を回し、4 関数すべてが `RuntimeError: memory access out of bounds` で trap することを確かめる (`work/probe_rc.tsv`・4 行)。範囲検査の有無で trap が決まることの確認。
- 本 PR は `tools/shimx/src` を変えない。`run.sh` の対照部は、範囲検査が main に入った後も挿入位置が無くならないよう、「外す」向きに直した (旧版は範囲検査を入れる向きで、main では挿入位置が消えて `rc=1` になった)。

## 4. 検証 (測定 commit `5cca7cb4`)

測定 commit: `5cca7cb4` (コードを変えた最後の commit。`tools/shimx/evidence_3070/run.sh` の対照部を直した)。実測は `622a9276` (実測時の PR HEAD。`5cca7cb4` からの差分は REPORT のみ) で、各検証を 3 回ずつ foreground・直列に実行した。`origin/main` (`79d5e7c8`) とも対象範囲の差分は 0 行 (§4.4)。

### 4.1 `bash tools/shimx/test.sh` (step 5 を含む) — n=3・3 回とも rc=0 (全 step PASS)

| 回 | rc | 所要 (wall) | load average (1 分値・開始→終了) |
|---|---|---|---|
| 1 | 0 | 50.2 s | 0.37 → 0.73 |
| 2 | 0 | 48.5 s | 0.44 → 0.74 |
| 3 | 0 | 48.2 s | 0.70 → 0.91 |

- 所要の min–max: **48.2–50.2 s** (n=3)。並列数: 計測は 1 件ずつ直列 (並列 1)。スクリプト内では、オブジェクトビルド (`tools/shimx/scripts/build_objs.sh`) の emcc が 1 本ずつ直列 (1)、MT テストの pthread pool が 12 (`tools/shimx/flags.sh` の `SHIMX_EMCC_MT`)、M4 互換 MT の pool が 8 (step 5)。実行機の vCPU は 4 (`nproc`)。
- 3 回とも同じ結果: step 2 MT `PASS (8 グループ)`、step 3 ST `PASS`、step 4 fail-fast 13 件 + ExitProcess(7)、step 5 M4 (MT/ST) `PASS`、step 6b `sig_test ALL PASS` (verify_ott は SKIP: `tools/m8/work/ott_m8.ll` または `tools/m6/work` が無い)、step 7 `697 公開関数 × MT/ST × M4 互換 × fail-fast 全 PASS`。
- 旧測定 (`875eba29`) の step 5 FAIL (`test_main.c:203`) は、SHX-T35 (#3056) で HeapFree が M4 契約に揃ったため解消した。
- step 6 は inventory.md・BACKLOG.md・data/coverage.json・data/inventory.csv を再生成する。3 回の再生成結果は互いに同一 (`cmp`) だが、commit 済みとは一致しない。BACKLOG の件数は集計表の P0 行の件数列で、数え方は `grep -E '^\| P0 \| [0-9]+ \| [0-9]+ \|' tools/shimx/BACKLOG.md | cut -d'|' -f3`。commit 済み **194**、再生成後 **0** (3 回とも)。0 になる原因はコードで確認した: P0 は `work/ir_m11.json` と `work/ott/result.json` から作られ (`tools/shimx/scripts/gen_inventory.py` :99-100・:161-162)、どちらも M11・M8 の IR (`tools/m11/work/boot_final2.ll`・`tools/m8/work/ott_m8.ll`) が無いため作られない (実測時の `tools/shimx/work/` に `ir_m11.json` は無く、`ott/` は空)。
- 再生成した 4 ファイルは `git restore` で commit 済みに戻し、PR に含めない (`git status --short` は空)。

### 4.2 `bash tools/shimx/evidence_3070/run.sh` — n=3・3 回とも rc=0

| 回 | rc | 所要 (wall) | load average (1 分値・開始→終了) |
|---|---|---|---|
| 1 | 0 | 6.30 s | 1.24 → 1.20 |
| 2 | 0 | 6.33 s | 1.20 → 1.18 |
| 3 | 0 | 6.35 s | 1.18 → 1.17 |

- 所要の min–max: **6.30–6.35 s** (n=3)。並列数: 直列 1 (emcc は 1 回でビルドし、probe は node を 1 プロセスずつ起動する)。
- 3 回の表本体 (`tools/shimx/evidence_3070/work/probe.tsv`・34 行) と対照 (`probe_rc.tsv`・注記 1 行 + 4 行) は、それぞれ `cmp` で一致。表本体の TRAP は 0 件、対照の TRAP は 4 件 (§4.3)。
- 初期の修正: 対照の挿入位置 (旧 `blk_ok` の 1 行) が main の SHX-T35 で消えたため、`run.sh` が `rc=1` で止まった。対照を「範囲検査を外す」向きに直した (`run.sh` の対照部のみ・表本体の probe は変えていない。修正は `5cca7cb4`)。
- 実行には `EMSDK_ENV` (`docs/REFERENCES.md` の `[EMSDK]` = `/opt/emsdk/emsdk_env.sh`) が要る。本 run は `EMSDK_ENV=/opt/emsdk/emsdk_env.sh` で実行。

### 4.3 ネガティブコントロール

- 範囲検査を外した複製で 4 関数すべてが再び trap すること (§3・`probe_rc.tsv`)。3 回とも 4/4 TRAP。範囲検査の有無で 0xFFFFFFF0 の trap が決まる。
- M4 の HeapFree 検査 (step 5) は、SHX-T35 の前後で PASS/FAIL が変わる。旧測定の FAIL (`:203`) は再現しない (§4.1)。

### 4.4 差分・生成物

- `git diff 5cca7cb4 HEAD -- tools/shimx/src tools/shim/src tools/shim/test tools/shimx/evidence_3070` は 0 行 (最終 HEAD で確認)。実測時の `622a9276` でも 0 行。
- `git diff 622a9276 origin/main -- tools/shimx/src tools/shim/src tools/shim/test` は 0 行 (`origin/main` = `79d5e7c8`)。main の取り込みで測定対象は変わらない。
- 旧測定 (`875eba29`) からの差分は、`git diff 875eba29 0ff22979 -- tools/shimx/src tools/shim/src tools/shim/test` で 43 行 (`tools/shimx/src/heap.c` +6/-2 = SHX-T35 の範囲検査と HeapFree の TRUE 応答、`tools/shim/src/sync.c` +5/-1 = #2880 の CS-MISS 出力)。この差分を受けて再測定した。
- 差分の範囲を実行コードに絞った理由: 受入の `git diff 875eba29 HEAD -- tools/shimx` は本 PR が追加する REPORT と evidence だけを数える (既存ファイルの変更・削除は 0)。既存のコードが変わらないことを見るため、判定は実行コード (`src`・`shim/src`・`shim/test`) と測定対象の `evidence_3070` の範囲で行う。
- 20 MiB 超の blob: `find tools/shimx/evidence_3070 -type f -size +20M -not -path '*/work/*'` は 0 件。

## 5. 製品 KPI

起動・GUI に関わらない (shim の不正入力応答の表と判断のみで、コードは変えない)。KPI 対象外。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HeapReAlloc の errcode 87 と MSDN「SetLastError を呼ばない」の不一致 (§2.3) | 文書との差 (観測不能) | PM 判断 (HeapFree の errcode 契約と一括) |
| native 参照の GlobalLock・GlobalUnlock・GlobalFree の戻り値が MSDN・M4 と不一致 (§1・§2.2) | native と wasm の応答表が一致しない | #2821 |
| 実機 Windows の errcode 値 (87・6 の推定) は未検証 (§1) | 推定値のまま | #2821 (実機の素材は本 run に無く取得不可) |
| step 6 の再生成 (inventory.csv・BACKLOG.md 等) が commit 済みと一致しない (§4.1) | 生成物の正本が揺れる。本 PR は生成物を含めない | PM 判断 (step 6 の入力素材。`tools/m8` 成果物の要否) |

解決済み (main の SHX-T35・#3056 merge で解消): 0xFFFFFFF0 の wasm trap (§3)、`test.sh` step 5 の HeapFree FAIL (§4.1)。
