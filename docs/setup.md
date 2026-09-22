# 環境構築と最初の演習

## 対象環境

Windows 64bit / Python 3.12。今回の実行環境は3.12.14。
Phase 0ではNumPy・pandas・PyArrow・pytestを導入する。
scikit-learn 1.7.2は基本環境にも導入済み。Phase 0の学習項目を確認する専用環境は、matplotlib 3.10.6・LightGBM 4.6.0・CatBoost 1.2.8・JupyterLab 4.4.9等をrequirements-phase0-lock.txtに固定する。基本環境の依存を無条件に増やさず、別venvで再現確認する。

## セットアップ

リポジトリ直下で実行する。Python 3.12がPATHにない場合は、最初のコマンドのpythonをインストール済み実行ファイルの絶対パスに置き換える。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m shibata.phase0
```

requirements-lock.txtはWindows / Python 3.12で検証した直接・間接依存の固定版。
ビルド用setuptoolsもpyproject.tomlで固定している。初回インストールにはネットワーク接続が必要。

## 演習の内容

架空の2頭・3レース・6行をコード内で作成する。実在の競走成績ではない。

1. CSVとParquetへ保存して再読込し、IDの先頭ゼロを含めて一致を確認する。
2. 馬・日付順にsortし、groupbyで集計する。
3. レースごとの頭数をmany-to-oneの検証付きmergeで結合する。
4. shift後にrollingを適用し、当該行の結果を過去成績に混ぜない。
5. 最初の履歴欠損は欠損のまま残す。
6. SQLiteの集計とpandasの集計が一致することを確認する。
7. pytestで期待値と、結果を変更した場合の時系列不変性を確認する。

出力はoutputs/phase0/。report.jsonにPython・ライブラリ版と実行結果を記録する。
このフォルダの合成データは再生成可能で、Gitでは追跡しない。

## 学習時に読む順番

[最小演習ガイド](phase0-learning-guide.md)とnotebooks/phase0-foundations.ipynbを併用する。Notebookは出力なしの教材をGitへ保存し、実行済みコピーはローカルoutputsへ保存する。

src/shibata/phase0.pyのmake_example → exercise_operations → runを読む。
DataFrame、groupby、merge、shift、rollingの役割を実行結果と照合する。
過去成績のない馬の値と、2走目以降の値の違いを確認する。

## 利用範囲

このコードはPhase 0の操作演習専用。実データ受入れや本番特徴量生成には使わない。
日付順だけでは情報の公表時刻・訂正履歴を保証できない。実データでは予測時刻に応じた時点結合とデータ品質検証が必要。
期間全体のsummaryは説明用集計であり、予測特徴量ではない。

続いて、契約なしで進めるよう依頼された範囲として市場ベースラインのオフライン予行を追加した。
[offline-workflow.md](offline-workflow.md)を参照。実データのPhase完了判定や機械学習への移行とは区別する。

## Phase 0を空の環境から確認する

リポジトリ直下、Windows 64bit / Python 3.12で実行する。下記の環境名と出力先は毎回新しくする。-Pythonには利用可能なPython 3.12の実行ファイルを指定できる。

```powershell
./scripts/check-phase0.ps1 -Python .venv/Scripts/python.exe -EnvironmentDirectory work/phase0-replay-next -OutputDirectory outputs/phase0-replay-next
```

固定した全依存115件を新しいvenvへインストールし、プロジェクトのeditable install、pip check、全pytest、Phase 0受入CLIを順に実行する。初回はネットワーク接続が必要。カーネルは同じvenvのPythonを明示して起動し、Notebook内の実行ファイル表示とも照合する。

outputs配下のclean-environment.jsonが全体の成否。失敗時はinstall.log、project-install.log、pip-check.log、pytest.log、acceptance.logとacceptance/report.jsonを確認する。レポートにstatus=PASSがあることを確認し、終了コードだけで判断しない。

受入処理はCSV/Parquet往復、SQL照合、2025年の後続合成標本の期待値と4つの時点境界、図の生成、3ライブラリの最小学習・確率出力、Notebook全セル実行を確認する。乱数種は0、LightGBM/CatBoostは単一スレッド。利用者の理解や実競馬の予測性能を自動認定するものではない。

導入済みの専用環境で処理だけ再実行する場合:

```powershell
work/phase0-replay/Scripts/python.exe -m shibata.phase0_completion --output outputs/phase0-acceptance-next
```

Notebookを手元で操作する場合のみ、同環境でpython -m jupyterlab notebooks/phase0-foundations.ipynbを起動する。自動検証ではブラウザや常駐Jupyterサーバーは起動しない。
