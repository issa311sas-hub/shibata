# 開発記録

## 2026-09-20 — 記録用リポジトリの初期化

- 記録先: https://github.com/issa311sas-hub/shibata
- ユーザー提供の開発・学習計画書を原文のまま保存。
- README、AI作業ルール、実験記録テンプレート、Git除外設定を追加。
- 変更範囲はプロジェクト記録の初期整備。学習コードやデータへの変更なし。
- 検証: 計画書のコピー元と保存先のSHA-256一致、git diff --check。
- データ取得・特徴量作成・学習・評価は未実施。Phase 0は未完了。

## 初期化時点の予定

1. データ提供元・利用条件・収録範囲・取得可能な時刻を確認する。
2. Python環境と依存関係の管理方法を決め、再現手順を整備する。
3. Phase 0のデータ処理操作とGitでの記録を確認する。
4. Phase 0の完了判定後、市場ベースラインへ進む。

## 初期化時点のPhase 0 判定

| 項目 | 状態 |
|---|---|
| DATA | 未確認 |
| LEAKAGE | 未確認（データ未取得） |
| CODE | 未着手 |
| TEST | 未実施 |
| VALIDATION | 未実施 |
| DOCUMENTATION | 初期整備済み・Phase完了時に再確認 |

## 2026-09-21 — Phase 0の環境と操作演習

- 変更対象: pyproject.toml、requirements-lock.txt、src/shibata/phase0.py、tests/test_phase0.py、説明文書、ディレクトリ構成。
- 変更理由: 計画書のPhase 0に従い、再現可能な環境と基本的なデータ処理操作を実行できるようにする。
- 変更内容: Python 3.12仮想環境、固定版NumPy・pandas・PyArrow・pytest、合成データのCSV／Parquet読書き、集計・groupby・merge・sort・shift・rolling・SQLite比較。
- 影響範囲: 新規の環境・演習のみ。本番特徴量、評価指標、学習期間はまだ定義していない。
- リーク確認: 演習で当該行をshiftにより除外し、現在・未来の結果改変に対する履歴不変性をテスト。実データの公表時刻・訂正履歴は未検証。
- テスト方法: pip check、pytest -q、python -m shibata.phase0。
- 結果: 依存関係整合性PASS、4 tests passed。CSV／Parquetの完全往復とSQL集計一致PASS。出力の実データフラグはfalse、モデル評価はNOT_RUN。
- 実行環境: Windows 64bit、Python 3.12.14、numpy 2.2.6、pandas 2.2.3、pyarrow 20.0.0。間接依存はrequirements-lock.txt。
- 調査: JRA-VAN公式SDK・FAQ・規約を確認。出典と未確認事項はdata-sources.mdに記録。
- 実データの学習実験ではないためEXP番号・予測性能は付与しない。合成出力はoutputs/phase0へ保存しGit追跡対象外。
- 環境上の問題: 通常のpython/py/uvコマンドが見つからなかったため、利用可能なPython 3.12から専用venvを作成。共有環境にPyArrowがなかったため専用venvへ固定版を導入して解消した。

### 現在のPhase 0判定

| 項目 | 状態 |
|---|---|
| DATA | 合成データPASS、実データ未確認 |
| LEAKAGE | 演習の時系列テストPASS、実データ未確認 |
| CODE | 演習の実行PASS、依存版と再実行手順を保存 |
| TEST | 4件PASS |
| VALIDATION | 未実施（未知期間の実データなし） |
| DOCUMENTATION | 今回の変更・検証・取得元調査を記録済み |

計画書第24章の全PASS条件を満たしていないため、Phase 0全体は未完了とし、Phase 1には進んでいない。
Phase 0は環境演習だが第24章には未知期間評価も要求されているため、対象外扱いへ勝手に変更せず未実施として記録する。

### 次の作業

1. 既存データまたはData Lab.の利用状況をユーザーに確認する（確認依頼済み）。
2. 取得元・条件・取得時刻の証拠を確認し、少量の実データを読み込む。
3. データ品質と時点整合性を確認し、Phase 0の残る判定項目を整理する。
