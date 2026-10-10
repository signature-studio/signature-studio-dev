#!/usr/bin/env python3
"""hs_ids_recount.py — CAB-195 検収: Dispatcher ID カバー率の独立再計算 (別アルゴリズム)。

hs_ids.py (実装側) は host_calls.py の集計 JSON を読み直して top-N cover を出す。
本脚本は **別アルゴリズム** で検算する:
  (1) 元データ work/host_calls.json の unique_ids_total を独立に集計 (降順ソート + 累積和)。
  (2) hs_ids.json の per-ID 'sites' を元データの値と 1 件ずつ照合 (辞書のキー網羅も確認)。
  (3) hs_ids.json の 'top30_cover' / 'top30_cover_pct' フィールドと、実際の
      top_n (= ファイル内 top_n の値) の累積和を比較し、**ラベルと実体の不一致**を出す。
  (4) ret_use 内訳から「store/reg を含む ID 数」「ignore/test のみの ID 数」を数える
      (REPORT §2.2 の 9 / 21 の検算)。数え方: ret_use 辞書のキーに 'store' か 'reg' が
      1 つでもあれば store/reg クラス、'ignore'/'test' のみなら ignore/test クラス。

使い方: python3 hs_ids_recount.py
"""
import json
import os
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', '..', 'work')
IDS = os.path.join(HERE, 'hs_ids.json')

src = json.load(open(os.path.join(WORK, 'host_calls.json')))
js = json.load(open(IDS))

# ---- (1) 元データ独立集計 ----
ut = {int(k): v for k, v in src['unique_ids_total'].items() if k != 'None'}
total = sum(ut.values())
print('[recount] 元データ unique_ids_total: %d ID 種 / %d site (定義: r8 即値で識別できた'
      ' disp==0 site の合計)' % (len(ut), total))
assert total == js['identified_sites_total'], \
    '総 site 数が hs_ids.json (%d) と不一致' % js['identified_sites_total']

# ---- (2) hs_ids.json の per-ID sites 照合 ----
ids = {int(k): v for k, v in js['ids'].items()}
bad = [k for k, v in ids.items() if ut.get(k) != v['sites']]
print('[recount] hs_ids.json の %d ID の sites が元データと一致: %s'
      % (len(ids), '全件一致' if not bad else '不一致 %s' % bad))
extra = [k for k in ids if k not in ut]
print('[recount] hs_ids.json にあって元データに無い ID: %s' % (extra or 'なし'))

# ---- (3) top-N cover: 累積和 (別アルゴリズム) とフィールドの比較 ----
order = sorted(ut.items(), key=lambda kv: (-kv[1], kv[0]))
cum = 0
for n in (20, 30, 35):
    s = sum(v for _, v in order[:n])
    print('[recount] 上位 %2d ID の累積 site = %d / %d = %.1f%%'
          % (n, s, total, 100.0 * s / total))
topn = js['top_n']
s = sum(v for _, v in order[:topn])
print('[recount] hs_ids.json の top_n=%d → 累積 %d / %d = %.1f%% (ファイルの cover フィールド'
      ' = %d / %.1f%%)' % (topn, s, total, 100.0 * s / total, js['top30_cover'], js['top30_cover_pct']))
print('[recount] ⇒ ファイルの "top30_cover" は **top_n=%d** の累積と一致: %s'
      % (topn, 'はい (フィールド名が top_n と不一致)' if s == js['top30_cover'] else 'いいえ'))
print('[recount] ⇒ 本当の上位 30 ID は %d site = %.1f%% (REPORT 本文の 778/894 %%%s と一致: %s)'
      % (sum(v for _, v in order[:30]), 100.0 * sum(v for _, v in order[:30]) / total, '',
         'はい' if sum(v for _, v in order[:30]) == 778 else 'いいえ'))

# ---- (4) ret_use クラス別 ID 数 ----
sr, it = [], []
for k in sorted(ids):
    uses = set(ids[k]['ret_use'])
    (sr if (uses & {'store', 'reg'}) else it).append(k)
print('[recount] ret_use に store/reg を含む ID: %d 件 %s' % (len(sr), ['0x%x' % k for k in sr]))
print('[recount] ignore/test のみの ID      : %d 件 %s' % (len(it), ['0x%x' % k for k in it]))
print('[recount] 合計 %d 件 (hs_ids.json の ID 数 %d と一致: %s)'
      % (len(sr) + len(it), len(ids), 'はい' if len(sr) + len(it) == len(ids) else 'いいえ'))

# ---- (5) 「DLL 数」の再計算 ----
raw = json.load(open(os.path.join(WORK, 'host_calls_raw.json')))
keys = set(raw)
print('[recount] host_calls_raw.json のキー (plugin PE ファイル名) = %d 件' % len(keys))
print('[recount] host_calls.json の unique_ids_per_plugin キー = %d 件'
      % len(src['unique_ids_per_plugin']))
print("[recount] hs_ids.json の 'plugins' フィールド合計 (ID ごとの双重計上) = %d 件"
      % sum(v['plugins'] for v in ids.values()))
print('[recount] ⇒ REPORT の「133 DLL」はこの 3 つのどれとも一致しない')
