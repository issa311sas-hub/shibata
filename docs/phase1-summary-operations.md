# Phase 1の全期間集計手順

準備日: 2026-09-23。取得・予測・評価の条件は変更しない。この処理はネットワーク取得や予測生成を行わない。

## 現在の未準備状態を確認する

```powershell
.venv/Scripts/python.exe -m shibata.pilot_summary --manifest configs/pilot-summary-pending.json --output-dir outputs/phase1-pending-report
```

出力先は毎回新しくする。現時点では4日ともROSTER_MISSING、全期間対象数はnull、指標なしが正しい。架空の正式台帳を実運用先へ作らない。

## 正式台帳作成後の入力

ローカルにdata/pilot/summary-manifest.jsonを作り、各日の値をそのファイルからの相対パス、または絶対パスで指定する。未作成日はnullを残す。全4日を明記し、日付の削除で欠測を隠さない。

```json
{
  "2026-09-26": "20260926",
  "2026-09-27": null,
  "2026-10-03": null,
  "2026-10-04": null
}
```

各workspaceは既存pilot initで公式情報を確認して固定したものを使う。結果はpilot_finishで評価し、runnerや手動評価が終了してから集計する。集計中はworkspaceを更新しない。

```powershell
.venv/Scripts/python.exe -m shibata.pilot_summary --manifest data/pilot/summary-manifest.json --output-dir outputs/phase1-summary-v1
```

## 検査と成果物

- 全4日を明示し、workspaceの重複、日付違い、存在しないパスを拒否する。
- 既存pilot reportで凍結ファイルのハッシュと保存済み予測の締切・鮮度を検証する。
- 固定台帳とDBのレース集合・時刻・馬場種別・対象外分類を照合する。日別報告、固定台帳・設定のコピー、状態・理由・イベントを保存する。
- 全EVALUATEDの一覧を作り、既存aggregate_savedでハッシュを確認し全行から評価指標を再計算する。日別指標を平均しない。
- coverage.jsonに全日と欠測日、既知対象数、全期間対象数、未評価数、未解決数、理由を保存する。台帳未作成の日があれば全期間対象数はnull。
- races.jsonは対象外・失敗を含む全登録レース、evaluation-ledger.jsonは評価済み対象の一覧。各日events.jsonと元の予測保存先から時刻証拠を追跡する。
- status.jsonのoutput_sha256に全成果物のハッシュを記録する。評価0件なら指標を作らない。エラーはFAILEDとして記録し、不正な入力を黙って除外しない。

PASSは報告生成の成功だけを意味する。final_review_readyは全台帳があり、処理中・結果待ちがなく、評価が1件以上ある場合のレビュー着手目安であり、性能の十分性やPhase完了を保証しない。全場確認とWindows時刻同期の証拠は別途人が確認する。障害競走を含む全対象表と、成功分に限る指標を区別する。

## 開催前・当日の証拠

正式台帳作成後にpilot_runnerの引数--runなしで競合を確認し、その出力をローカル保存する。当日朝は取得開始前にWindowsの時刻同期状態を確認してログを保存する例:

```powershell
w32tm /query /status | Out-File -Encoding utf8 data/pilot/20260926/clock-before-run.txt
```

コマンド成功だけで同期正常とは判断しない。Leap Indicator、Stratum、最終同期時刻を確認する。異常ならrunner起動前に対処する。runner.jsonlのSTART・FINISHと対象プロセスの稼働を確認する。過去ログを使い回さない。正式台帳作成・runner実行・結果取得の詳細はpilot-operations.mdを参照。

## 再現確認と最終記入

入力の更新を止めて同じmanifestで別の出力先へ再実行する。coverage.json、races.json、evaluation-ledger.json、metrics以下の指標・表のSHA256が一致することを確認する。日別集計statusのパス依存ハッシュ等まで異なる出力先で完全一致するとは限らない。

phase1-report-template.mdをコピーして根拠と判定を記入する。生データ・ローカルパス付き詳細成果物はGitへ送らず、検証した集計値と制約・再現手順を文書として記録する。残る問題を隠して全PASSにせず、原計画の6項目を確認する。
