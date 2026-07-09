from datetime import datetime

from flask_login import UserMixin

from extensions import db


class User(UserMixin, db.Model):
    """東北大学のGoogleアカウントで認証されるユーザー。

    本デモでは実際のOAuthの代わりにメールアドレス入力で代替しているが、
    実運用では Authlib 等で Google の OpenID Connect を利用し、
    `hd`(hosted domain) クレームが大学ドメインと一致することを検証する。
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    university_email = db.Column(db.String(255), unique=True, nullable=True)
    # OB・OG が卒業後（大学アカウント失効後）も使い続けるための連携アカウント
    alumni_email = db.Column(db.String(255), unique=True, nullable=True)

    real_name = db.Column(db.String(120), nullable=False)
    # 実名SNS上の表示名。基本は real_name と同じ値で初期化する。
    display_name = db.Column(db.String(120), nullable=False)

    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # --- 通報によるモデレーション ---
    ban_until = db.Column(db.DateTime, nullable=True)          # 一時利用停止の期限
    is_permanently_banned = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_suspended(self) -> bool:
        return bool(self.ban_until and self.ban_until > datetime.utcnow())

    @property
    def is_blocked_from_service(self) -> bool:
        return self.is_permanently_banned or self.is_suspended

    def __repr__(self):
        return f"<User id={self.id} {self.display_name}>"


class Thread(db.Model):
    """匿名チャットモードのスレッド（掲示板のトピック）。"""

    __tablename__ = "threads"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship(
        "Post", backref="thread", lazy="dynamic",
        order_by="Post.created_at", cascade="all, delete-orphan",
    )


class Post(db.Model):
    """匿名チャットモード内の個々の書き込み。"""

    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    @property
    def anon_id(self) -> str:
        """投稿日時点での日替わり匿名IDを返す（毎日24時に更新される）。"""
        from utils import generate_anon_id  # 循環import回避のため遅延import
        return generate_anon_id(self.author_id, self.created_at.date())


class Report(db.Model):
    """匿名投稿の通報記録。1ユーザー・1対象につき1回まで。"""

    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)   # 'post'
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("reporter_id", "target_type", "target_id", name="uix_report_once"),
    )


class Appeal(db.Model):
    """利用停止・BANに対する異議申し立て。"""

    __tablename__ = "appeals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / approved / rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


class SNSPost(db.Model):
    """実名SNSモードの投稿（通常投稿 / アンケート / メンバー募集）。"""

    __tablename__ = "sns_posts"

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(20), default="normal")  # normal / poll / recruitment
    poll_options = db.Column(db.Text, nullable=True)  # JSON文字列
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")


class PollVote(db.Model):
    __tablename__ = "poll_votes"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("sns_posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    option_index = db.Column(db.Integer, nullable=False)

    __table_args__ = (db.UniqueConstraint("post_id", "user_id", name="uix_vote_once"),)


class RecruitmentInterest(db.Model):
    """メンバー募集スレッドへの「興味あり」表明。"""

    __tablename__ = "recruitment_interests"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("sns_posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("post_id", "user_id", name="uix_interest_once"),)


class Follow(db.Model):
    """フォロー関係。他ユーザーからは非公開（本人のみ件数を確認できる）。"""

    __tablename__ = "follows"

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    followee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("follower_id", "followee_id", name="uix_follow_once"),)


class Block(db.Model):
    __tablename__ = "blocks"

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("blocker_id", "blocked_id", name="uix_block_once"),)


class DMThread(db.Model):
    """実名SNSモードのDMスレッド。初回はメッセージリクエストとしてpending。"""

    __tablename__ = "dm_threads"

    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user_b_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / accepted / declined
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_from_link = db.Column(db.Boolean, default=False)  # 匿名モードからの連携経由か
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_a_id", "user_b_id", name="uix_dm_pair"),)

    def other(self, user_id: int) -> int:
        return self.user_b_id if self.user_a_id == user_id else self.user_a_id


class DMMessage(db.Model):
    __tablename__ = "dm_messages"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("dm_threads.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LinkRequest(db.Model):
    """匿名チャット上で意気投合したユーザーが実名SNSへ移行するための
    相互承認（マッチング）リクエスト。双方が『実名で繋がりたい』を選ぶと
    自動的にマッチし、実名SNSモードのDMが開設される。
    """

    __tablename__ = "link_requests"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / matched
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("thread_id", "from_user_id", "to_user_id", name="uix_link_once"),
    )
