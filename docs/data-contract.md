# 内部データ形式 v1

この形式は本プロジェクト内で新しく定義したもの。公式JV-Dataのバイト形式とは異なる。
実データ変換器は未接続。入力値と情報提供時刻の正しさは、原本・仕様・取得記録に照らして別途確認する。

## ファイル

入力フォルダにdataset.jsonと、races / entries / odds / resultsの4テーブルを置く。
各テーブルはUTF-8 CSVまたはParquetのどちらか1ファイル。両形式を同時に置くことは不可。
列は以下と完全一致させる。余分な列も自動で削除せずエラーにする。原本の列を削除する指示ではなく、原本を保存した上で内部テーブルを別に作る。
空テーブル・欠損・空文字・重複キーを拒否する。IDは文字列とし、先頭ゼロを保持する。
時刻はUTCまたは+09:00などのオフセット必須。タイムゾーンのない日時を推測しない。

## dataset.json

```json
{
  "schema_version": 1,
  "dataset_id": "SYNTHETIC_BASELINE_V1",
  "data_kind": "synthetic",
  "source": "generated_by_shibata.demo",
  "availability_mode": "observed",
  "availability_evidence_reviewed": false
}
```

data_kindはsynthetic / real。availability_modeはobserved / historical。
historicalのときavailability_evidence_reviewedは真偽値のtrueが必須。
これは利用者によるレビュー済み宣言であり、単なるフラグ変更によって証拠が成立するわけではない。
実データのsourceは取得元を識別する値とし、認証情報を含めない。

## races（1行＝1レースの予測条件）

| 列 | 意味 |
|---|---|
| race_id | レースID、主キー |
| start_at | 予測時点で分かっていた発走予定時刻。後日修正された実発走時刻を流用しない |
| prediction_at | 今回固定する予測締切。start_atより前 |
| entries_available_at | その出走表・発走予定時刻・頭数が利用可能になった時刻 |
| entries_retrieved_at | その出走表をローカルで取得した時刻 |
| entries_evidence_id | 出走表の原本・時刻を確認する根拠ID |
| expected_runners | 予測時点の対象頭数。現在の処理対象は2～18頭 |

出走表は予測ごとに確定したスナップショットを入力する。結果判明後の取消馬削除で出走表を作り直さない。

## entries（1行＝出走表の1頭）

race_id, horse_id, horse_number

主キーはrace_id + horse_id。horse_numberは1～18の整数でレース内一意。
race_id集合はracesと一致し、レース内行数はexpected_runnersと一致する。

## odds（1行＝1スナップショットの1頭）

| 列 | 意味 |
|---|---|
| race_id, horse_id | 対象レースと馬 |
| snapshot_id | 提供元の同一時点・同一版を識別するID |
| odds_at | オッズの発表時刻。available_at以下 |
| available_at | 当該版が外部で利用可能だったことを根拠付きで示す時刻 |
| retrieved_at | ローカル取得時刻。available_at以上 |
| evidence_id | 原本・公表時刻の証拠ID。未知の場合は入力を完成扱いしない |
| odds_kind | pre_race / final。finalは保存されても予測には選ばれない |
| win_odds | 有限の1.0以上の確定数値。上限打切り・無投票・取消の特殊値は未対応 |
| popularity | 同じスナップショットの提供元人気順位（1～18の整数） |

主キーはrace_id + snapshot_id + horse_id。
同一スナップショット内の各時刻・odds_kind・evidence_idは一致必須。
原本の訂正と遅延配信を考慮し、発表時刻とavailable_atを根拠なく同一にしない。
値が999.9でも、提供元で「999.9以上」を意味する場合は正確なオッズとして入力しない。

## results（予測後の評価専用）

race_id, horse_id, win, result_status, settled_at

主キーはrace_id + horse_id。予測のキー集合と完全一致させる。
winは0/1で、レースごとに1着がちょうど1頭。複数1着は明示的に停止する。
result_statusは現在officialのみ。settled_atは発走後・レース内共通の結果確定時刻。
着順不明を0で埋めない。競走中止と開催中止・取消を区別し、入力側で状態を確認する。
この表はpredict_marketに渡さず、予測保存後の評価にだけ使用する。

## 検証の限界

形式検証は捏造された時刻や誤った出走表を見破るものではない。
evidence_idは原本を指す識別子であり、自動で外部資料を取得・検証する機能はない。
古いオッズをどこまで許容するか、締切後の取消、発走変更、同着・返還は実データ受入れ前に方針を確定する。

観測した確定結果の評価は[saved-evaluation.md](saved-evaluation.md)を参照。観測結果はresult_observed_atを使い、上記resultsのsettled_atへ取得時刻を詐称しない。指標の式は共通だが、時刻の意味は分離する。
