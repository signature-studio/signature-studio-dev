# #1168 (LD-36) D17 修復 pass 続き: 複数 load の CELL_COLLAPSED 調査 (部分達成)

**判定: 未達 (調査のみ)**。修復 pass は未実装。受入条件 1〜3 は未達、4 は未実施。PR は `Refs #1168`。
実装は子 issue `[LD-47]` に分割 (親: #1168)。

前提: `REPORT_968.md` §4。単一 load 規則 (`fix_d17.py`) の対象外の 28 関数 / 53 site。

## 1. 再現 (`audit_lsf_ssa.py`, HEAD 起点, work-m11 のみ)

- cfg は glob をクォートして渡す (`'../work/boot*.drc.config.json'`)。クォートしないと `boot0` 1 本だけになり、
  集計が `lsf_sites_arg 29` になる (誤り)。クォートすると `90 / 370 / 169` となり、REPORT_968 の修復前と一致する。
- 修復前の store 宛 CELL_COLLAPSED 関数は 49、うち K を読む IR load が 1 本の 21 関数を除く 28 関数が対象。

## 2. 対応付けの調査結果

対象 28 関数 (K 単位で 32 組。IR load が 1 本だけの K は除く) について、K を読む IR load の本数と、機械語側で `mov r,[rip+X]` が X=K を指す本数を比べた。

- 同数は 17 組、異なるのは 15 組 (例: `100a3d0` K=`11e35c8` IR 5 / 機械 8、`128f9e0` K=`11e26a0` IR 14 / 機械 17、`d0cee0` K=`11e4080` IR 11 / 機械 13、`ff63f0` K=`11e14a0` IR 15 / 機械 16)。
- 機械側の参照には、load 以外 (store 先・アドレス計算) も含まれる。そのため本数の差だけでは対応を決められない。
- 同じ K を読む load が同一関数内に複数あり、かつ型 (`load ptr` / `load i32`) が混在する例がある (`e53810`, K=`0x11e0120`: `load ptr` 1 本と `load i32` 1 本)。型だけでは一意に決まらない。
- `11d47c0` (K=`0x11e0120`) は IR load 2 本が同一型 (`load i32`) で、機械側の site 2 本 (`mov dword ptr [rax], ecx`) も同型。順序で対応させる根拠はあるが、本数が一致する他の関数で検証していない。

結論: 機械語 site と IR load の対応は本数・型・幅だけでは決まらない。対応規則は、機械側の**値の流れ** (rip セル → レジスタ → store 先) を追う必要がある。
単純な順序対応を入れると、誤った load を `%cellp` 経由に書き換えて silent miscompile を起こすおそれがあるため、本 run では規則を書かない。

## 3. 次の作業 (子 issue `[LD-47]`)

- 機械語 site ごとに「rip セル → 読んだレジスタ → 使う load」の連鎖を追い、load と site を 1 対 1 で結ぶ。
- 結べた load だけを `fix_d17.py` の拡張で修復。結べない load は触らない。
- ネガコン (修復を外すと store 宛 CELL_COLLAPSED が戻る) を追加。
- 検証: `audit_lsf_ssa.py` の store 宛 CELL_COLLAPSED の減少、`emcc -c` の構文検証。
- 受入条件 2 (CELL_COLLAPSED 0) は、上記の対応付けがすべて結べた場合にだけ達成可能。結べない site が残れば、その時点で数を報告する。
