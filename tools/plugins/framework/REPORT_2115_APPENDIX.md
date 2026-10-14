# #2115 REPORT 付録 — §10 (TLS index 未設定の確認と注釈の置換)

> **正本**: `tools/plugins/framework/REPORT_2115.md`。本書は同 REPORT の §10 を 250 行上限のため分割移動したもの (本文は改訂済み・改訂前の節は Git 履歴にある)。§1〜§9 は本体に残す。

## 10. TLS index 未設定の確認と注釈の置換 (測定 commit 91308efd)

前提: §8 の `return 0` 版も注釈削除版も Phase B は同じ OOB。TLS 経路 (`gs:[0x58][[0x6d6e70]]`) の未設定を確認した。

### 10.1 確認事実

- `block18983_PE.bin` に TLS directory は無く、TLS index 変数 `0x6d6e70` の初期値は `0xFFFFFFFF` (`.data`)。
- `[0x7162d8]` は `.bss` で 0 のため、`function_4181e0` は TLS 経路を通る。`idx = -1` は `zext` 後に線形メモリ外のアドレスになる (canon3 `dec_label_pc_7d8a61`)。
- `[0x6d6e70]` を設定するのは `function_418120` (`TlsAlloc` → store) のみ。canon3 と hs_flat3 に直接 call は 0 件、hs_e2e の dispatch ログにも `0x418120` は 0 件 (注釈版・置換版とも)。
- 呼出元は戻り値を `[BLK+0x80]` から読み `+568` を deref する (§8 の注釈記述・hs_dbg 実測)。

### 10.2 注釈の置換 (`fw_hostfix.py` 0x4181e0)

- `idx == -1` なら `TlsAlloc()` で確保し `[0x6d6e70]` に store する。
- TLS スロットが 0 なら 4096 byte の 0 埋めブロック `@fw_tls_block` を割り当てて書く。戻り値は SSA と `[BLK+0x80]` の両方に store する。
- フラグ `[0x7162d8]` != 0 の経路 (418030・4180d0・`[0x7162d0]`) は未モデル (初期値 0 の前提)。

### 10.3 実測 (全て n=1・変動未評価)

対照 = 注釈 `return 0` 版 (コミット 3b581236・plain 実行)、置換版 = 91308efd (`--fresh`)。

| 手順 | 結果 | 所要 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (canon3 新規生成・3b581236 の framework) | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 ff=0) | 7 分 23.5 秒 | 0.14 / 0.27 / 0.14 (12:49:06) → 2.39 / 2.32 / 1.11 (12:56:30) |
| `hs_e2e.sh` (対照・plain) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 2 分 37.9 秒 | **未記録** |
| `hs_e2e.sh --fresh` (置換版・91308efd) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 2 分 38.6 秒 | 0.64 / 0.88 / 0.89 (13:08:11) → 1.05 / 0.97 / 0.93 (13:10:50) |

- Phase B の OOB は両版で残る。対照は `0x4e5fa6` の間接呼出先 0 → `0x40d807` (target 0) → OOB。置換版は `0x4e5fa6` の target が `0x1712` になり、その後 `0x40d807` (target 0) → OOB。**失敗位置の差は 1 回ずつの観測で、変動を評価していない。効果とは断定しない。**
- **§8 との食い違い**: 同一の実行コードで結果が違う。`git diff c2f67568 3b581236 -- tools/plugins/framework tools/liftlib ':!*.md'` は 0 行。§8 (c2f67568・`--fresh`・注釈あり) は `rec=8` / `E2E FAIL: 3 項目`、§10.3 の対照は `rec=7` / 1 項目。run mode・環境のばらつき・後述の増分判定のいずれかが原因だが、切り分けていない。よって「同じ Phase A / Phase B の結果」は §10.3 の対照と置換版の間でだけ言える。
- **対照の増分判定**: plain 実行の `hostshim/hs_e2e.sh` は `hs_flat3.ll` を `hs_flat2.ll -nt hs_flat3.ll` の時刻だけで作り直す (49 行目)。`fw_hostfix.py` の変更では再生成されない。対照が古い `hs_flat3.ll` を使った可能性は排除できていない。
- **中間版** (TLS 割当のみ・`[BLK+0x80]` store なし): dev 観測・未記録 (rc・所要・load は未記録、n=1)。`0x4e5fa6` の target が文字列由来の値 `0x6572432000000000` になった。戻り値の受け渡し先を `[BLK+0x80]` に揃えるため store を追加した。

### 10.4 再測定の扱い (この fix run)

- 対照の `--fresh` 再測定と load average の補完は**未実施**。この run では emsdk・RetDec (`[EMSDK]`・`[RETDEC]`) の実体と `tools/plugins/work/fw/` が無く、`fw_stage2.sh` / `hs_e2e.sh` を実行できない (`ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ)。
- 次 run の素材要請: `oc_artifacts: fl-win64 work-fw-stage1 toolchain-emsdk toolchain-retdec` (`docs/WORKFLOW.md` §11 の許可名)。対照と置換版をそれぞれ n≥3 で測り min–max を書く (WORKFLOW §5)。`hs_hostfix.json` の 0x4181e0 注入記録も添える。
- 再測定まで、本節の数値は n=1 の観測としてのみ扱う。

### 10.5 結論

- 受入 2 は未達。0 埋めブロックは stand-in で、正しい戻り値 (TLS ブロックの中身・`+568` の意味) は未確定。OOB は解消していない。
- 受入 3 は n=1 の実測と対照で部分達成。変動と §8 との食い違いは未評価。
- 未解決の一覧は `REPORT_2115.md` §9 に置く (本節では重複させない)。
