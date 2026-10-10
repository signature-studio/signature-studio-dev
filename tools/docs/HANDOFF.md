# HANDOFF — 環境再起動時の引継ぎメモ

最終更新: 2026-10-10 (HEAD = a826997)

## 確定した状態 (コミット済み)
- マイルストーン M1〜M8 (subagent 番号) まで完了/部分達成。詳細は `README.md` と `tools/docs/MILESTONES.md` に反映済み。
  - M1: toolchain pin + E2E (ab7f9b9)
  - M2: FLEngine 解析機械化 (7e72717)
  - M3: 純計算4関数 bit-exact 50/50 (7afa0fd, 部分達成)
  - M4: Win32 shim コア 53 API (1c49c61)
  - M5: Delphi Mini-PoC + A9 命令化 (4aa68a2, 部分達成)
  - M6: OTT closure emcc 通過 + SIMD helper 接続 (2607a2e → c46bd30 → 検収 48fe75f)
  - M7: 1 コマンド E2E 化 `tools/m7/m6_e2e.sh` + f32 引数接続 PoC (50c4ccf, 検収 805110b)
  - M8: DSP value-flow 接続 — t1 が qNaN 不応答から param diffs 192 / input diffs 225 へ回復 (9dd2f47, 自検収 15 項目 OK)
  - 進捗 docs コミット: ace44da → 188479b → 8fea79d → 4e0e06e → 901ce24 → a826997

## 中断時に未完了だったタスク: M9 (tools/m9/)
環境再起動により M9 subagent (sessionID ses_edd141254ffeEAF2RKqSZFEs42) は強制終了の可能性が高い。**再開手順**:
1. `ls tools/m9/` と `git status` で中断時の成果物確認 (未追跡 = 未コミット)。REWARD 判断: REPORT.md が無ければやり直し、あれば continuable。
2. 未達なら subagent を再起動し、下記 spec をそのまま与える。
3. 完了後は従来どおり **検収 subagent** → メインで README/MILESTONES 更新 → コミット。

### M9 spec (再起動用・そのまま再利用可)
- 優先順: (1) 出力スケール正常化 — SVF 係数 ramp 上流 (obj+648… stream × setParameter chunk 0x108cd890 系) の broken point 特定・修正 + 出力 copy の L/R 配置 (最重要); (2) obj+584 (0x248) flag 分岐の他方 = 18011efb0 per-sample path の broken point (修正できなければ分析のみで可); (3) bit-exact 参照実装 (JS 移植 or native unit 分割) で t1 512/512 または tolerance 定義 (絶対/相対 max 誤差, 数値根拠必須); (4) broken-lift OOB 2 (c38c8 family) の table base 算術合成 remap PoC (tools/m6 REPORT §7-6 案); (5) `tools/m9/m9_e2e.sh` 1 コマンド検収 + `tools/m9/REPORT.md` (日本語 250 行以内, 結論先出し) + 自前コミット `feat(m9): svf coeff ramp + output scale + bit-exact reference`。
- M8 直前の確定事実: processReplacing は obj+584 flag で路線分岐 (≠0 = SVF 未使用 path, ==0 = SVF 16 callsite 群); t1 出力は param/入力に応答するがスケールが巨大値 junk (0x0c17fa41 系); m7 REPORT の「-6.0f」実態は f32 -qNaN bits。
- デバッグ資産: tools/m8/{nanring.mjs, msimd8_dbg.c, crumbs.mjs}。RetDec 非決定性 artifact の fixup は tools/m7/m6_e2e.sh 内に実装済み。
- 硬い制約: 書込可 = tools/m9/ のみ。tools/m6/m7/m8 は git 上改変 0 行。README/MILESTONES/src/tools/issues などその他は編集・add 禁止。sleep 禁止。

## 解決済みの既知番号・定数 (参照用)
- FastMM 0x412d60 (66B, xref 15,505) / RTTI 0x497e40 / SEH UHANDLER 8,021 / try-finally 0x409fe0 (ParamCount off-by-one 既知課題)
- accessor 誤訳: function_180126030 / SVF: function_1801260c0 (xmm1 dropped) / per-sample path: 18011efb0 / c38c8 family OOB 2
- t1 既定値群: obj+0x2dc/0x2d8 member slot, param chunk 0x108cd890, chunk[idx*4] = 0x20c 基準 (=fsetparam(5,0.5) → obj+544)
- シミュレータ検証定数: t3 0x2DDFA232 (IR literal = DLL .data 実測, 旧 0x2DEB8762 は誤値), undefined 残 47 種 (fn18 23 + Win/CRT 24)

## ツールチェイン
- emsdk 6.0.12 (/opt/emsdk), RetDec v5.0 (/opt/retdec), Ghidra 12.1.4 (/opt/ghidra), node LTS。PoC 実績は /opt/_test/。
- 解析レポート: /home/ubuntu/work/analysis/{win64,mac}/REPORT.md, strategy.md 非在 (MILESTONES.md §4 で代読), plugins/ott/REPORT.md

## ユーザ確定方針 (変更なき限り再掲)
- FL 実物の wrecompile (lifter→wasm) ルートが第一目標。スクラッチ再実装は不採用。
- プロプリアイタリ plugin は解析→wasm 同梱路線 (VST/CLAP をネイティブでホストする機構は優先度低)。
- 排除: mtytel/vital, Surge XT, Dexed。目標 plugin: Serum 2 / Massive X (instrument), OTT (最重視) / Fresh Air / Kilohearts (effect)。解析素材は ~/ダウンロード にユーザが随時配置。
- 外部通信 (Gopher/FL Cloud/認証系) は対象外。ホスティング: R2 バケット カスタムドメイン + Transform Rules で COOP/COEP 注入, Cloudflare Access は Self-hosted App (Worker 不要)。GitHub Pages 不採用。
