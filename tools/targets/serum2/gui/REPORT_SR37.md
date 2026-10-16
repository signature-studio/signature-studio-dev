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

## 5. [SR-85 #5034] 間接 call 51 箇所の候補列挙と閉包の上限

- 日付: 2026-10-16 / 親: #5005 (SR-83) / 前段: §4 (下限 87 関数・10,194 B・間接 call 51)
- 測定 commit: 本 §5 と `gui/indirect_sr85_own_vt.py`・`gui/ghidra_xferonoff_indirect.java` を追加した commit (PR 本文の測定 commit 欄参照)。以後このディレクトリのコードは未変更。
- 入力: §1 と同じ (sha256 `501e7bb3…4e5283` / 19,236,864 B)。Ghidra 12.1.4 を repo 外 (作業用 `/tmp`) に展開、JDK 21 (`/usr/lib/jvm/temurin-21-jdk-amd64`)。
- 出力: `work/own_vt_sites.tsv` (gitignore 対象)。decompile の C 本文は commit しない (`docs/LEGAL.md`)。

### 5.1 再現手順・実測 (n=1、runner 上、逐次)

```sh
cd tools/targets/serum2/work                     # gitignore 対象
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" Install_Xfer_Serum2_2.1.5.exe
7z x -y Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' -oexe
cp -f 'exe/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
python3 ../gui/vtable_fn_addrs.py Serum2_win64.vst3 XferOnOffButton > xferonoff_fns.tsv
# Ghidra 12.1.4 は公式 release (ghidra_12.1.4_PUBLIC_20260921.zip) を取得し、sha256 ddac49f9…d4db を検査してから展開する (tools/m11/m11_ghidra_dll.sh と同じ)。展開先を GHIDRA_HOME とする
mkdir -p ghproj                                  # Ghidra project 置き場 (無いと import が Directory not found で止まる)
export JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64 PATH=$JAVA_HOME/bin:$PATH FN_ADDRS_TSV=$PWD/xferonoff_fns.tsv OUT_DIR=$PWD/closure
$GHIDRA_HOME/support/analyzeHeadless ghproj xo -import Serum2_win64.vst3 -overwrite -scriptPath ../gui -postScript ghidra_fn_size.java
$GHIDRA_HOME/support/analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_closure.java   # 下限 (87 関数)
$GHIDRA_HOME/support/analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_indirect.java > indirect_ghidra.log   # 間接 call の 1 件ずつ
python3 ../gui/indirect_sr85_own_vt.py Serum2_win64.vst3 indirect_ghidra.log aa9750,aa96b0,aa9770 > own_vt_sites.tsv
# 上限: 下限の root 8 件 (§2) と own vtable の候補 16 件 (§5.2) の union 19 件を root にして閉包を取り直す
# root 集合は commit 済みの gui/xferonoff_upper_fns.tsv (19 行・先頭列 RVA・形式は xferonoff_fns.tsv と同じ)。作業用 dir へ複製して使う
cp -f ../gui/xferonoff_upper_fns.tsv xferonoff_upper_fns.tsv
sha256sum xferonoff_upper_fns.tsv                # c741878353fee17bda93a14a581bcf8504de6795d6203b89d29a7837b76626fb
FN_ADDRS_TSV=$PWD/xferonoff_upper_fns.tsv OUT_DIR=$PWD/closure_upper $GHIDRA_HOME/support/analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_closure.java
FN_ADDRS_TSV=$PWD/xferonoff_upper_fns.tsv OUT_DIR=$PWD/closure_upper $GHIDRA_HOME/support/analyzeHeadless ghproj xo -process Serum2_win64.vst3 -noanalysis -readOnly -scriptPath ../gui -postScript ghidra_xferonoff_indirect.java > upper_indirect.log   # 上限の computed call の種別 (m1)
```

- 測定 commit (コード): `1542ade80` (以後 `gui/*.py`・`gui/*.java` は未変更)。上限の再測定は検証 HEAD (TSV 追加・REPORT の文言修正の commit) で実施。
- 上限 root の入力 `gui/xferonoff_upper_fns.tsv`: sha256 `c741878353fee17bda93a14a581bcf8504de6795d6203b89d29a7837b76626fb`・19 行 (ヘッダ行を除く)。

- 実測時間: import + 自動解析 (`ghidra_fn_size.java`) **19 分 25 秒** (real)。下限の閉包 `-process` **6.5 秒**。間接 call 列挙 `-process` **7.0 秒**。上限の閉包 `-process` **6.6 秒**。Python 解析 (`indirect_sr85_own_vt.py`) 約 4 秒。測定時の負荷は 4 vCPU の runner で他ジョブなし (load average 1 分値 1.08)。
- 境界の再確認: 8 件すべて `start_eq=true`・未対応 0・合計 **507 B** (§2 と一致)。

### 5.2 受入 1: 間接 call 51 箇所の呼出し先候補

Ghidra の計数 (`computed_call_sites=51`) の内訳は次のとおり。

| 種別 | 件数 | 候補の出し方 |
|---|---|---|
| IAT 経由 (`call qword ptr [0x180fe....]`・`ref=EXTERNAL:…KERNEL32.DLL::…`) | **27** | 参照先が import 名に一意に解決 (候補 1 件・外部 import。本体は閉包の外) |
| レジスタ経由 `call [reg+disp]` (own vtable の slot に一致) | **21** | COL `0xaa9750`・`0xaa96b0`・`0xaa9770` (XferOnOffButton の 3 種) の vtable slot から候補化。候補 1〜3 件 |
| `INT3` / `INT 0x29` | 3 | 呼出しではない。Ghidra が computed flow として数えたもの (候補なし) |

- 数え方: 間接 call の実数は **48 件** (51 − INT 系 3)。§4.3 の 51 は INT 系を含む計数。
- レジスタ経由の間接 call 21 件は、全件が own vtable の COL 3 種の slot で候補化できた (未解決 0 件)。`[R8]`・`[RAX]` の 2 件は disp 無し = slot 0。
- 候補の列挙: 候補関数は `work/own_vt_sites.tsv` の `result` 列 (VA)。候補の総数は重複除去後 **16 関数** (`0x180136bf0`・`0x1801428d0`・`0x180142180`・`0x180142150`・`0x1801470d0`・`0x180142540`・`0x18000d920`・`0x1804b6690`・`0x18018e4b0`・`0x1800181c0`・`0x18018f2e0`・`0x180138180`・`0x18018e800`・`0x18018f290`・`0x180622780`・`0x180622840`)。
- 限界: 候補は「XferOnOffButton の vtable の同じ slot の関数」であり、実行時の動的型は未確認。同じ slot を持つ別クラスの vtable は見ていない (`this` の型を追跡していない)。
- 解決の対象外: 直接 `call reg` (レジスタ値 `call R10`・`call RAX`) は下限の閉包 (87 関数) では 0 件。上限の閉包 (157 関数) では 5 箇所 (`0x180136bf0` の 3 箇所・`0x180138180` の 1 箇所・`0x180142540` の 1 箇所。§5.3 の内訳)。いずれも候補化せず、解決対象外として残す。

### 5.3 受入 2: 上限 (閉包の候補込み、1 段)

| 集合 | 関数数 | 本体合計 (外部 import 除く) | computed call 計数 (INT 系を含む) |
|---|---|---|---|
| 下限 (§4.3・SR-83) | 87 (外部 import 16・thunk 8・通常 63) | **10,194 B** | 51 (うち INT 系 3) |
| 上限 (本 §5・1 段・union 19 件を root) | 157 (外部 import 24・thunk 8・通常 125) | **22,227 B** (通常 22,182 B・thunk 45 B) | 100 (うち INT 系 7・IAT・外部 49・`[reg+disp]` 39・直接 `call reg` 5) |

- 上限の root 集合: §2 の 8 件 + §5.2 の候補 16 件の union **19 件** (重複 5 件 `0x18018f290`・`0x18018f2e0`・`0x1804b6690`・`0x180622780`・`0x180622840` を除くと新規 root は 11 件)。入力は commit 済みの `gui/xferonoff_upper_fns.tsv` (sha256 `c741878353fee17bda93a14a581bcf8504de6795d6203b89d29a7837b76626fb`・19 行)。
- 測定: 上の値は union 19 件の TSV を root にした閉包 (`-process ghidra_xferonoff_closure.java`) の実測。import した Ghidra 12.1.4 の解析結果 (`ghidra_fn_size.java`) と同じ project で取った。下限の再測定 (87 関数・10,194 B・51) も §4.3 と一致。
- 上限の内訳: 通常 125 関数 = 22,182 B、thunk 8 件 = 45 B (合計 22,227 B)。下限との差は **+12,033 B** (+118%)。
- 注: 上限は 1 段 (own vtable の候補 16 関数を root に足した閉包)。新たに到達した 70 関数の中の間接 call は候補化していない。**真の上限ではない**。上限を閉じるには、新規到達分の間接 call の候補化を繰り返す必要がある (未実施)。
- 測定時間: 上限の閉包 `-process` 6.8 秒 (real)。import + 自動解析は 18 分 21 秒 (real)。

### 5.4 受入 3: 下限と上限の差

- 差分: 関数数 **+70** (157 − 87)、本体合計 **+12,033 B** (22,227 − 10,194)。
- 差分の内訳: 1 段目の新規 root は **11 件** (候補 16 件のうち、下限の root 8 件と重複する 5 件を除く)。下限の root 8 件は両方の集合に含まれる。そこから到達した追加の関数 70 件 (本体 +12,033 B) が 2 段目以降を含む。
- 差分の由来は上限の root 集合 (1 段) であり、真の上限との差は未測定。
- 対応物: 本 REPORT §4.4 の canvas 側の対応物なしの判定は変えない (本 §5 は閉包の大きさだけを測る)。

### 5.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 上限 (2 段目以降) の間接 call の候補化 | 上限が 1 段のみ。真の上限は未測定 | #5005 の「残作業 (#5034 の run から追記)」の 1 項目目 (本 issue の範囲外) |
| 同じ slot を持つ別クラス vtable の候補 (型未追跡) | 候補が XferOnOffButton の vtable に限定 | #5005 の同節の 2 項目目 |
| `call reg` (レジスタ値) の 2 段目以降の解決 | 2 段目以降の呼出し先が未確定。上限 1 段の閉包内の直接 `call reg` 5 箇所も未解決 | #5005 の同節の 3 項目目 |

### 5.6 候補を root に加える反復 (収束の実測)

- 手順: 閉包 → 閉包内の間接 call の候補化 (own vtable・§5.2 の規則と同じ) → 新規候補を root に加えて閉包し直す。新規候補が 0 になるまで回す。スクリプト `gui/iterate_sr85_upper.py` (commit 済み)。
- 測定 commit: 本 §5.6 と `gui/iterate_sr85_upper.py`・`gui/xferonoff_upper2_fns.tsv` を追加した commit。入力は §5.1 と同じ `Serum2_win64.vst3` (sha256 `501e7bb3…4e5283`)。Ghidra 12.1.4 の import は `ghidra_fn_size.java` で再実施 (**18 分 50 秒**・real)。

| 反復 | root 数 | 閉包 関数数 | 本体合計 | 間接 call | 候補関数 | 新規候補 |
|---|---|---|---|---|---|---|
| 0 (§5.3 の 1 段) | 19 | 157 | 22,227 B | 100 | 20 | 4 |
| 1 | 23 | 161 | 23,180 B | 107 | 21 | 1 |
| 2 | 24 | 162 | 23,190 B | 107 | 21 | **0 (収束)** |

- 反復の総時間: 3 回で **48.95 秒** (real・Ghidra 2 回 + Python 解析を含む・runner 4 vCPU・load average 約 1.1)。
- 収束時の閉包 (`out/sr85_xferonoff_upper_closure.tsv`・sha256 `b9f034be…cc25`)、root 集合 (`gui/xferonoff_upper2_fns.tsv`・sha256 `fcafc8df…82f9`)、候補 (`out/sr85_own_vt_iter3.tsv`)。
- 収束時の間接 call 107 箇所の内訳: IAT・外部 import 48 箇所 (閉包の外)、own vtable で候補化 46 箇所 (未解決 0)、INT 系 7 箇所 (呼出しではない)、**未解決 6 箇所** (下表)。48 + 46 + 7 + 6 = 107。
- 未解決 6 箇所 (収束後も候補化できなかったもの):

| 関数 | 命令 | 理由 |
|---|---|---|
| `0x180136bf0` (3 箇所) | `call R10`・`call R10`・`call RAX` | レジスタ値の直接 call。候補規則の対象外 |
| `0x180138180` | `call RAX` | 同上 |
| `0x180142540` | `call RAX` | 同上 |
| `0x1809ca77c` | `call qword ptr [0x180fe12f0]` | IAT 形式だが参照先の import 名が出力に無い。分類は未確定 (次の run で確認) |

- **これは真の上限ではない**: (1) 候補化の規則は XferOnOffButton 自身の vtable の slot に限る (他クラスの vtable・型追跡は未実施)、(2) 未解決 6 箇所の先は閉包に入っていないため、閉包は下限側の値を含みうる。収束したのは「この規則の下での閉包」であり、§5.3 の 1 段の値 (157 関数) より 5 関数・963 B 多い。
- 差分 (1 段 → 収束): **+5 関数・+963 B** (22,227 → 23,190 B)。本体合計の増分は 1 段目から 2 段目で +963 B 増えた分。
