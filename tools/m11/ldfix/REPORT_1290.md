# #1290 (LD-43) ldfix_509_e2e の修復前 wasm を fail-closed gate を弱めずに作る手順

**判定: 達成** (受入条件 4 件のうち、手順の決定・step 6/7 の完走・survey/dyn の実測記録・gate 非弱化の確認が満たされた)。

既知類型との関係: 該当なし (本件は build gate と IR 指紋の運用手順。silent miscompile 類型ではない)。

## 1. 根本原因 (実測)

`ldfix_509_e2e.sh` の step 6 (wasm 再ビルド) が 2 箇所で `m11_build.sh` の gate に拒否されていた (#680 fail-closed):

- 修復前 wasm: step 1 は `M11_LDFIX=0` で IR を取る。`ir_conditions.json` は `ldfix=disabled` を残す。step 6 はそれを
  `cp -a "$W"` で複製した作業ツリーで build するが、記録ファイルも修復前 IR も置き換えていなかった。
  `m11_build.sh` は `ldfix=applied` の記録が無いと拒否する (`ERROR: ... ldfix=applied の記録無し (現在: '')`)。
- 修復後 wasm: `--passes f3c` の overlay (`bf_f3c.ll`) を `boot_final.ll` へ `cp` していた。正規 pass を経ていないため
  `ir_sha256` 指紋 (`m11_cond.py --check`) と一致せず拒否される。

work-m11 素材には `ir_conditions.json` が無い (`tar --zstd -tf ... | grep -c ir_conditions` = 0)。
`docs/WORKFLOW.md` §11 も work-m11 は #516 以前の生成物で `ir_conditions.json` を持たないと記している。よって step 1 の記録だけが根拠になる。

## 2. 決定 (DECISIONS.md D12)

- 修復前: 既存の明示 opt-in `M11_ALLOW_LDFIX_DISABLED=1` (#1165) を、step 1 が書いた `ldfix=disabled` の記録と共に使う。既定の拒否は残る。
- 修復後: 修復前 IR に `ldfix/ldfix.py --pe` (`m11_gen_ir2.sh` と同じ正規 pass) を適用 → `ldfix=applied` → `--bind` → 既定 gate で build。
  overlay IR は build に渡さない。
- 不採用: gate の既定化・指紋検査の省略 (fail-closed を弱める)、修復後 wasm 単独への縮退 (修復前比較が取れなくなる)。

## 3. 検証

- 測定 commit: `3c6b9d8e` (コードを変えた最後の commit)。`git diff 3c6b9d8e HEAD -- tools/m11` = 0 行 (本 REPORT の追記後も差分 0)。
- クリーン検証: `git worktree add --detach <RUNNER_TEMP>/wt_verify_1290 3c6b9d8e` で展開し、同じ手順で再実行 (rc=0・5 分 01.9 秒・DYN after_fail=0/5)。
- 実行: `EMSDK_ENV=/opt/emsdk/emsdk_env.sh FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_WORK=<ws-1290>/tools/m11/work bash tools/m11/ldfix/ldfix_509_e2e.sh`
- 素材: fl-win64 (PE `block00031_PE.bin`)・toolchain-emsdk・work-m11 (`tools/m11/work/`)。PE は `$RUNNER_TEMP/fl-win64/extracted/` に展開。
- 所要: 実測 5 分 06 秒 (real 306 s / user 293 s、worktree 実行)。クリーン HEAD 再実行は 5 分 01.9 秒 (real 302 s / user 288 s)。load average (終了時) 1.09 / 1.00。並列数 1 (`nproc` = 4)。

| step | 結果 |
|---|---|
| 1/7 修復前 IR 再生成 | `ldfix=disabled` を記録 |
| 2/7 旧版/新版 ldfix | 出力が異なる関数 838 / 7421 (旧版 009e823 との差。修復の範囲) |
| 3/7 audit_lsf | 完走 |
| 4/7 f3c overlay 突合 | 完走 |
| 5/7 ネガティブコントロール | 完走 |
| 6/7 build (修復前 / 修復後) | 両方 `[m11build] OK` (WARNING 1 件 = opt-in の表示のみ)。survey 942 unit 突合で記録が異なる unit 12 件 |
| 6/7 動的到達 (reach_509) | 計装 26 関数・942 unit。実行された関数 4 件 (41a670 7 unit, 409c80 54 unit, 40ffe0 1 unit, 447ee0 1 unit)。残り 22 件は survey で入口を通らず |
| 7/7 dyn_509 (修復前 / 修復後) | 修復前 FAIL 5/5、修復後 PASS 5/5 (`DYN_SUMMARY after_fail=0/5`) |

dyn の内訳 (want / before / after):
- c62780 8B → array: want `0x1122334455667788` / before `0x11e00100` / after `0x1122334455667788`
- 7e5240 dword → arg2[1]: `0xdeadbeef` / `0x11e00300` / `0xdeadbeef`
- 409c80 4B path: `0x13121110` / `0x13121100` / `0x13121110`
- 41a670 unlink: `0x1111` / `0x11e00600` / `0x1111`
- 1063090 D4: `0xabcd` / `0x0` / `0xabcd`

### 3.1 ネガティブコントロール (fail-closed が弱まっていないこと)

- 既定 (opt-in 無し) で `ldfix=disabled` の IR を build: `[m11build] ERROR: work/ir_conditions.json に ldfix=applied の記録無し (現在: 'disabled')` で拒否。
  (注: 直前の `rc=0` は `tail` の終了コードであり、build の終了コードではない。拒否の根拠はこの ERROR 行。)
- 手作り overlay (`bf_f3c.ll`) を記録無しで build: 同じ gate で拒否 (1 節の原因の再現。修正前 step 6 の失敗と同一)。

### 3.2 survey 差分

step 6 の survey 突合で、修復前後の unit 記録 (kind・msg・frame・stub 呼出・va_mb) が異なる unit は 12 件
(`144 158 280 291 296 302 304 314 493 659 888 895`)。修復の効果として期待される差分であり、本件の受入条件は
「完走時の survey 差分 (unit 数) を実測で記録する」ことのみ。差分の解釈 (trap/halt0 の増減) は #130 (M11-N2) の範囲。

## 4. 未解決・限界

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復前 wasm は `M11_ALLOW_LDFIX_DISABLED=1` (opt-in) で作る。e2e の step 6 は PE 必須になった | PE の無い環境では step 6/7 が走らない (以前は PE 無しで完走していた) | 本 PR (D12 に記録) |
| 修復前 IR を `ldfix.py --pe` で再適用する。`work-m11` の `boot_final.ll` (旧 snapshot) とは一致しない場合がある | 修復後 wasm が snapshot の wasm と異なる | #1290 の範囲外。`tools/m11/REPORT_N27.md` §12 の IR 正系統の整理 (既存 #728 系) |
| 修復後 wasm の survey 差分 12 unit の解釈 | 修復の波及先が未定 | #130 (M11-N2) |

## 5. 再現

```sh
EMSDK_ENV=/opt/emsdk/emsdk_env.sh FL_WIN64_DIR=<fl-win64 展開先> M11_WORK=<tools/m11/work> \
  bash tools/m11/ldfix/ldfix_509_e2e.sh
```

成果物は `$RUNNER_TEMP/ldfix_509_e2e/` (`build_base.log` / `build_new.log` / `ldfix_new.log` / `sv_*.json` / `reach.json`)。
