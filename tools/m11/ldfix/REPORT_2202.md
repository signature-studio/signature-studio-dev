# REPORT_2202 — 監査 writer chain を read-modify-write の先まで辿る (LD-86 / #2143 残件)

親: #2143。対象: `audit_undefload_dest.py` の `trace_dest`。

## 結論

- reg-only RMW writer (`sub eax,1` 等) を飛ばし、同じレジスタを書いた次の writer まで遡る規則を入れた。
- `69c381 not eax` (69c360) は REGLIVE から **DEST_RIPREAD** に分類された (元は `69c378 mov eax,[rip+0xf58576]` まで辿れる)。
- 他の関数の分類は **1 consumer のみ変化** (REGLIVE → DEST_RIPREAD)。FRAME 系・MEMREAD は before/after で不変。

## 測定条件

- 測定 commit: `860f8b0c` (fix(ldfix): read dest in rcl/rcr consumers for dest trace (#2202))。コードを最後に変えた commit。以後 `audit_undefload_dest.py` のコードは変わっていない (下の差分節を参照)
- コード差分: 測定 commit から HEAD まで 0 行 (差分節を参照)。以後の文書 commit で HEAD が進んでも同じ
- 入力: `work-m11` の `tools/m11/work/boot{0,1,2,3,4}.norm0.ll` (5 入力, `docs/REFERENCES.md` の `[WORK-M11]` の展開先。gitignore・commit しない)
- PE: `fl-win64` の `extracted/block00031_PE.bin` (`oc_artifacts: fl-win64` で取得し、`docs/WORKFLOW.md` §11 の手順で展開。commit しない)
- 比較基準 (before): `cdc67bb8` 時点の `audit_undefload_dest.py` (`git show cdc67bb8:...`)。出力は `dest_riprip` を含むよう作業用コピーで 1 箇所だけ補った (`work/2202/base/`)。分類ロジックは cdc67bb8 のまま。依存 (`ldmach.py`・`ldframe.py`・`audit_undefload.py`) は cdc67bb8 → HEAD で不変
- 実行: `python3 audit_undefload_dest.py <PE> <OUT> boot{0..4}.norm0.ll`。rc 0。
  - 測定 (`860f8b0c`): real 39.24 秒 (`time` 実測。`user` 38.88 秒)。実行前後の load average 0.68 → 0.90
  - 直前の測定 (`ace67882`・rcl/rcr 追加前): real 49.96 秒
  - before (`cdc67bb8`): 50.3 秒 (`1626c4c7` 時点の測定)
  - 実行環境: 4 vCPU

## 実測 (sites 2,729 同一)

結果 JSON: `results/audit_undefload_dest_2202.json` (測定 `860f8b0c` で再生成・`dest_riprip` 入り。`ace67882` 時点の出力とバイト単位で一致)、`results/audit_undefload_dest_2202_head.json` (before `cdc67bb8`・`dest_riprip` 入り)。

| 分類 | before (cdc67bb8) | after (860f8b0c) | 差 |
|---|---|---|---|
| DEST_FRAME_IN_ESCAPED | 15 | 15 | 0 |
| DEST_FRAME_PTR_ESCAPED | 3 | 3 | 0 |
| DEST_FRAME_OTHER | 9 | 9 | 0 |
| DEST_MEMREAD | 6 | 6 | 0 |
| DEST_RIPREAD | 1 | 2 | +1 |
| REGLIVE | 2,502 | 2,501 | −1 |
| NOADDR | 193 | 193 | 0 |

関数単位 (fns_by_class): REGLIVE 2,438 → 2,437、NOADDR 190 → 190、DEST_RIPREAD 1 → 2。他は不変。

個別 site の差 (`dest_riprip` を両 JSON で突き合わせ):

| fn | consumer | before | after | writer |
|---|---|---|---|---|
| function_69c360 (boot1) | 69c381 `not eax` | REGLIVE | DEST_RIPREAD | 69c378 `mov eax,[rip+0xf58576]` |

before の DEST_RIPREAD は `11ca250` (boot3, `11ca2d9 movsd [rax],xmm0` ← `11ca2d2 mov rax,[rip+0x416a87]`) の 1 件で、after でも同一 site。REGLIVE 側の変化は 69c381 の 1 件のみ。`dest_frame_in_escaped`・`dest_frame_ptr_escaped` の site 一覧は before/after で完全一致。

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
cd <repo root>
python3 tools/m11/ldfix/audit_undefload_dest.py extracted/block00031_PE.bin out.json tools/m11/work/boot{0,1,2,3,4}.norm0.ll
```

## 測定 commit から検証 HEAD までの差分 (コード)

測定 commit `860f8b0c` → HEAD (本 PR の最新 commit は PR 本文を参照):`git diff 860f8b0c HEAD -- tools/m11/ldfix/audit_undefload_dest.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/ldframe.py tools/m11/ldfix/audit_undefload.py` の実出力):

```
(空: 差分 0 行)
```

測定 commit は、コードを最後に変えた commit (`860f8b0c`・`READS_DEST_EXTRA` に `rcl`/`rcr` を追加)。それ以降の commit は `REPORT_2202.md`・`results/`・`verify_dest_2202.py` (回帰ケース追加) の文書・検証のみで、測定対象のコード (上の 4 ファイル) は変わっていない。
したがって表の件数は検証 HEAD のコードの値である。

(参考: `7117602e` → `860f8b0c` の差分は `audit_undefload_dest.py` の 1 行 (`READS_DEST_EXTRA` への `'rcl', 'rcr'` 追加) のみ。`git diff 7117602e 860f8b0c -- tools/m11/ldfix/audit_undefload_dest.py` の実出力: `-...'cmpxchg')` `+...'cmpxchg', 'rcl', 'rcr')`。)



## review 対応 (fix モード)

PR head `255d5a53` の review (request-changes) への対応 (測定 commit `7117602e` に含まれる)。

| # | 指摘 | 対応 | 検証 |
|---|---|---|---|
| 1 | DEST_RIPREAD の詳細が JSON に無い | `main()` に `dest_riprip` (fn・file・detail) を追加。5 入力で再生成し、JSON に `dest_riprip` を含めた (上の実測節) | `verify_dest_2202.py` [1]: PE 69c381 `not eax` ← 69c378 `mov eax,[rip+0xf58576]` (rip_rva=0x15f48f4) |
| 2 | `is_reg_rmw` が第 2 オペランドを追跡しない | RMW writer を飛ばす際、その第 2 オペランドの reg (`cl` は `rcx` に正規化) を `want` に加える | `verify_dest_2202.py` [2a] `add eax,ecx` の ecx は reg 定義 `mov ecx,edx` → mem=False (REGLIVE)、[2b] `shl eax,cl` の cl は `mov ecx,[rip+0x1fa]` → mem=True |
| 3 | `reads_dest` が `bt*`・`shld/shrd`・`xadd`・`cmpxchg` を落とす | 上記 mnemonic を `reads_dest` に追加。後続の指摘 (`rcl`/`rcr` 漏れ) は `860f8b0c` で `READS_DEST_EXTRA` に追加 | `verify_dest_2202.py` [3a] `bt eax,ecx`・[3b] `xadd eax,ecx`・[3c] `cmpxchg ecx,edx` の consumer が、dest の元 `mov [rip+..]` に到達 (mem=True) |
| 4 | REPORT の stat が実物と不一致 | 上の実出力で置換 (64 → 73 / 190 / 190) | `git diff --stat` の実出力 |

### 検証スクリプト

`tools/m11/ldfix/verify_dest_2202.py` (commit `07cb1f47`、回帰ケース 3d・3e は `860f8b0c` で追加)。入力: `fl-win64` の `extracted/block00031_PE.bin` (`docs/WORKFLOW.md` §11 の `oc_artifacts: fl-win64` 手順で展開)。合成機械語は同ファイル内に記載。

実行 (測定 commit `860f8b0c`、リポジトリ直下で実行。`timeout 300`・rc 0):

```
$ python3 tools/m11/ldfix/verify_dest_2202.py extracted/block00031_PE.bin
[1] PE 69c381 eax <- 69c378 mov eax, dword ptr [rip + 0xf58576] : rip_rva=0x15f48f4  OK
[2a add eax,ecx (ecx=reg def)] consumer cmp eax, 0 -> writer mov ecx, edx  mem=False  OK
[2b shl eax,cl (cl=rip read)] consumer cmp eax, 0 -> writer mov ecx, dword ptr [rip + 0x1fa]  mem=True  OK
[3a bt eax,ecx] consumer bt eax, ecx -> writer mov eax, dword ptr [rip + 0xfa]  mem=True  OK
[3b xadd eax,ecx] consumer xadd eax, ecx -> writer mov eax, dword ptr [rip + 0xfa]  mem=True  OK
[3c cmpxchg ecx,edx] consumer cmpxchg ecx, edx -> writer mov ecx, dword ptr [rip + 0xfa]  mem=True  OK
[3d rcl eax,cl] consumer rcl eax, cl -> writer mov eax, dword ptr [rip + 0xfa]  mem=True  OK
[3e rcr eax,1] consumer rcr eax, 1 -> writer mov eax, dword ptr [rip + 0xfa]  mem=True  OK
ALL OK
```

`rcl`/`rcr` (3d・3e) は修正前コード (`8446b8d4` の `audit_undefload_dest.py`) では `writer - - mem=False NG` で FAIL になることを確認した。

注: 本検証は `trace_dest` の writer 特定を確認するもので、件数 (5 入力) の変化は含まない (件数は上の実測節)。

### 既存 18 件 (DEST_FRAME_IN_ESCAPED 15 / PTR_ESCAPED 3) の件数・site 一覧

5 入力・検証 HEAD (`ace67882`) で再測定し、before/after で `dest_frame_in_escaped`・`dest_frame_ptr_escaped` の site 一覧が完全一致した (上の実測節)。
指摘 2・3 の規則 (第 2 オペランド追跡・`reads_dest` 拡張) は、これら 18 件の分類を変えていない。

### 実測の範囲

- 5 入力 (`boot{0..4}.norm0.ll`) で、検証 HEAD (`ace67882`) と before の両方を実行した。件数の差は上の実測節の 1 件 (69c381) のみ。
- 本 run で再生成した JSON は `dest_riprip` を含む (`results/audit_undefload_dest_2202.json`)。受入条件 1 の根拠は `dest_riprip` の 69c360 エントリ。
