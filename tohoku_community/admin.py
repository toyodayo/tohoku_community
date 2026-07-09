from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Appeal, User

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@bp.route("/appeals")
@login_required
def appeals():
    _require_admin()
    pending = Appeal.query.filter_by(status="pending").order_by(Appeal.created_at.asc()).all()
    return render_template("admin_appeals.html", appeals=pending)


@bp.route("/appeals/<int:appeal_id>/approve", methods=["POST"])
@login_required
def approve(appeal_id):
    _require_admin()
    appeal = Appeal.query.get_or_404(appeal_id)
    appeal.status = "approved"
    appeal.resolved_at = datetime.utcnow()

    user = User.query.get(appeal.user_id)
    user.is_permanently_banned = False
    user.ban_until = None

    db.session.commit()
    flash("異議申し立てを承認し、利用制限を解除しました。", "success")
    return redirect(url_for("admin.appeals"))


@bp.route("/appeals/<int:appeal_id>/reject", methods=["POST"])
@login_required
def reject(appeal_id):
    _require_admin()
    appeal = Appeal.query.get_or_404(appeal_id)
    appeal.status = "rejected"
    appeal.resolved_at = datetime.utcnow()
    db.session.commit()
    flash("異議申し立てを却下しました。", "info")
    return redirect(url_for("admin.appeals"))
