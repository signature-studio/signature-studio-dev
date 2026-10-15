# #2069 REPORT — 0x4181e0 の呼出元と基底構造体 (途中経過・注釈は未変更)

- 担当 issue: #2069 `[PLG-P0b-13]` (親 #2016 / 起点 #1933)。
- 起点: `origin/main` 0d9b5385。branch `2069-plg-p0b-13-0x4181e0-base`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-fw-stage1` を worktree 直下の `tools/plugins/work/fw/` に展開。
- コード変更: なし (`tools/plugins/framework/fw_hostfix.py` は未変更)。本 REPORT の追加のみ。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | `0x418190` の呼出元から、`0x4181e0` の戻り値が指す基底構造体 (`+24` / `+520`) を確定 | **未達**。native 側の戻り値は確定 (§3.1)。lift 側は呼出元の `rcx` が IR に残っておらず、基底構造体の型は確定できず (§3.2) |
| 2 | 正しい戻り値を確定し `fw_hostfix.py` の 0x4181e0 注釈を修正 (Phase B 実測) | **未達**。確定できないため注釈は未変更 (§4) |
| 3 | REPORT に実測 (所要・load・PASS/FAIL) と Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測 (測定 commit 0d9b5385)

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の 1 / 5 / 15 分値。

| 手順 | commit | 結果 | 所要 (real) | load (開始時 → 終了時) |
|---|---|---|---|---|
| `fw_stage2.sh` (`FL_WIN64_DIR` 指定) | 0d9b5385 | rc 0・`SMOKE PASS` | 281.75 秒 | 0.38 / 0.61 / 0.28 (08:46:26) → 2.76 / 1.77 / 0.83 (08:51:08) |
| `hs_e2e.sh --fresh` | 0d9b5385 | rc 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 88.55 秒 | 2.61 / 1.75 / 0.83 (08:51:11) → 1.60 / 1.64 / 0.88 (08:52:40) |

- Phase B の失敗は REPORT_2016 §2 と同一 (OOB・`plug=0x0 rec=7`)。本 run で変化なし。
- 測定 commit は 0d9b5385。`git diff 0d9b5385 HEAD -- tools/plugins/framework` の差分 0 (本 REPORT 追加のみのため、コード差分は 0)。
- 1 回測定 (n=1)。変動レンジ (min–max) は未取得。

## 3. 読解

### 3.1 native `0x418190` の戻り値 (確定)

`hs_callee_disasm.py 60 0x418190 0x4181e0` の出力 (`.pdata` 関数 `[0x418190, 0x41820c)` 基準):

- 先頭で `mov rbx, rcx` (第 1 引数を保持)。`mov rsi, [rbx]` で参照先を取り出し、`[rbx] = 0` にする。
- 参照カウント (`[rcx-0xc]`) を `lock xadd` で減算し、0 になった場合のみ `call 0x416230` / `call 0x409440` で解放する。
- 末尾は `mov rax, rbx` で **第 1 引数 `rcx` そのものを返す**。

よって native の `0x418190` は「引数 `rcx` の参照を解放し、`rcx` を返す」関数である。REPORT_2016 §3.1 の結論と一致する。

### 3.2 lift 側の呼出規約 (確定した事実)

- stage-1 IR (`tools/plugins/work/fw/*.restored.ll`) の 0 引数呼出 `call i64 @function_4181e0()` は計 75 件 (fw0 14・fw1 10・fw2 7・fw3 2・fw4 6・fw5 12・fw6 8・fw7 8・r2 8)。(訂正: 旧記述の 142 は、この 75 に結合 IR `fw_all` の 67 件 (fw0〜fw7 と同じ呼出点) を加えた二重計上。IR 行は REPORT_2115 §3)。
- 引数付き `call i64 @function_4181e0(i64 ...)` は r3 のみ 8 件 (r3 7054・7078・7100 ほか)。0 引数版の定義と引数規約が一致していない。
- 0 引数の呼出元 (例: fw0 2360・4335) は、直前で `rcx` を `[BLK+8]` (= 9048072) に store しない。`9048072` を読む・書く IR は 10 ファイルとも 0 件。
- 呼出後は `[BLK+0x80]` (= 9048192) を基底として読む (例: fw0 2361・4336 の `load i64 9048192` → `+520`)。`[BLK+0x80]` は戻り値の受け渡しスロットで、`fw_hostfix.py` の 0x4181e0 override が 0 を書く (`RETSLOT = BLK+0x80`)。

### 3.3 推定 (未確認)

- 0 引数の lift では `rcx` が呼出元の IR から失われ、`[BLK+0x80]` には直前の別関数の戻り値が残る、と推定する。この場合 `0x4181e0` の戻り値は呼出ごとに異なる。
- 「0 を返す注釈」は、その残った値を 0 で置き換えているだけで、基底構造体の正しい値を与えていない可能性が高い。ただし本 run では確認していない (根拠: §3.2 の IR 事実のみ)。
- 正しい修正は、0 引数版を `rcx` を受け取る版へ揃えるか、呼出元で `[BLK+8]` の `rcx` を復元するかのどちらかと推定する。どちらも `fw_retw.py` / `fw_sigfix.py` の範囲に入るため、本 issue の `fw_hostfix.py` 注釈修正では閉じない可能性がある。

## 4. 注釈を変更しなかった理由

受入 2 の「正しい戻り値の確定」は、§3.2 の呼出規約が確定してはじめて可能になる。確定していない戻り値 (0 でも他の値でも) を `fw_hostfix.py` に書くと、Phase B が別の場所で誤動作する silent miscompile を作りうる。よって本 PR では注釈を変えず、Phase A 回帰と Phase B の現状だけを測定した。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1・2: 0 引数版 `function_4181e0` の `rcx` の由来 (呼出元で `[BLK+8]` を復元するか、版を揃えるか) と正しい戻り値 | Phase B が OOB のまま。`fw_hostfix.py` 注釈が未確定 | #2069 (本 issue を継続) |
| r3 系の引数付き呼出と 0 引数定義の不一致 | 引数規約の不整合が残る | #2069 (同上) |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B が OOB のまま | #1890 `[PLG-P0b-8]` / #2008 `[PLG-P0b-11]` (既存) |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst          # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                      # rc 0・SMOKE PASS が期待値
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh        # Phase A 回帰 OK・Phase B OOB で FAIL が期待値
python3 tools/plugins/framework/hostshim/hs_callee_disasm.py 60 0x418190 0x4181e0
grep -c 'call i64 @function_4181e0()' tools/plugins/work/fw/*.restored.ll   # 0 引数の呼出数 (計 75 件。142 は二重計上の誤り)
grep -c 'i64 9048072' tools/plugins/work/fw/*.restored.ll                    # BLK+8 の使用 (0 件が期待値)
```
