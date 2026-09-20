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
- [契約なしで実行できるオフライン処理](docs/offline-workflow.md)
- [入力データ形式](docs/data-contract.md)
- [JV-Link導入前の取得準備](docs/acquisition.md)
- [特徴量・市場ベースライン台帳](docs/feature-registry.md)
- [AI作業ルール](AGENTS.md)

## 現在の状態

Phase 0の環境演習に続き、契約・JV-Link導入なしで実行できる市場ベースラインの予行を実装しました。データ保存・時刻検証・予測・評価・実行記録まで人工データで通り、52件のテストが通過しています。
O1単勝オッズの部分解析と、通信しない取得要求の確認機能も用意しました。
実データ取得、JV-Link実通信、機械学習、未知期間評価は未実施です。Phase 0/1の実データでの完了判定は保留しています。
次に必要なのはJV-Link導入後の接続試験と、原本・時刻根拠を確かめながらの実データ変換です。

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
