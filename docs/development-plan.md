# JRA単勝勝率予測AI 開発・学習計画書

## 0. この文書の目的

本プロジェクトの最終目的は、JRAの各レースについて、出走する各馬の「1着になる確率」をレース開始前の情報だけから推定する機械学習システムを完成させることである。

本プロジェクトでは単に「1着馬を当てる」ことを目的としない。

最終的には各馬について、

- AI予測勝率
- 市場が示唆する勝率
- 単勝オッズ
- AIと市場の評価差
- 理論期待値

を計算できる状態を目指す。

例：

| 馬 | AI勝率 | 市場勝率 | 単勝オッズ | Edge | 理論期待値 |
|---|---:|---:|---:|---:|---:|
| A | 31% | 33% | 3.0 | -2pt | 0.93 |
| B | 24% | 17% | 5.8 | +7pt | 1.39 |
| C | 14% | 12% | 8.2 | +2pt | 1.15 |

ただし、最終的な投票判断を機械的に行うことよりも、まず「未知の未来データに対して勝率推定が適切に機能するモデル」を完成させることを優先する。

---

# 1. 絶対に守る開発原則

以下は、本プロジェクトを担当する人間および生成AIが必ず守ること。

## 原則1：未来情報を使用しない

あるレースRを予測する場合、Rの予測時点より後に判明する情報を特徴量に使用してはならない。

禁止例：

- Rの着順
- Rの走破タイム
- Rの上がり3F
- Rのレース後コメント
- R終了後に更新された騎手勝率
- R終了後に更新された馬の通算成績
- 予測時刻より後のオッズ
- Rの結果を含めて計算した各種統計量

特徴量を作成するときは常に、

「この数値は、そのレースを実際に予想していた時点で知ることができたか？」

を確認すること。

答えがNOなら使用禁止とする。

---

## 原則2：学習データとテストデータを時間順に分割する

原則としてランダム分割を使用しない。

悪い例：

2015～2025年のレースをランダムに80%/20%へ分割する。

良い例：

Train：2016～2022  
Validation：2023  
Test：2024

さらに、

Train：2017～2023  
Validation：2024  
Test：2025

のようなWalk-Forward Validationを実施する。

未来のデータを過去の予測に使用してはならない。

---

## 原則3：テストデータを見ながらモデルを改善しない

Testは最終試験である。

特徴量の追加・削除、ハイパーパラメータ調整、モデル選択などはTrainとValidationのみで行う。

Testの成績を見てモデルを変更すると、そのTestは以後「未知データ」ではなくなる。

---

## 原則4：的中率だけで評価しない

最低限、以下を評価する。

- Log Loss
- Brier Score
- Calibration
- Accuracy等の参考指標
- ROI
- オッズ帯別成績
- 人気別成績
- 年度別成績

単勝モデルでは特に「予測勝率の品質」を重視する。

例えばAIが「勝率20%」と予測した馬を大量に集めた場合、実際に約20%が勝っていることが望ましい。

---

## 原則5：一度に複雑なモデルを作らない

必ず単純なモデルから開始する。

市場ベースライン  
↓  
単純な機械学習  
↓  
基本能力特徴量  
↓  
適性  
↓  
騎手・調教師  
↓  
展開  
↓  
当日情報  
↓  
オッズ時系列  
↓  
非構造化データ

の順に拡張する。

---

# 2. 最終成果物

プロジェクト完了時には以下を完成させる。

### 成果物A：競馬データセット

原則として「1行＝1レースに出走した1頭」とする。

例：

race_id | horse_id | date | track | distance | jockey | weight | ... | win
---|---|---|---|---|---|---|---|---
001 | H01 | ... | Tokyo | 1600 | ... | ... | ... | 0
001 | H02 | ... | Tokyo | 1600 | ... | ... | ... | 1

目的変数：

win = 1：1着  
win = 0：それ以外

---

### 成果物B：特徴量生成パイプライン

生データから機械学習用特徴量を自動生成できるプログラムを作成する。

---

### 成果物C：学習パイプライン

データ期間を指定すると、

データ読み込み  
→ Train/Validation/Test分割  
→ 学習  
→ 予測  
→ 評価

まで自動実行できる状態にする。

---

### 成果物D：予測モデル

各出走馬について勝率を出力する。

重要：

同一レース内の各馬の勝率合計がどのように扱われるかを必ず確認する。

独立二値分類によって合計が1にならない場合は、レース単位の正規化、softmax型モデル、ランキング/選択モデル等も比較検討する。

---

### 成果物E：評価レポート

最低限、

- Log Loss
- Brier Score
- Calibration Plot
- 年度別性能
- 人気別性能
- オッズ帯別性能
- ROI
- 特徴量重要度
- SHAP
- Ablation Test

を出力する。

---

### 成果物F：実戦予測プログラム

対象レースを指定すると、

「その予測時点で取得可能な情報だけ」

を取得・加工して予測する。

---

# 3. Phase 0：開発環境を作る

## 目的

競馬分析以前に、再現可能なPython環境を作る。

## 学習内容

以下について最低限理解する。

Python：
- 変数
- list
- dict
- if
- for
- function
- classの概念
- exception

データ処理：
- NumPy
- pandasまたはPolars

可視化：
- matplotlib

機械学習：
- scikit-learn

勾配ブースティング：
- LightGBM
- CatBoost

その他：
- Git
- GitHub
- SQL
- Jupyter Notebook

## 推奨ディレクトリ

project/

data/
  raw/
  interim/
  processed/

src/
  ingestion/
  preprocessing/
  features/
  models/
  evaluation/

notebooks/

configs/

tests/

outputs/
  models/
  predictions/
  figures/
  reports/

README.md

## 完了条件

PythonからCSV/Parquetを読み込み、

- 集計
- groupby
- merge
- sort
- shift
- rolling

が扱える。

Gitで変更履歴を残せる。

---

# 4. Phase 1：機械学習を使わない市場ベースライン

## 目的

いきなりAIを作らない。

まず「オッズだけならどの程度の予測性能になるか」を測定する。

これは今後すべてのモデルが超えるべき基準になる。

## 作成する特徴量

- 単勝オッズ
- 人気
- 出走頭数

市場勝率の基本形：

raw_probability_i = 1 / odds_i

ただし控除等により、そのままでは同一レース内で合計1にならない。

そこで、

market_probability_i =
(1 / odds_i) / Σ(1 / odds_j)

として正規化する。

## 評価

- Log Loss
- Brier Score
- Calibration
- 人気別成績
- オッズ帯別成績

## 完了条件

「オッズだけのモデル」の性能を数値として保存する。

以後、

Model 1 vs Market Baseline

のように必ず比較する。

---

# 5. Phase 2：最小機械学習モデル

## 目的

競馬予測パイプライン全体を一度完成させる。

精度は追求しない。

## 最初の特徴量

例：

- 年齢
- 性別
- 枠番
- 馬番
- 頭数
- 距離
- 芝/ダート
- 競馬場
- 負担重量
- 前走着順
- 前走着差
- 前走上がり3F
- 前走距離
- 前走からの日数

## モデル

最初は以下を比較する。

1. Logistic Regression
2. LightGBM
3. CatBoost

Deep Learningはまだ使用しない。

## 完了条件

raw dataから、

特徴量生成
→ 学習
→ 予測
→ 評価

を一つのコマンドまたはスクリプトで再現できる。

---

# 6. Phase 3：特徴量台帳を作る

ここから本格的な特徴量開発に入る。

すべての特徴量を「特徴量台帳」で管理する。

最低限、以下の列を持つ。

feature_name  
category  
description  
formula  
raw_source  
available_time  
missing_rate  
leakage_risk  
hypothesis  
implemented  
validation_result  
keep_or_drop  
notes

例：

feature_name:
horse_last3_speed_mean

description:
対象馬の直近3走のスピード指数平均

available_time:
レース前

hypothesis:
直近能力を表現する

leakage_risk:
Low

と記録する。

特徴量をコードだけで管理してはならない。

---

# 7. Phase 4：馬の基礎能力特徴量

## 作成候補

過去1走、3走、5走、10走について、

- 平均着順
- 中央値着順
- 勝率
- 複勝率
- 平均着差
- 平均走破タイム
- 平均上がり3F
- ベスト上がり
- 平均スピード指数
- 最大スピード指数
- スピード指数標準偏差

などを作る。

## 特に重要

単純な平均だけではなく、

- mean
- max
- min
- std
- trend

を比較する。

例えば直近5走Performanceについて線形回帰し、

performance_trend

を作る。

正なら上昇傾向、負なら下降傾向を意味する。

---

# 8. Phase 5：独自Performance Ratingを作る

着順だけでは馬の能力を適切に表現できない可能性がある。

そこで、

- 走破タイム
- 着差
- 距離
- 馬場
- 競馬場
- クラス
- 負担重量
- 相手レベル

などを補正したPerformance Ratingを設計する。

最初から完璧な指数を作ろうとしない。

Rating v1  
↓
評価  
↓
Rating v2  
↓
評価

と改善する。

重要：

Ratingを計算する際にも未来情報を使用してはならない。

---

# 9. Phase 6：条件適性

作成する。

### 距離

- distance_runs
- distance_win_rate
- distance_performance_mean
- similar_distance_performance

### コース

- track_runs
- track_win_rate
- track_performance

### 芝/ダート

- surface_performance

### 馬場

- firm_performance
- wet_performance

さらに、

current_condition − horse_historical_condition

という考え方で適性値を作る。

---

# 10. Phase 7：騎手・調教師・血統

## 騎手

- 過去勝率
- 複勝率
- 直近成績
- コース別成績
- 距離別成績
- 芝/ダート別成績
- 馬とのコンビ成績
- 乗り替わり

## 調教師

同様に、

- 全体成績
- 直近成績
- 条件別成績
- 休養明け成績

など。

## 血統

- sire
- dam_sire
- sire_distance_performance
- sire_surface_performance
- sire_going_performance

など。

重要：

勝率などの集計値は必ず「当該レースより前のデータ」だけで計算する。

---

# 11. Phase 8：相手関係

競馬では絶対能力だけでなく、同じレースの他馬との比較が必要。

作成する。

horse_rating  
field_mean_rating  
field_max_rating  
field_std_rating  
rating_rank  
rating_gap_to_best  
rating_vs_field_mean

例えば、

rating_vs_field_mean =
horse_rating - field_mean_rating

とする。

ここで「レース単位特徴量」という概念を学習する。

---

# 12. Phase 9：展開モデル

各馬について脚質を推定する。

例：

- 逃げ
- 先行
- 差し
- 追込

ただし可能なら固定ラベルだけでなく、

P(逃げ)  
P(先行)  
P(差し)  
P(追込)

という確率として表現する。

その後、レース全体について、

- 逃げ候補数
- 先行馬数
- 前方志向馬割合
- expected_pace
- pace_pressure

などを作る。

さらに、

pace_advantage

を各馬について生成する。

---

# 13. Phase 10：当日情報

ここで初めて当日情報を追加する。

- 天候
- 馬場状態
- 馬体重
- 馬体重増減
- 馬体重増減率

さらに、

weight_vs_good_run_mean

を作る。

これは、

今回馬体重 − 過去好走時平均馬体重

とする。

「+10kg」の絶対値より意味があるか検証する。

---

# 14. Phase 11：オッズ情報

ここで市場情報を機械学習モデルへ投入する。

重要：

オッズなしモデルとオッズありモデルを別々に保存する。

### Model A

競馬情報のみ

### Model B

競馬情報 + オッズ

これによって、

「AIが市場とは独立にどの程度予測できるか」

と、

「市場情報を利用するとどこまで強くなるか」

を区別する。

---

# 15. Phase 12：時系列オッズ

取得できる場合、

- odds_60m
- odds_30m
- odds_20m
- odds_10m
- odds_5m

などを保存する。

生成する。

- odds_change_60_30
- odds_change_30_10
- odds_change_10_5
- odds_velocity
- odds_rank_change
- implied_probability_change

注意：

「発走10分前モデル」に発走5分前オッズを入れてはいけない。

予測モデルごとに情報締切時刻を固定する。

---

# 16. Phase 13：非構造化データ

ここまですべて完成してから実施する。

対象：

- 調教師コメント
- 騎手コメント
- 調教コメント
- ニュース
- パドック画像
- パドック動画

テキストについてはNLP/LLMを使用して、

- condition_score
- confidence_score
- improvement_score
- negative_signal
- distance_confidence

等への構造化を検討する。

ただし、LLMの出力をそのまま信用しない。

「LLM特徴量を追加したモデル」と「追加していないモデル」を比較して有効性を判断する。

---

# 17. 特徴量選択方法

特徴量を追加するたびに以下を実施する。

## Step 1

データ品質確認。

- 欠損率
- 分布
- 異常値
- 時系列
- リーク

を確認。

## Step 2

モデルへ投入。

## Step 3

Validation性能を測定。

## Step 4

SHAPまたはPermutation Importanceを確認。

## Step 5

Ablation Testを行う。

例えば、

FULL

から

- 血統特徴量削除
- 騎手特徴量削除
- 馬体重特徴量削除
- 展開特徴量削除

などを実施する。

## Step 6

複数期間で再現するか確認。

ある1年間だけ改善した特徴量を「有効」と断定してはいけない。

## Step 7

特徴量台帳へ結果を記録する。

---

# 18. 評価体系

モデル評価を4階層に分ける。

## Level 1：予測能力

- Log Loss
- Brier Score

## Level 2：確率品質

Calibration Plotを作成する。

例えば、

予測勝率0～5%  
5～10%  
10～15%  
15～20%  
...

ごとに実際の勝率を確認する。

## Level 3：ランキング能力

AI勝率順位と実際の勝敗の関係を見る。

## Level 4：経済的評価

- ROI
- 的中率
- 平均配当
- 最大ドローダウン
- オッズ帯別ROI
- 人気別ROI

ただしROIだけでモデルを選択しない。

---

# 19. 市場との差を分析する

AI勝率：

P_model

市場勝率：

P_market

として、

Edge = P_model - P_market

を計算する。

また、

ExpectedReturn = P_model × Odds

を計算する。

ただしExpectedReturn > 1だからといって即座に有効と判断しない。

多数の過去レースで再現性を検証する。

Edgeについて、

0～2pt  
2～5pt  
5～10pt  
10pt以上

などに分け、

実際の勝率とROIを確認する。

---

# 20. 最重要：Walk-Forward Backtest

最終モデルでは必ず、

過去 → 未来

の順番を守ってバックテストする。

例えば、

2018–2021 → 2022予測  
2019–2022 → 2023予測  
2020–2023 → 2024予測  
2021–2024 → 2025予測

という形式。

各期間について、

- Log Loss
- Brier
- Calibration
- ROI

を保存する。

特定年度だけ非常に強いモデルを採用してはならない。

---

# 21. モデル比較

最低限、

### Baseline
市場確率

### Model 1
Logistic Regression

### Model 2
LightGBM

### Model 3
CatBoost

を比較する。

その後必要なら、

- XGBoost
- Neural Network
- Ranking model
- レース単位Softmaxモデル

等を検討する。

複雑なモデルが単純なモデルを安定して上回らない場合、単純なモデルを優先する。

---

# 22. 実験管理

すべての実験にIDを付ける。

例：

EXP_001  
EXP_002  
EXP_003

記録するもの：

experiment_id  
date  
dataset_version  
train_period  
validation_period  
features  
model  
hyperparameters  
logloss  
brier  
roi  
notes

「前のモデルの方が良かったが何を変更したか分からない」という状態を絶対に作らない。

---

# 23. 生成AIへの作業ルール

生成AIが本プロジェクトを支援する場合、以下を厳守する。

### 禁止事項

ユーザーの許可なく、

- 大量のコードを書き直さない
- データ列を削除しない
- 特徴量定義を変更しない
- 評価指標を変更しない
- Train/Test期間を変更しない
- 欠損値を勝手に0で埋めない
- データリークの可能性がある特徴量を使用しない

### コード変更時

必ず、

1. 変更対象
2. 変更理由
3. 変更内容
4. 影響範囲
5. リークの有無
6. テスト方法

を確認する。

### エラー発生時

推測だけで修正しない。

エラーメッセージを読む。

原因候補を特定する。

最小限の修正を行う。

テストする。

修正結果を記録する。

---

# 24. 各Phaseの終了判定

「コードを書いた」だけでは完了としない。

各Phaseについて、

### DATA

データが正しいか。

### LEAKAGE

未来情報がないか。

### CODE

再実行可能か。

### TEST

最低限のテストを通るか。

### VALIDATION

未知期間で評価したか。

### DOCUMENTATION

特徴量台帳・実験記録を更新したか。

の6項目を確認する。

すべてPASSした場合のみ次Phaseへ進む。

---

# 25. 学習順序

本プロジェクトでは以下の順番で勉強する。

### Stage 1

Python  
pandas/Polars  
SQL  
Git

↓

### Stage 2

確率・統計基礎  
二値分類  
Logistic Regression  
Train/Validation/Test  
Log Loss  
Brier Score

↓

### Stage 3

決定木  
Random Forest  
Gradient Boosting  
LightGBM  
CatBoost

↓

### Stage 4

特徴量エンジニアリング  
欠損処理  
カテゴリ変数  
rolling/shift  
時系列データ

↓

### Stage 5

Cross Validation  
Walk-Forward Validation  
Data Leakage

↓

### Stage 6

Feature Importance  
Permutation Importance  
SHAP  
Ablation Study

↓

### Stage 7

Calibration  
Platt Scaling  
Isotonic Regression

↓

### Stage 8

期待値  
市場確率  
オッズ  
ROI  
バックテスト

↓

### Stage 9

必要になった場合のみ、

NLP  
LLM  
Computer Vision  
Deep Learning

へ進む。

---

# 26. 「勉強してから作る」を禁止する

本プロジェクトでは、

「機械学習を全部勉強してから競馬AIを作る」

という進め方をしない。

必ず、

学ぶ
↓
小さく実装
↓
実データで確認
↓
問題を発見
↓
必要な理論を学ぶ
↓
改善

を繰り返す。

例：

Logistic Regressionを学ぶ  
↓  
競馬データで使う  
↓  
確率校正が悪い  
↓  
Calibrationを学ぶ  
↓  
改善する

という形式を取る。

---

# 27. 最終完成条件

以下をすべて満たしたとき、本プロジェクトのVersion 1.0完成とする。

1. 過去データを自動取得・読み込みできる。
2. 生データから特徴量を自動生成できる。
3. 特徴量に未来情報が含まれていない。
4. 学習処理を再現できる。
5. Walk-Forward Validationが自動実行できる。
6. 市場ベースラインと比較できる。
7. Log Lossを計算できる。
8. Brier Scoreを計算できる。
9. Calibrationを確認できる。
10. 特徴量重要度を分析できる。
11. Ablation Testができる。
12. 未知期間について予測できる。
13. 当日レースについて予測できる。
14. 各馬のAI勝率を出力できる。
15. 市場勝率と比較できる。
16. Edgeを計算できる。
17. 理論期待値を計算できる。
18. バックテスト結果を保存できる。
19. 特徴量台帳が存在する。
20. 実験履歴から過去モデルを再現できる。

---

# 28. 完成後の出力イメージ

最終プログラムを実行すると、

Race:
東京11R

Model:
WIN_MODEL_v1.0

Prediction time:
発走10分前

のように予測条件を記録する。

その上で、

馬  
AI勝率  
市場勝率  
単勝オッズ  
AI順位  
人気順位  
Edge  
Expected Return

を表示する。

同時に、

- model_version
- dataset_version
- prediction_timestamp
- feature_version
- 使用した各特徴量

を保存する。

これにより後日、

「その時点で本当にこの予測を出せたのか」

を完全に再現できる状態にする。

---

# 29. このプロジェクトで最も重要な考え方

目的は、

「過去データに最もよく当てはまるモデル」

を作ることではない。

目的は、

「その時点で取得可能だった情報だけを使って、未知の未来レースに対する勝率を適切に推定できるモデル」

を作ることである。

したがって、

高い学習精度よりデータリーク防止。

複雑なモデルより正しい検証。

一時的な高ROIより再現性。

的中率より確率推定品質。

を優先する。

特徴量についても人間の競馬観で「効く」「効かない」を決めつけない。

仮説を立てる。

実装する。

過去から未来への検証をする。

Ablation Testをする。

複数期間で再現するか確認する。

その結果によって採用・不採用を決定する。

以上を、本プロジェクト全期間における基本原則とする。