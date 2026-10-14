# REPORT — [SR-37 #2066] XferOnOffButton の .text 対応付けと本体バイト数の実測

- 日付: 2026-10-14 / 親: #2029 (SR-31) / 前段: `gui/REPORT_EFFORT.md` §10-1・§10-3
- 範囲: vtable 由来の override・新規 8 関数 (`XferOnOffButton`) の Ghidra 関数境界への対応付けと本体バイト数。人日は出さない (#1351 のユーザ判断に残す)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `exe/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (§10-1 と一致)。
- 測定 commit: 本 REPORT と `gui/vtable_fn_addrs.py`・`gui/ghidra_fn_size.java` を追加した commit (PR 本文の測定 commit 欄参照)。以後このディレクトリのコードは未変更。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. vtable 由来の 8 関数の .text アドレスを Ghidra の関数境界に対応付ける | **達成**。8 件すべて関数先頭に一致 (`start_eq=true`)、未対応 0 件 |
| 2. 対応付けた関数の本体バイト数の合計を実測し REPORT に残す (測定 commit と再現手順を併記) | **達成**。distinct entry 8 件の本体合計 **507 B** (§2) |
| 3. 対応付けできなかった関数は件数と理由を残す | **該当なし** (0 件) |
| 4. 人日は出さない | 達成 (人日は記載せず) |

## 1. 再現手順・実測 (runner 上)

```sh
# 作業用 dir は worktree 内の tools/targets/serum2/work/ (gitignore 対象)
cd tools/targets/serum2/work
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" Install_Xfer_Serum2_2.1.5.exe
7z x -y Install_Xfer_Serum2_2.1.5.exe -oexe
cp -f 'exe/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
sha256sum Serum2_win64.vst3   # 501e7bb3…4e5283

# 1) vtable 由来の override・新規 .text アドレス (vtable_measure.py と同じ判定)
cd ../gui
python3 vtable_fn_addrs.py ../work/Serum2_win64.vst3 XferOnOffButton | tee ../work/xferonoff_fns.tsv
#   total distinct = 8 (vtable_measure.py の union 8 と一致)

# 2) Ghidra 12.1.4 headless で関数境界と本体バイト数
export JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64 PATH=$JAVA_HOME/bin:$PATH
export FN_ADDRS_TSV=$PWD/../work/xferonoff_fns.tsv
cd ../work && mkdir -p ghproj
/path/to/ghidra_12.1.4_PUBLIC/support/analyzeHeadless ghproj xo \
  -import Serum2_win64.vst3 -overwrite -scriptPath ../gui -postScript ghidra_fn_size.java
```

- 環境: Ghidra 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`、GitHub release の `Ghidra_12.1.4_build`)・JDK 21 (temurin-21)。`[GHIDRA]` が runner に無いため、初回使用時に上の zip を `_temp` 配下へ展開した。実測時間: 1 回目 (スクリプト修正前、NPE で終了) の `analyzeHeadless` は 14 分 34 秒 (real)。2 回目 (採用した結果) の時間は未計測。
- 注意: `analyzeHeadless` の既定 project 名は `ghproj/xo` の前にディレクトリが要る (無いと `Directory not found` で abort)。

## 2. 対応付けの結果 (Ghidra 出力・再現可能)

| vtable RVA | Ghidra 関数 entry | 名前 | body | bytes | 備考 |
|---|---|---|---|---|---|
| 0x18f290 | 0x18018f290 | `FUN_18018f290` | 18018f290..18018f2d5 | 70 | COL 0xaa9750 (副次 vtable 0) |
| 0x18f2e0 | 0x18018f2e0 | `FUN_18018f2e0` | 18018f2e0..18018f2eb | 12 | 同上 |
| 0x4b5670 | 0x1804b5670 | `thunk_FUN_180117c10` | 1804b5670..1804b5674 | 5 | thunk (ジャンプ 1 命令) |
| 0x4b6690 | 0x1804b6690 | `thunk_FUN_180142720` | 1804b6690..1804b6694 | 5 | thunk (ジャンプ 1 命令) |
| 0x4b66a0 | 0x1804b66a0 | `FUN_1804b66a0` | 1804b66a0..1804b6754 | 181 | |
| 0x622780 | 0x180622780 | `FUN_180622780` | 180622780..1806227aa | 43 | |
| 0x6227b0 | 0x1806227b0 | `FUN_1806227b0` | 1806227b0..18062283c | 141 | |
| 0x622840 | 0x180622840 | `FUN_180622840` | 180622840..180622871 | 50 | COL 0xaa9770 (副次 vtable) |

- 合計: **507 B** (8 件、重複 entry 0)。内訳は通常関数 6 件 = 497 B (70 + 12 + 181 + 43 + 141 + 50)、thunk 2 件 = 10 B (5 + 5)。
- thunk 2 件 (`0x4b5670`・`0x4b6690`) は Ghidra が thunk と判定した関数 (本体 5 B)。転送先は `thunk_FUN_180117c10`・`thunk_FUN_180142720` の名前から示されるが、転送先の本体は測っていない。
- 上限の意味: 本体合計は「vtable から直接指される関数 8 件の本体」であり、`XferOnOffButton` の置換に要る全コードの大きさではない。呼び出し先の閉包は未測定。

## 3. 限界

- 関数本体は Ghidra の自動解析による境界。関数の一部が未検出の場合、本体が短く出る可能性がある (本 run では全 8 件が関数先頭と一致し、境界の欠落は検出されなかった)。
- 副次 vtable (COL 0xaa9750・0xaa9770) の継承元の対応は `vtable_measure.py` と同じ未検証事項を引き継ぐ (`gui/REPORT_EFFORT.md` §10-1 の限界参照)。
- Ghidra の関数名は自動命名 (`FUN_<addr>`)。`XferOnOffButton` のメソッド名は付けていない。
