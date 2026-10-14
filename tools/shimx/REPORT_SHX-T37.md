# shimx REPORT — SHX-T37 (#3070): HeapReAlloc・GlobalLock/GlobalUnlock/GlobalFree の不正入力の戻り値・errcode 判断

既知類型との関係: 該当なし (lift 欠陥ではなく shim の API 応答契約。`docs/DEFECTS.md` の類型には当たらない)。
親: #3023 (SHX-T35)。関連: #2821 (native/wasm 応答表の統一)・#3056 (SHX-T35 の PR。HeapFree の errcode と blk_ok 範囲検査・open)。

## 結論

- **`tools/shimx/src` は変えない (直さない)**。不正入力の戻り値は M4 契約 (`tools/shim/test/test_main.c`) と MSDN の記載に一致する。errcode は M4 が検査せず、MSDN と一部食い違う (§2) が、値を変える根拠 (実機データ・アプリの依拠経路) が無いため、HeapFree と同じ errcode 契約の PM 判断に残す。
- **native 参照 (`tools/liftdiff/rt/ld_core.h`) は基準にできない**。GlobalLock・GlobalUnlock・GlobalFree の戻り値が MSDN・M4 と異なり、errcode を設定しないスタブである (§1)。
- **HeapFree は変更しない** (受入 3)。main の M4 テストは #2821 の変更で HeapFree の範囲外に TRUE・ERROR_SUCCESS を期待し、shimx は FALSE・ERROR_INVALID_PARAMETER のため、`test.sh` step 5 が `test_main.c:203` で FAIL する (§4.1)。PM 判断待ち。
- **範囲外の 4B 整列値 (0xFFFFFFF0) は、4 関数すべてが wasm trap する** (main の実測)。`blk_ok` の範囲検査 (#3056 の A 項) で trap は消える (負の対照で確認・§3)。本 PR は heap.c に触れず、#3056 と衝突しない。

## 1. 不正入力の戻り値と GetLastError (実測と文書の対照)

shimx の値は `tools/shimx/evidence_3070/run.sh` (ST ビルド・1 ケース 1 プロセス) の実測。errcode は呼び出し前に 0 へ戻した GetLastError で、0 は「呼び出しが設定しなかった」。M4 の行番号は `tools/shim/test/test_main.c` (測定 commit `875eba29`)。native は `tools/liftdiff/rt/ld_core.h` の `ld_model_call` (:245 から) の読み取り。GlobalLock :313・GlobalUnlock :314・GlobalFree :436 は明示分岐、HeapReAlloc は既定 :460 の 0。`ld_stub` (:462) は `ld_model_call` を呼んで記録するラッパ。

| 関数 | 入力 | shimx 戻り値 / errcode | M4 契約 | native 参照 | MSDN 記載 |
|---|---|---|---|---|---|
| HeapReAlloc | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (NULL) / 87 | NULL (:206。errcode 未検査) | 既定 0 (errcode 不変) | 失敗時 NULL。**失敗時は SetLastError を呼ばない** |
| GlobalLock | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (NULL) / 6 | NULL (:205。errcode 未検査) | **a0 をそのまま返す** (errcode 不変) | 失敗時 NULL。errcode の値は規定なし |
| GlobalUnlock | NULL・0x1・0x3・0x10・0x1000・0xFFFFFFFC | 0 (FALSE) / 6 | 未検査 | **1 (TRUE)** (errcode 不変) | 失敗時は 0 かつ NO_ERROR 以外 (値は規定なし) |
| GlobalFree | NULL | 0 (NULL) / 0 | 未検査 | 0 | 成功時 NULL |
| GlobalFree | 0x1・0x3・0x10・0x1000・0xFFFFFFFC | 入力値 / 6 | 入力値 (:207) | **0** (errcode 不変) | 失敗時は hMem を返す (errcode の値は規定なし) |
| 4 関数 | 0xFFFFFFF0 (4B 整列・範囲外) | **wasm trap** (4 関数とも) | 到達せず (:203 で停止) | — | — |
| 4 関数 | 解放済み (GlobalFree 後のポインタ) | HeapReAlloc 0/87・GlobalLock 0/6・GlobalUnlock 0/6・GlobalFree 入力値/6 | 未検査 | — | — |
| GlobalUnlock | 確保直後 (未ロック) | 0 / **158** (ERROR_NOT_LOCKED) | 未検査 | 1 | 未ロックは FALSE・ERROR_NOT_LOCKED (一致) |
| GlobalUnlock | Lock 1 回の後の Unlock (正常入力) | **1 (TRUE)** / 0 | TRUE (:165) | 1 | 解放後は 0・NO_ERROR (**MSDN と異なる。M4 が pin**) |

- 「一致」は shimx の戻り値・errcode が MSDN の記載と矛盾しないこと。値が規定されていない errcode は推定 (87 / 6)。
- 解放済みブロックの行は、解放後に header を読む経路を含む (shimx の `HeapFree` は magic を消してから free する)。結果は範囲内の不正入力と同じ応答だった。

## 2. 判断: 直さない

1. **戻り値は M4 と MSDN に一致する** (不正入力の全行)。shimx を native 側 (GlobalLock→入力値・GlobalUnlock→1・GlobalFree→0) に揃えると、M4 の :205・:207 と MSDN の記載に反する。
2. **native 参照は基準にできない**。`ld_core.h` は未対応の import に既定 0 を返すスタブ (HeapReAlloc はこれ) で、errcode を設定しない。GlobalLock・GlobalUnlock・GlobalFree は既定 0 ではなく明示分岐 (:313・:314・:436) で、戻り値は MSDN・M4 と異なる。native 側の直しと応答表の統一は #2821 の論点。`GlobalFree`・`LocalFree` の範囲外の応答 (native 0・shim は入力値) は #2821 側の未解決として残す。
3. **errcode は M4 が検査せず、値を変える根拠が無い**。HeapReAlloc の 87 は MSDN の「失敗時 SetLastError を呼ばない」と食い違う。ただし文書上アプリは GetLastError で詳細を読めず、観測可能な差は M4 でも native でも検査されていない。値の統一は HeapFree の errcode 契約と一括で PM 判断 (#3056 の未解決表)。Global 系の 6 は MSDN が値を規定しないため推定で、実機未検証。
4. **GlobalUnlock の「Lock→Unlock で TRUE」は MSDN と異なる** (解放後は 0・NO_ERROR)。`heap.c` 冒頭の M4 互換の注記と M4 (:165) が pin しているため変更不可。

## 3. 範囲外 trap (0xFFFFFFF0) と負の対照

- main では 4 関数すべてが `RuntimeError: memory access out of bounds` で止まる。`blk_ok` が範囲検査の前にヘッダを読むため (0xFFFFFFF0 は 16B 整列で `(user & 15) == 0` を通る)。
- 負の対照: `run.sh` が `work/src_rc/` に範囲検査 (`u < HEAP_HDR || u > memory 長`) を入れた複製で同じ probe を回した。判定は #3056 の A 項と同じだが、積の型が違う (本 run は `uintptr_t` の積 `(uintptr_t)__builtin_wasm_memory_size(0) * 65536u`、#3056 は `uint64_t` で計算)。wasm32 でメモリが 4 GiB (65536 ページ) のときだけ、本 run の積は 0 に溢れて全入力を範囲外と判定する。0xFFFFFFF0 の結果はこの差に影響されない (メモリはそれより小さい)。`work/probe_rc.tsv`:
  `HeapReAlloc 0/87`・`GlobalLock 0/6`・`GlobalUnlock 0/6`・`GlobalFree 0xfffffff0/6`。trap は消え、範囲内の不正入力と同じ応答になる。
- 本 PR は `tools/shimx/src` を変えない。修正は #3056 の merge に任せ、merge 後に `run.sh` を再実行して trap が 0 件になることを確認する (#3056 は open のため未実施)。

## 4. 検証 (測定 commit `875eba29`)

測定 commit: `875eba29` (origin/main。本 run の起点)。コードを変えた commit は本 PR に無い (§4.4)。

### 4.1 `bash tools/shimx/test.sh` (step 5 を含む) — rc=1 (既存の FAIL・本 PR では変えない)

- 1 回実行 (n=1): 所要 18.4 s (wall)。load average 0.16 0.30 0.18 → 0.48 0.36 0.21 (開始→終了)。
- step 0〜4 PASS: step 2 MT `PASS (8 グループ)`、step 3 ST `PASS`、step 4 fail-fast の 13 件すべて `exit=1 ✓`、`ExitProcess(7) → exit=7 + hook ✓`。
- step 5 (M4 MT) で `FAIL tools/shim/test/test_main.c:203: HeapFree(heap, 0, p) == TRUE` (p = 0x1)。`test_main.c` は #2821 の変更 (コミット `7278e857`・`26bb47cc`) で HeapFree の範囲外に TRUE を期待する。shimx の HeapFree は `heap.c:79` で FALSE・ERROR_INVALID_PARAMETER を返す。
- step 5 の ST 以降・step 6/6b/6c/7 は未実行 (中断)。本 PR 前の origin/main でも同じ箇所で FAIL する。

### 4.2 `bash tools/shimx/evidence_3070/run.sh` — rc=0

- 2 回実行 (n=2): 3.2 s (wall) と 5 s (21:46:58 → 21:47:03。1 秒分解能)。load average 0.08 0.25 0.18 → 0.15 0.26 0.18 (2 回目の開始→終了)。
- 表本体 34 行 (`work/probe.tsv`)・対照 4 行 (`work/probe_rc.tsv`)。TRAP は表本体の 0xFFFFFFF0 の 4 行。
- 実行には `EMSDK_ENV` (`docs/REFERENCES.md` の `[EMSDK]` の `emsdk_env.sh`) が要る。

### 4.3 ネガティブコントロール

- 範囲検査を入れた複製で trap が消えること (§3)。逆に main の `blk_ok` (範囲検査なし) では 0xFFFFFFF0 で trap することが、本表の TRAP 行で再現した。
- M4 の HeapFree 検査が step 5 を止めることは §4.1 で再現した (`:203`)。

### 4.4 差分・生成物

- `git diff 875eba29 HEAD -- tools/shimx/src tools/shim/src tools/shim/test` は 0 行 (本 PR の HEAD で確認)。同じ範囲の `875eba29..origin/main` (main の後続 24 commit) も 0 行。
- 差分の範囲を実行コードに絞った理由: 受入の `git diff 875eba29 HEAD -- tools/shimx` は本 PR が追加する REPORT と evidence だけを数える (既存ファイルの変更・削除は 0)。既存のコードが変わらないことを見るため、判定は実行コードの範囲で行う。
- 20 MiB 超の blob: `find tools/shimx/evidence_3070 -type f -size +20M -not -path '*/work/*'` は 0 件。
- `test.sh` step 1 の生成物 (`src/proctable.c`・`exports.txt` 等) は差分 0 (`git status` は clean のまま)。

## 5. 製品 KPI

起動・GUI に関わらない (shim の不正入力応答の表と判断のみで、コードは変えない)。KPI 対象外。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0xFFFFFFF0 で 4 関数が wasm trap (main 実測・§3) | 不正入力で実行が止まる | #3056 (SHX-T35・blk_ok 範囲検査)。merge 後に `run.sh` を再実行して trap 0 件を確認 |
| main の M4 HeapFree (`test_main.c:203`) と shimx の不一致で step 5 が FAIL (§4.1) | `test.sh` の gate が常に FAIL | PM 判断 (HeapFree 契約。#3056 の未解決表の行)。親 #3023 |
| HeapReAlloc の errcode 87 と MSDN「SetLastError を呼ばない」の不一致 (§2.3) | 文書との差 (観測不能) | PM 判断 (HeapFree の errcode 契約と一括)。親 #3023 |
| native 参照の GlobalLock・GlobalUnlock・GlobalFree の戻り値が MSDN・M4 と不一致 (§1・§2.2) | native と wasm の応答表が一致しない | #2821 |
| 実機 Windows の errcode 値 (87・6 の推定) は未検証 (§1) | 推定値のまま | #2821 (実機の素材は本 run に無く取得不可) |
