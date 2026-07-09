from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from models import Appeal, User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("anonymous.board"))

    domain = current_app.config["ALLOWED_EMAIL_DOMAIN"]

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        real_name = request.form.get("real_name", "").strip()

        # --- 本来はここでGoogle OAuth (Authlibなど) のIDトークンを検証し、
        #     `hd` (hosted domain) クレームが大学のGoogle Workspaceドメインと
        #     一致するかを確認する。デモ版のためフォーム入力で代替している。 ---

        user = User.query.filter_by(university_email=email).first()
        if not user:
            # 大学アカウントが失効したOB・OGは、連携済みの個人メールでログインできる
            user = User.query.filter_by(alumni_email=email).first()

        if not user:
            if not email.endswith("@" + domain):
                flash(f"大学のメールアドレス（@{domain}）でログインしてください。", "danger")
                return redirect(url_for("auth.login"))
            if not real_name:
                flash("初回登録には氏名の入力が必要です。", "danger")
                return redirect(url_for("auth.login"))
            user = User(university_email=email, real_name=real_name, display_name=real_name)
            db.session.add(user)
            db.session.commit()

        if user.is_permanently_banned:
            flash("このアカウントは永久停止されています。ログイン後、異議申し立てが行えます。", "danger")
        elif user.is_suspended:
            flash(f"このアカウントは {user.ban_until.strftime('%Y-%m-%d %H:%M')} まで利用停止中です。", "warning")

        login_user(user)
        return redirect(url_for("anonymous.board"))

    return render_template("login.html", domain=domain)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/account/link-alumni", methods=["GET", "POST"])
@login_required
def link_alumni():
    """卒業後も使い続けられるよう、個人メールアドレスを紐付ける機能。"""
    if request.method == "POST":
        alumni_email = request.form.get("alumni_email", "").strip().lower()
        if not alumni_email:
            flash("メールアドレスを入力してください。", "danger")
        elif User.query.filter(User.alumni_email == alumni_email, User.id != current_user.id).first():
            flash("そのメールアドレスは既に別のアカウントに連携されています。", "danger")
        else:
            current_user.alumni_email = alumni_email
            db.session.commit()
            flash("卒業後も使えるメールアドレスを連携しました。", "success")
        return redirect(url_for("auth.link_alumni"))

    return render_template("link_alumni.html")


@bp.route("/account/appeal", methods=["GET", "POST"])
@login_required
def appeal():
    """通報による利用制限に対する異議申し立て。"""
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            db.session.add(Appeal(user_id=current_user.id, content=content))
            db.session.commit()
            flash("異議申し立てを受け付けました。運営が確認します。", "success")
        return redirect(url_for("auth.appeal"))

    my_appeals = Appeal.query.filter_by(user_id=current_user.id).order_by(Appeal.created_at.desc()).all()
    return render_template("appeal.html", appeals=my_appeals)
