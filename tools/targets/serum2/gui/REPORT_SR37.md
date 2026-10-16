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
export JAVA_HOME=<JDK 21 のインストール先> PATH=$JAVA_HOME/bin:$PATH
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

## 4. [SR-83 #5005] 8 関数の逆解析と呼び出し閉包の実測

- 日付: 2026-10-15 / 親: #4267 (SR-64) / 前段: §2 (境界 8 件・507 B)
- 測定 commit: `ddbadcb26` (`gui/ghidra_xferonoff_closure.java` を追加した commit)。以後このディレクトリのコードは未変更。
- 入力: §1 と同じ (sha256 `501e7bb3…4e5283` / 19,236,864 B)。Ghidra 12.1.4 を runner の作業用ディレクトリ (repo 外) に展開 (`[GHIDRA]` の代替)、JDK 21。
- 出力: `out/sr83_xferonoff_closure.tsv` (閉包 87 件、commit 対象)。8 関数の decompile は `work/decomp_sr83/*.c` (gitignore 対象・再配布しない)。decompile の C 本文は commit しない (Xfer の EULA は逆コンパイルを禁じる。`docs/LEGAL.md` の Xfer 条項 (c) 参照。REPORT には要点だけを書く)。

### 4.1 再現手順・実測 (n=1、runner 上、逐次)

```sh
cd tools/targets/serum2/work                     # gitignore 対象
7z x -y Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' -oexe
cp -f 'exe/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
python3 ../gui/vtable_fn_addrs.py Serum2_win64.vst3 XferOnOffButton > xferonoff_fns.tsv
export JAVA_HOME=<JDK 21> PATH=$JAVA_HOME/bin:$PATH FN_ADDRS_TSV=$PWD/xferonoff_fns.tsv OUT_DIR=$PWD/closure
analyzeHeadless ghproj xo -import Serum2_win64.vst3 -overwrite -scriptPath ../gui -postScript ghidra_fn_size.java
analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_closure.java
```

- 実測時間: import + 自動解析 (`ghidra_fn_size.java`) **18 分 36 秒** (real)。閉包 (`-process`、既存 project を開く) **7.4 秒** (real)。測定時の負荷は 4 vCPU の runner で他ジョブなし (実行後の load average 1 分値 0.35)。
- 注意: `7z x ... '-i!*Serum2.vst3*'` のワイルドカードは 0 件になった。完全パス指定で取り出せた。
- 境界の再確認: 8 件すべて `start_eq=true`・`dup_entry=false`・未対応 0・合計 **507 B** (§2 と一致)。

### 4.2 受入 1: 8 関数の役割 (decompile からの推定)

名前は付けていない (`FUN_` のまま)。役割は `work/decomp_sr83/` の decompile と vtable 位置から推定した。**確定ではない**。

| vtable RVA | entry | 名前 | B | 推定役割 | 根拠 (decompile の要点) |
|---|---|---|---|---|---|
| 0x18f290 | 0x18018f290 | `FUN_18018f290` | 70 | `Release` 相当 | 副次基底の this 補正 (`[this-4]` のオフセット) を使い、参照カウントを減算。0 になると vt[0x10] を呼び、続けて vt[0] を引数 1 で呼ぶ (deleting 経路) |
| 0x18f2e0 | 0x18018f2e0 | `FUN_18018f2e0` | 12 | `AddRef` 相当 | 同じ this 補正で参照カウントを +1。戻り値なし |
| 0x4b5670 | 0x1804b5670 | `thunk_FUN_180117c10` | 5 | thunk (転送先 `FUN_180117c10`・348 B) | 引数 `(this, double* v4, char notify)`。`this[3]` の内部オブジェクトの +0x58/+0x60/+0x68/+0x70 (double 4 個) と比較し、同値なら return。異なる場合は値を更新し、`notify == 0` のとき通知 (間接 call 4 箇所) |
| 0x4b6690 | 0x1804b6690 | `thunk_FUN_180142720` | 5 | thunk (転送先 `FUN_180142720`・201 B) | 転送先の役割は §4.3 の閉包表で測定。本体の読解は未実施 |
| 0x4b66a0 | 0x1804b66a0 | `FUN_1804b66a0` | 181 | `setValue(float)` 相当 | 引数 `(this, float v)`。vt[0x220]・vt[0x210] で範囲端を取り v を clamp。`FUN_180118150` で設定。vt[0x1f0] の前後で値が変わったら vt[0x48](this,1) で変更通知 (間接 call 4 箇所) |
| 0x622780 | 0x180622780 | `FUN_180622780` | 43 | scalar deleting dtor 相当 | `FUN_180118070` (基底 dtor 相当) を呼ぶ。引数フラグ ≠0 のとき `thunk_FUN_1809fe350(this, 0x78)` で delete (0x78 = 120 B) |
| 0x6227b0 | 0x1806227b0 | `FUN_1806227b0` | 141 | 値の通知 (推定) | `FUN_1801382a0()` が非 null のとき vt[0x200] で値を取得し、閾値 `DAT_180a21fe4` との比較で加算値を決める。`FUN_18010cf70` の結果と vt[0x18](obj, arg, …, 1.0f) を呼ぶ。最後に vt[0x48](this,0) |
| 0x622840 | 0x180622840 | `FUN_180622840` | 50 | scalar deleting dtor 相当 (副次基底) | `this-0x20` に補正してから `FUN_180118070` を呼び、フラグ ≠0 のとき 0x78 B を delete |

- 戻り値: `FUN_180622780`・`FUN_180622840` は `this` (補正後) を返す。ほかは void。
- 参照するメンバ: 上の表の `this[3]`・+0x58..+0x70 (double)・vtable slot (0x18・0x48・0x200・0x210・0x220 など)。

### 4.3 受入 2: thunk 転送先と閉包の実測

- 閉包: 呼び出し・thunk 転送で到達する **87 関数** (entry 単位で重複なし)。
  - 内訳: 外部 import 16 件 (本体 0 B) / thunk 8 件 (45 B) / 通常関数 63 件 (10,149 B)。
  - 通常関数 63 件のうち、名前で分類した「アプリ由来」は **43 件・7,873 B**、CRT・ランタイム (`_malloc_base`・`__acrt_*`・`_guard_*` など) は **20 件・2,276 B**。
  - 閉包の本体合計 **10,194 B** (thunk・外部 import を含む)。
- 転送先: `thunk_FUN_180117c10` → `FUN_180117c10` (348 B・間接 call 4)、`thunk_FUN_180142720` → `FUN_180142720` (201 B・間接 call 2)。
- **下限である理由**: 閉包は静的な直接 call と thunk 転送だけを辿った。間接 call (`call [reg+...]`) は **51 箇所** あり、その先は含まない。実際の閉包はこれより大きい。上限は測っていない。
- CAP (5000 件) には達していない (`cap_hit=false`)。

### 4.4 受入 3: canvas 側に対応物が無いもの

- 確認方法: `gui/canvas/` の全クラス名 (`canvas_*.h`) を見た。`CControl`・`CButton`・`XferOnOff` 相当の型は無い。`canvas_*` のクラスは IPlatform* の 8 種 (Bitmap・Font・Frame・Gradient・GraphicsDevice・GraphicsPath・PlatformFactory・String) だけ。
- 判定は名前と型の grep による。機能の同等性は見ていない。
- 結論: 8 関数 (§4.2) はすべて対応物なし。閉包のうち、アプリ由来 43 件もすべて対応物なし (下表)。CRT・ランタイム 20 件と外部 import 16 件は、canvas 側に移植しない前提 (実装時に別途判断)。
- 実装は子 issue で行う (本 issue の範囲外)。

| entry | 名前 | B | 間接 call |
|---|---|---|---|
| 0x18018f290 | FUN_18018f290 | 70 | 1 |
| 0x18018f2e0 | FUN_18018f2e0 | 12 | 0 |
| 0x1804b66a0 | FUN_1804b66a0 | 181 | 4 |
| 0x180622780 | FUN_180622780 | 43 | 0 |
| 0x1806227b0 | FUN_1806227b0 | 141 | 3 |
| 0x180622840 | FUN_180622840 | 50 | 0 |
| 0x180117c10 | FUN_180117c10 | 348 | 4 |
| 0x180142720 | FUN_180142720 | 201 | 2 |
| 0x180118150 | FUN_180118150 | 74 | 2 |
| 0x180118070 | FUN_180118070 | 224 | 1 |
| 0x1801085b0 | FUN_1801085b0 | 157 | 4 |
| 0x18010cf70 | FUN_18010cf70 | 9 | 0 |
| 0x1801382a0 | FUN_1801382a0 | 399 | 0 |
| 0x1801a5760 | FUN_1801a5760 | 602 | 0 |
| 0x180110b20 | FUN_180110b20 | 146 | 0 |
| 0x1809fe350 | FUN_1809fe350 | 60 | 2 |
| 0x180a188e0 | FUN_180a188e0 | 1353 | 0 |
| 0x180018230 | FUN_180018230 | 389 | 0 |
| 0x18008d820 | FUN_18008d820 | 394 | 0 |
| 0x1801ab5f0 | FUN_1801ab5f0 | 219 | 0 |
| 0x1801ab6e0 | FUN_1801ab6e0 | 194 | 0 |
| 0x1809df55c | FUN_1809df55c | 35 | 0 |
| 0x1809df5cc | FUN_1809df5cc | 207 | 0 |
| 0x1809e164c | FUN_1809e164c | 365 | 6 |
| 0x180014e20 | FUN_180014e20 | 54 | 0 |
| 0x1809a4b80 | FUN_1809a4b80 | 59 | 1 |
| 0x1809fe648 | FUN_1809fe648 | 144 | 2 |
| 0x1809adea0 | FUN_1809adea0 | 30 | 0 |
| 0x180a18f80 | FUN_180a18f80 | 725 | 0 |
| 0x1809ada94 | FUN_1809ada94 | 11 | 0 |
| 0x1809ca77c | FUN_1809ca77c | 167 | 3 |
| 0x1809dea00 | FUN_1809dea00 | 51 | 0 |
| 0x1809a7798 | FUN_1809a7798 | 31 | 0 |
| 0x1809ad7c8 | FUN_1809ad7c8 | 31 | 0 |
| 0x1809fe9d4 | FUN_1809fe9d4 | 181 | 3 |
| 0x180a0080c | FUN_180a0080c | 10 | 0 |
| 0x1809c9680 | FUN_1809c9680 | 211 | 2 |
| 0x1809dea50 | FUN_1809dea50 | 55 | 0 |
| 0x1809a7774 | FUN_1809a7774 | 33 | 0 |
| 0x1809a5a08 | FUN_1809a5a08 | 33 | 0 |
| 0x1809c97c4 | FUN_1809c97c4 | 116 | 3 |
| 0x180a123c0 | FUN_180a123c0 | 8 | 0 |
| 0x180a13668 | FUN_180a13668 | 50 | 0 |

- 注: `FUN_180118150`・`FUN_180118070`・`FUN_1801085b0`・`FUN_1801382a0` など、§4.2 の役割で参照した関数の中身は本 REPORT では読解していない。名前の付与は別 issue。

## 5. [SR-85 #5034] 間接 call の候補化と閉包の上限 (要約)

- 結論: XferOnOffButton の閉包は下限 87 関数・10,194 B (§4.3)。own vtable の候補を加えて反復すると 162 関数・23,190 B に収束 (`REPORT_APPENDIX_5005.md` §5.6)。
- 収束は候補化規則の範囲の値で、真の上限ではない (未解決 6 箇所)。詳細・手順・実測は付録へ分割移動した。
