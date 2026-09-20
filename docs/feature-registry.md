# 特徴量・市場ベースライン台帳

版: v1。ここでimplementedはオフライン準備の実装を示す。実データでの有効性や採用決定ではない。
欠損を0埋めせず受入れ時に停止するため、実データの欠損率は未計測。

| feature_name | category | description | formula | raw_source | available_time | missing_rate | leakage_risk | hypothesis | implemented | validation_result | keep_or_drop | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| win_odds | market_input | 締切以前の単勝オッズ | 原数値 | 内部odds／将来O1の正常値 | 根拠付き公表時刻、observedでは取得時刻も締切以前 | 未計測 | 最終値・後日訂正・上限打切りに注意 | 市場評価を表現 | オフラインのみ | 合成入力で検証、実データ未評価 | 保留 | 逆数正規化に使用 |
| popularity | market_input | 同時点の提供元人気順位 | 原順位 | 内部odds／将来O1 | 同上 | 未計測 | 最終人気の流用禁止 | 人気帯の評価に使用 | オフラインのみ | 合成入力で検証、実データ未評価 | 保留 | 確率の計算には不使用 |
| runner_count | race_context | 予測時点の対象頭数 | 出走表の頭数と行数一致 | 内部races/entries | 出走表が締切以前に利用可能 | 未計測 | 結果から取消馬を除いて作り直すと危険 | 全頭が揃っているかを確認 | オフラインのみ | 欠頭検知テスト | 保留 | 確率の計算には間接的に関係 |
| odds_rank | diagnostic | 同一オッズ時点での計算順位 | odds昇順、同値は最小順位 | win_odds | 選択時点と同じ | 未計測 | オッズと同じ | 提供元人気と区別した診断 | オフラインのみ | 同オッズの順位テスト | 保留 | ML特徴量として未採用 |
| market_probability | baseline_output | レース内市場勝率 | (1/odds_i) / sum(1/odds_j) | win_odds | 選択時点と同じ | 未計測 | 欠頭・異時点混在は不正 | 今後のモデルの比較基準 | オフラインのみ | 合計1・既知値テスト | 保留 | MLモデル予測ではない |

Phase 0のprevious_win / previous_two_meanは操作演習であり、本番特徴量として採用していない。
馬の能力・適性・騎手・当日情報などの追加は、実市場ベースライン確認後に計画順で進める。
