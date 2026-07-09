import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me-in-production")

    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(basedir, "tohoku_community.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 大学のGoogle Workspaceドメイン。
    # 本番では Google OAuth のトークンに含まれる `hd` (hosted domain) クレームを
    # このドメインと突き合わせて検証すること（README参照）。
    ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "tohoku.ac.jp")
