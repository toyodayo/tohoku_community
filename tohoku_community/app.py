from flask import Flask, redirect, url_for

from config import Config
from extensions import db, login_manager
from models import User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from admin import bp as admin_bp
    from anonymous import bp as anonymous_bp
    from auth import bp as auth_bp
    from sns import bp as sns_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(anonymous_bp)
    app.register_blueprint(sns_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("anonymous.board"))

    with app.app_context():
        db.create_all()
        _ensure_seed_admin()

    return app


def _ensure_seed_admin():
    """デモ用の管理者アカウントを1つ用意する（異議申し立て審査の確認用）。"""
    admin_email = "admin@" + Config.ALLOWED_EMAIL_DOMAIN
    if not User.query.filter_by(university_email=admin_email).first():
        db.session.add(User(
            university_email=admin_email, real_name="運営管理者",
            display_name="運営管理者", is_admin=True,
        ))
        db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
