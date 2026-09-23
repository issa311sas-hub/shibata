# デスクトップPCへの引き継ぎ

更新日: 2026-09-24。対象: Windows 64bitの新しいデスクトップPC。新PCにはCodexだけが導入済みで、既存チャット履歴・リポジトリ・JRA-VAN環境はない前提。

## 最初にデスクトップPCのCodexへ送る文

> JRA単勝勝率予測プロジェクトをこのPCへ引き継ぎたいです。リポジトリは https://github.com/issa311sas-hub/shibata です。まずクローンまたは既存フォルダの確認を手伝い、`AGENTS.md`、`docs/development-plan.md`、`docs/progress.md`、`docs/pilot-operations.md`、`docs/desktop-handoff.md`を読んでください。Phase 0完了、Phase 1は2026-09-26/27と10-03/04の発走10分前観測を準備中です。JRA-VANのインストール方法も忘れたので、公式サイトとこの文書を確認しながら、私が操作する画面を一手ずつ案内してください。Python環境・JV-Link・時刻同期・未追跡データ・観測runner・定期確認を順に点検し、動作確認が終わるまで本番取得や二重起動をしないでください。秘密情報や生データをGitHubへ送らないでください。旧PCの定期確認からの切り替えも案内してください。

この文はチャット履歴の代替入口。進捗の正本はGit上の文書、当日取得・予測の正本は当該PCのローカル`data/pilot/`にある。チャットの存在だけで観測済みとは判断しない。

## 1. コードを新PCへ用意

1. Gitがあるか確認する。なければ公式配布元から導入し、デスクトップCodexに操作を案内してもらう。
2. 保存先を決め、PowerShellで`git clone https://github.com/issa311sas-hub/shibata.git`を実行する。既にフォルダがある場合は上書きせず状態を確認する。
3. リポジトリ直下で`git status --short --branch`と`git log -1 --oneline`を確認する。旧PC側の未push変更がないかも確認し、同じ作業を二重に進めない。
4. 上記の最初の依頼文を、そのリポジトリを開いたデスクトップCodexへ送る。作業規則は`AGENTS.md`を優先する。

## 2. Python環境を再構築

Windows 64bitのPython 3.12を使用。旧PCの`.venv/`をコピーしない。Pythonの有無は`py -3.12 --version`または`python --version`で確認し、未導入なら公式Python配布元から3.12系を導入する。詳しい手順は[setup.md](setup.md)。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

`py`が使えない場合は`python`またはPython 3.12の絶対パスへ置き換える。インストール失敗時は実際のエラーを確認して対処し、安易に依存版を変更しない。Phase 0の全ライブラリ演習を再現する場合は別の環境と[check-phase0.ps1](../scripts/check-phase0.ps1)を使用する。既存の実験条件・評価値は新PCでの単なる環境確認によって更新しない。

## 3. JRA-VAN / JV-Linkを導入

旧PCには2026-09-21にSDK 5.0.0の64bit JV-Linkが導入され、接続に成功した。ただしSDKの展開フォルダ`C:\Users\nuzoy\Downloads\JVDTLABSDK500\_64bit`は旧PCのローカルパスで、新PCに存在するとは限らない。インストール済み状態や無料体験が新PCへ自動移行するとも仮定しない。

1. 新PCでWindowsが64bitであることを確認する。
2. [JRA-VAN公式SDK案内](https://developer.jra-van.jp/t/topic/45)を開き、**64bit版**SDKと同梱の開発ガイド・インストール説明を確認する。手元に正規のSDK一式がない場合は公式リンクから入手する。32bit版や、古いローカルパスを前提にしない。
3. SDKを展開し、同梱の説明に沿ってユーザー自身が64bit JV-Linkをインストールする。利用規約、管理者権限、認証・利用キー、有料契約を求める画面はユーザーに内容を示し、勝手に入力・申込しない。公式案内には初回1か月の利用キーなし優待が記載されているが、**新PCでの適用・残期間を旧PCの成功から断定しない**。
4. 64bit PowerShellで`New-Object -ComObject JVDTLab.JVLink`が成功するか確認する。これはCOM生成の確認で、通信成功ではない。失敗時は64bit版の導入状態、PowerShellのビット数、公式検証ツールの結果を確認する。
5. 必要に応じ、SDK同梱の**Data Lab.検証ツール**で少量の取得を試す。公式ページも、自作コードで取得できないときは先に検証ツールで確認するよう案内している。
6. コード側の通信確認は、公式に存在を確認した提供期間内の**単一レース**で、既存の[`collect-jvlink.ps1`](../scripts/collect-jvlink.ps1)を新しいローカル出力先に使う。過去の例示race keyが現在も提供されるとは限らない。まずCOM・公式ツール・小規模取得の順に進み、大量取得や本番runner起動はしない。`probe.json`の`complete`、JVInit/JVRTOpen/JVCloseの戻り値、件数を確認する。

旧PCの成功記録は[connection-check.md](connection-check.md)、初期導入と取得の注意点は[acquisition.md](acquisition.md)。同ページに当初の「未導入」の記述が残るため、**現在の状態は本書とprogress.mdの新しい記録を優先**する。

## 4. GitHubにないローカル資料を扱う

`.gitignore`により`data/`、`outputs/`、`work/`、`.venv/`、モデル、認証情報はGitHubに載らない。`git clone`だけでは旧PCの取得原本・実験出力・日別観測状態は再現されない。

- 過去の診断や参考実験を継続するなら、必要な`data/raw/`、`data/interim/`、`data/processed/`と対応する`outputs/`を旧PCから非公開の媒体でコピーする。原本・manifest・ハッシュはフォルダ構造ごと保ち、照合前に改変しない。
- 4日間の観測で最も重要なのは`data/pilot/`内の日別台帳・SQLite・イベント・予測である。**あるPCで`pilot init`やrunnerを始めた後は、その日を原則そのPCで完結**させる。稼働中にフォルダをコピーして別PCで続行しない。移動が不可避なら両PCのrunnerを停止し、原本のハッシュと状態を検査してから判断する。締切を過ぎた予測を後から作らない。
- 新PCへの移行時点でまだ正式台帳がなければ、その日の台帳は新PCで公式出馬表から作る。旧PCの予定表時刻をコピーしない。
- `.venv/`は新PCで再作成する。`work/`には一時スクリプトもあるが、正式な運用入口は追跡済みの`scripts/`と`src/`を使う。丸ごと移す必要性を先に点検する。
- USB等で運ぶ場合も生データ・認証情報を公開クラウドやGitHubへ置かない。コピー前後のファイル数・容量・必要なSHA256を照合する。

## 5. 4日間の観測を新PCへ切り替える

承認条件は2026-09-26/27、10-03/04のJRA平地全場、発走10分前締切、オッズ経過5分以内、保存は締切後1分以内。変更しない。詳細は[pilot-operations.md](pilot-operations.md)と[phase1-summary-operations.md](phase1-summary-operations.md)。

1. 9/26・27は正式出馬表公開後に全開催場・全レース・発走時刻を確認して日別台帳を固定する。10/3・4は翌週の正式発表を待つ。予定の競馬番組を正式台帳に流用しない。
2. 各開催日の前に`pilot_runner`の表示だけで予定と取得枠の競合を確認する。`--run`なしでは取得しない。
3. 当日の最初の対象レースより十分前にWindows時刻の同期、電源・スリープ、ネット接続、JV-Link、出力先空き容量を確認する。新PCでrunnerを**1つだけ**起動し、起動成功と`runner.jsonl`を確認する。9時・17時のCodex定期確認は厳密なレース締切の代わりにはならない。
4. 全レース終了後、runner停止・状態を確認し、`pilot_finish`で未評価の結果を取得・評価する。`RESULT_PENDING`と全対象の欠測を報告する。
5. 旧PCのこのタスクには定期確認`jra`が9時・17時に設定されている。**デスクトップ側の定期確認が作成・動作確認できてから旧PC側を停止**する。二つのCodexが同じ観測日を並行して操作しない。旧PC側が停止できない間は、どちらを実行機とするか明示し、もう一方では取得・runner起動をしない。

## 引き継ぎ完了の判定

- 新PCのリポジトリと設定が確認でき、Pythonテストが通る。
- JV-LinkのCOM生成と公式ツール／小規模取得が確認できる。取得できなければ原因・戻り値を記録し、観測可能と宣言しない。
- GitHubにない資料のうち必要なものの所在が確定し、コピーした資料は原本整合性を確認できる。
- 正式出馬表から作った日別台帳、時刻同期、runner予定と競合、単一起動、結果評価の担当PCが明確。
- デスクトップの定期確認を確認し、旧PCの定期確認と二重に実行しない。

この確認が済む前に旧PCのデータを削除しない。移行中に期限に間に合わない日があれば、欠測を正直に記録し、締切を後から延ばさない。
