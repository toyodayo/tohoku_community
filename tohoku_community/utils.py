"""アプリ横断で使う共通ロジック。

- generate_anon_id: 匿名チャットモードの日替わりID生成
- get_ranked_threads: 直近1時間の書き込み数によるスレッド表示順
- register_report / _apply_penalty_if_needed: 通報の集計とBAN判定
- try_match_link_request: 匿名⇔実名モードの相互承認（マッチング）
- active_required: 利用停止中のユーザーの書き込み系操作をブロックするデコレータ
"""
import hashlib
from datetime import date as date_cls
from datetime import datetime, timedelta
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import desc, func

from extensions import db
from models import DMThread, LinkRequest, Post, Report, Thread, User

# 本番では環境変数などで管理する秘密のsalt。これを知らない限り
# 「今日のIDから元のユーザーを逆算する」ことはできない設計になっている。
ANON_SALT = "change-this-secret-salt-in-production"


def generate_anon_id(user_id: int, for_date: date_cls) -> str:
    """同一ユーザーでも日付が変われば別のIDになる、日替わり匿名ID。

    同じ日の投稿は同じIDで表示されるため「昨日の名無しさんとの会話の続き」
    という体験は保てつつ、日をまたぐと第三者には追跡できなくなる。
    """
    raw = f"{ANON_SALT}:{user_id}:{for_date.isoformat()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"名無し#{digest[:6].upper()}"


def get_ranked_threads():
    """直近1時間の書き込み数が多い順にスレッドを並べる。

    書き込みが少ないスレッドも最終投稿日時順でリストの下に表示されるため、
    「新着だが誰も反応していない」スレッドが消えてしまうことはない。
    """
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

    recent_counts = (
        db.session.query(Post.thread_id, func.count(Post.id).label("recent_count"))
        .filter(Post.created_at >= one_hour_ago)
        .group_by(Post.thread_id)
        .subquery()
    )

    rows = (
        db.session.query(Thread, func.coalesce(recent_counts.c.recent_count, 0).label("recent_count"))
        .outerjoin(recent_counts, Thread.id == recent_counts.c.thread_id)
        .order_by(desc("recent_count"), desc(Thread.created_at))
        .all()
    )
    return rows


def register_report(target_user: User, reporter: User, target_type: str, target_id: int, reason: str = ""):
    """通報を1件登録する。同じ人が同じ投稿を二重に通報することはできない。"""
    existing = Report.query.filter_by(
        reporter_id=reporter.id, target_type=target_type, target_id=target_id
    ).first()
    if existing:
        return None, "この投稿はすでに通報済みです。"

    report = Report(
        target_user_id=target_user.id,
        reporter_id=reporter.id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
    )
    db.session.add(report)
    db.session.commit()

    _apply_penalty_if_needed(target_user)
    return report, None


def _apply_penalty_if_needed(target_user: User) -> None:
    """仕様: 1日に3人から通報→3日間利用停止 / 累計10人から通報→永久BAN。"""
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())

    reporters_today = (
        db.session.query(Report.reporter_id)
        .filter(Report.target_user_id == target_user.id, Report.created_at >= today_start)
        .distinct()
        .count()
    )
    reporters_total = (
        db.session.query(Report.reporter_id)
        .filter(Report.target_user_id == target_user.id)
        .distinct()
        .count()
    )

    if reporters_total >= 10:
        target_user.is_permanently_banned = True
    elif reporters_today >= 3 and not target_user.is_permanently_banned:
        target_user.ban_until = datetime.utcnow() + timedelta(days=3)

    db.session.commit()


def get_or_create_dm_thread(user_a_id: int, user_b_id: int, requested_by_id: int,
                             status: str = "pending", from_link: bool = False) -> DMThread:
    """2人組ごとに1つのDMスレッドしか作らない（順序を正規化してユニーク制約と一致させる）。"""
    a, b = sorted((user_a_id, user_b_id))
    thread = DMThread.query.filter_by(user_a_id=a, user_b_id=b).first()
    if thread:
        return thread
    thread = DMThread(
        user_a_id=a, user_b_id=b, status=status,
        requested_by_id=requested_by_id, created_from_link=from_link,
    )
    db.session.add(thread)
    db.session.commit()
    return thread


def try_match_link_request(thread_id: int, from_user_id: int, to_user_id: int):
    """匿名チャット→実名SNSへの『相互承認』ロジック。

    Aが「実名で繋がりたい」を押した時点ではまだ相手には何も起きない。
    Bも同じ相手に対して同じ操作をした時点で初めてマッチが成立し、
    実名SNSモードのDM（承認済み状態）が自動的に開設される。
    """
    existing = LinkRequest.query.filter_by(
        thread_id=thread_id, from_user_id=from_user_id, to_user_id=to_user_id
    ).first()
    if existing:
        return existing, False  # 既にリクエスト済み。新規マッチではない。

    new_request = LinkRequest(thread_id=thread_id, from_user_id=from_user_id, to_user_id=to_user_id)
    db.session.add(new_request)

    reciprocal = LinkRequest.query.filter_by(
        thread_id=thread_id, from_user_id=to_user_id, to_user_id=from_user_id
    ).first()

    matched = False
    if reciprocal:
        new_request.status = "matched"
        reciprocal.status = "matched"
        get_or_create_dm_thread(
            from_user_id, to_user_id, requested_by_id=from_user_id,
            status="accepted", from_link=True,
        )
        matched = True

    db.session.commit()
    return new_request, matched


def active_required(view):
    """利用停止・BAN中のユーザーが書き込み系の操作をできないようにするデコレータ。"""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_blocked_from_service:
            flash("現在アカウントが利用制限中のため、この操作はできません。異議申し立てが可能です。", "danger")
            return redirect(url_for("auth.appeal"))
        return view(*args, **kwargs)

    return wrapped
