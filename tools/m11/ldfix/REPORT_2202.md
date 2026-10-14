# REPORT_2202 — 監査 writer chain を read-modify-write の先まで辿る (LD-86 / #2143 残件)

親: #2143。対象: `audit_undefload_dest.py` の `trace_dest`。

## 結論

- reg-only RMW writer (`sub eax,1` 等) を飛ばし、同じレジスタを書いた次の writer まで遡る規則を入れた。
- `69c381 not eax` (69c360) は REGLIVE から **DEST_RIPREAD** に分類された (元は `69c378 mov eax,[rip+0xf58576]` まで辿れる)。
- 他の関数の分類は **1 consumer のみ変化** (REGLIVE → DEST_RIPREAD)。FRAME 系・MEMREAD は before/after で不変。

## 測定条件

- 測定 commit: `d7998dca` (fix(ldfix): skip reg-only RMW writers in dest trace)
- 入力: `work-m11` の `tools/m11/work/boot{0,1,2,3,4}.norm0.ll` (5 入力)
- PE: `fl-win64` の `extracted/block00031_PE.bin`
- 比較基準: HEAD (`cdc67bb8` 時点の `audit_undefload_dest.py`) を同じ入力で実行
- 実行: `python3 audit_undefload_dest.py PE OUT 5入力`。HEAD は 70 秒、測定 commit は 70 秒 (load average 約 1.0, 4 vCPU, rc 0)。

## 実測 (sites 2,729 同一)

| 分類 | HEAD | 測定 commit | 差 |
|---|---|---|---|
| DEST_FRAME_IN_ESCAPED | 15 | 15 | 0 |
| DEST_FRAME_PTR_ESCAPED | 3 | 3 | 0 |
| DEST_FRAME_OTHER | 9 | 9 | 0 |
| DEST_MEMREAD | 6 | 6 | 0 |
| DEST_RIPREAD | 1 | 2 | +1 |
| REGLIVE | 2,502 | 2,501 | −1 |
| NOADDR | 193 | 193 | 0 |

関数単位 (fns_by_class): REGLIVE 2,438 → 2,437、DEST_RIPREAD 1 → 2。他は不変。

個別 site の差 (HEAD と測定 commit を同一 site で突き合わせ):

| fn | consumer | HEAD | 測定 commit | writer |
|---|---|---|---|---|
| function_69c360 | 69c381 `not eax` | REGLIVE | DEST_RIPREAD | 69c378 `mov eax,[rip+0xf58576]` |

## 途中で見つけた誤分類 (修正済み・同 commit に含む)

- 初版は RMW を飛ばすだけだったため、`cvttsd2si rax,xmm0` (純粋な def) の consumer が
  `reads_of` の「dest も read 扱い」で偽の RMW 先を辿り、DEST_FRAME_IN_ESCAPED 等 8 site が REGLIVE に落ちた。
- 対策: `reads_of` の dest read 判定を `reads_dest()` (RMW・cmp/test/xchg/bswap/cmov) に限定。
  これで cmp/test の consumer が dest を読むケースも保たれる。修正後は上記の site 差のみ。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 再生成 IR (`boot5.norm0.ll` 等) での再確認 | 入力が `work-m11` 由来のため、REPORT_1866 の 2,737 とは sites が一致しない (既知) | #2144 [LD-80] |
| REGLIVE 残 2,501 件の内訳 (NOADDR 193 を含む) | 本件の範囲外 | 既存の監査 REPORT 群 |

## 再現

```
cd tools/m11/ldfix
python3 audit_undefload_dest.py <fl-win64 extracted/block00031_PE.bin> out.json tools/m11/work/boot{0,1,2,3,4}.norm0.ll
```

結果 JSON: `results/audit_undefload_dest_2202_head.json` (HEAD)・`results/audit_undefload_dest_2202.json` (測定 commit)。

## 測定 commit から PR head までの差分 (`git diff --stat d7998dca 255d5a53 -- tools/m11/ldfix` の実出力)

```
 tools/m11/ldfix/REPORT_2202.md                              |  73 ++++++++
 tools/m11/ldfix/results/audit_undefload_dest_2202.json      | 190 +++++++++++++++++++++
 tools/m11/ldfix/results/audit_undefload_dest_2202_head.json | 190 +++++++++++++++++++++
```

`d7998dca` → `255d5a53` では `audit_undefload_dest.py` の差分は 0 行で、表の数値はこの範囲のコードで測った値。

## review 対応 (fix モード)

PR head `255d5a53` の review (request-changes) への対応。**この節以降の変更で、測定 commit のコードは変わった。**
新コードの 5 入力実測は未了 (下表)。

| # | 指摘 | 対応 | 検証 |
|---|---|---|---|
| 1 | DEST_RIPREAD の詳細が JSON に無い | `main()` に `dest_riprip` (fn・file・detail) を追加。**JSON は未再生成** (入力 IR 無し、下記未解決) | `trace_dest` 単体で 69c381 → 69c378 `mov eax,[rip+0xf58576]` を再確認 (PE: `fl-win64` の `block00031_PE.bin`) |
| 2 | `is_reg_rmw` が第 2 オペランドを追跡しない | RMW writer を飛ばす際、その第 2 オペランドの reg (`cl` は `rcx` に正規化) を `want` に加える | 合成機械語: `add eax,ecx` / `shl eax,cl` の源を RIP 読み `mov` まで辿れることを確認 |
| 3 | `reads_dest` が `bt*`・`shld/shrd`・`xadd`・`cmpxchg` を落とす | 上記 mnemonic を `reads_dest` に追加 | 合成機械語: `bt eax,ecx` / `xadd eax,ecx` を consumer とした時、eax の元 `mov` を辿れることを確認 (修正前は REGLIVE) |
| 4 | REPORT の stat が実物と不一致 | 上の実出力で置換 (64 → 73 / 190 / 190) | `git diff --stat` の実出力 |

### 既存 18 件 (DEST_FRAME_IN_ESCAPED 15 / PTR_ESCAPED 3) の再判定

既存 JSON の各 site について、detail の先頭 1 件 (consumer) を新コードで `trace_dest` し直した。
writer は 18 件すべて旧と同一 (`fl-win64` の PE から disasm)。ただし見たのは detail の先頭 1 件だけで、
残りの consumer や REGLIVE 側の変化は測っていない。

### 未測定 (新コードで JSON を再生成していない)

- 5 入力 (`boot{0..4}.norm0.ll`) の site 数・分類件数は **d7998dca の値のまま**。新規則 (指摘 2・3) が件数をどう変えるかは未測定。
- 入力 IR が `$HOME/artifacts` (fl-win64 のみ) と `tools/m11/work/` に無く、`oc_artifacts: work-m11` も本 PR 本文に無いため再生成できない。
- 次回 `oc_artifacts: fl-win64 work-m11` で再測定し、`dest_riprip` を含む JSON で REPORT の表を更新する (未解決の表を参照)。
