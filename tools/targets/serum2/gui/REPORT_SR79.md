# REPORT — [SR-79 #4610] Serum 2 `0x1803573f0` の呼出元で、レジスタ値の間接 call の宛先を解決する (部分達成)

- 日付: 2026-10-15 / 親: #4484 (SR-76) / 前段: `REPORT_SR76.md` §5 (a)・§4 / 対象: `0x1803573f0` (`+0x20408` の書込元)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。FLEngine 起動・GUI は**動かしていない** (製品 KPI は測っていない)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` (REPORT_SR76 §1 と一致)。作業用 dir はリポジトリ外。
- 測定 commit (解析に使ったコード): `d7d352b84` (`reg_call_resolve.py` の追加 commit)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `call reg`・`call [rsp+disp]` の宛先を定義元まで遡って解決する (解決不能は未解決として数える) | **部分達成**。`call reg` 1058 件・`call [rsp+disp]` 10 件 (計 1068 サイト) のうち 120 件を解決、948 件は未解決。解決した 120 件の宛先はいずれも R (`0x1803573f0` の direct 逆閉包 8 関数) に当たらない |
| 2. 1 の結果を含めて、setState 閉包 `0x1800c2b50`・getState 閉包 `0x1800c6090` と demo bit 関数 (`0x22792` を参照する関数) との交わりを示す | **部分達成**。C∩R = 0 (setState・getState とも)。demo bit 関数 2 件 (`0x1800c2b50`・`0x1800c6090`) は根そのもので、閉包との交わりは根自身のみ (demo∩C = 1)。C 内の未解決サイトは setState 28 件・getState 25 件あり、『交わり 0』はこれらを含めた完全な結論ではない (§3) |
| 3. REPORT に測定 commit と再現手順 | **達成** (§1・§5) |

**このため、本 REPORT は『R への経路が無い』とは主張しない。** 解決できた範囲と、未解決が残る範囲を分けて示す。

## 1. 再現手順と実測

```sh
# S: リポジトリ外の作業用 dir (例: $RUNNER_TEMP/s76)。P: tools/targets/serum2/gui
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/reg_call_resolve.py Serum2_win64.vst3 0x1803573f0 0x1800c2b50
venv/bin/python $P/reg_call_resolve.py Serum2_win64.vst3 0x1803573f0 0x1800c6090
```

| 実行 | 所要時間 (実測 wall) | 結果 |
|---|---|---|
| `reg_call_resolve.py` root `0x1800c2b50` (HEAD `d7d352b84`) | 10.24 秒 (user 10.08 秒) | rc 0。出力 md5 `40ba80074d23f2a91fed83ec281372c2` |
| `reg_call_resolve.py` root `0x1800c6090` (HEAD `d7d352b84`) | 10.17 秒 (user 9.96 秒) | rc 0。出力 md5 `2f0232a61d4c13c904f2c1a1bb8a15a3` |

実行前後の load average: 0.30 → 0.50 (1 分平均)。同 run 内で逐次実行。同一入力での再実行 (コミット前の版) でも出力 md5 は一致した。

## 2. 解決の結果 (両 root 共通)

| 項目 | setState `0x1800c2b50` | getState `0x1800c6090` |
|---|---|---|
| R (`0x1803573f0` の direct 逆閉包) | 8 | 8 |
| C (root から direct call/jmp で到達する関数) | 854 | 291 |
| C∩R | 0 | 0 |
| サイト (call reg 1058・call [rsp+disp] 10) の解決 | 120 解決・948 未解決 | 同左 |
| 解決サイトのうち宛先が R に当たる数 | 0 | 0 |
| C 内の未解決サイト (関数数) | 28 (13) | 25 (7) |
| demo bit 関数 ∩ C | 1 (根自身) | 1 (根自身) |

解決ロジックは `reg_call_resolve.py` の `resolve()`。`mov reg, [rip+X]`・`lea rip`・`mov reg, [reg2+off]` を後ろ向きに辿り、呼出しを跨ぐ場合は volatile レジスタ (rax/rcx/rdx/r8-r11) だけ未解決にする。`call [rsp+disp]` は同じ disp への直前の `mov` から辿る。

## 3. 未解決の内訳 (C 内)

| 供給元 | setState (28) | getState (25) |
|---|---|---|
| `load[reg+other]` (vtable 読みだが disp が 0x28・0x60 以外) | 19 | 12 |
| `after-call` (呼出し後の callee-saved レジスタ) | 6 | 7 |
| `stack-slot`・`stack-arg` (スタック渡し) | 2 | 4 |
| その他 (`sub`・`cmove`) | 1 | 2 |

- `load[reg+other]` の disp は 0x30・0x38・0x50・0x58 など。R のスロットの disp (0x28・0x60) とは一致しない。ただし vptr がスロットの途中を指す場合は別の disp でも R に届きうるため、『R に届かない』とは言えない (未検証)。
- `after-call` は、呼出し後も生きる callee-saved レジスタ (rbx・rsi・rdi・r12-r15) を、呼出し前の定義元まで辿れなかったもの。
- `stack-arg` の `call [rsp+0x60]` (`0x180571e89`・`0x180571ea9`) は、直前で `[rsp+0x60]` へ書かれる値を辿れていない。

## 4. R の関数アドレスの出現形

- `.text` 中の即値で R のアドレス (絶対 VA・RVA 一致) に当たるのは 8 件。すべて R 内・R への direct call の即値 (`call 0x...`)。
- R の関数アドレスを rip 相対で materialise する箇所は 0 件 (REPORT_SR76 §4 と一致)。
- したがって、R の関数ポインタがコード上に現れるのは `.rdata`/`.data` の vtable スロット 3 件 (`0x180a24030`・`0x180a240a8`・`0x180a24180`) だけ。

## 5. demo bit 関数 (`0x1800c2b50`・`0x1800c6090`) の間接 call

- `0x1800c2b50`: 非 direct call 1 件 `call qword ptr [rax + 0x30]` (`0x1800c2f05`)。
- `0x1800c6090`: 非 direct call 2 件 `call qword ptr [rdx + 0xe8]` (`0x1800c67b8`)・`call qword ptr [rax + 0x20]` (`0x1800c68ee`)。
- いずれの disp も R のスロット disp (0x28・0x60) と一致しない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) `call reg`・`call [rsp+disp]` の 948 サイト (全体)。解決は 120 サイトのみ | 受入 1・2 の『交わり 0』は未解決サイトを含めた完全な結論ではない | #4610 (本 issue を継続) |
| (b) C 内の未解決 28 (setState)・25 (getState) サイトの供給元。`load[reg+other]`・`after-call`・`stack-arg` の個別解決 | 受入 2 の『C∩R = 0』が、これらのサイトを通る経路を除外できていない | #4610 (本 issue を継続) |
| (c) `load[reg+other]` の disp が vptr のスロット途中 (MI・別 vtable) を指す場合に R へ届くか | R の vtable 形状 (1 vtable の先頭か途中か) の検証が未了 | #4610 (本 issue を継続) |
| (d) demo bit 関数が .text で 2 件 (根のみ) しかない。`0x22792` の読出しは別経路 (オブジェクト経由の間接読出し) の可能性 (REPORT_SR76 §5(b) と同じ) | 『demo∩C』の意味が根自身だけになる | #4610 (本 issue を継続) |

## 7. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
