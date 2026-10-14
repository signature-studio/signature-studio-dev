# #2115 REPORT 付録 — §10 (TLS index 未設定の確認と注釈の置換)

> **測定値の正本**: 本書 (§10.3)。結論と受入の判定は `REPORT_2115.md` が正本。本書は同 REPORT の §10 を 250 行上限のため分割移動したもの (本文は改訂済み・改訂前の節は Git 履歴にある)。

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

### 10.3 実測 (fix round 3・2026-10-14・各 n=1)

- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に展開 (12 ファイル)。[EMSDK]・[RETDEC] (`docs/REFERENCES.md` の ID) は runner に存在。fl-win64 は展開していない (`fw_stage2.sh`・`hs_e2e.sh` は `$FL_WIN64_DIR` を読まない)。
- 実行: 逐次 (並列数 1・nproc 4)。`fw_stage2.sh` は増分 (`--fresh` なし。stage-1 の RetDec は再実行しない)。`hs_e2e.sh` は両回 `--fresh`。
- 対照 = 注釈 `return 0` 版 (コミット 3b581236 の `fw_hostfix.py`)。置換版 = 91308efd の `fw_hostfix.py` (ca85489e の同ファイルと同一)。

| 手順 | 結果 | 所要 (real) | load average (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (増分・canon3 生成・HEAD ca85489e) | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 ff=0) | 426.1 秒 | 0.13 / 0.24 / 0.11 (13:46:53) → 2.11 / 2.17 / 1.06 (13:53:59) |
| `hs_e2e.sh --fresh` 対照 (3b581236) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 157.4 秒 | 1.87 / 2.12 / 1.05 (13:54:11) → 1.13 / 1.69 / 1.05 (13:56:48) |
| `hs_e2e.sh --fresh` 置換版 (91308efd) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 159.3 秒 | 0.95 / 1.63 / 1.04 (13:56:57) → 1.09 / 1.42 / 1.05 (13:59:36) |

- `hs_flat3.ll` (各 run の終了時点): 対照は mtime 13:56:30・sha256 `8a5f2608ea46c2d35cf569a9c4664876b5e8cb940586e5afc0d72fec1487be22`、置換版は mtime 13:59:18・sha256 `95e4ddd11521a24b7d0a6b4e66e938b3515538035e606f339262df359dd3ee80`。両 sha256 が異なるため、各 run が自分の `fw_hostfix.py` で作り直されたことを確認した。
- `hs_hostfix.json` の `0x4181e0`: 両回とも `old_lines: 79`・`injected: false` (既存 define を置換した記録。新規注入ではない)。
- 失敗位置 (両回とも同じ順序): `0x40d807` の soft-miss (target 0) → OOB。`0x4e5fa6` の soft-miss target は、対照が `0x0`、置換版が `0x1712`。この差は両回で再現した。変動は未評価のため、効果とは断定しない。
- 中間版 (TLS 割当のみ・`[BLK+0x80]` store なし): dev 観測・未記録 (rc・所要・load・値は未記録、n=1)。戻り値の受け渡し先を `[BLK+0x80]` に揃えるため store を追加した。
- §8 との食い違い: 本節の 2 回はいずれも `rec=7` で、§8 の結果 (件数は REPORT_2115.md §8 が正本) は再現しなかった。原因は未確定。

### 10.4 再測定の扱い (fix round 3)

- 旧版の対照 (plain 実行・load 未記録) の数値は使わない。対照と置換版を `--fresh` で測り直し、load average と `hs_flat3.ll` の mtime・sha256 を §10.3 に書いた。
- 各条件は n=1 のみ。WORKFLOW §5 の min–max (n≥3) は未実施。所要 157.4 秒・159.3 秒は n=1 の値として扱う。
- `hostshim/hs_e2e.sh` の増分判定 (49 行目) は本測定に影響しない (両回 `--fresh`)。plain 実行は影響を受けるため、REPORT_2115.md §9 に未解決として残す。

### 10.5 結論

- 受入 2 は未達。0 埋めブロックは stand-in で、正しい戻り値 (TLS ブロックの中身・`+568` の意味) は未確定。OOB は解消していない。
- 受入 3 は n=1 の実測と対照で部分達成。変動 (n≥3) と §8 との食い違いは未評価。
- 未解決の一覧は `REPORT_2115.md` §9 に置く (本節では重複させない)。
