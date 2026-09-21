# 承認済みパイロットの運用手順

2026-09-21にユーザー承認済み。設定は`configs/market-observed-pilot-v1.json`。9/26・9/27・10/3・10/4のJRA平地競走、情報締切は発走10分前、オッズは締切時点で5分以内、予測保存は締切後1分以内。学習・Test期間の設定ではない。

今回、条件検査、日別台帳、1レースの取得・予測・結果評価、欠測集計を実装した。定期実行・バックグラウンド起動はまだ設定していない。

## 開催前：全対象台帳を固定

最新の公式出馬表で全開催場と全レースを確認し、次の形のJSONをローカルに作成する。障害競走も一覧には含め、トラックコードによりOUT_OF_SCOPEとして残す。race_idはJV-Linkの16桁キー、track_codeはJV-Dataコード表2009。コード10〜29が平地、51〜59が障害。

- date: 承認された対象日のYYYY-MM-DD
- source_url: 確認したJRA公式ページ
- verified_at: 実際に確認したタイムゾーン付き時刻
- all_venues_reviewed: 全開催場の確認を終えた場合のみtrue
- venue_race_counts: 開催場コードから予定レース数への対応（例：06 → 12）
- races: race_id / start_at / track_codeを持つ全レースの配列

初期化は全レースの締切より前に行う。重複、宣言した開催場のレース欠落、不明なトラック、対象日外、確認時刻の未来指定は拒否する。開催場の申告漏れを自動発見する機能ではなく、元資料の全場確認が必要。

```powershell
.venv/Scripts/python.exe -m shibata.pilot init --policy configs/market-observed-pilot-v1.json --roster data/pilot/roster-20260926.json --workspace data/pilot/20260926
```

各開催日を別workspaceで初期化する。設定・台帳の原本とハッシュ、SQLiteの状態・イベント履歴が保存される。途中で原本を書き換えると処理を拒否する。予定変更は黙って置換せず、当該レースは保留として理由を残す。初期化後の手動台帳削除・SQL編集は運用手順に含めない。

## 取得と予測

発走13〜10分前の間に、登録済み1レースを取得する。コマンドは即時実行であり、開始時刻を待つ予約ではない。

```powershell
.venv/Scripts/python.exe -m shibata.pilot collect --workspace data/pilot/20260926 --race-id <登録済みの16桁キー>
```

0B15、確認用0B15、0B41を順に取得し、取得先を台帳に登録する。COM利用のためJV-Link導入済みWindows/PowerShellとネットワーク接続が必要。各子プロセスは60秒を上限に待ち、締切を超えた取得は使わない。内容が安定していない場合の自動再試行や締切の延長はしない。

発走10分前以降、1分以内に予測する。最新オッズの時刻、予定発走・馬ID・頭数・トラック、再取得一致、保存完了時刻も検査する。

```powershell
.venv/Scripts/python.exe -m shibata.pilot predict --workspace data/pilot/20260926 --race-id <同じキー>
```

同一レースの二重予測は拒否する。元の取得から保存までを後日やり直して当日の予測に見せることはできない。時間内に開始しても保存が遅れた場合はFAILED/INELIGIBLEとなり評価に入らない。

外部取得を使う場合はpredictに--entries / --odds / --confirmationを明示できるが、時刻・内容・ハッシュ検証は同じ。

## 結果と評価

結果が確定した後、既存collect-jvlink.ps1で0B12を新規フォルダへ保存してから評価する。

```powershell
./scripts/collect-jvlink.ps1 -DataSpec 0B12 -RaceKey <同じキー> -OutputDirectory data/raw/<新規の結果取得ID>
.venv/Scripts/python.exe -m shibata.pilot evaluate --workspace data/pilot/20260926 --race-id <同じキー> --results data/raw/<結果取得ID>
```

予測は台帳に固定したstatus SHA256で検証し、読み取り専用で評価する。結果取得失敗や未確定・同着等は理由付きRESULT_PENDING。再取得後に評価を再試行できるが、新しい評価フォルダを作り過去の失敗記録も残す。成功済み評価の二重計上は拒否する。

## 欠測と集計

未処理のレースの締切超過を記録し、全対象の状態を出力する。

```powershell
.venv/Scripts/python.exe -m shibata.pilot expire --workspace data/pilot/20260926
.venv/Scripts/python.exe -m shibata.pilot report --workspace data/pilot/20260926 --output outputs/<新規の日別レポートID>
```

通信失敗や中止などを手動で記録する場合は、未処理レースに対し`failure --workspace ... --race-id ... --reason "具体的な理由"`を使う。集計には全登録数、平地対象数、状態別・理由別件数、時系列イベント、評価済み実験の台帳とv1指標を含む。評価済みが0件なら指標は作らない。未処理/中断は隠さず表示する。

主な状態: PLANNED、OUT_OF_SCOPE、CAPTURING、CAPTURED、CAPTURE_FAILED、PREDICTING、PREDICTED、INELIGIBLE、MISSED_CUTOFF、INTERRUPTED、EVALUATING、RESULT_PENDING、EVALUATED。

SQLiteトランザクションで二重実行を防ぐが、電源断後の自動復旧・外部時刻認証はない。実行が中断された場合は状態と原本を保全して確認する。reportは成功例だけの母集団を新しく作らず、凍結した日別台帳を基準にする。対象4日間の網羅性を一日分だけで主張しない。

## 現在の準備状態

承認条件のコード化と合成データによる取得→予測→結果評価→全対象集計の検証まで完了。将来4日分の正式出馬表はまだ確認しておらず、本番台帳は未作成。開催前に公式出馬表を確認し、台帳を固定してから当日の起動方法を整える。ユーザーに出馬表の入力を依頼する段階ではない。

## 時刻に合わせて取得・予測する常駐起動

正式台帳を固定した後、次のコマンドで実行予定を確認する。この確認だけでは取得は開始しない。

```powershell
.venv/Scripts/python.exe -m shibata.pilot_runner --workspace data/pilot/20260926
```

当日は最初の対象レースの発走13分前より前に、次を起動して稼働を続ける。

```powershell
.venv/Scripts/python.exe -m shibata.pilot_runner --workspace data/pilot/20260926 --run
```

起動したプロセスが発走13分前に取得、10分前に予測保存を行う。OSの予約タスクではなく、PCとプロセスの継続稼働・ネット接続が必要。結果取得と評価は上記の別手順で行う。対象の取得・予測がすべて成功または失敗として記録されたら終了する。実行予定の取得・保存枠が重なる場合は開始を拒否する。

同一workspaceの常駐処理は専用SQLiteロックで二重起動を拒否し、終了・プロセス停止でロックを解放する。runner-lock.sqliteは削除しない。常駐中は同じworkspaceに対する手動collect/predict/expireを並行実行しない。

再起動時、完了した予測は作り直さない。取得・予測途中の状態はINTERRUPTEDとし自動再試行しない。取得締切後の未取得レースや保存締切超過は失敗・欠測として残す。runner.jsonlに開始・操作・エラー・停止・終了を追記する。外部時刻認証とOSの時刻変更検出、電源断復旧の保証はない。

## 当日の結果取得をまとめて行う

常駐処理が終了し、全レースの予定発走時刻を過ぎた後に実行する。全結果の確定を保証する時刻ではないため、未確定は保留する。

```powershell
.venv/Scripts/python.exe -m shibata.pilot_finish --workspace data/pilot/20260926
```

保存済み予測のある未評価レースだけを1回ずつ取得し、既存のハッシュ検証付き評価を行う。1取得の待機は60秒まで。結果未確定・通信失敗はRESULT_PENDINGとして残し、新しい取得フォルダで後から同じコマンドを再実行できる。評価済みのレースは処理しない。予測の再計算は行わない。途中停止した評価は記録を保全して別フォルダで再試行する。

実行後、workspace内reports/report-<一意ID>に全対象の状態と評価を出力する。取得失敗がある場合も、出力されたcoverageのRESULT_PENDING件数を確認する。コマンド終了だけを全件成功と解釈しない。

## 開始前の時計確認

2026-09-21 23時台の確認では、Windows Timeが未同期（Leap Indicator=3、Stratum=0）を返した。過去に同期した日時の表示だけでは現在の正常同期を証明しない。観測前にWindowsの「設定 → 時刻と言語 → 日付と時刻」で時刻の自動設定を確認し、「今すぐ同期」を実行する。復旧後に同期状態を再確認する。時計を変更した場合は取得・予測処理を動かしていない間に行い、過去の保存時刻は修正しない。

時計同期はユーザー操作後の再確認で復旧した（2026-09-21 23:24:10に正常同期、Leap Indicator=0、Stratum=5）。観測開始前にも再確認する。

このタスクには毎日9時・17時の定期確認を設定済み（ID: jra）。正式台帳作成前であり、観測プロセス自体が起動済みという意味ではない。定期確認のためPCとCodexアプリを稼働させておく。状態不変では通知を控え、進展・問題・必要操作を知らせる。対象4日分の結果集計が済んだら定期確認を停止する。
