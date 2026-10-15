# REPORT 付録 — LD-170 (#3619): ld_stub_common の stk 位置を MS 第5引数 (entry+0x28) に直す

親: [`REPORT_APPENDIX_3557.md`](REPORT_APPENDIX_3557.md) §6.2 (stk 位置の不一致)。修正前の基準は origin/main `13a180ed7`。修正の commit は 2 つ: stk 位置 `e7e112de3`、6 引数 API の int 切り詰め `3be39188d` (測定 commit = コードを変えた最後の commit)。

## 1. 修正と根拠

- 変更 1 (stk 位置): `rt/ld_ms_call.S` の 78 行 `leaq 212(%rsp),%r9` → `leaq 224(%rsp),%r9`。
- 根拠: `ld_stub_common` は `pushq %rdi`・`pushq %rsi`・`subq $168,%rsp` の後で `rsp = E - 184` (E = 入口 rsp。`[E]` が呼出元の戻り番地)。IAT thunk は `mov r11, ld_stub_common; jmp r11` で入るので、E は戻り番地の位置と一致する。第5引数は `E+0x28` = `rsp+184+40` = `rsp+224` (0xe0)。`gcc -c` 後の `objdump -d` で `lea 0xe0(%rsp),%r9` を確認した。
- 修正前は `212 = 184 + 28` で、第5引数の位置より 12 バイト手前を指していた (#3557 §6.2 の `stk_minus_entry=28` と一致)。
- 変更 2 (int 切り詰め・レビュー B1): `rt/ld_core.h` の `MultiByteToWideChar`・`WideCharToMultiByte` で、a3・a5 を `ld_int_arg` (下位 32bit を符号付き int として読む) で読む。native (`ld_stub_c`) と wasm ブリッジ (`fle_ldbridge.c` の `LD64(R[4]+0x30)`) は同じ分岐を通る。

## 2. 6 引数 API の a3〜a5 の読み方

番号は 0 始まり (本ファイルと `REPORT_APPENDIX_3557.md` の表と同じ)。

- a0〜a3 = rcx・rdx・r8・r9 (レジスタ)。a4 = `[E+0x28]` = `stk[0]`、a5 = `[E+0x30]` = `stk[1]` (スタック上の第5・第6引数)。`ld_native.c` の `ld_stub_c` は `MultiByteToWideChar`・`WideCharToMultiByte` だけ `a4 = stk[0]`・`a5 = stk[1]` を読む。
- `MultiByteToWideChar(CodePage=a0, dwFlags=a1, lpMultiByteStr=a2, cbMultiByte=a3, lpWideCharStr=a4, cchWideChar=a5)`。
- `WideCharToMultiByte(CodePage=a0, dwFlags=a1, lpWideCharStr=a2, cchWideChar=a3, lpMultiByteStr=a4, cbMultiByte=a5, …)`。第 7・第 8 引数 (a6・a7) は stub が読まない。
- a3・a5 は int (32bit)。上位 32bit は ABI 上未定義で、lifted 側は dword で書くので下位 32bit だけが確定する。64bit で読むと上位は host の古い値になり得る。
- 修正前の a4 はホスト stack の値 (例 `0x55844ec000000000`)。stk 修正後は guest heap 域のポインタ (例 `0x1e43370`) になった。
- 実測 (修正後・boot 中の `WideCharToMultiByte` 538 件・`MultiByteToWideChar` は 0 件): dst ≠ NULL の 270 件は a3・a5 の上位 32bit がともに 0 (a3 は 3〜24 の正値、a5 は 0〜24 の正値。a5 は a3 と同じとは限らない)。dst = NULL の 268 件は書込み前に return する (a5 の上位 32bit は 10 件で非 0・例 `0x7fff00000000`、258 件は 0)。boot の中で a3 が負 (終端 -1) になる呼出しは無い。

## 3. 修正前後の測定 (実測)

| 項目 | 修正前 (`13a180ed7`) | stk 修正 (`e7e112de3`・`cca0661e7` と同じコード) | stk + int 切り詰め (`3be39188d`) |
|---|---|---|---|
| spike: units_run / first_fail | 928/942・830 | 892/942・149 | **892/942・149** |
| spike: boot の止まり方 | segv (rip_rva `0x26833d`・InitCount 246) | abort (SIGABRT・libc 内 rip_rva `0x7ffff789ec0c`・InitCount 145) | 同左 |
| spike: unit 単位の失敗 | 3 件 (最初 830 segv) | 15 件 (全て abort・最初 149 `664260`) | 同左 (15 件) |
| spike: CreateFruityInstance | segv rip_rva `0x4e0fab` | segv rip_rva `0xd053a9` | 同左 |
| spike: 呼出し import 数 (cfi) | 35 | 1 (`timeGetTime` のみ) | 1 |
| spike: 窓 import の呼出元 (§6.1 of 3557) | `0x52a825`・`0x52a85e`・`0x52a8c3` | 到達せず (記録 0 件) | 到達せず (0 件) |
| e2e `--m11-only` | PASS・360 / 234 / 206 (前回測定。今回は未再測定) | PASS・360 / 234 / 206 | **PASS・360 / 234 / 206** |
| e2e 内 `CHECK_INITUNITS` | PASS | PASS | PASS |
| e2e 内 UNIT18 の 3 項目 | PASS 3 件 | PASS 3 件 | PASS 3 件 |

測定の条件: 素材 `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)、`work-m11`・`work-liftdiff` を worktree の `tools/m11/work`・`tools/liftdiff/work` に展開。`toolchain-emsdk` は展開せず、runner 既存の emcc を使った。spike の実時間は 16.4 s (`3be39188d`)。e2e の実時間は 3 分 9.5 秒 (pre-B1) と 3 分 13.7 秒 (`3be39188d` 相当)。

### 3.1 関数単位の突合 (800 件・`tests/batch_flips.py`)

| 比較 | case outcome 変化 (関数) | verdict 変化 |
|---|---|---|
| 修正前 vs 修正後 (`e7e112de3` の測定 1 回目) | 5 | 0 |
| 修正前 vs 修正後 (`e7e112de3` HEAD の再測定) | 3 | 0 |
| 修正後 1 回目 vs HEAD 再測定 (同じコード) | 5 | 0 |
| **stk 修正のみ (`cca0661e7`) vs int 切り詰め (`3be39188d`)** | **2** (case 単位 7 件: hang ↔ both_fault 3+4) | **0** |

同じコード同士でも outcome は数件揺れる (前回の §6.4 と同じ範囲)。int 切り詰めによる outcome 変化 2 関数は、この揺れの範囲内と判断する。sample:800 の判定 (一致 360 / 不一致 234 / 実行不能 206) は変わらない。

## 4. 変化の類型 (切り分け・実測)

boot の変化 (928 → 892) の原因を、修正の内訳を 1 つずつ変えて確かめた (spike 1 回ずつ・コミットしない一時変更で、後で元に戻した)。

| 実験 | 変更 | units_run / first_fail |
|---|---|---|
| A | (stk 修正のみ) stk 位置 224 | 892/942・149 |
| B | A + `MultiByteToWideChar`・`WideCharToMultiByte` の dst への書込みを止める (修正前と同じく `need` だけ返す) | **928/942・830 (修正前と同一)** |
| C | A + a5 (`cchWideChar`・`cbMultiByte`) が 0 のとき `need` を返す | 892/942・149 (変化なし) |
| D | A + a3・a5 の int 切り詰め (`3be39188d`・レビュー B1) | 892/942・149 (変化なし) |

- 結論: 変化の直接の理由は、正しい位置になった dst (a4) へ stub が書込みを始めたこと (実験 B)。サイズ問い合わせの扱い (実験 C) と int 切り詰め (実験 D) は boot の応答を変えない。
- 実験 D の内訳 (§2 の実測): 切り詰めで値が変わるのは a5 の上位 32bit が非 0 の呼出しだけで、その 10 件はすべて dst = NULL のため書込みが起きない。dst ≠ NULL の 270 件は上位 32bit が 0 で、切り詰めの前後で値は同じ。レビューの懸念 (上位の古い値による過書込み) は、この boot では実際の書込みを変えていない。ABI 上の誤りなので直した。
- 後続の abort: 15 unit が libc 内の SIGABRT で落ちる (rip_rva `0x7ffff789ec0c` が全件同一)。直接の起点は**未特定**。推定: 書込みで guest 状態 (globals・heap の内容) が変わり、後続の RTL 経路が変わった結果、host 側の検査 (malloc・stack protector 等) で abort する。確認はしていない。子 issue #3946 [LD-184] (候補に実験 D の結果を加えた)。

## 5. 製品 KPI (起動に関わる。PR 本文に転記)

| KPI | 前 (`13a180ed7`) | 後 (`3be39188d`) |
|---|---|---|
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942 (first_fail 830) | **892/942 (first_fail 149)・悪化** |
| 最初のウィンドウ (可視) | 無し・動かしていない | 無し・動かしていない |
| 隠し窓 `TPUtilWindow` (CreateWindowExW) | 作られる (呼出元 `0x52a8c3`) | 作られない (CFI が窓 import に到達しない) |

- 悪化の原因は §4 (dst 書込みの経路)。stk の修正そのものは ABI どおりに正しく、悪化は後続の別の欠陥が見えたもの。
- int 切り詰め (レビュー B1) では戻らない。レビューの条件 (928/942・830 以上へ戻る) は満たさない。
- **PM agent の判断待ち**: KPI 悪化を承認して stk 修正を先に入れるか。既定案: #3946 の原因修正と同時に merge (本 PR は単独では merge しない)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後の libc abort 15 unit (最初 149 `664260`) の直接原因。dst 書込みの後続 | native boot 892/942 (基準 928/942)。製品 KPI の悪化 | 子 issue [LD-184] #3946 (B1 を候補に追加・実験 D で boot の応答は変わらないと実測) |
| PM agent の判断待ち: KPI 悪化 (928/942・830 → 892/942・149) を承認して stk 修正を先に入れるか。既定案: #3946 の原因修正と同時に merge | 製品 KPI の悪化。merge の可否 | PM agent (本 PR の判断) |

## 7. 再現

```sh
cd tools/liftdiff
FL_WIN64_DIR=<fl-win64 展開先> python3 spike_cfi.py targets/flelift.json
bash liftdiff_e2e.sh --m11-only                  # 一致/不一致/実行不能 = 360/234/206
python3 tests/batch_flips.py <修正前の batch_sample_800.jsonl> <修正後の batch_sample_800.jsonl>
```

## 8. 測定 commit と HEAD 差分

- 測定 commit (コードを変えた最後の commit): `20fb4ad90` (origin/main を取り込んだ merge commit)。この commit で spike・e2e を再測定した (§9)。
- main 取り込み (`20fb4ad90`) で `rt/ld_native.c`・`spike_cfi.py`・`ldlib/*`・`liftdiff_e2e.sh` が変わったため、`3be39188d` の測定値は現 HEAD の値として使わない。
- `git diff 3be39188d HEAD -- tools/liftdiff/rt tools/liftdiff/spike_cfi.py tools/liftdiff/ldlib tools/liftdiff/liftdiff_e2e.sh` は main 由来の差分 (8 files・139 insertions) を含む。以後の commit は REPORT の文書だけ。

## 9. main 取り込み後の再測定 (HEAD `20fb4ad90`)

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。`work-m11`・`work-liftdiff` を worktree の `tools/m11/work`・`tools/liftdiff/work` に展開。
- spike (`python3 spike_cfi.py`): units_run=892/942・first_fail=149 (abort rip_rva `0x7ffff789ec0c`・InitCount 145・失敗 15 unit)。CreateFruityInstance は segv (`0xd053a9`)。実時間 10.3 s。
- e2e (`bash liftdiff_e2e.sh --m11-only`): LIFTDIFF_E2E PASS・一致 360 / 不一致 234 / 実行不能 206。CHECK_INITUNITS PASS。実時間 2 分 44.9 秒。
- 既定 (stk 修正あり) の spike は 928/942・830 に戻っていない。B2 の条件 (a) (既定 off の切替) または (b) (#3946 の修正を含める) は、本 run では未実装。判断は PM。
