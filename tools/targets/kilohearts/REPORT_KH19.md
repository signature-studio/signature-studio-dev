# KH-19 (#782): ホスト 3 種の間接 call (vtable 経由) を含めた closure 再計算

- 対象: HeartCore.core_64 (Windows, 76,642,304 B, 素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` から `extract_installer.sh` で展開)
- 再現: 依存 `pip install pefile capstone` (または `uv pip install pefile capstone`) の後、
  `python3 scripts/vtable_closure.py work/winpkg/HeartCore.core_64 work/callgraph.pkl work/rtti_vtables.json <ns> <all|nogui> <out.json>`
  (前段 `rtti_walk.py` → `callgraph.py` (14 proc) は `run_all.sh` [3] と同じ。`closures.py` は本 PR では未変更)
- 統計の数え方: 関数数 = 関数の .pdata 先頭アドレス単位の数。バイト = `callgraph.py` の `size` の和。

## 0. 結論

- **closure の再計算は実施した (before/after を実測)。ただし after は「正確な closure」ではなく、vtable slot 番号一致による過大評価である。**
  after は真の closure の上界とは限らない (reg / rip_data / indexed / other の call 先は after に含まれない)。
  before は直接 call だけで到達する集合なので真の closure の下界である。
  対照 Gain でも 160 → 555 (nogui) / 1,995 (all) に膨らみ、after が過大評価側に大きくずれることが分かった。
- 表 (§2) は IAT 分離後の HEAD で再計測した値。`iat` (外部 DLL 関数, 解決不要) と `rip_data` (IAT 以外の関数ポインタ変数) を分けて計上している。
- 「lift / build できるか」は**未実施** (本 run で closure が確定しないため)。未解決は子 issue に分離した (§4)。

## 1. 規則 (`scripts/vtable_closure.py`)

1. before = roots (`<ns>::*Dsp / *MasterDsp / *DspModel` の vtable slot) からの直接 call/jmp 閉包 (`callgraph.py` の辺)。下界。
2. 集合内の各関数を capstone で逆アセンブルし、`call` を分類:
   - `vtable`: `qword ptr [reg + disp]` (disp = 8k) → 候補 = 同 ns の class の vtable の slot k 番目 (全 slot の集合)
   - `direct`: 即値
   - `iat`: `call [rip+..]` の参照先が pefile の import table の IAT slot (`IMAGE_IMPORT_DESCRIPTOR.FirstThunk` から import 数ぶん) → 外部 DLL 関数。解決不要として別計上
   - `rip_data`: `call [rip+..]` の参照先が IAT 以外 (関数ポインタ変数等)。解決せず未解決として件数計上
   - `reg` / `indexed` / `other`: 解決せず未解決として件数計上
3. 候補を閉包に加え、増分が無くなるまで反復 (不動点)。after = 不動点 (vtable slot 一致による過大評価)。
4. モード: `all` = ns の全 class の vtable を候補にする (候補を最大に広げた側。過大評価の参考値)。
   `nogui` = 名前に Editor / Controller / Ui / View / Gui / Skia を含む class を除く (GUI は DSP から呼ばれないという仮定の下の、より狭い候補)。
   どちらも真の closure の上界・下界を保証しない。

**既知の限界**: slot 番号 k が一致する別 class の関数を候補にするため、オブジェクトの型を追わない。これが過大評価の主因。
正確化には「`reg` に入る this の型」の追跡が要る (§4 子 issue)。

## 2. 実測 (HEAD `56b6f85` + 本 PR の IAT 分離, 4 vCPU, 各 1 回)

素材 `plugins-kilohearts` (Windows 側 `HeartCore.core_64` 76,642,304 B) を展開し、`rtti_walk.py` (6,307 クラス) → `callgraph.py` (120,856 関数) の後に `vtable_closure.py` を 8 通り実行した。各 run は 0.26〜1.05 s。

| ns | モード | roots | before 関数 / B | after 関数 / B | vtable 部位 | iat | rip_data | reg | other | indexed |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Snap Heap (micropass) | nogui | 30 | 311 / 97,327 | 1,531 / 722,713 | 2,137 | 122 | 20 | 27 | 5 | 1 |
| Snap Heap (micropass) | all | 30 | 311 / 97,327 | 3,094 / 1,388,293 | 4,147 | 251 | 54 | 86 | 6 | 14 |
| Multipass (multipass) | nogui | 31 | 321 / 113,050 | 1,802 / 817,610 | 2,337 | 139 | 20 | 36 | 10 | 14 |
| Multipass (multipass) | all | 31 | 321 / 113,050 | 3,328 / 1,476,922 | 4,326 | 266 | 54 | 87 | 11 | 27 |
| Phase Plant (phaseplant) | nogui | 25 | 504 / 228,241 | 3,767 / 1,791,711 | 6,854 | 221 | 56 | 83 | 9 | 86 |
| Phase Plant (phaseplant) | all | 25 | 504 / 228,241 | 5,582 / 2,768,378 | 14,138 | 283 | 56 | 119 | 10 | 200 |
| 対照 Gain (gain) | nogui | 27 | 160 / 39,357 | 555 / 178,451 | 622 | 75 | 8 | 2 | 2 | 3 |
| 対照 Gain (gain) | all | 27 | 160 / 39,357 | 1,995 / 731,396 | 1,847 | 251 | 54 | 62 | 3 | 8 |

- `iat` は外部 DLL 関数の call (解決不要)。`rip_data` は IAT 以外の `call [rip+..]` (関数ポインタ変数)。
  IAT 判定前の旧表で `rip_data` に入っていた値 (例: Phase Plant nogui 277) は IAT を含んでいたため、今の値より大きい。
- before の値は `callgraph.py` / `closures.py` の既存値 (Snap Heap 311 関数 / Multipass 321 / Phase Plant 504 は `closures.py` の `closure_funcs` と一致)。
  REPORT §4 の「固有」値 (50,021 / 64,338 / 153,382 B) は `closures.py` の `own_bytes` (共通基盤 188 関数を除き、他 snap-in から到達されない関数のみ) で、本表 (共通基盤を除かない) とは別の数え方。
- 対照 Gain の before は closure 160 関数。REPORT §4 の Gain 固有 1,727 B は own (共通基盤除く) の数であり、本表とは別。
- 未解決 call の内訳: `reg` / `indexed` / `other` / `rip_data` はいずれも解決未着手 (`rip_data` は #849 で扱う)。

## 3. 判定 (#782 の受入条件)

- #782 受入 1 (間接 call を追跡して 3 種の closure を再計算し before/after を表にする): **部分達成**。IAT 分離後の HEAD で再計測した表を出した。after は過大評価で、真の closure ではない。
- #782 受入 2 (lift / build の最初の失敗点): **未達**。正確な closure が無いため lift 対象を確定できない。
- #782 受入 3 (数え方と再計算スクリプトを REPORT に書く): **達成** (§1・§2、スクリプトは `scripts/vtable_closure.py`)。

## 4. rip_data (IAT 以外の関数ポインタ変数) の読み出し解決 (#849)

- 数え方: 「rip_data call 件数」= closure 内の `call [rip+..]` (IAT 以外) の件数 (§2 の rip_data 列と同じ)。「slot 種別」= その参照先 slot (VA) を 1 本ずつ分類した数。
- 規則 (`scripts/vtable_closure.py`): 参照先 slot S について
  - `runtime_store` (.text に `mov [rip+S], x` があり実行時に書き換わる) / `addr_taken` (`lea` で S の番地を取る) → 未確定
  - `null_unused` (初期値 0) / `nonfunc_init` (初期値が関数先頭でない) → 未確定
  - `trampoline` (初期値の関数先頭が `jmp reg` または IAT 外の `jmp [rip+..]`) → 呼び先が静的に決まらない thunk。未確定
  - `static_fn` (初期値の関数が上記以外) → 確定し候補に加える (after_rip)
- 再計測 (HEAD `d7cf3c77` + 本 PR, 4 vCPU, 各 1 回, 各 run 11〜13 s):

| ns | モード | rip_data call 件数 | 参照先 slot | slot 種別 | 確定 slot | after (旧) 関数 | after_rip 関数 |
|---|---|--:|--:|---|--:|--:|--:|
| Snap Heap (micropass) | nogui | 20 | 2 | trampoline 2 | 0 | 1,531 / 722,713 B | 1,531 / 722,713 B |
| Snap Heap (micropass) | all | 54 | 2 | trampoline 2 | 0 | 3,094 / 1,388,293 B | 3,094 / 1,388,293 B |
| Multipass (multipass) | nogui | 20 | 2 | trampoline 2 | 0 | 1,802 / 817,610 B | 1,802 / 817,610 B |
| Multipass (multipass) | all | 54 | 2 | trampoline 2 | 0 | 3,328 / 1,476,922 B | 3,328 / 1,476,922 B |
| Phase Plant (phaseplant) | nogui | 56 | 2 | trampoline 2 | 0 | 3,767 / 1,791,711 B | 3,767 / 1,791,711 B |
| Phase Plant (phaseplant) | all | 56 | 2 | trampoline 2 | 0 | 5,582 / 2,768,378 B | 5,582 / 2,768,378 B |
| 対照 Gain (gain) | nogui | 8 | 2 | trampoline 2 | 0 | 555 / 178,451 B | 555 / 178,451 B |
| 対照 Gain (gain) | all | 54 | 2 | trampoline 2 | 0 | 1,995 / 731,396 B | 1,995 / 731,396 B |

- 全 8 条件で、rip_data の参照先 slot は同じ 2 本 (`0x1813a1d38` / `0x1813a1d40`, `.rdata`)。どちらも初期値は thunk:
  - `0x1813a1d38` → `jmp rax` (レジスタ間接。呼び先は実行時に決まる)
  - `0x1813a1d40` → `jmp [rip+0x1dee2]` → `0x1813a1d38` (上と同じ slot を経由)
- **結論: rip_data の読み出し解決で確定できた候補は 0 件。** after と after_rip は全条件で一致し、rip_data の件数は closure を広げない。
- 過程の誤り (記録): 初版は初期値の先 (thunk) を関数とみなして `static_fn` 判定し、after_rip を +2 関数と出した。thunk の先頭命令を見て `trampoline` 判定を足したところ、確定 0 件になった。この 2 本を関数として扱うのは誤り。
- 残りの未解決 (本 PR 後): rip_data call 件数 8〜56 件/ns は、すべて上記 2 本 (load config の CFG/XFG dispatch ポインタ) 経由で、呼び先は直前の `rax` で決まる。`rax` の出所の追跡は #849 の再試行で行った: [REPORT_APPENDIX_849.md](REPORT_APPENDIX_849.md) (vtable 形 40/54 は候補確定・閉包は不変、残り 14 件は #3363)。
- 対象外 (明記): res 外 (sweep されなかった関数) が S へ書き込む可能性は未確認。store 走査は `callgraph.pkl` の res 内関数だけ。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 型を追う (this の型追跡) による正確な closure。現在は slot 番号一致の過大評価 | after 表が真値でない | #848 |
| `rip_data` の呼び先 `rax` (#849 の再試行): vtable 形 40/54 は候補確定 (閉包は不変)。残り 14 件 (対照 Gain・all) は呼び出し戻り値等で未確定 | 14 件の呼び先が閉包に入らない | #3363 (KH-55) |
| 確定 closure の lift / build 最初の失敗点 | 受入 2 未達 | #850 |
| 人手の検収 (lift 結果の bit-exact 化は本 issue の範囲外) | — | — |

## 5. #848 (this 型の 1 段追跡) の試行結果 (再測定 HEAD `54fc6273`, 4 vCPU, 各 1 回)

- 測定コード (`vtable_probe_this.py`) は `c36afb68` で追加した。その後 `d8a873a9` は文書のみの変更で、`main` を merge した HEAD (`54fc6273`) では `vtable_closure.py` が `main` 側で更新されている。
- 表の値は `54fc6273` (merge 後の `scripts/`) で再測定した。素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` を `tar --zstd -xf` で展開し、Windows 側のみ `unzip` → `rtti_walk.py` (6,307 class) → `callgraph.py` (120,856 関数, 4 round) → `vtable_closure.py` / `vtable_probe_this.py` の順で実行した。
- 再測定の結果: Gain before 160 / vtable_closure nogui 555 / all 1,995 / probe narrow 1,994 (vtable sites narrow 83・wide 1,764)。いずれも前回の報告値と一致。

試行は `scripts/vtable_probe_this.py` (1 行 JSON を出力)。規則: 呼び出し元 f の所有 class が ns 内で一意に決まれば、
vtable call の候補をその class の同 slot に限る (narrow)。一意に決まらなければ従来どおり ns 全 class の同 slot (wide)。

| 対象 | before 関数 | after (narrow) 関数 | vtable call 内訳 narrow / wide |
|---|--:|--:|--|
| 対照 Gain (gain) | 160 | 1,994 | 83 / 1,764 |

- 判定: **棄却**。narrow は after を 1,995 → 1,994 (1 関数) しか縮めない。受入 2 (160 関数との差分 0) には届かない。
- 原因: closure の大半 (1,764 / 1,847 の vtable call) は呼び出し元が vtable に載らない関数 (shared template・自由関数) で、
  所有 class を決められない。`this` の型は呼び出し元の vtable 所有では決まらず、呼び出し鎖を通した伝播 (呼出し引数の型) が要る。
- 含意: vtable 規則の精度は「呼び出し元の所有」では上がらない。次の候補は (a) 呼び出し点の `rcx` (this) を
  直前の代入 (`mov rcx, reg` / 引数レジスタ) から逆方向に追う、(b) 登録側 (`new ...Dsp` 生成箇所) から class を
  伝播させる、のいずれか。どちらも本 run の範囲外 (要 Ghidra 等の基盤または別 run)。
#### #848 の受入条件への対応 (本節)

- 受入 1 (this 型を追跡し、Snap Heap / Multipass / Phase Plant の 3 種の間接 call 候補を型に限定して closure を再計算): **部分達成**。Gain のみ narrow を実装・計測。3 種は未実施。
- 受入 2 (対照 Gain の closure が手検証の 160 関数と差分 0): **未達**。narrow は 1,994 関数 (差分 1,834)。
- 受入 3 (before/after 表と未解決 call の内訳を REPORT に書く): **部分達成**。本節の表は Gain のみ。§2 の表は #782 の wide 規則による値で、3 種の narrow 表は無い。

## 6. #848 (KH-19b) 受入 2 の検証と判定 (検証 HEAD `8504517d`, 4 vCPU)

- 注記: 本節の計測値は素材 `plugins-kilohearts` を展開した旧 run の出力を転記したもの。PR 本文は計測コードを HEAD `8504517d` 相当としているが、旧 run の HEAD は再確認できない。JSON は保存していない。本 HEAD での再計測は素材不足 (`fl-win64` のみ取得) で未実施。
- 再現手順: 素材 `plugins-kilohearts` を展開 → `extract_installer.sh` → `rtti_walk.py` → `callgraph.py` → `vtable_closure.py` / `vtable_probe_this.py` / `vtable_gap_probe.py`。§5 と同じ値 (before 160 / nogui 555 / all 1,995 / narrow 1,994) を旧 run で得た。
- `scripts/vtable_gap_probe.py` (gain, 旧 run の出力): before 160 関数の中の vtable call 112 部位。候補 (全 class の同 slot) 781 件のうち before 外は 458 件。
- 呼び出し直前に `rcx` (this) へ書く命令 (同一関数内・直前のみ): `mov reg, reg` 102 / 書き手なし 6 / その他 4。レジスタ由来は同関数内では追えず、this 型は呼び出し鎖の伝播が要る (§5 と同じ結論)。
- 未計測・取り下げ: 外れる候補の class 別内訳 (GUI 系/その他) は出力していないため記載しない。「112 部位すべてに before 外の候補がある」は `sites_with_outside_cand` を JSON に記録していないため取り下げる。
- 家族規則 (`*MasterDsp` / `*Dsp` / `*DspModel` の vtable slot のみを候補にする) の closure 関数数 (`before_funcs`) は未記録。160 関数との集合比較は未実施。手検証の 160 関数一覧はリポジトリに無いため、差分 0 は主張しない。
- **受入 2 の判定: 未達のまま**。家族規則を採用するかは、手検証の一覧を得てから判断する。

## 7. #1619 (KH-19e) 対照 Gain の before 160 一覧と検証 (測定 commit `3a76c8cb`, 4 vCPU)

- 検証起点: 測定 commit は `3a76c8cb` (コードを変えた最後の commit)。以降の `764b1719` と本節の追記 commit は REPORT_KH19.md の追記のみ。`git diff 3a76c8cb HEAD -- tools/targets/kilohearts` は REPORT_KH19.md だけ。PR 本文の検証 HEAD は、この節を含む最新 HEAD に揃える。
- 数値の再測定: 素材 `plugins-kilohearts` は本 run の `$ARTIFACTS_DIR` に無い (`fl-win64` のみ) ため、`rtti_walk` / `callgraph` / `vtable_closure` は本 run では再実行していない。before / after の値は §2・§5 の値と一致 (ここでは書き直さない)。
- 測定時の所要 (4 vCPU・各 1 回): `rtti_walk.py` 1.8 s → `callgraph.py` 7.8 s → `vtable_closure.py gain all` 11.3 s。測定時の load average は記録していない (未記録)。
- 一覧: `gain_before_160.tsv` (正本・生成: `scripts/gain_before_list.py`)。列は `func_rva` / `size` / `root_class` / `parent_rva` / `call_site_rva` / `verified`。`verified` 列は全行 `auto` (機械生成)。
- 本 run の新規検査 (TSV のみ。`python3` で読み込み。load average 1 分平均 0.40・4 vCPU の時点で実行):
  - 行数 160 (ヘッダ除く)。§2 の before 160 と一致。`func_rva` の重複 0 件。
  - `verified` は `auto` 160 行・`manual` 0 行。
  - `root_class` が空でない行 (root) は `parent_rva` が空。それ以外の全行は `parent_rva` が一覧内にあり、親を辿ると root に到達する (欠落 0 件)。
- 差分: 一覧は `vtable_closure` と同じ `direct_closure(roots)` から作るため、「before 160 の再現が一覧と一致する」ことは自明にしか確認できず、手検証の代替にはならない。
- **受入 1 (各関数を手で確認) は未達**。受入 2 (手検証 160 との差分 0) は未達。`verified` 列を `manual` に変える行は、本 run では 0 件。
- 人手検証の範囲と差分の判定は #1816 (KH-19f) に切り出す。

## 8. #1816 (KH-19f) 機械照合と手検証の判定 (4 vCPU, 基点 main `f34e4f46`)

- **測定 commit** (測定対象のコードを変えた最後の commit): `264893e2`。以下の実測はすべてこの commit の内容で実行した。
- **検証 HEAD** (本節を含む PR の最終 commit): PR 本文に記載。測定 commit とは別の概念で、両者の差分は下の鮮度の証跡で示す。

- 前提 #1823 (KH-19e) は merge 済み。TSV は main に存在する (`3a76c8cb`・`verified` 全 160 行 `auto`)。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` のみ展開 (tar で zip だけ取り出し)。Windows 側の `extract_installer.sh` 相当 (`payload.dat` → `windows.zip/*` → `HeartCore.core_64` 76,642,304 B)。mac 側は不要のため未展開。
- 素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` (3,833,108,300 B) を `tar --zstd -xf` で取り出し、Windows 側を手で展開した
  (`payload.dat` → `windows.zip/*` → `HeartCore.core_64` 76,642,304 B)。`extract_installer.sh` は mac 側の dmg (`Kilohearts Offline Installer.dmg`) が無いと途中で停止するため、本 run では Windows 部分だけを手で展開した (スクリプト修正は本 PR の範囲外)。
- 再生成 (測定 commit `264893e2`・4 vCPU・各 1 回・load average は 1 分値): `rtti_walk.py` 1.614 s (load 0.72) → `callgraph.py` 7.539 s → `vtable_closure.py gain all` 11.351 s (load 1.66 時点)。
  before 160 / after(all) 1,995 / vtable 1,847 / iat 251 / rip_data 54 / reg 62 / indexed 8 / other 3 — §2・§5 と一致。
- 再現コマンド (`tools/targets/kilohearts` で実行): `python3 scripts/rtti_walk.py work/winpkg/HeartCore.core_64 work/ms/rtti_vtables.json` → `callgraph.py <同> work/ms/rtti_vtables.json work/ms/callgraph.pkl 14` → `vtable_closure.py <同> work/ms/callgraph.pkl work/ms/rtti_vtables.json gain all work/ms/gain_all.json`。
  以下の `verify_gain_tsv.py` / `gain_tsv_negctl.py` も同じ `work/ms/` を使う。
- 機械照合 `scripts/verify_gain_tsv.py` (TSV の各行を .text のバイト列から独立に検査、160 行):

| 検査 | 内容 | 結果 |
|---|---|---|
| A | root 行 27 件が gain の `*Dsp`/`*MasterDsp`/`*DspModel` の vtable slot に載る | 27 / 27 |
| B | 非 root 行 133 件で、親関数の `call_site_rva` の命令が `call`/`jmp` rel で子 `func_rva` を指す | 133 / 133 |
| D | 親鎖を辿ると全行が root に到達する | 160 / 160 |
| C (情報) | `func_rva` が .pdata の関数先頭と一致 | 113 / 160 (残り 47 は leaf sweep で拾った関数) |

- 測定時間: `verify_gain_tsv.py` 8.432 s (測定 commit `264893e2`)。

**ネガティブコントロール** (`scripts/gain_tsv_negctl.py` で TSV を 1 件だけ壊したコピーを作り、同じ `verify_gain_tsv.py` で照合。元 TSV は変更しない):

| 壊し方 | 対象の検査 | 正常時 | 壊した後 | FAIL した行 |
|---|---|--:|--:|---|
| root 行 1 件 (`func_rva` 0x3370) の `root_class` を `BogusDsp` に置換 | A | 27 / 27 | 26 / 27 | 0x3370 |
| 非 root 行 1 件 (`func_rva` 0x5c50) の `call_site_rva` を +1 (0x4d096 → 0x4d097) | B | 133 / 133 | 132 / 133 | 0x5c50 |

- 検査は両方とも 1 件の破損で FAIL し、他の検査 (C・D) は変わらない。レビュワーが別環境で同じ 2 件を壊して得た値 (26 / 27・132 / 133) とも一致。

- 判定: **受入 1 (各関数を手で確認し `verified=manual`) は未達**。上記は機械照合であり、人手検証ではない。`verified` 列は 160 行すべて `auto` のまま残した。
- 受入 2 (手検証 160 との差分 0): **未達・判定不能**。手検証の集合が無いため、差分は取れない。機械照合で「TSV の 160 行は gain の direct closure の再現として整合する」ことまでは言える。
- 受入 3 (自動生成分を手検証済みと書かない): 本節で遵守。

**鮮度の証跡** (`docs/WORKFLOW.md` §6・#1268):

- 測定 commit: `264893e2`。`git diff --stat 3a76c8cb 264893e2 -- scripts/rtti_walk.py scripts/callgraph.py scripts/vtable_closure.py scripts/extract_installer.sh gain_before_160.tsv` は空 (測定パイプラインと TSV は `3a76c8cb` 以降不変)。
  `3a76c8cb` からの追加は検査 2 本のみ: `scripts/verify_gain_tsv.py` (c38d37a4) と `scripts/gain_tsv_negctl.py` (264893e2)。
- `git diff 264893e2 HEAD -- tools/targets/kilohearts/scripts` の出力は**空 (0 行)**。scripts 以下の実行コードは測定 commit から変えていないため、再測定は不要 (差分 0 の範囲)。
- `git diff --stat 264893e2 HEAD -- tools/targets/kilohearts` の出力 (検証 HEAD 時点):
  `REPORT_KH19.md` (+29/-1) と `license/KH656_REPORT.md` (+18)。後者は main 取り込み merge (`cba3379d` 以降) による main 側の変更で、測定対象 (scripts / TSV / 素材の展開手順) の外。
- 検証起点 (測定を実行した HEAD) = 測定 commit `264893e2`。検証 HEAD (PR の最終 commit) とは区別する。

#782 の受入 (lift / build の最初の失敗点) は未達で、§3 に記載。

未解決の起票先: (a)/(b) の this 型伝播は #848 に残す (#848 は CLOSED。受入 2 は未達のまま)。rip_data は #849、lift 失敗点は #850 (§4)。

## 8. #2098 (KH-19g) 対照 Gain の before 160 の機械照合 (人手検証は未実施)

- 素材: `plugins-kilohearts` を `$RUNNER_TEMP` に `tar --zstd -xf` で展開し、`KH_SRC` で `extract_installer.sh` を実行 (Windows 側は成功。macOS スライスの `llvm-lipo` は runner に無く失敗したが本節の対象外)。
- 再生成: `rtti_walk.py` → `callgraph.py` (120,856 関数) → `gain_before_list.py gain`。`before_funcs` = 160、roots = 27 で §2 と一致。load average 0.99 (開始時)。
- 一覧の再生成結果は正本 `gain_before_160.tsv` と列 1〜5 が全行一致。
- 機械照合 `scripts/gain_mech_check.py` (本 issue で追加): `{"rows":160,"roots":27,"root_slot_ok":27,"nonroot":133,"edge_ok":133,"bad":[]}`。
  - root 27 件は rtti の gain ns vtable slot に実在。
  - 非 root 133 件は親関数の `call_site_rva` 位置の命令が `func_rva` への direct call/jmp。
- `vtable_closure.py gain nogui` の before_funcs = 160 (before_bytes 39,357) で一致。
- **判定**: 機械照合は通ったが、これは人手検証ではない。`verified` 列は全 160 行 `auto` のまま。手検証された行は 0 件のため、手検証集合と before 集合の差分は計算できず、差分 0 は主張しない。
- 受入 1 (人手で呼び出し元と call 位置を確認し `manual` にする): **未達**。
- 受入 2 (手検証集合と before 集合の差分 0 を書く): **未達** (手検証集合が空)。
- 受入 3 (自動生成分を手検証済みと書かない): **達成** (本節と `verified` 列で明示)。

## 9. #2155 (KH-34) 人手検証用ダンプの生成 (人手検証は未実施・ダンプは素材付きで再生成済み)

- 基点 main: `6444b186`。本節の追加で変えたコードは `scripts/gain_manual_dump.py` (新規) のみ。既存 scripts は変えていない。
- 素材: `plugins-kilohearts` を `tar --zstd -xf` で展開し、Windows 側 (`payload.dat` → `windows.zip/*` → `HeartCore.core_64` 76,642,304 B) だけを手で取り出した (mac 側は不要)。
- 再生成: `rtti_walk.py` → `callgraph.py` (120,856 関数) → `gain_before_list.py <core> work/ms/callgraph.pkl work/ms/rtti_vtables.json gain <out>`。before_funcs = 160、roots = 27。列 1〜5 は正本 `gain_before_160.tsv` と全行一致。
- 修正 (レビュー指摘 2): ROOT 行の読み取りを 4 バイトから「関数の `size` 内に収まる命令を最大 3 個」に変えた (`ins_at(f, 48)` を `end = f + size` で切る)。4 バイトでは `push`/`mov` 1〜2 個分しか出ず、16 バイトでは `int3` パディングや 17 バイト超の命令で 3 個に届かない行が残った (旧 `cf0f042e` の #10 は 2 命令、#7 は `int3` を含んでいた)。
- 測定 commit: `ce3e80e4` (コード変更の最後の commit)。main `6444b186`→`e082c4f1` の取り込み merge `6d48916d` 後、`git diff ce3e80e4 HEAD -- tools/targets/kilohearts/scripts` の出力は空 (差分 0)。
- 測定 (素材 `plugins-kilohearts.tar.zst` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B。作業は `_temp` 配下 (repo 外・gitignore 外)・`tools/**/work/` 不使用。4 vCPU・load average 1.00〜1.25・1 回):
  - `rtti_walk.py`: vtable classes 6307 (約 1.8 s)
  - `callgraph.py`: 120,856 関数、4 round で収束 (約 6.6 s)
  - `gain_before_list.py`: before_funcs = 160、roots = 27 (約 0.3 s)。列 1〜5 は正本 `gain_before_160.tsv` と全行一致 (diff 0)
  - `gain_manual_dump.py`: exit 0、0.10 s、出力 160 行 (`#` ヘッダ 160・ROOT 27)。call_site が命令境界に乗らない行 0 件
  - 4 段の全チェーンを `ce3e80e4` (2 回目) と `6d48916d` (取り込み後) で実行し、`gain_manual_dump.py` の出力は 3 回 (`ce3e80e4` の既存 TSV 再入力・`ce3e80e4` 全チェーン・`6d48916d` 全チェーン) とも同一。
- ROOT 行の出力例 (`#9`、`GainMasterDsp`):
  ```
  #9 0x1dac0 size=12 root=.?AVGainMasterDsp@gain@@
    ROOT
      0x1dac0: movsxd rax, edx
      0x1dac3: mov rcx, qword ptr [rcx + 0x10]
      0x1dac7: mov rax, qword ptr [rcx + rax*8]
  ```
- ROOT 行の命令数: 27 行中 20 行が 3 命令。残り 7 行は `size` が 1〜8 B の短い関数 (`ret` 等) で、関数内に 3 命令が存在しない (例: #7 `size=1`、`ret` のみ)。`size` を超えて読まないため、この 7 行は関数内の全命令を出す。
- 判定: ダンプは人手検証の**材料**であり、検証結果ではない。`verified` 列は 160 行すべて `auto` のまま。手検証集合は空のため、受入 1・2 は未達。
- 未達の追跡: 160 行の人手確認 (受入 1) と、手検証集合と before 集合の差分 (受入 2) は #2176 (KH-35) に残す。再測定は本節で完了済み (#2176 には含めない)。
- #2176 (KH-35) の PR で、AI が dump を読んだ判定の記録と検算を [REPORT_APPENDIX_2176.md](REPORT_APPENDIX_2176.md) に置いた。この判定は人手検証ではなく、`verified` 列は 160 行とも `auto` のまま。人手確認は子 issue #3254 ([KH-50]) に移した。

## 10. #3064 (KH-37) x64c 閉包 148 と TSV 160 行の数え方

- 結論: x64c 閉包 148 と TSV 160 行の差 12 件は、数え方で説明できる (`iat_thunk` 2・`tail_absorbed` 9・SEH 着地点 1。未説明 0)。`0xfd0995` は `0xfd08d0` の `__except` 着地点で、CFG の辺では到達しない。`x64c.py` は変更しない。
- 測定・内訳・判定: `REPORT_APPENDIX_3064.md` (測定 commit `a89f92b2`)。

## 11. KH-38 (#3065) 対照 Gain closure の unsup 被覆 (結論のみ)

- 対照 Gain の before 160 closure で残っていた unsup (VEX/FMA 系ほか) を flelift x64c で被覆した。before / after の数値・内訳・未解決は [REPORT_APPENDIX_3065.md](REPORT_APPENDIX_3065.md)。
- 再測定スクリプト: `scripts/lift_closure_x64c.sh`。差分テスト: `tools/flelift/tests/x64c_vex_diff.py`。

