"""
GAWA V6 – App Flask + SQLModel (SQLite)
--------------------------------------
- Base SQLite via SQLModel (SQLAlchemy)
- Endpoints: /api/stats/overview, /api/stats/timeseries, /api/stats/top, /api/stats/quality, /api/catalog/projects
- UI: /stats (templates/stats.html)
"""
from __future__ import annotations

from datetime import datetime, timedelta, date, timezone
from typing import Optional, Dict, Any
from uuid import uuid4
from collections import Counter

from flask import Flask, jsonify, request, render_template
from sqlmodel import SQLModel, Field, create_engine, Session, select, Column, JSON
from sqlalchemy import func

# -----------------------------
# Config / DB
# -----------------------------
DB_URL = "sqlite:///gawa.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})
app = Flask(__name__)

# -----------------------------
# Helpers datetime (UTC aware)
# -----------------------------
def utcnow() -> datetime:
    # Datetime conscient du fuseau, conforme aux avertissements (PEP 495 / SQLAlchemy)
    return datetime.now(timezone.utc)

# -----------------------------
# Modèles (ERD minimal)
# -----------------------------
class Query(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    label: str
    params: Dict[str, Any] = Field(sa_column=Column(JSON), default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow, index=True)

class Article(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    wiki: str = "frwiki"
    pageid: Optional[str] = None
    length: Optional[int] = None
    views_30d: Optional[int] = None
    has_references: Optional[bool] = None
    stub_like: Optional[bool] = None
    last_seen: Optional[datetime] = None

class Suggestion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    query_id: str = Field(foreign_key="query.id", index=True)
    article_id: str = Field(foreign_key="article.id", index=True)
    score: Optional[float] = None
    reasons: Dict[str, Any] = Field(sa_column=Column(JSON), default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow, index=True)

class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    username: str = Field(index=True)
    roles: Optional[str] = None
    last_login: Optional[datetime] = None

class Assignment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    suggestion_id: str = Field(foreign_key="suggestion.id", index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    status: str = Field(default="todo", index=True)  # todo | in_progress | done
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)

# -----------------------------
# Catalogue WikiProjets (pour le <select>)
# -----------------------------
PROJECTS = [
    {"slug": "CIV",   "label": "Côte d’Ivoire"},
    {"slug": "AFR",   "label": "Afrique"},
    {"slug": "POL",   "label": "Politique"},
    {"slug": "TECH",  "label": "Technologie"},
    {"slug": "BIO",   "label": "Biographies"},
    {"slug": "HIST",  "label": "Histoire"},
    {"slug": "GEO",   "label": "Géographie"},
    {"slug": "CULT",  "label": "Culture"},
    {"slug": "SPORT", "label": "Sport"},
    {"slug": "ECO",   "label": "Économie"},
    {"slug": "EDU",   "label": "Éducation"},
    {"slug": "SANTE", "label": "Santé"},
    {"slug": "SCI",   "label": "Sciences"},
    {"slug": "ENV",   "label": "Environnement"},
    {"slug": "ENTR",  "label": "Entreprises"},
]
ALLOWED_PROJECT_SLUGS = {p["slug"] for p in PROJECTS}

@app.get("/api/catalog/projects")
def api_catalog_projects():
    return jsonify({"projects": PROJECTS})

# -----------------------------
# Init & seed (démo)
# -----------------------------
def _scalar(row):
    try:
        return row[0]
    except Exception:
        return row

def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

def seed_if_empty() -> None:
    with Session(engine) as s:
        row = s.exec(select(func.count(Query.id))).one()
        any_query = int(_scalar(row) or 0)
        if any_query > 0:
            return

        users = [User(username=f"User{i}") for i in range(1, 7)]
        s.add_all(users)
        s.commit()

        # Seed : 30 jours, projets variés
        today = datetime.now(timezone.utc).date()
        slugs = [p["slug"] for p in PROJECTS]
        for i in range(30):
            d = today - timedelta(days=29 - i)
            proj = slugs[i % len(slugs)]
            q = Query(
                label=f"Auto query {i}",
                params={"project": proj},
                created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
            )
            s.add(q)
            for j in range(5):
                art = Article(
                    title=f"Article {i}-{j}",
                    wiki="frwiki",
                    length=1500 + i * 10,
                    views_30d=200 + j * 5,
                )
                s.add(art)
                sug = Suggestion(
                    query_id=q.id,
                    article_id=art.id,
                    score=50 + j,
                    created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                )
                s.add(sug)
                if j < 2:
                    u = users[(i + j) % len(users)]
                    st = ("done" if (i + j) % 3 == 0
                          else "in_progress" if (i + j) % 3 == 1 else "todo")
                    asg = Assignment(
                        suggestion_id=sug.id, user_id=u.id, status=st,
                        created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                        updated_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    )
                    s.add(asg)
        s.commit()

create_db_and_tables()
seed_if_empty()

# -----------------------------
# Helpers fenêtrage
# -----------------------------
ISO = "%Y-%m-%d"

def _parse_date(s: Optional[str], default: date) -> date:
    if not s:
        return default
    try:
        return datetime.strptime(s, ISO).date()
    except ValueError:
        return default

def _window() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    d_from = _parse_date(request.args.get("from"), today - timedelta(days=29))
    d_to   = _parse_date(request.args.get("to"), today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to

# -----------------------------
# UI + favicon
# -----------------------------
@app.get("/stats")
def stats_page():
    return render_template("stats.html")

@app.get("/favicon.ico")
def favicon():
    # Pas d’icône dédiée pour l’instant : supprime le 404 dans les logs
    return ("", 204)

# -----------------------------
# API: Overview
# -----------------------------
@app.get("/api/stats/overview")
def api_overview():
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        q_count = _scalar(s.exec(
            select(func.count(Query.id)).where(Query.created_at.between(d_from, end_dt))
        ).one())
        s_count = _scalar(s.exec(
            select(func.count(Suggestion.id)).where(Suggestion.created_at.between(d_from, end_dt))
        ).one())
        a_count = _scalar(s.exec(
            select(func.count(Assignment.id)).where(Assignment.created_at.between(d_from, end_dt))
        ).one())
        contribs = _scalar(s.exec(
            select(func.count(func.distinct(Assignment.user_id))).where(Assignment.created_at.between(d_from, end_dt))
        ).one())

    return jsonify({
        "counts": {
            "queries": int(q_count or 0),
            "suggestions": int(s_count or 0),
            "assignments": int(a_count or 0),
            "contributors": int(contribs or 0)
        },
        "rate": {"assign_to_resolve_median_days": 3.4, "progress_percent": 62.1}
    })

# -----------------------------
# API: Timeseries
# -----------------------------
@app.get("/api/stats/timeseries")
def api_timeseries():
    metric = request.args.get("metric", "queries")
    if metric not in {"queries", "suggestions", "assignments", "contributors"}:
        return jsonify({"error": "invalid metric"}), 400
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        if metric == "queries":
            stmt = (
                select(func.date(Query.created_at), func.count())
                .where(Query.created_at.between(d_from, end_dt))
                .group_by(func.date(Query.created_at))
                .order_by(func.date(Query.created_at))
            )
        elif metric == "suggestions":
            stmt = (
                select(func.date(Suggestion.created_at), func.count())
                .where(Suggestion.created_at.between(d_from, end_dt))
                .group_by(func.date(Suggestion.created_at))
                .order_by(func.date(Suggestion.created_at))
            )
        elif metric == "assignments":
            stmt = (
                select(func.date(Assignment.created_at), func.count())
                .where(Assignment.created_at.between(d_from, end_dt))
                .group_by(func.date(Assignment.created_at))
                .order_by(func.date(Assignment.created_at))
            )
        else:  # contributors distinct / jour
            stmt = (
                select(func.date(Assignment.created_at), func.count(func.distinct(Assignment.user_id)))
                .where(Assignment.created_at.between(d_from, end_dt))
                .group_by(func.date(Assignment.created_at))
                .order_by(func.date(Assignment.created_at))
            )
        rows = s.exec(stmt).all()

    points = [{"t": r[0], "v": int(r[1])} for r in rows]
    return jsonify({"metric": metric, "points": points})

# -----------------------------
# API: Top (compte par 'params.project' via ORM)
# -----------------------------
@app.get("/api/stats/top")
def api_top():
    limit = max(1, min(int(request.args.get("limit", 10)), 50))
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        rows = s.exec(
            select(Query.params)
            .where(Query.created_at.between(d_from, end_dt))
        ).all()
    projects = []
    for row in rows:
        params = row[0] if isinstance(row, (list, tuple)) else row
        proj = params.get("project") if isinstance(params, dict) else None
        projects.append(proj or "(sans projet)")
    items = [{"label": lab, "value": cnt} for lab, cnt in Counter(projects).most_common(limit)]
    return jsonify({"dimension": "project", "items": items})

# -----------------------------
# API: Quality (distribution statuts + contenu moyen)
# -----------------------------
@app.get("/api/stats/quality")
def api_quality():
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        # Statuts
        rows = s.exec(
            select(Assignment.status, func.count())
            .where(Assignment.updated_at.between(d_from, end_dt))
            .group_by(Assignment.status)
        ).all()
        dist = {str(st or "todo"): int(cnt or 0) for st, cnt in rows}

        # Longueur moyenne & Vues 30j (Suggestion -> Article)
        row_len = s.exec(
            select(func.avg(Article.length))
            .select_from(Suggestion)
            .join(Article, Suggestion.article_id == Article.id)
            .where(Suggestion.created_at.between(d_from, end_dt))
        ).one()
        avg_len = _scalar(row_len) or 0

        row_views = s.exec(
            select(func.coalesce(func.sum(Article.views_30d), 0))
            .select_from(Suggestion)
            .join(Article, Suggestion.article_id == Article.id)
            .where(Suggestion.created_at.between(d_from, end_dt))
        ).one()
        sum_views = _scalar(row_views) or 0

    return jsonify({
        "status": {
            "todo": dist.get("todo", 0),
            "in_progress": dist.get("in_progress", 0),
            "done": dist.get("done", 0),
        },
        "content": {
            "length_avg": int(avg_len),
            "views_30d_sum": int(sum_views)
        }
    })

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    print(f"[GAWA] DB url: {DB_URL}")
    app.run(host="0.0.0.0", port=5000, debug=True)