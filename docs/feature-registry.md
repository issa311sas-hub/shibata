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

観測入力の追加経路（2026-09-21）: 上記の式・意味は変更せず、RA/SE/O1の正常値から内部形式へ接続するobserved CLIを追加した。取得manifestの検証と保守的なローカル取得時刻を条件にする。合成のバイト列から市場確率までの結合テストに成功。実観測の正常オッズがまだ揃わないため、実データ性能・欠損率・採用判定は引き続き保留。手順・対応範囲はobserved-workflow.md。

2026-09-21追記: 阪神1Rの8頭について、発走前実観測からwin_odds/popularity/runner_count/odds_rank/market_probabilityの生成に成功。計算式は不変。runner_countは発走前のRA登録頭数・SE集合・O1頭数を照合し、RAの結果用出走頭数は使わない。実験observed-20260921-hanshin01-v3、出力再現性を確認。1レースの計算確認であり、精度・採否は結果評価待ち。


2026-09-21 承認済みpilot-v1: win_odds/popularityの情報締切を予定発走10分前、発表からの経過5分以内とする条件をユーザー承認に基づき追加。既存の早朝診断は別枠で保持し、式・モデル・学習期間は不変。実際の保存も締切後1分以内を検査する。

| feature_name | category | description | formula | raw_source | available_time | missing_rate | leakage_risk | hypothesis | implemented | validation_result | keep_or_drop | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| track_code_raw | eligibility_metadata | 平地/障害の対象区分確認 | RA項番36の原コード | RA 706バイト目から2バイト | 締切以前に取得したRA | 未計測 | 後日版を対象選定に使わない | 承認された平地のみを含める | 対象検査のみ実装 | 合成データの平地/障害検査 | ML特徴量には不採用 | 出力確率の計算には不使用 |
