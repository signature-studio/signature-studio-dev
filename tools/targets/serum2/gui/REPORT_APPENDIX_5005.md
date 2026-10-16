# REPORT 付録 — SR-85 (#5034) 間接 call の候補化と閉包の上限 (#5005 の残作業)

- 親: `REPORT_SR37.md` §4 (下限・SR-83)。本付録は §4 の下限に対する上限の測定と反復の結果。


- 日付: 2026-10-16 / 親: #5005 (SR-83) / 前段: §4 (下限 87 関数・10,194 B・間接 call 51)
- 測定 commit (コード): §5.1〜§5.5 は `1542ade80` (`gui/indirect_sr85_own_vt.py`・`gui/ghidra_xferonoff_indirect.java` を追加した commit)。§5.6 は `593b6915a` (`gui/iterate_sr85_upper.py`・`gui/xferonoff_upper2_fns.tsv` を追加した commit)。以後このディレクトリのコードは未変更。
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

- §5.1〜§5.5 の測定 commit (コード): `1542ade80`。
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
- 注: これは **1 段の値** (own vtable の候補 16 関数を root に足した閉包)。新たに到達した 70 関数の中の間接 call は、この段では候補化していない。反復で収束させた値は §5.6 (162 関数・23,190 B)。
- 測定時間: 上限の閉包 `-process` 6.8 秒 (real)。import + 自動解析は 18 分 21 秒 (real)。

### 5.4 受入 3: 下限と上限 (1 段) の差

- 差分: 関数数 **+70** (157 − 87)、本体合計 **+12,033 B** (22,227 − 10,194)。
- 差分の内訳: 1 段目の新規 root は **11 件** (候補 16 件のうち、下限の root 8 件と重複する 5 件を除く)。下限の root 8 件は両方の集合に含まれる。そこから到達した追加の関数 70 件 (本体 +12,033 B) が 2 段目以降を含む。
- 反復で収束した値 (§5.6・162 関数・23,190 B) との差は **+75 関数・+12,996 B** (23,190 − 10,194)。うち 1 段 → 収束の増分は +5 関数・+963 B。
- 対応物: 本 REPORT §4.4 の canvas 側の対応物なしの判定は変えない (本 §5 は閉包の大きさだけを測る)。

### 5.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 収束後 (§5.6) の未解決 6 箇所: `0x180136bf0` 3・`0x180138180`・`0x180142540`・`0x1809ca77c` | 閉包は収束したが真の上限ではない (6 箇所の先は閉包に入らない) | #5935 [SR-97] (未解決 6 箇所と `call reg` の 2 段目以降) |
| 同じ slot を持つ別クラス vtable の候補 (型未追跡) | 候補が XferOnOffButton の vtable に限定 | #5934 [SR-96] (別クラス vtable の型追跡) |
| `call reg` (レジスタ値) の 2 段目以降の解決 | 収束後の閉包内の直接 `call reg` 5 箇所 (§5.6) が未確定 | #5935 [SR-97] |

### 5.6 候補を root に加える反復 (収束の実測)

- 手順: 閉包 → 閉包内の間接 call の候補化 (own vtable・§5.2 の規則と同じ) → 新規候補を root に加えて閉包し直す。新規候補が 0 になるまで回す。スクリプト `gui/iterate_sr85_upper.py` (commit 済み)。
- 測定 commit (コード): `593b6915a`。入力は §5.1 と同じ `Serum2_win64.vst3` (sha256 `501e7bb3…4e5283`)。Ghidra 12.1.4 の import は `ghidra_fn_size.java` で再実施 (**18 分 50 秒**・real)。

#### 5.6.1 再現手順

前提: §5.1 の sh ブロックで `work/` に `Serum2_win64.vst3` と `xferonoff_fns.tsv` を作り終えていること。`GHIDRA_HOME` に Ghidra 12.1.4 が展開済みで、`work/ghproj` に `ghidra_fn_size.java` による import 済みのプロジェクトがあること。`work/` は gitignore 対象。

```sh
cd tools/targets/serum2/work
cp -f ../gui/xferonoff_upper_fns.tsv xferonoff_upper_fns.tsv   # 上限の初期 root (19 行・sha256 c741878…26fb)
export JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64 PATH=$JAVA_HOME/bin:$PATH
GHIDRA_HOME=<Ghidra 12.1.4 の展開先> python3 ../gui/iterate_sr85_upper.py   # 反復ごとに iter=N 行を標準出力へ出す
```

出力 (`work/` 直下): `iter{1,2,3}_fns.tsv` (各反復の root)・`closure_iter{N}/closure.tsv` と `decomp_*.c` (閉包・decompile は commit しない)・`closure_iter{N}.log`・`indirect_iter{N}.log`・`own_vt_iter{N}.tsv` (候補化の結果)。収束時の閉包の commit 済みコピーは `out/sr85_xferonoff_upper_closure.tsv` (sha256 `b9f034be…cc25`)、root の commit 済みコピーは `gui/xferonoff_upper2_fns.tsv` (24 行・sha256 `fcafc8df…82f9`)。

#### 5.6.2 収束の実測 (各反復の期待値 = この表)

| 反復 | root 数 | 閉包 関数数 | 本体合計 | 間接 call | 候補関数 | 新規候補 |
|---|---|---|---|---|---|---|
| 1 (§5.3 の 1 段) | 19 → 23 | 157 | 22,227 B | 100 | 20 | 4 |
| 2 | 23 → 24 | 161 | 23,180 B | 107 | 21 | 1 |
| 3 | 24 | 162 | 23,190 B | 107 | 21 | **0 (停止・収束)** |

- 反復の総時間: 3 回で **48.95 秒** (real・Ghidra 2 回 + Python 解析を含む・runner 4 vCPU・load average 約 1.1)。
- 収束時の閉包 (`out/sr85_xferonoff_upper_closure.tsv`・sha256 `b9f034be…cc25`)、root 集合 (`gui/xferonoff_upper2_fns.tsv`・sha256 `fcafc8df…82f9`)、候補 (`out/sr85_own_vt_iter3.tsv`)。
- 収束時の間接 call 107 箇所の内訳: IAT・外部 import 48 箇所 (閉包の外)、own vtable で候補化 46 箇所 (未解決 0)、INT 系 7 箇所 (呼出しではない)、**未解決 6 箇所** (下表)。48 + 46 + 7 + 6 = 107。
- 未解決 6 箇所 (収束後も候補化できなかったもの):

| 関数 | 命令 | 理由 |
|---|---|---|
| `0x180136bf0` (3 箇所) | `call R10`・`call R10`・`call RAX` | レジスタ値の直接 call。候補規則の対象外 |
| `0x180138180` | `call RAX` | 同上 |
| `0x180142540` | `call RAX` | 同上 |
| `0x1809ca77c` | `call qword ptr [0x180fe12f0]` | 当時は IAT 形式と記録。§5.7 で CFG 間接呼び出しに訂正 |

- **これは真の上限ではない**: (1) 候補化の規則は XferOnOffButton 自身の vtable の slot に限る (他クラスの vtable・型追跡は未実施)、(2) 未解決 6 箇所の先は閉包に入っていないため、真の閉包はここでの値より大きい可能性がある (この値は真の上限の下界の候補)。収束したのは「この規則の下での閉包」であり、§5.3 の 1 段の値 (157 関数) より 5 関数・963 B 多い。
- 差分 (1 段 → 収束): **+5 関数・+963 B** (22,227 → 23,190 B)。本体合計の増分は 1 段目から 2 段目で +963 B 増えた分。

### 5.7 未解決 6 箇所の分類 (run 3・SR-83 残作業 1 項目目)

- 分類スクリプト: `gui/classify_sr83_unresolved.py` (入力 `Serum2_win64.vst3`・sha256 `501e7bb3…4e5283` を確認してから実行)。Ghidra を使わず `pefile`・`capstone` で直接読む。
- 再実行の状態: 本 run (HEAD `5293bb806`) では `plugins-serum2` 素材が `$ARTIFACTS_DIR` に無く、PE を読めないため再実行していない。下表は測定 commit `2297e8a59` の実測 (前 run の値)。
- 測定 commit 以降の差分 (`git diff 2297e8a59 HEAD -- tools/targets/serum2/gui/`):

```diff
-    (0x1809CA7B2, "call [rip] (IAT形式)", "cfg"),
-    (0x1809CA88D, "call [rip] (IAT形式)", "cfg"),
+    (0x1809CA7B2, "call [rip] (CFG候補: slot 中身を確認)", "cfg"),
+    (0x1809CA88D, "call [rip] (CFG候補: slot 中身を確認)", "cfg"),
```

  `label` は `print` の文字列にしか使われず (スクリプトの 87〜119 行)、判定は `kind` と命令の形で決まる。`kind` は両方 `cfg` のまま。よって判定値 (slot・content・CFG-dispatch・global・direct-stores・lea-takes・bss) は変わらない。出力行の TSV は本 run では再現していない。
- 結果 (測定 commit `2297e8a59`。7 サイト = §5.6 の 6 箇所 (`0x1809ca77c` の 1 箇所は `0x1809CA7B2` に対応) + 閉包外の `0x1809CA88D` 1 箇所):

| 箇所 | 命令 | 分類 (実測) |
|---|---|---|
| `0x180136CA7`・`0x180136CE8`・`0x180136D1D` (関数 `0x180136bf0` 内 3 箇所) | `call r10`・`call r10`・`call rax` | 直前の `mov reg, [rip+d]` が読むグローバル `0x1817bf760`。出力 `bss=yes` (ファイルの raw データに無い)。直接 store は 0 件・`lea` での取得は 0 件。静的には書き込みが見つからない (実行時に設定されると解釈) |
| `0x1801381D8` (関数 `0x180138180`) | `call rax` | 同上 (同じグローバル) |
| `0x1801425E3` (関数 `0x180142540`) | `call rax` | 同上 (同じグローバル) |
| `0x1809CA7B2` (関数 `0x1809ca77c` 内) | `call qword ptr [rip+d]` | 旧表の「IAT 形式」は誤り。スロット (`slot=0x180fe12f0`) の中身は `jmp rax` (`content=0x180a186e0`・出力 `CFG-dispatch=yes`)。閉包 TSV では `0x180a186e0` が `_guard_dispatch_icall` (2 バイト) として出る。宛先は `rax` に入る値で、vtable 等から読むため静的には確定しない |
| `0x1809CA88D` (関数 `0x1809ca824` 内・閉包外) | `call qword ptr [rip+d]` | 上と同じ CFG 間接呼び出し (出力 `CFG-dispatch=yes`)。閉包 TSV に `0x1809ca824` は無い。旧表の 6 箇所には含まれていなかった |

- 解釈: `call reg` の 5 箇所 (`0x180136bf0` 3・`0x180138180`・`0x180142540`) の先は、静的解析では確定しない (bss のグローバル・実行時設定)。CFG の 2 箇所は、vtable の型を追跡しない限り宛先を確定できない。よって §5.6 の値 (162 関数・23,190 B) は、この規則の下での値のままで、真の上限は未確定。
