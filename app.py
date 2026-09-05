import os
import csv
import io
import hmac
import hashlib
import secrets
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, update, func

app = Flask(__name__)

# ---------- 환경설정 ----------
app.secret_key = os.environ.get("SECRET_KEY", "local-dev-secret-change-this")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")
RECEIPT_SECRET = os.environ.get("RECEIPT_SECRET", app.secret_key)

database_url = os.environ.get("DATABASE_URL", "sqlite:///songpyeon.db")
# 일부 서비스가 postgres:// 형식으로 줄 경우 SQLAlchemy용으로 변환
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ---------- DB 모델 ----------
class DrawCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used = db.Column(db.Boolean, nullable=False, default=False)
    used_at = db.Column(db.DateTime)
    nickname = db.Column(db.String(80))
    pick_number = db.Column(db.Integer)
    reward_name = db.Column(db.String(100))
    reward_points = db.Column(db.Integer)
    receipt = db.Column(db.String(32))
    memo = db.Column(db.String(120))


class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    probability = db.Column(db.Integer, nullable=False)
    is_gold = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


DEFAULT_REWARDS = [
    ("일반 송편", 5000, 60, False, 1),
    ("복 송편", 10000, 25, False, 2),
    ("대박 송편", 30000, 10, False, 3),
    ("황금 송편", 50000, 5, True, 4),
]


def initialize_database():
    db.create_all()
    count = db.session.scalar(select(func.count()).select_from(Reward))
    if not count:
        for name, points, probability, is_gold, sort_order in DEFAULT_REWARDS:
            db.session.add(
                Reward(
                    name=name,
                    points=points,
                    probability=probability,
                    is_gold=is_gold,
                    sort_order=sort_order,
                )
            )
        db.session.commit()


with app.app_context():
    initialize_database()


# ---------- 공통 ----------
def admin_logged_in():
    return bool(session.get("admin"))


def require_admin():
    if not admin_logged_in():
        return redirect(url_for("admin_login"))
    return None


def get_rewards():
    return db.session.scalars(
        select(Reward).order_by(Reward.sort_order.asc(), Reward.id.asc())
    ).all()


def pick_reward():
    rewards = get_rewards()
    total = sum(max(0, r.probability) for r in rewards)
    if total != 100:
        raise RuntimeError("관리자 확률 합계가 100%가 아닙니다.")

    n = secrets.randbelow(100)  # 서버 측 암호학적 난수
    cumulative = 0
    for reward in rewards:
        cumulative += reward.probability
        if n < cumulative:
            return reward
    return rewards[-1]


def make_receipt(code, nickname, pick_number, reward_points, used_at):
    raw = f"{code}|{nickname}|{pick_number}|{reward_points}|{used_at.isoformat()}".encode("utf-8")
    digest = hmac.new(RECEIPT_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return digest[:12].upper()


def new_code():
    while True:
        code = secrets.token_hex(4).upper()
        exists = db.session.scalar(select(DrawCode).where(DrawCode.code == code))
        if not exists:
            return code


# ---------- 회원 ----------
@app.get("/")
def index():
    rewards = get_rewards()
    return render_template("index.html", rewards=rewards)


@app.post("/draw")
def draw():
    code = request.form.get("code", "").strip().upper()
    nickname = request.form.get("nickname", "").strip()
    pick_number_raw = request.form.get("pick_number", "").strip()

    if not code or not nickname or not pick_number_raw:
        flash("닉네임, 참여코드, 송편을 모두 입력해주세요.")
        return redirect(url_for("index"))

    if len(nickname) > 80:
        flash("닉네임이 너무 깁니다.")
        return redirect(url_for("index"))

    try:
        pick_number = int(pick_number_raw)
    except ValueError:
        flash("송편 번호가 올바르지 않습니다.")
        return redirect(url_for("index"))

    if pick_number not in range(1, 11):
        flash("송편은 1번부터 10번까지 선택할 수 있습니다.")
        return redirect(url_for("index"))

    draw_code = db.session.scalar(select(DrawCode).where(DrawCode.code == code))
    if not draw_code:
        flash("유효하지 않은 참여코드입니다.")
        return redirect(url_for("index"))

    if draw_code.used:
        flash("이미 사용된 참여코드입니다.")
        return redirect(url_for("index"))

    try:
        reward = pick_reward()
    except RuntimeError:
        flash("이벤트 설정 오류입니다. 운영자에게 문의해주세요.")
        return redirect(url_for("index"))

    used_at = datetime.utcnow()
    receipt = make_receipt(code, nickname, pick_number, reward.points, used_at)

    # 같은 코드로 거의 동시에 두 번 요청해도 1건만 성공하도록 조건부 UPDATE
    stmt = (
        update(DrawCode)
        .where(DrawCode.code == code, DrawCode.used.is_(False))
        .values(
            used=True,
            used_at=used_at,
            nickname=nickname,
            pick_number=pick_number,
            reward_name=reward.name,
            reward_points=reward.points,
            receipt=receipt,
        )
    )
    result = db.session.execute(stmt)
    if result.rowcount != 1:
        db.session.rollback()
        flash("이미 사용된 참여코드입니다.")
        return redirect(url_for("index"))

    db.session.commit()

    return render_template(
        "result.html",
        nickname=nickname,
        pick_number=pick_number,
        reward_name=reward.name,
        reward_points=reward.points,
        is_gold=reward.is_gold,
        receipt=receipt,
        used_at=used_at,
    )


# ---------- 관리자 ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        entered = request.form.get("password", "")
        if hmac.compare_digest(entered, ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("관리자 비밀번호가 틀렸습니다.")
    return render_template("admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    gate = require_admin()
    if gate:
        return gate

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "generate":
            try:
                count = int(request.form.get("count", "1"))
            except ValueError:
                count = 1
            count = max(1, min(count, 100))
            memo = request.form.get("memo", "").strip()[:120]

            created = []
            for _ in range(count):
                code = new_code()
                db.session.add(DrawCode(code=code, memo=memo or None))
                created.append(code)
            db.session.commit()

            if len(created) <= 10:
                flash("생성 완료: " + ", ".join(created))
            else:
                flash(f"{len(created)}개의 참여코드를 생성했습니다.")

        elif action == "rewards":
            rewards = get_rewards()
            values = []
            try:
                for r in rewards:
                    name = request.form.get(f"name_{r.id}", r.name).strip()[:100]
                    points = max(0, int(request.form.get(f"points_{r.id}", r.points)))
                    probability = max(0, int(request.form.get(f"prob_{r.id}", r.probability)))
                    values.append((r, name, points, probability))
            except ValueError:
                flash("포인트와 확률은 숫자로 입력해주세요.")
                return redirect(url_for("admin"))

            total = sum(x[3] for x in values)
            if total != 100:
                flash(f"확률 합계가 현재 {total}%입니다. 반드시 100%로 맞춰주세요.")
                return redirect(url_for("admin"))

            for r, name, points, probability in values:
                r.name = name
                r.points = points
                r.probability = probability
            db.session.commit()
            flash("당첨 보상과 확률을 저장했습니다.")

    codes = db.session.scalars(select(DrawCode).order_by(DrawCode.id.desc())).all()
    rewards = get_rewards()

    total_codes = db.session.scalar(select(func.count()).select_from(DrawCode)) or 0
    used_codes = db.session.scalar(
        select(func.count()).select_from(DrawCode).where(DrawCode.used.is_(True))
    ) or 0
    total_points = db.session.scalar(
        select(func.coalesce(func.sum(DrawCode.reward_points), 0)).where(DrawCode.used.is_(True))
    ) or 0

    return render_template(
        "admin.html",
        codes=codes,
        rewards=rewards,
        total_codes=total_codes,
        used_codes=used_codes,
        total_points=total_points,
    )


@app.post("/admin/reset/<code>")
def reset_code(code):
    gate = require_admin()
    if gate:
        return gate

    row = db.session.scalar(select(DrawCode).where(DrawCode.code == code.upper()))
    if row:
        row.used = False
        row.used_at = None
        row.nickname = None
        row.pick_number = None
        row.reward_name = None
        row.reward_points = None
        row.receipt = None
        db.session.commit()
        flash(f"{row.code} 코드를 미사용 상태로 초기화했습니다.")
    return redirect(url_for("admin"))


@app.post("/admin/delete/<code>")
def delete_code(code):
    gate = require_admin()
    if gate:
        return gate

    row = db.session.scalar(select(DrawCode).where(DrawCode.code == code.upper()))
    if row and not row.used:
        db.session.delete(row)
        db.session.commit()
        flash(f"{code.upper()} 미사용 코드를 삭제했습니다.")
    else:
        flash("사용 완료된 코드는 기록 보존을 위해 삭제할 수 없습니다.")
    return redirect(url_for("admin"))


@app.get("/admin/export.csv")
def export_csv():
    gate = require_admin()
    if gate:
        return gate

    rows = db.session.scalars(select(DrawCode).order_by(DrawCode.id.asc())).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "code", "created_at_utc", "used", "used_at_utc", "nickname",
        "pick_number", "reward_name", "reward_points", "receipt", "memo"
    ])
    for r in rows:
        writer.writerow([
            r.code,
            r.created_at.isoformat() if r.created_at else "",
            r.used,
            r.used_at.isoformat() if r.used_at else "",
            r.nickname or "",
            r.pick_number or "",
            r.reward_name or "",
            r.reward_points or "",
            r.receipt or "",
            r.memo or "",
        ])

    return Response(
        "\ufeff" + out.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=songpyeon_results.csv"},
    )


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
