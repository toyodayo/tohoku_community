import json

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Block, DMMessage, DMThread, Follow, PollVote, RecruitmentInterest, SNSPost, User
from utils import active_required, get_or_create_dm_thread

bp = Blueprint("sns", __name__, url_prefix="/sns")


@bp.route("/")
@login_required
def feed():
    followee_ids = [f.followee_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    followee_ids.append(current_user.id)  # 自分の投稿も表示する

    posts = (
        SNSPost.query.filter(SNSPost.author_id.in_(followee_ids))
        .order_by(SNSPost.created_at.desc())
        .all()
    )

    posts_data = []
    for p in posts:
        options = json.loads(p.poll_options) if p.post_type == "poll" and p.poll_options else None
        vote_counts, my_vote = None, None
        interest_count, i_am_interested = None, False

        if options is not None:
            votes = PollVote.query.filter_by(post_id=p.id).all()
            vote_counts = [0] * len(options)
            for v in votes:
                if v.option_index < len(vote_counts):
                    vote_counts[v.option_index] += 1
                if v.user_id == current_user.id:
                    my_vote = v.option_index

        if p.post_type == "recruitment":
            interest_count = RecruitmentInterest.query.filter_by(post_id=p.id).count()
            i_am_interested = (
                RecruitmentInterest.query.filter_by(post_id=p.id, user_id=current_user.id).first()
                is not None
            )

        posts_data.append(dict(
            post=p, options=options, vote_counts=vote_counts, my_vote=my_vote,
            interest_count=interest_count, i_am_interested=i_am_interested,
        ))

    return render_template("sns_feed.html", posts_data=posts_data)


@bp.route("/posts/new", methods=["POST"])
@login_required
@active_required
def new_post():
    content = request.form.get("content", "").strip()
    post_type = request.form.get("post_type", "normal")
    options_raw = request.form.get("options", "")

    if not content:
        flash("内容を入力してください。", "danger")
        return redirect(url_for("sns.feed"))

    poll_options = None
    if post_type == "poll":
        options = [o.strip() for o in options_raw.split(",") if o.strip()]
        if len(options) < 2:
            flash("アンケートには2つ以上の選択肢をカンマ区切りで入力してください。", "danger")
            return redirect(url_for("sns.feed"))
        poll_options = json.dumps(options, ensure_ascii=False)

    db.session.add(SNSPost(
        author_id=current_user.id, content=content,
        post_type=post_type, poll_options=poll_options,
    ))
    db.session.commit()
    return redirect(url_for("sns.feed"))


@bp.route("/posts/<int:post_id>/vote", methods=["POST"])
@login_required
@active_required
def vote(post_id):
    post = SNSPost.query.get_or_404(post_id)
    option_index = int(request.form.get("option_index", -1))
    existing = PollVote.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if existing:
        existing.option_index = option_index
    else:
        db.session.add(PollVote(post_id=post.id, user_id=current_user.id, option_index=option_index))
    db.session.commit()
    return redirect(url_for("sns.feed"))


@bp.route("/posts/<int:post_id>/interest", methods=["POST"])
@login_required
@active_required
def toggle_interest(post_id):
    SNSPost.query.get_or_404(post_id)
    existing = RecruitmentInterest.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(RecruitmentInterest(post_id=post_id, user_id=current_user.id))
    db.session.commit()
    return redirect(url_for("sns.feed"))


@bp.route("/users/<int:user_id>")
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    posts = SNSPost.query.filter_by(author_id=user.id).order_by(SNSPost.created_at.desc()).all()
    is_following = Follow.query.filter_by(follower_id=current_user.id, followee_id=user.id).first() is not None
    is_blocked = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user.id).first() is not None

    # フォロー・フォロワーは非公開仕様のため、本人が見る場合のみ件数を表示する
    follower_count = follow_count = None
    if user.id == current_user.id:
        follower_count = Follow.query.filter_by(followee_id=user.id).count()
        follow_count = Follow.query.filter_by(follower_id=user.id).count()

    return render_template(
        "sns_profile.html", profile_user=user, posts=posts,
        is_following=is_following, is_blocked=is_blocked,
        follower_count=follower_count, follow_count=follow_count,
    )


@bp.route("/users/<int:user_id>/follow", methods=["POST"])
@login_required
@active_required
def follow(user_id):
    if user_id != current_user.id and not Follow.query.filter_by(
        follower_id=current_user.id, followee_id=user_id
    ).first():
        db.session.add(Follow(follower_id=current_user.id, followee_id=user_id))
        db.session.commit()
    return redirect(url_for("sns.profile", user_id=user_id))


@bp.route("/users/<int:user_id>/unfollow", methods=["POST"])
@login_required
@active_required
def unfollow(user_id):
    f = Follow.query.filter_by(follower_id=current_user.id, followee_id=user_id).first()
    if f:
        db.session.delete(f)
        db.session.commit()
    return redirect(url_for("sns.profile", user_id=user_id))


@bp.route("/users/<int:user_id>/block", methods=["POST"])
@login_required
@active_required
def block(user_id):
    if user_id != current_user.id and not Block.query.filter_by(
        blocker_id=current_user.id, blocked_id=user_id
    ).first():
        db.session.add(Block(blocker_id=current_user.id, blocked_id=user_id))
        db.session.commit()
    flash("ブロックしました。", "success")
    return redirect(url_for("sns.profile", user_id=user_id))


@bp.route("/users/<int:user_id>/unblock", methods=["POST"])
@login_required
@active_required
def unblock(user_id):
    b = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
    if b:
        db.session.delete(b)
        db.session.commit()
    return redirect(url_for("sns.profile", user_id=user_id))


def _blocked_either_way(user_a_id, user_b_id) -> bool:
    return Block.query.filter(
        db.or_(
            db.and_(Block.blocker_id == user_a_id, Block.blocked_id == user_b_id),
            db.and_(Block.blocker_id == user_b_id, Block.blocked_id == user_a_id),
        )
    ).first() is not None


@bp.route("/dm")
@login_required
def dm_inbox():
    threads = DMThread.query.filter(
        db.or_(DMThread.user_a_id == current_user.id, DMThread.user_b_id == current_user.id)
    ).order_by(DMThread.created_at.desc()).all()

    accepted, requests_in, requests_out = [], [], []
    for t in threads:
        other = User.query.get(t.other(current_user.id))
        if t.status == "accepted":
            accepted.append((t, other))
        elif t.status == "pending":
            (requests_out if t.requested_by_id == current_user.id else requests_in).append((t, other))

    return render_template(
        "dm_inbox.html", accepted=accepted, requests_in=requests_in, requests_out=requests_out
    )


@bp.route("/dm/start/<int:user_id>", methods=["POST"])
@login_required
@active_required
def dm_start(user_id):
    if user_id == current_user.id:
        flash("自分自身にはDMを送れません。", "warning")
        return redirect(url_for("sns.feed"))
    if _blocked_either_way(current_user.id, user_id):
        flash("この相手とはやり取りできません。", "danger")
        return redirect(url_for("sns.feed"))

    content = request.form.get("content", "").strip()
    if not content:
        flash("メッセージを入力してください。", "danger")
        return redirect(url_for("sns.profile", user_id=user_id))

    thread = get_or_create_dm_thread(current_user.id, user_id, requested_by_id=current_user.id)
    db.session.add(DMMessage(thread_id=thread.id, sender_id=current_user.id, content=content))
    db.session.commit()
    flash("メッセージリクエストを送信しました。相手が承認すると継続してやり取りできます。", "success")
    return redirect(url_for("sns.dm_inbox"))


@bp.route("/dm/<int:thread_id>")
@login_required
def dm_thread(thread_id):
    thread = DMThread.query.get_or_404(thread_id)
    if current_user.id not in (thread.user_a_id, thread.user_b_id):
        flash("このDMにアクセスする権限がありません。", "danger")
        return redirect(url_for("sns.dm_inbox"))

    other = User.query.get(thread.other(current_user.id))
    messages = DMMessage.query.filter_by(thread_id=thread.id).order_by(DMMessage.created_at.asc()).all()
    is_blocked = _blocked_either_way(current_user.id, other.id)
    return render_template("dm_thread.html", thread=thread, other=other, messages=messages, is_blocked=is_blocked)


@bp.route("/dm/<int:thread_id>/accept", methods=["POST"])
@login_required
@active_required
def dm_accept(thread_id):
    thread = DMThread.query.get_or_404(thread_id)
    if current_user.id in (thread.user_a_id, thread.user_b_id) and thread.requested_by_id != current_user.id:
        thread.status = "accepted"
        db.session.commit()
        flash("メッセージリクエストを承認しました。", "success")
    return redirect(url_for("sns.dm_thread", thread_id=thread.id))


@bp.route("/dm/<int:thread_id>/decline", methods=["POST"])
@login_required
@active_required
def dm_decline(thread_id):
    thread = DMThread.query.get_or_404(thread_id)
    if current_user.id in (thread.user_a_id, thread.user_b_id) and thread.requested_by_id != current_user.id:
        thread.status = "declined"
        db.session.commit()
    return redirect(url_for("sns.dm_inbox"))


@bp.route("/dm/<int:thread_id>/messages", methods=["POST"])
@login_required
@active_required
def dm_send(thread_id):
    thread = DMThread.query.get_or_404(thread_id)
    if current_user.id not in (thread.user_a_id, thread.user_b_id):
        flash("権限がありません。", "danger")
        return redirect(url_for("sns.dm_inbox"))
    if thread.status != "accepted":
        flash("相手が承認するまで継続してやり取りできません。", "warning")
        return redirect(url_for("sns.dm_thread", thread_id=thread.id))
    if _blocked_either_way(thread.user_a_id, thread.user_b_id):
        flash("この相手とはやり取りできません。", "danger")
        return redirect(url_for("sns.dm_thread", thread_id=thread.id))

    content = request.form.get("content", "").strip()
    if content:
        db.session.add(DMMessage(thread_id=thread.id, sender_id=current_user.id, content=content))
        db.session.commit()
    return redirect(url_for("sns.dm_thread", thread_id=thread.id))
