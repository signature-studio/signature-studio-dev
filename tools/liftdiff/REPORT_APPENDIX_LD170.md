# REPORT 付録 — LD-170 (#3619): ld_stub_common の stk 位置を MS 第5引数 (entry+0x28) に直す

親: [`REPORT_APPENDIX_3557.md`](REPORT_APPENDIX_3557.md) §6.2 (stk 位置の不一致)。修正前の基準は origin/main `13a180ed7`、修正の commit は `e7e112de3` (測定 commit)。

## 1. 修正と根拠

- 変更: `rt/ld_ms_call.S` の 78 行 `leaq 212(%rsp),%r9` → `leaq 224(%rsp),%r9`。
- 根拠: `ld_stub_common` は `pushq %rdi`・`pushq %rsi`・`subq $168,%rsp` の後で `rsp = E - 184` (E = 入口 rsp。`[E]` が呼出元の戻り番地)。IAT thunk は `mov r11, ld_stub_common; jmp r11` で入るので、E は戻り番地の位置と一致する。第5引数は `E+0x28` = `rsp+184+40` = `rsp+224` (0xe0)。`gcc -c` 後の `objdump -d` で `lea 0xe0(%rsp),%r9` を確認した。
- 修正前は `212 = 184 + 28` で、第5引数の位置より 12 バイト手前を指していた (#3557 §6.2 の `stk_minus_entry=28` と一致)。

## 2. 6 引数 API の a4/a5 の読み方

番号は 0 始まり (本ファイルと `REPORT_APPENDIX_3557.md` の表と同じ)。

- a0〜a3 = rcx・rdx・r8・r9 (レジスタ)。
- a4 = `[E+0x28]` = `stk[0]`、a5 = `[E+0x30]` = `stk[1]` (スタック上の第5・第6引数)。`ld_native.c` の `ld_stub_c` は `MultiByteToWideChar`・`WideCharToMultiByte` だけ `a4 = stk[0]`・`a5 = stk[1]` を読む。
- `MultiByteToWideChar(CodePage=a0, dwFlags=a1, lpMultiByteStr=a2, cbMultiByte=a3, lpWideCharStr=a4, cchWideChar=a5)`。
- `WideCharToMultiByte(CodePage=a0, dwFlags=a1, lpWideCharStr=a2, cchWideChar=a3, lpMultiByteStr=a4, cbMultiByte=a5, …)`。第 7・第 8 引数 (a6・a7) は stub が読まない。
- 修正前の a4 はホスト stack の値 (例 `0x55844ec000000000`)。修正後は guest heap 域のポインタ (例 `0x1e43370`) になった。

## 3. 修正前後の測定 (実測)

| 項目 | 修正前 (`13a180ed7`) | 修正後 (`e7e112de3`) |
|---|---|---|
| spike: units_run / first_fail | 928/942・830 | **892/942・149** |
| spike: boot の止まり方 | segv (rip_rva `0x26833d`・InitCount 246) | abort (SIGABRT・libc 内 rip_rva `0x7ffff789ec0c`・InitCount 145) |
| spike: unit 単位の失敗 | 3 件 (最初 830 segv) | 15 件 (全て abort・最初 149 `664260`) |
| spike: CreateFruityInstance | segv rip_rva `0x4e0fab` | segv rip_rva `0xd053a9` |
| spike: 呼出し import 数 (cfi) | 35 | 1 (`timeGetTime` のみ) |
| spike: 窓 import の呼出元 (§6.1 of 3557) | `0x52a825`・`0x52a85e`・`0x52a8c3` | 到達せず (記録 0 件) |
| e2e `--m11-only` | PASS・360 / 234 / 206 | PASS・360 / 234 / 206 |
| e2e 内 `CHECK_INITUNITS` | PASS | PASS (検査は 928/942 を要求しない) |
| e2e 内 UNIT18 の 3 項目 | PASS 3 件 | PASS 3 件 |

測定の条件: `spike_cfi.py` は `SPIKE_WINTRACE=1`。素材 `fl-win64`・`work-m11`・`work-liftdiff` を展開 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)。`toolchain-emsdk` は展開せず、runner 既存の `[EMSDK]` (`emcc` あり) を使った。spike の実時間は修正前 23.9 s・修正後 15.5 s。e2e の実時間は修正前 3 分 15 秒・修正後 3 分 12 秒 (HEAD 再測定 3 分 12 秒)。

### 3.1 関数単位の突合 (800 件・`tests/batch_flips.py`)

| 比較 | case outcome 変化 | verdict 変化 |
|---|---|---|
| 修正前 vs 修正後 (`e7e112de3` の測定 1 回目) | 5 | 0 |
| 修正前 vs 修正後 (`e7e112de3` HEAD の再測定) | 3 | 0 |
| 修正後 1 回目 vs HEAD 再測定 (同じコード) | 5 | 0 |

同じコード同士でも outcome が 5 件揺れる (前回 REPORT の §6.4 と同じ揺れの範囲)。sample:800 の判定 (一致/不一致/実行不能) は変わらない。

## 4. 変化の類型 (切り分け・実測)

boot の変化 (928 → 892) の原因を、修正の内訳を 1 つずつ変えて確かめた (spike 1 回ずつ・コミットしない一時変更で、後で元に戻した)。

| 実験 | 変更 | units_run / first_fail |
|---|---|---|
| A | (修正のみ) stk 位置 224 | 892/942・149 |
| B | A + `MultiByteToWideChar`・`WideCharToMultiByte` の dst への書込みを止める (修正前と同じく `need` だけ返す) | **928/942・830 (修正前と同一)** |
| C | A + a5 (`MultiByteToWideChar` の cchWideChar・`WideCharToMultiByte` の cbMultiByte) が 0 のとき `need` を返す | 892/942・149 (変化なし) |

- 結論: 変化の直接の理由は、正しい位置になった dst (a4) へ stub が書込みを始めたこと。`ld_dst_ok` を通る dst が増え、guest の状態が変わる。サイズ問い合わせの扱い (実験 C) は原因ではない。
- 修正後の boot 中の呼出し: `WideCharToMultiByte` 538 件 (`MultiByteToWideChar` は boot 停止まで呼ばれず 0 件)。dst ≠ NULL の 270 件は a4 がヒープ域のポインタ、a5 (cbMultiByte) は a3 と同程度の妥当な値 (例 `a3=32, a5=32`)。dst = NULL の 261 件は a5 が host 値 (`0x5555…` 系) だが、dst が NULL なので書込みは起きず、戻り値 (`need`) にも影響しない。
- 後続の abort: 15 unit が libc 内の SIGABRT で落ちる (rip_rva `0x7ffff789ec0c` が全件同一)。直接の起点は**未特定**。推定: 書込みで guest 状態 (globals・heap の内容) が変わり、後続の RTL 経路が変わった結果、host 側の検査 (malloc・stack protector 等) で abort する。確認はしていない。子 issue へ (§6)。

## 5. 製品 KPI (起動に関わる。PR 本文に転記)

| KPI | 前 (`13a180ed7`) | 後 (`e7e112de3`) |
|---|---|---|
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942 (first_fail 830) | **892/942 (first_fail 149)・悪化** |
| 最初のウィンドウ (可視) | 無し・動かしていない | 無し・動かしていない |
| 隠し窓 `TPUtilWindow` (CreateWindowExW) | 作られる (呼出元 `0x52a8c3`) | 作られない (CFI が窓 import に到達しない) |

悪化の原因は §4 (dst 書込みの経路)。stk の修正そのものは ABI どおりに正しく、悪化は後続の別の欠陥が見えたもの。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後の libc abort 15 unit (最初 149 `664260`) の直接原因。dst 書込みの後続 | native boot 892/942 (基準 928/942)。製品 KPI の悪化 | 子 issue [LD-184] #3946 (本 PR と同時に起票) |
| dst = NULL 時の a5 がホスト値になる (6 引数目の書込み元の確認) | 使われないため測定値への影響は無し | 追跡のみ (本付録) |

## 7. 再現

```sh
cd tools/liftdiff
FL_WIN64_DIR=<fl-win64 展開先> python3 spike_cfi.py targets/flelift.json
bash liftdiff_e2e.sh --m11-only                  # 一致/不一致/実行不能 = 360/234/206
python3 tests/batch_flips.py <修正前の batch_sample_800.jsonl> <修正後の batch_sample_800.jsonl>
```

## 8. 測定 commit と HEAD 差分

- 測定 commit (コードを変えた最後の commit): `e7e112de3`。spike・e2e の再測定 (§3) もこの commit で行った。
- `git diff e7e112de3 HEAD -- tools/liftdiff/rt tools/liftdiff/spike_cfi.py tools/liftdiff/ldlib tools/liftdiff/liftdiff_e2e.sh` の出力は空 (コード差分 0)。以後の commit は REPORT の文書だけ。
