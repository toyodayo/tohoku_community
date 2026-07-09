# 東北大学community

東北大学の学生同士が「匿名チャット」と「実名SNS」を安全にシームレスに行き来しながら、
起業・研究・イベント企画などの仲間を見つけるための学内限定プラットフォームです。
Flask + SQLite で実装したフルスタックのプロトタイプです。

## セットアップ

```bash
cd tohoku_community
pip install -r requirements.txt
python app.py
```

`http://localhost:5000` にアクセスすると、初回起動時に SQLite データベース
(`tohoku_community.db`)が自動的に作成されます。

### デモ用ログイン

実際の Google OAuth は組み込んでいません（下記「本番移行時の注意点」参照）。
デモでは、ログイン画面で `@tohoku.ac.jp` で終わるメールアドレスと氏名を入力すると、
その場でアカウントが作成されてログインできます。同じメールアドレスで再度ログインすれば
同じアカウントとして扱われます。

管理者アカウント（異議申し立て審査用）は起動時に自動生成されます。

```
admin@tohoku.ac.jp  （氏名欄は空でOK、初回登録済みのため）
```

`ALLOWED_EMAIL_DOMAIN` 環境変数でドメインを変更できます。

## 実装した機能と仕様書との対応

| # | 仕様書の機能 | 実装箇所 |
|---|---|---|
| ① | ユーザー認証（大学Googleアカウント限定 + OB/OG連携） | `auth.py` `/login`, `/account/link-alumni` |
| ② | 匿名チャットツールモード（トレンド表示・日替わりID・通報/BAN・異議申し立て） | `anonymous.py`, `utils.py` |
| ③ | 実名SNSモード（投稿・アンケート・募集・非公開フォロー・DMリクエスト・ブロック） | `sns.py` |
| ④ | モード間連携（エクスポート）機能 | `anonymous.py: connect()`, `utils.py: try_match_link_request()` |

### ②匿名チャットのロジック詳細

- **トレンド表示**: `utils.get_ranked_threads()` が直近1時間の投稿数でスレッドを並べ替えます。
- **日替わり匿名ID**: `utils.generate_anon_id(user_id, date)` が `SHA-256(salt:user_id:date)` から
  ID を導出します。日付が変わるとIDも変わりますが、実装上は毎日0時に自動的に切り替わります
  （テーブルに保存せず都度計算するため、深夜バッチ処理は不要です）。
- **通報・BAN**: `Report` テーブルに通報を記録し、`utils._apply_penalty_if_needed()` が
  「当日に3人の異なるユーザーから通報 → 3日間利用停止」「累計10人から通報 → 永久BAN」を判定します。
- **異議申し立て**: `/account/appeal` から申し立てでき、`/admin/appeals` で管理者が承認/却下できます。
  承認されると `ban_until` と `is_permanently_banned` がリセットされます。

### ④モード間連携（エクスポート）のロジック詳細

匿名チャットの投稿画面にある「実名で繋がりたい」ボタンは、**双方が押した時点で初めてマッチ**します
（`LinkRequest` テーブルで相互リクエストの有無を確認）。マッチが成立すると、実名SNSモードの
DM（承認済み状態）が自動的に開設され、`DM`メニューの「トーク」一覧に
「匿名チャットから連携」のバッジ付きで表示されます。

## プロジェクト構成

```
tohoku_community/
├── app.py            # アプリケーションファクトリ、DB初期化
├── config.py         # 設定（DB接続先、許可ドメインなど）
├── extensions.py     # SQLAlchemy / Flask-Login のインスタンス
├── models.py          # 全テーブル定義
├── utils.py           # 匿名ID生成・スレッドランキング・通報判定・マッチングのロジック
├── auth.py            # ログイン/ログアウト、OB/OG連携、異議申し立て
├── anonymous.py        # 匿名チャットモード（掲示板・スレッド・通報・連携リクエスト）
├── sns.py              # 実名SNSモード（投稿・フォロー・DM・ブロック）
├── admin.py            # 運営向け：異議申し立て審査
├── templates/          # Jinja2テンプレート（Bootstrap 5使用）
├── static/style.css    # 東北大学カラー（パープル）を基調としたスタイル
└── requirements.txt
```

## 本番移行時の注意点

- **Google OAuth**: 現状はメールアドレスをフォーム入力する簡易認証です。本番では
  [Authlib](https://docs.authlib.org/) 等で Google の OpenID Connect を実装し、
  IDトークンの `hd`（hosted domain）クレームが大学の Google Workspace ドメインと
  一致することを検証してください。`auth.py` の `login()` 内にその旨のコメントを記載しています。
- **匿名ID生成のsalt**: `utils.py` の `ANON_SALT` は本番では環境変数化し、
  ソースコードに含めないでください。
- **スケール**: SQLite は開発・デモ用です。本番運用では PostgreSQL 等への切り替えを推奨します。
- **通報の悪用対策**: 現状は「異なる3人・10人からの通報数」のみで判定しています。
  実運用では通報内容の目視確認や、組織的な通報（多重アカウント等）への対策も検討してください。
