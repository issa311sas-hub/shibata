# 実験記録テンプレート

実験ごとに一意のIDで文書を作成する。未実施の値は未実施と記し、推測で埋めない。

- experiment_id:
- date:
- git_commit:
- dataset_version:
- データ取得元・取得時刻:
- 予測情報締切時刻:
- train_period:
- validation_period:
- test_period（最終評価時のみ）:
- features / feature_version:
- model:
- hyperparameters:
- seed / 環境・依存関係:
- 実行コマンド:
- 市場ベースライン:
- logloss（定義・集約単位も記録）:
- brier（定義・集約単位も記録）:
- calibration:
- roi（購入条件・払戻の扱いも記録）:
- 年度別・人気別・オッズ帯別評価:
- 特徴量重要度 / SHAP / Ablation:
- データ品質・リーク確認:
- 成果物の保存先:
- notes / 採用判断:

Testを見て調整しない。比較・採用判断はTrainとValidationに基づいて行う。
