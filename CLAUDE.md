# tech-news-bot：公開版の作業指示

AI関連ニュースの取得・要約・Discord通知と週次Markdown下書きの実装例。

## 作業方針

- 共通の公開ルールはAGENTS.mdを参照する。
- main.pyを実行すると外部通信が起き、Webhook設定済みなら実配信される。確認はモックテストから始める。
- 公開版のworkflowは手動実行のみ。個人運用のSecrets・配信先・既読データをコピーしない。
- 公開版で「現在稼働中」「常に無料」と断定しない。元の運用実績と公開版の状態を区別する。
- テストは python -m pytest tests/ -v。生成済み下書きや画像は機械検査だけで公開可としない。
- READMEは実装・config.json・workflowを照合し、ソース数や環境変数名を推測しない。
- Indie Hackersは現在のconfig.jsonにない。コードがあるだけで有効な情報源として説明しない。
- weekly_note.ymlは下書きを確認用artifactとして保存する。生成物の自動コミット・pushを行わない。
- 既存リポジトリを更新する場合は、未コミット変更を確認してからfetchし、履歴を無断でrebaseしない。
