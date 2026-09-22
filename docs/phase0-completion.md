# Phase 0完了記録

2026-09-23。実行ID: phase0-acceptance-20260923。

**Phase 0（再現可能な開発環境・基本操作）は完了。6項目すべてPASS。**

第3章の目的に対応する判定である。第24章のVALIDATIONは、元の演習で使わなかった後続日付の合成標本に対する操作検証として実施した。この適用範囲はphase0-completion-audit.mdに明記。実競馬の未知期間に対する予測性能、ユーザー本人の理解度、Phase 1以降の完了を認定するものではない。原計画本文・承認済みの実競馬期間と9特徴量は変更していない。

## 終了判定

| 項目 | 判定 | 確認した証拠 |
|---|---|---|
| DATA | PASS | 合成データのCSV/Parquet往復一致、IDの先頭ゼロ・型・欠損保持、SQLとpandasの集計一致 |
| LEAKAGE | PASS | shift後のrollingと、現在・未来の結果を改変する4時点境界の不変性検査。全期間集計は説明用に分離 |
| CODE | PASS | 新規venvへ固定依存115件から再構築、pip check成功、同環境でNotebookとCLIを実行 |
| TEST | PASS | 再構築環境で全227件成功、失敗・エラー・skipなし |
| VALIDATION | PASS | 既存処理を変更せず、2025-04-01〜06-02の別標本3頭4レース12行で手指定の期待値と照合 |
| DOCUMENTATION | PASS | 教材、再実行スクリプト、依存固定、特徴量台帳、変更・失敗・再検証記録を更新 |

元の演習は2024-01〜03の2頭3レース6行。phase0.pyのSHA256はa4171fd16823d3936020784dff21360f4098b1061a5d00e2f83076c86d2b9eccで、今回その処理は変更していない。新しい検証を通すための式の調整はしていない。

## 学習項目と環境

Python 3.12.14 / Windows 64bit。NumPy 2.2.6、pandas 2.2.3、PyArrow 20.0.0、matplotlib 3.10.6、scikit-learn 1.7.2、LightGBM 4.6.0、CatBoost 1.2.8、JupyterLab 4.4.9。直接・間接依存の全版はrequirements-phase0-lock.txt。

Notebookで変数、list、dict、if、for、function、class、exceptionとデータ処理・可視化を扱う。5コードセルを指定venvのカーネルで順に実行し、実際のPythonパスも照合。グラフのラベル・表示を目視確認した。

3学習ライブラリは、人工16行でfitし、別の人工4行で確率の形・有限値・合計1を確認。乱数種0、LightGBM/CatBoostは単一スレッド。これはライブラリ動作確認であり、競馬モデルの比較実験ではない。

## 再構築と失敗の扱い

最初の環境work/phase0-buildで導入・受入を確認して依存版を固定し、別の新規環境work/phase0-replayを固定ファイルから構築した。

初回の全テストは共有のpytest一時フォルダ・キャッシュのWinError 5により152件がセットアップエラーになった。依存関係の導入とpip checkは成功していた。権限設定・既存フォルダは変更せず、テスト一時領域・キャッシュを新規出力先に分離して、同じ再構築環境で全227件を再実行し成功した。失敗ログを保全し、check-phase0.ps1にも分離設定を反映した。追加の環境再構築を行ったとは記録しない。

Notebookの初回受入後にカーネル終了警告が出た。nbclientの同梱コードから、外部指定のKernelManagerは既定で終了しないことを確認し、cleanup_kc=Trueを指定した。再実行では受入成功と警告解消を確認。

## 保存した証拠と再実行

- 初期環境の修正後受入: outputs/phase0-completion-build-v2/report.json
- 再構築のインストール・初回失敗: outputs/phase0-completion-replay-v1/
- 再構築環境の成功した検証: outputs/phase0-completion-replay-v2/clean-environment.json、pytest.xml、acceptance/report.json
- Gitへ保存する集約証拠: [phase0-completion-evidence.json](phase0-completion-evidence.json)
- 教材: [phase0-learning-guide.md](phase0-learning-guide.md)、notebooks/phase0-foundations.ipynb
- 再実行手順: [setup.md](setup.md)、scripts/check-phase0.ps1

生成データ・実行済みNotebook・環境フォルダはローカルのみ。集約証拠にファイルハッシュと結果を残す。コード差分の基点はe990f46で、本記録と変更一式を同じコミットに保存する。

次はPhase 1の実競馬市場ベースライン検証。承認済みの発走前観測4日間や正式台帳の準備は継続課題として残る。今回の環境合格をその性能・時点検証に流用しない。
