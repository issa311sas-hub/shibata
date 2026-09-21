# 保存済み予測の結果評価

発走前に保存した市場ベースラインを読み取り専用で評価する。予測の再計算・学習・モデル選択は行わない。単一レースの動作確認は、未知期間に対する予測能力の証明ではない。

## 阪神1Rの実験

- 対象: 2026-09-21 阪神1R、レースキー2026092109040701
- 発走予定: 10:00 JST。結果取得は発走・確定後に行う。
- 保存済み予測: outputs/observed-20260921-hanshin01-v3
- 固定するstatus.json SHA256: `8a64a3d149887fd994b124e8c1d7b207b27dac617547b0a3c44c5930a010b561`
- 予測SHA256は既にprogress.mdにも記録済み。評価のために予測を保存し直さない。

```powershell
./scripts/collect-jvlink.ps1 -DataSpec 0B12 -RaceKey 2026092109040701 -OutputDirectory data/raw/results-20260921-hanshin01
.venv/Scripts/python.exe -m shibata.score_saved --prediction-dir outputs/observed-20260921-hanshin01-v3 --prediction-status-sha256 8a64a3d149887fd994b124e8c1d7b207b27dac617547b0a3c44c5930a010b561 --result-dir data/raw/results-20260921-hanshin01 --output-dir outputs/evaluation-20260921-hanshin01
```

上記は終了後に実行する手順であり、自動実行の予約ではない。未確定で停止した場合は、新規の取得先・評価先で後からやり直す。失敗した記録も保持する。

## 検査と出力

まず事前に固定したstatusのハッシュと、そこから参照される予測・出走表・オッズ・レース表の全ファイルを照合する。保存時刻が締切後かつ予定発走前であることも確認する。これが通る前には結果ファイルを読み込まない。ハッシュは原本の不変性確認であり、独立した時計認証ではない。

結果は別取得の0B12に限定し、manifestの整合性、発走後の取得、RA 1件、全SE、区分6または7の一致を要求する。登録頭数・実出走頭数・予測頭数、およびレースID・馬ID・馬番号が一致し、異常区分なし・同着なし・順位1〜Nが一意に揃うことを検査する。日時の版不一致、発走時刻変更、取消・競走中止等は個別方針が未実装のため停止する。HRは原本保存・ハッシュ記録のみで、ROIは算出しない。

出力:

- observed_results.csv: 確定結果のラベルとresult_observed_at
- metrics.json: 既存v1と同じLog Loss・Brier等の式による値
- year/popularity/odds_rank/odds_band/calibration.csv: 既存の評価集計
- status.json: 成否、保存予測・結果manifest・評価コード・出力のハッシュ、評価時刻

`result_observed_at`は「確定内容をローカルで取得し終えた時刻」。正確な確定時刻を示す`settled_at`とは別であり、`exact_settlement_time`はnullのままにする。既存の手動入力results契約と評価関数は変更せず、観測用結果にだけ別の入口を用意した。評価式は共通。未確定ラベルの補完はしない。

2026-09-21早朝時点では合成レコードによるテストと実際の保存予測の整合性確認まで完了。実結果による評価は未実施。

2026-09-21 16:05 JST追記: 阪神1Rの実結果取得と保存予測の評価が完了。記録は[first-live-evaluation.md](first-live-evaluation.md)。本手順で新規実験を行う際は出力先を変更し、既存実験を上書きしない。
