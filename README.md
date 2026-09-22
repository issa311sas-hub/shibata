# JRA単勝勝率予測AI

JRAの各レースについて、予測時点で取得可能な情報のみから各馬の1着確率を推定するプロジェクトです。

## 記録先

https://github.com/issa311sas-hub/shibata

## ドキュメント

- [開発・学習計画書（ユーザー提供の原文）](docs/development-plan.md)
- [開発記録](docs/progress.md)
- [実験記録テンプレート](docs/experiment-template.md)
- [環境構築・演習の実行手順](docs/setup.md)
- [Phase 0の完了条件と残タスク](docs/phase0-completion-audit.md)
- [過去成績を使う参考実験](docs/retrospective-experiment.md)
- [データ取得元の調査と受入れ確認事項](docs/data-sources.md)
- [契約なしで実行できるオフライン処理](docs/offline-workflow.md)
- [入力データ形式](docs/data-contract.md)
- [JV-Link導入前の取得準備](docs/acquisition.md)
- [JV-Link接続確認結果](docs/connection-check.md)
- [特徴量・市場ベースライン台帳](docs/feature-registry.md)
- [AI作業ルール](AGENTS.md)

## 現在の状態

2026-09-22時点。Phase 0の基本操作・CSV/Parquet・SQL演習は再実行成功。全225テストが通過しています。JV-Linkによる取得、原本ハッシュ照合、発走前の保存済み市場予測と結果評価も実装済みです。

ユーザー承認の参考実験として、過去成績を復元した9特徴量で実データの学習・検証を実行しました。初回は41レース575頭で学習、後の65レース805頭で検証。発走前の利用時点は未証明で、Test評価・Phase完了の認定には使いません。詳細は参考実験記録を参照してください。

現在はユーザー指示により追加開発を一区切りとし、Phase 0の終了判定・新規環境での再現性・学習項目の不足を整理しています。具体的な残タスクと証拠はPhase 0完了監査に集約しました。正式なPhase完了判定は保留です。

セットアップ後、次のコマンドで確認できます。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m shibata.phase0
.\.venv\Scripts\python.exe -m shibata.offline demo --output-dir outputs/offline-demo
```

デモの出力先は毎回新しいフォルダを指定します。デモの評価値は予測性能の実績ではありません。

## 基本方針

- 未来情報の混入を防ぎ、情報取得時刻と予測時刻を記録する。
- 時系列分割とWalk-Forward Validationを使用する。
- Testをモデル調整に使用しない。
- 市場ベースラインから段階的に実装する。
- Log Loss・Brier Score・Calibrationを重視する。
- 特徴量定義、実験条件、評価結果、変更理由を履歴として残す。

生データ、大容量のモデル、認証情報はGitに保存しません。データセットの版・取得元・再現手順は文書で管理します。

発走前の取得記録を検証する診断経路: [観測ワークフロー](docs/observed-workflow.md)。

保存済み予測を変更せずに結果で評価する手順: [保存済み予測の結果評価](docs/saved-evaluation.md)。

承認済みの発走10分前試験: [パイロット運用手順](docs/pilot-operations.md)。固定締切・鮮度検査と全対象台帳を実装済み。自動起動は未設定。
