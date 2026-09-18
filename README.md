# tech-news-bot

AI・LLM関連の情報を収集し、新着を日本語で要約してDiscordへ通知するPython製Botです。個人利用していた仕組みをポートフォリオ用に整理しています。

収集先・通知先・要約を設定で分離し、既読IDを保存して重複通知を抑えます。週次のMarkdown下書き生成も含みます。

「通知が多すぎて読めない」「英語のまま・要約なしの記事が混ざる」という運用上の課題から、
**1回最大5件・情報源ごと最大2件**に選別し、日本語の見出しと短い要約をまとめて送る構成へ改善しました。
特徴は、URLによる横断的な重複排除と、配信成功を確認してから既読を確定する再試行可能な配送処理です。

## まず見るデモ

[通知のサンプルと確認ポイント](docs/DEMO.md) をブラウザで読めます。
手元ではセットアップ後に `python main.py --demo` を実行してください。
架空ニュースと手書き要約だけを使い、APIキー・外部通信・Discordアカウントは不要です。
常設のWeb画面や公開Discordへの案内はありません。

## 構成

```mermaid
flowchart TD
    S[情報源] --> C[取得・整形]
    C --> D[既読IDとの比較]
    D --> G[日本語要約]
    G --> N[Discord通知]
    N --> P[既読状態の保存]
    C --> W[週次Markdown下書き]
```

| ファイル | 役割 |
|---|---|
| `main.py` | 収集・差分抽出・要約・通知・既読状態の保存 |
| `bot/delivery.py` | 重複排除、通知件数制限、日本語品質確認、送信後の状態確定 |
| `config.json` | 情報源・検索条件・要約設定 |
| `bot/github_trending.py` | GitHub Trendingの取得 |
| `bot/reddit.py` | RedditのRSS取得 |
| `bot/generate_note_draft.py` | 週次Markdown下書き生成 |
| `seen.json`（実行時生成） | 通知済みID。Git管理外で、初回はファイル不要 |
| `tests/` | 取得・整形・下書き生成の単体テスト |

## 現在の設定対象

| 情報源 | 設定 |
|---|---|
| arXiv | cs.AI / cs.CL、キーワードで絞り込み |
| Hacker News | スコア300以上 |
| TechCrunch・Product Hunt・Lobsters | RSS |
| Anthropic・OpenAI | config.jsonに指定したフィード。Anthropicは第三者提供の非公式フィード |
| GitHub Trending | 全言語とPython |
| Reddit | AI関連コミュニティと個人開発関連コミュニティ |

Indie Hackersの取得処理はコードに残っていますが、現在の `config.json` には設定がありません。稼働中の情報源として扱いません。外部フィードの到達性は変わるため、実行時の確認が必要です。

## セットアップ

Python 3.12、PowerShellの例です。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

| 環境変数 | 用途 |
|---|---|
| `GEMINI_API_KEY` | 日本語要約・翻訳 |
| `DISCORD_WEBHOOK_DIGEST` | 選別したニュースの共通通知先 |
| `DISCORD_WEBHOOK_TECH` | DIGEST未設定・空の場合の通知先 |

秘密値はローカルの環境変数または実行先のSecretsに設定します。コード・README・スクリーンショットには含めません。
空の設定例は [.env.example](.env.example) を参照してください。`.env` の自動読込は行わないため、PowerShellの `$env:変数名 = '値'` などでプロセスへ設定します。

```powershell
# 実行すると外部通信が発生します。Webhook設定済みなら実際に通知します。
.\.venv\Scripts\python.exe main.py

# 取得件数・保留数を表示。保存済みの要約があれば本文もプレビューします。
# 要約API・Discord通知・状態ファイル更新は行いません。
.\.venv\Scripts\python.exe main.py --dry-run

# 外部通信なしの自作サンプル。実ニュースや実APIの結果は含みません。
.\.venv\Scripts\python.exe main.py --demo

# 週次下書き。output/にファイルを生成します。
.\.venv\Scripts\python.exe -m bot.generate_note_draft
```

## テスト

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

単体テストの対象は下書き生成・Trending・Redditに加え、通知件数・重複排除・配送失敗時の再試行です。全情報源の現行仕様やDiscordへの実配信を保証するものではありません。

通知は `config.json` の `notification.max_items`（全体上限）と
`notification.max_per_source`（情報源ごとの上限）で絞ります。同じ正規化URLは
情報源をまたいで一件にまとめ、要約のタイトル翻訳または本文要約が日本語にならない項目は
送信せず保留します。取得した候補と要約は先に `delivery_state.json` へ保存し、
送信成功後にだけ通知済みへ移します。要約失敗・配信失敗は、次のフィードから消えても保存済み候補から再試行できます。
取得そのものに失敗した項目は、情報源が次回返す範囲で再取得します。
同じ優先度では要約失敗の少ない候補を先に選び、失敗した記事だけで通知枠が埋まることを防ぎます。
保留記事は削除せず残しますが、新規候補が多い間は再試行が後になる場合があります。
配送状態に既読記録があればそれを使うため、副本の `seen.json` が欠落・破損しても復旧できます。

## 公開版と個人運用

- 公開版の [収集workflow](.github/workflows/watch.yml) と [週次workflow](.github/workflows/weekly_note.yml) は手動実行のみです。コピーしただけでは定期実行されません。
- 収集workflowは `--dry-run` で取得とプレビューだけを実行します。LLM・DiscordのSecretsは渡さず、配信や既読コミットはしません。
- 実配信には、同じ作業ディレクトリに `delivery_state.json` と `seen.json` を保持して一度に1プロセスだけ実行してください。実行ごとに消えるCI環境では保留状態を引き継げないため、実配信には使いません。
- 週次workflowは下書きを確認用artifact（7日間）として保存し、自動コミット・pushしません。公開版には既読履歴がないため、生成されるのは空のテンプレートです。
- 下書き生成は保存済みIDの累積一覧です。IDに取得日時がないため「直近7日」の抽出は未対応です。配送状態の本文・日付を使った週次記事への統合は今後の課題です。
- API・GitHub Actionsの利用料は契約と利用量に依存します。無条件に無料で動くサービスとはしていません。

## 工夫と制約

- ソース定義を `config.json` に集約し、情報源を切り替えやすくしています。
- APIやフィードの失敗を記録し、可能な範囲で他の情報源の処理を続けます。
- 既読管理にファイルを使い、別のデータベースを必要としない構成です。
- Webhookの応答が失われた場合や送信直後・状態保存前に終了した場合は、再試行で重複通知する可能性があります。
- 日本語文字の有無を検査していますが、内容の正確さや自然な翻訳の保証ではありません。実APIでの要約品質は未評価です。
- RSS・スクレイピング先は内容や仕様が変わり得ます。失敗時のログ確認が必要です。
- `bot/src/` はCloudflare Workers上の別コンポーネントです。上記Pythonパイプラインの起動には不要です。

Windows / Python 3.14で39件の回帰テストとオフラインデモを確認しています（2026-09-18）。CIのPython 3.12は変更後未実行です。実フィードの現時点の到達性、
Geminiの実生成品質、実Discord配信、Workersのデプロイ・稼働は今回の確認に含みません。
Python依存はバージョン固定していないため、新規環境での再検証が必要です。

## AIの活用

ニュースの日本語要約・翻訳にGemini APIを使用します。要約は誤り得るため、通知には一次情報へ戻れるリンクを残します。
