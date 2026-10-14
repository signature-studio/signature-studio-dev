# 付録: icall #2120 (ICALL-59) — SlateCore の encoded slot の実行時トレース

> 親: #2081 (ICALL-57)。前付録: `REPORT_APPENDIX_2081.md` (静的解析)・`REPORT_APPENDIX_1921.md`・`REPORT_APPENDIX_2009.md`。
> 本 run は受入条件 1 の一部 (実行時の slot 読出し VA 採取) まで。表の境界・entry 数・OTT 比較は子 issue へ移管 (§4)。

既知類型との関係: 該当なし (DEFECTS.md の lift 欠陥ではなく、encoded 関数ポインタ表の解析)。

## 1. 結論

- 受入条件 1 (表の開始 VA・終了 VA・entry 数の確定): **未達**。実行時に読まれた zero-fill 域の VA は 7 個に限られ、
  表の連続範囲は決まらなかった。
- 受入条件 2 (既知 12 slot が表に含まれるかの判定): **未達**。実行時に読まれたのは 12 件中 3 件
  (`0x1813068f8`・`0x1813073f0`・`0x181307418`)。残る 9 件は、closure の 131 関数を単独実行した範囲では読まれなかった。
- 受入条件 3 (OTT api-set 表 `0x18026c9f0` との形式比較): **未達**。
- 測定の制約: 131 関数は 1 関数 1 プロセスで単独実行した。53 関数は closure 外の indirect target `0x1810806a0`
  (#2079) へ飛んで SIGSEGV し、8 関数は `ott_native` の arena 枯渇、1 関数はタイムアウトで終了した (rc は実測)。
  **推定 (REPORT_APPENDIX_2009 の観測に基づく・本 run では未実測)**: 53 関数の rc=95 は `0x1810806a0` の呼出しで起きたと見られる。
  `slot_trace.sh` は子プロセスの stderr を `2>/dev/null` で捨てるため、fatal 行 (rip/addr) は記録されておらず、この因果はこの出力からは確認できていない。
  そのため読出しの有無は判定できていない。表の添字アクセスを行う呼び出し元が、この 53 関数に含まれる可能性はあるが未確認。

## 2. 実測 (SlateCore.core_64, `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`)

測定 commit: `4c69d5db` (コードを変えた最後の commit・`feat(icall): add SlateCore encoded slot runtime tracer (#2120)`)。

| 項目 | 値 |
|---|---|
| 対象 | SlateCore.core_64 closure 131 関数 (`work/rt_freshair-core/map.json` の `func_map`) |
| 所要 | 12.0 s (real) / user 10.9 s / sys 1.4 s |
| load average | 0.30 (開始時, 09:11) |
| exit 別 | rc=0: 69 / rc=95 (SIGSEGV): 53 / rc=98 (arena 枯渇): 8 / rc=124 (timeout 10 s): 1 |
| 読出しのあった関数 | 18 関数 (ACC 行 18 件) |
| 読出された zero-fill VA | 7 個 |
| 既知 12 slot の判定 | 読出し 3 / 未読出し 9 |

読出された VA と、読んだ RIP (関数 VA ごとの ACC 行の抜粋):

| zero-fill VA | 既知 12 slot | 読んだ RIP (件数) | 読んだ関数 (例) |
|---|:---:|---|---|
| `0x1813068f8` | ✓ | `0x18105541a` (2) | `0x181055400` decode・`0x1810553d0` |
| `0x1813073f0` | ✓ | `0x1810580bf` (6)・`0x181058122` (2) | `0x1810580b0`・`0x1803dee20`・`0x18100beb0` ほか |
| `0x181307418` | ✓ | `0x181065909` (3)・`0x181065934` (3) | `0x181065900`・`0x181065928`・`0x18105d660` |
| `0x1813062d0` | | `0x18100cd94` (1) | `0x18100cd94` |
| `0x1813070f8` | | `0x18103fd70` (1) | `0x18103fd60` |
| `0x181306ce0` | | `0x181057ab7` (1) | `0x181057b38` |
| `0x181307420` | | `0x181066738` (1) | `0x181066738` |

- `0x181055400` (decode) は `0x1813068f8` だけを読む (RIP `0x18105541a` = `xor rbx,[0x1813068f8]`)。静的解析 (`REPORT_APPENDIX_2081.md` §2) の逆アセンブルと一致する。
- `0x181065900`・`0x181065928`・`0x18105d660`・`0x18105d8ac` は `0x181307418` を読む。このうち `0x181065909`・`0x181065934` は
  `0x181307418` の読出し RIP。静的解析 (`REPORT_APPENDIX_2081.md` §3) の `0x181307418` 行 (`mov, xor (x2)`) との突合は未実施。
- 既知 12 slot のうち読出し 3 件は、`0x1813068f8`・`0x181307418` (静的解析で decode の `xor` が確認済み) と `0x1813073f0` (静的解析では `and, mov`) である。

## 3. 再現

```
bash tools/ott/native/build.sh                           # libottnative.so
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh      # 約 12 秒 (load 0.3)
```

- `slot_trace.c` は `ott_native.c` を取り込み、読出しを PROT_NONE + SIGSEGV で捕まえ (zero-fill 域 `0x18128f000`〜`0x18130a000`)、
  TF 単歩の SIGTRAP で閉じ直す。native 参照と同じ IAT・heap・MS ABI 呼出し経路を使う。
- `SLOT_ENC_INIT=1` は `ott_enc_slots` で既知 12 slot を enc(NULL)=cookie に敷く (`fa_cmp.py` の `FA_ENC_INIT=1` と同じ)。
  未設定 (zero のまま) でも試したが、読出し VA の集合は 7 個で変わらなかった (測定 commit での既定条件の結果)。
- 解析の結果ファイル: `tools/icall/work/slot_trace_enc.txt` (gitignore)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 表の開始・終了 VA と entry 数の確定。読出しの無い 53 関数 (SIGSEGV・`0x1810806a0`) を `#2079` 解決後に再トレースし、添字アクセスの呼び出し元を特定する | 受入条件 1・2 | [ICALL-60] (子 issue) |
| OTT api-set 表 `0x18026c9f0` との形式比較 | 受入条件 3 | [ICALL-60] (子 issue) |
| closure 外 indirect target `0x1810806a0` | 53 関数の読出し判定ができない | #2079 (ICALL-56) |
