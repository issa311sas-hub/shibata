# JRA単勝勝率予測AI

JRAの各レースについて、予測時点で取得可能な情報のみから各馬の1着確率を推定するプロジェクトです。

## 記録先

https://github.com/issa311sas-hub/shibata

## ドキュメント

- [開発・学習計画書（ユーザー提供の原文）](docs/development-plan.md)
- [開発記録](docs/progress.md)
- [実験記録テンプレート](docs/experiment-template.md)
- [環境構築・演習の実行手順](docs/setup.md)
- [データ取得元の調査と受入れ確認事項](docs/data-sources.md)
- [AI作業ルール](AGENTS.md)

## 現在の状態

Phase 0に着手。Python 3.12の専用環境、依存関係の固定、CSV／Parquet・SQL・時系列処理の合成データ演習を実装し、4件のテストが通過しました。
実データは未取得で、モデル実装・学習・未知期間評価は未着手です。Phase 0全体の完了判定は保留しています。
次の作業は、利用できるデータまたはData Lab.契約状況を確認し、実データの小規模な取得・品質確認を行うことです。

セットアップ後、次のコマンドで確認できます。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m shibata.phase0
```

## 基本方針

- 未来情報の混入を防ぎ、情報取得時刻と予測時刻を記録する。
- 時系列分割とWalk-Forward Validationを使用する。
- Testをモデル調整に使用しない。
- 市場ベースラインから段階的に実装する。
- Log Loss・Brier Score・Calibrationを重視する。
- 特徴量定義、実験条件、評価結果、変更理由を履歴として残す。

生データ、大容量のモデル、認証情報はGitに保存しません。データセットの版・取得元・再現手順は文書で管理します。
