# KH-19 (#782): ホスト 3 種の間接 call (vtable 経由) を含めた closure 再計算

- 対象: HeartCore.core_64 (Windows, 76,642,304 B, 素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` から `extract_installer.sh` で展開)
- 再現: `python3 scripts/vtable_closure.py work/winpkg/HeartCore.core_64 work/callgraph.pkl work/rtti_vtables.json <ns> <all|nogui> <out.json>`
  (前段 `rtti_walk.py` → `callgraph.py` (14 proc) は `run_all.sh` [3] と同じ。`closures.py` は本 PR では未変更)
- 統計の数え方: 関数数 = 関数の .pdata 先頭アドレス単位の数。バイト = `callgraph.py` の `size` の和。

## 0. 結論

- **closure の再計算は実施した (before/after を実測)。ただし「正確な closure」ではない。** 間接 call の解決を vtable slot 番号だけで行うため、
  after は真の closure の**上界に近い過大評価**になる。Gain (対照) でも 160 → 555 (nogui) / 1,995 (all) に膨らみ、
  過小評価ではなく過大評価であることが分かった。
- 「lift / build できるか」は**未実施** (本 run で closure が確定しないため)。未解決は子 issue に分離した (§4)。

## 1. 規則 (`scripts/vtable_closure.py`)

1. before = roots (`<ns>::*Dsp / *MasterDsp / *DspModel` の vtable slot) からの直接 call/jmp 閉包 (`callgraph.py` の辺)。
2. 集合内の各関数を capstone で逆アセンブルし、`call` を分類:
   - `vtable`: `qword ptr [reg + disp]` (disp = 8k) → 候補 = 同 ns の class の vtable の slot k 番目 (全 slot の集合)
   - `direct`: 即値
   - `reg` / `rip_data` / `indexed` / `other`: 解決せず未解決として件数のみ計上
3. 候補を閉包に加え、増分が無くなるまで反復 (不動点)。after = 不動点。
4. モード: `all` = ns の全 class の vtable を候補にする (上界)。`nogui` = 名前に Editor / Controller / Ui / View / Gui / Skia を含む class を除く (GUI は DSP から呼ばれないという仮定の下の、より狭い候補)。

**既知の限界**: slot 番号 k が一致する別 class の関数を候補にするため、オブジェクトの型を追わない。これが過大評価の主因。
正確化には「`reg` に入る this の型」の追跡が要る (§4 子 issue)。

## 2. 実測 (HEAD `9f52e7fc` + 本 PR, 4 vCPU, 各 1 回)

| ns | モード | roots | before 関数 / B | after 関数 / B | vtable call 部位 | 未解決 call (種別: 件数) |
|---|---|--:|--:|--:|--:|---|
| Snap Heap (micropass) | nogui | 30 | 311 / 97,327 | 1,531 / 722,713 | 2,137 | rip_data 142, reg 27, other 5, indexed 1 |
| Snap Heap (micropass) | all | 30 | 311 / 97,327 | 3,094 / 1,388,293 | 4,147 | rip_data 305, reg 86, other 6, indexed 14 |
| Multipass (multipass) | nogui | 31 | 321 / 113,050 | 1,802 / 817,610 | 2,337 | rip_data 159, reg 36, other 10, indexed 14 |
| Multipass (multipass) | all | 31 | 321 / 113,050 | 3,328 / 1,476,922 | 4,326 | rip_data 320, reg 87, other 11, indexed 27 |
| Phase Plant (phaseplant) | nogui | 25 | 504 / 228,241 | 3,767 / 1,791,711 | 6,854 | rip_data 277, reg 83, other 9, indexed 86 |
| Phase Plant (phaseplant) | all | 25 | 504 / 228,241 | 5,582 / 2,768,378 | 14,138 | rip_data 339, reg 119, other 10, indexed 200 |
| 対照 Gain (gain) | nogui | 27 | 160 / 39,357 | 555 / 178,451 | 622 | rip_data 83, reg 2, other 2, indexed 3 |
| 対照 Gain (gain) | all | 27 | 160 / 39,357 | 1,995 / 731,396 | 1,847 | rip_data 305, reg 62, other 3, indexed 8 |

- before の値は `callgraph.py` / `closures.py` の既存値 (Snap Heap 311 関数 / Multipass 321 / Phase Plant 504 は `closures.py` の `closure_funcs` と一致)。
  REPORT §4 の「固有」値 (50,021 / 64,338 / 153,382 B) は `closures.py` の `own_bytes` (共通基盤 188 関数を除き、他 snap-in から到達されない関数のみ) で、本表 (共通基盤を除かない) とは別の数え方。
- 対照 Gain の before は closure 160 関数。REPORT §4 の Gain 固有 1,727 B は own (共通基盤除く) の数であり、本表とは別。
- 未解決 call の内訳: `rip_data` は関数ポインタ変数 (IAT 以外) で、データ読みで解決できる余地がある (未実施)。`reg` / `indexed` / `other` は解決未着手。

## 3. 判定

- 受入 1 (間接 call を追跡して 3 種の closure を再計算し before/after を表にする): **部分達成**。表は出した。ただし after は過大評価で、真の closure ではない。
- 受入 2 (lift / build の最初の失敗点): **未達**。正確な closure が無いため lift 対象を確定できない。
- 受入 3 (数え方と再計算スクリプトを REPORT に書く): **達成** (§1・§2、スクリプトは `scripts/vtable_closure.py`)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 型を追う (this の型追跡) による正確な closure。現在は slot 番号一致の過大評価 | after 表が真値でない | 子 issue (下記) |
| `rip_data` (関数ポインタ変数) の読み出し解決 | 未解決 call 128〜339 件/ns | 子 issue |
| 確定 closure の lift / build 最初の失敗点 | 受入 2 未達 | 子 issue |
| 人手の検収 (lift 結果の bit-exact 化は本 issue の範囲外) | — | — |
