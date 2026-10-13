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

## 3. 判定

- 受入 1 (間接 call を追跡して 3 種の closure を再計算し before/after を表にする): **部分達成**。IAT 分離後の HEAD で再計測した表を出した。after は過大評価で、真の closure ではない。
- 受入 2 (lift / build の最初の失敗点): **未達**。正確な closure が無いため lift 対象を確定できない。
- 受入 3 (数え方と再計算スクリプトを REPORT に書く): **達成** (§1・§2、スクリプトは `scripts/vtable_closure.py`)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 型を追う (this の型追跡) による正確な closure。現在は slot 番号一致の過大評価 | after 表が真値でない | #848 |
| `rip_data` (IAT 以外の関数ポインタ変数) の読み出し解決 | 未解決 call (rip_data 8〜56 件/ns, nogui) が closure の外に残る | #849 |
| 確定 closure の lift / build 最初の失敗点 | 受入 2 未達 | #850 |
| 人手の検収 (lift 結果の bit-exact 化は本 issue の範囲外) | — | — |
