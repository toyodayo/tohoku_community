from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Post, Thread
from utils import active_required, get_ranked_threads, register_report, try_match_link_request

bp = Blueprint("anonymous", __name__, url_prefix="/anonymous")


@bp.route("/")
@login_required
def board():
    ranked = get_ranked_threads()
    return render_template("anonymous_board.html", ranked=ranked)


@bp.route("/threads/new", methods=["POST"])
@login_required
@active_required
def create_thread():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title or not content:
        flash("タイトルと本文を入力してください。", "danger")
        return redirect(url_for("anonymous.board"))

    thread = Thread(title=title, creator_id=current_user.id)
    db.session.add(thread)
    db.session.flush()  # thread.id を確定させる

    post = Post(thread_id=thread.id, author_id=current_user.id, content=content)
    db.session.add(post)
    db.session.commit()
    return redirect(url_for("anonymous.thread_detail", thread_id=thread.id))


@bp.route("/threads/<int:thread_id>")
@login_required
def thread_detail(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    posts = thread.posts.order_by(Post.created_at.asc()).all()
    return render_template("anonymous_thread.html", thread=thread, posts=posts)


@bp.route("/threads/<int:thread_id>/posts", methods=["POST"])
@login_required
@active_required
def reply(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    content = request.form.get("content", "").strip()
    if content:
        db.session.add(Post(thread_id=thread.id, author_id=current_user.id, content=content))
        db.session.commit()
    return redirect(url_for("anonymous.thread_detail", thread_id=thread.id))


@bp.route("/posts/<int:post_id>/report", methods=["POST"])
@login_required
@active_required
def report_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id == current_user.id:
        flash("自分の投稿は通報できません。", "warning")
        return redirect(url_for("anonymous.thread_detail", thread_id=post.thread_id))

    reason = request.form.get("reason", "不適切な投稿")
    _, error = register_report(post.author, current_user, "post", post.id, reason)
    if error:
        flash(error, "warning")
    else:
        flash("通報を受け付けました。", "success")
    return redirect(url_for("anonymous.thread_detail", thread_id=post.thread_id))


@bp.route("/posts/<int:post_id>/connect", methods=["POST"])
@login_required
@active_required
def connect(post_id):
    """『実名で繋がりたい』ボタン。双方が押すとマッチしDMが開設される。"""
    post = Post.query.get_or_404(post_id)
    if post.author_id == current_user.id:
        flash("自分自身とは繋がれません。", "warning")
        return redirect(url_for("anonymous.thread_detail", thread_id=post.thread_id))

    _, matched = try_match_link_request(post.thread_id, current_user.id, post.author_id)
    if matched:
        flash("お互いに承認されたため、実名SNSでのDMが開設されました。「DM」から確認できます。", "success")
    else:
        flash("『実名で繋がりたい』を送りました。相手も同じ操作をすると繋がります。", "info")
    return redirect(url_for("anonymous.thread_detail", thread_id=post.thread_id))
