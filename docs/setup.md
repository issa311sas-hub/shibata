# 環境構築と最初の演習

## 対象環境

Windows 64bit / Python 3.12。今回の実行環境は3.12.14。
Phase 0ではNumPy・pandas・PyArrow・pytestを導入する。
scikit-learn 1.7.2は承認済み参考実験のため追加済み。matplotlib・LightGBM・CatBoost・Jupyterは未導入。原計画のPhase 0の学習項目にも挙がっているため、最小演習と導入範囲を[Phase 0完了監査](phase0-completion-audit.md)の残タスクとして整理した。

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

src/shibata/phase0.pyのmake_example → exercise_operations → runを読む。
DataFrame、groupby、merge、shift、rollingの役割を実行結果と照合する。
過去成績のない馬の値と、2走目以降の値の違いを確認する。

## 利用範囲

このコードはPhase 0の操作演習専用。実データ受入れや本番特徴量生成には使わない。
日付順だけでは情報の公表時刻・訂正履歴を保証できない。実データでは予測時刻に応じた時点結合とデータ品質検証が必要。
期間全体のsummaryは説明用集計であり、予測特徴量ではない。

続いて、契約なしで進めるよう依頼された範囲として市場ベースラインのオフライン予行を追加した。
[offline-workflow.md](offline-workflow.md)を参照。実データのPhase完了判定や機械学習への移行とは区別する。
