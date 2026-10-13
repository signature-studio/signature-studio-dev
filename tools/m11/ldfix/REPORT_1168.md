# #1168 (LD-36) D17 修復 pass 続き: 複数 load の CELL_COLLAPSED 調査 (部分達成)

**判定: 未達 (調査のみ)**。修復 pass は未実装。受入条件 1〜3 は未達、4 は未実施。PR は `Refs #1168`。
実装は子 issue `[LD-47]` に分割 (親: #1168)。

前提: `REPORT_968.md` §4。単一 load 規則 (`fix_d17.py`) の対象外の 28 関数 / 53 site。

## 1. 再現 (`audit_lsf_ssa.py`, work-m11 のみ)

- 測定 commit: `916d9932` (`tools/m11` のコードを最後に変えた commit。以降の変更は docs のみ)
  - 訂正 (LD-47 review, §4 参照): 上記の「`tools/m11` のコードを最後に変えた commit」と「以降は docs のみ」は誤り。`tools/m11` の非 md 変更は `916d9932..12586095` に 18 件ある。`tools/m11` のコードを最後に変えた commit は `02e2c5a2` (`12586095` の祖先)。本 §1 の実測の基準は §4 の測定 commit `12586095` とする。
- 素材: `[WORK-M11]` (`docs/REFERENCES.md` §1。取得指定 `oc_artifacts: work-m11`、展開先 `tools/m11/work/`)
- 鮮度の証跡 (`git diff 916d9932 HEAD -- tools/m11`、`*.md` を除く): 空 = コード差分 0 (`git diff 916d9932 HEAD --name-only -- tools/m11` の結果は `*.md` のみ)
  - 訂正 (LD-47 review): 上記の証跡は誤り。`git diff --name-only 916d9932 HEAD -- tools/m11` の非 md は 18 件 (`git diff --numstat` で +698 / -27)。空ではない。正しい鮮度の証跡は `git diff 12586095 HEAD -- tools/m11` の非 md = 0 件 (§4 参照)。

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

## 4. LD-47 (#1375) 実測: 現 HEAD での基準値と訂正 (2026-10-14)

測定 commit: `12586095` (run 開始時の origin/main。`tools/m11` の検証はこの HEAD のコードで行った)。
素材: `work-m11` を `$HOME/artifacts` から `tar --zstd -xf ... -C <repo>` で展開 (展開先は `tools/m11/work/`)、`toolchain-emsdk` は `/opt/emsdk` (emcc 6.0.12)。

- 訂正: §3 の「修復前 53 site」は誤り。`REPORT_968.md` §2 の表では 53 は**修復後**の値。現 HEAD の修復前は store 宛 CELL_COLLAPSED **86 site / 49 関数**。
- 訂正: §1 の鮮度記述「`916d9932` 以降はドキュメントのみ」は誤り。`git diff --name-only 916d9932 HEAD -- tools/m11` の非 md は **18 件**、`git diff --numstat 916d9932 HEAD -- tools/m11` の非 md は **+698 / -27** (本節の旧記載「51 件・988 行」は誤り。LD-47 review で計測し直した)。`tools/m11` のコードを最後に変えた commit は `02e2c5a2` (`12586095` の祖先)。
- 訂正: §1 の「空 = コード差分 0」の証跡も誤り (上記 18 件と矛盾する)。測定 commit `12586095` から本 PR の HEAD までの `tools/m11` の非 md 差分は 0 件 (`git diff --name-only 12586095 HEAD -- tools/m11 | grep -v '\.md$'` の結果は空)。したがって §4 の数値は本 PR の HEAD でも有効。上記の再現は測定 commit `12586095` の tools/m11 で行った。

e2e (`bash tools/m11/ldfix/fix_d17_e2e.sh`、現 HEAD、foreground、31 秒、emcc rc=0):

| 項目 | 修復前 | 修復後 (fix_d17.py) |
|---|--:|--:|
| store 宛 CELL_COLLAPSED site | 86 | 53 |
| store 宛 CELL_COLLAPSED 関数 | 49 | 28 |
| store 宛 CELL_DEEP site | 19 | 52 |
| spill 宛 CELL_COLLAPSED site | 37 | 37 |
| alg3 flagged 関数 | 77 | 58 |
| 修復した関数 / cell | — | 24 / 29 |

- 再現: K を読む IR load が複数本の K 組は 28 関数・32 K 組 (issue の 28 関数 / 32 組と一致)。この 28 関数に含まれる store 宛 CELL_COLLAPSED は修復前で 56 site。
- 1:1 規則は未実装。ネガコンも未実装 (対象の修復関数が無いため)。受入条件 1・3 は未達。受入条件 4 (emcc 構文検証) は `fix_d17.py` の修復 IR (単一 load 規則のみ) に対して通過を確認した。
- 残作業: 機械語 site ごとの rip セル → レジスタ → load の連鎖追跡 (未着手)。issue #1375 のまま継続する。
