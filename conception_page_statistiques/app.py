# -*- coding: utf-8 -*-
"""
GAWA V6 – App Flask + SQLModel (SQLite)
--------------------------------------
- Remplace les données factices par une vraie base SQLite via SQLModel (SQLAlchemy).
- Fournit les endpoints: /api/stats/overview, /api/stats/timeseries, /api/stats/top, /api/stats/quality
- Sert le template Jinja2: templates/stats.html

Démarrage (Ubuntu/VS Code):
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python conception_page_statistiques/app.py
  # http://127.0.0.1:5000/stats
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from uuid import uuid4
from pathlib import Path
from collections import Counter

from flask import Flask, jsonify, request, render_template
from sqlmodel import SQLModel, Field, create_engine, Session, select, Column, JSON
from sqlalchemy import func, text

# -----------------------------
# Config / DB (propre, sans dépendre de app)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent                 # .../projet_gawa_v6
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)                   # s'assure que instance/ existe
DB_PATH = INSTANCE_DIR / "gawa.db"
DB_URL = f"sqlite:///{DB_PATH}"                                   # chemin absolu
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

# Crée l'app APRÈS la config
app = Flask(__name__, instance_relative_config=True)

# -----------------------------
# Modèles (ERD minimal)
# -----------------------------
class Query(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    label: str
    params: Dict[str, Any] = Field(sa_column=Column(JSON), default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

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
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    username: str = Field(index=True)
    roles: Optional[str] = None  # CSV simple pour MVP
    last_login: Optional[datetime] = None

class Assignment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    suggestion_id: str = Field(foreign_key="suggestion.id", index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    status: str = Field(default="todo", index=True)  # todo | in_progress | done
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

# -----------------------------
# Initialisation & seed (démo)
# -----------------------------
def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

def seed_if_empty() -> None:
    with Session(engine) as s:
        any_query = s.exec(select(func.count(Query.id))).one()
        # .one() renvoie (count,) ; on teste > 0 de manière robuste
        if (isinstance(any_query, (tuple, list)) and any_query[0] > 0) or (isinstance(any_query, int) and any_query > 0):
            return
        # Seed minimal: 30 jours de données synthétiques reproductibles
        users = [User(username=f"User{i}") for i in range(1, 8)]
        s.add_all(users)
        s.commit()
        today = datetime.utcnow().date()
        for i in range(30):
            d = today - timedelta(days=29 - i)
            q = Query(label=f"Auto query {i}", params={"project": "CIV"}, created_at=datetime(d.year, d.month, d.day))
            s.add(q)
            # 5 suggestions/jour
            for j in range(5):
                art = Article(title=f"Article {i}-{j}", wiki="frwiki", length=1500 + i * 10)
                s.add(art)
                sug = Suggestion(query_id=q.id, article_id=art.id, score=50 + j, created_at=datetime(d.year, d.month, d.day))
                s.add(sug)
                # 2 assignments/jour
                if j < 2:
                    u = users[(i + j) % len(users)]
                    st = "done" if (i + j) % 3 == 0 else ("in_progress" if (i + j) % 3 == 1 else "todo")
                    asg = Assignment(suggestion_id=sug.id, user_id=u.id, status=st,
                                     created_at=datetime(d.year, d.month, d.day),
                                     updated_at=datetime(d.year, d.month, d.day))
                    s.add(asg)
        s.commit()

create_db_and_tables()
seed_if_empty()

# -----------------------------
# Helpers filtres & fenêtres
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
    today = datetime.utcnow().date()
    d_from = _parse_date(request.args.get("from"), today - timedelta(days=29))
    d_to = _parse_date(request.args.get("to"), today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to

def _project_query_ids(s: Session, d_from: date, d_to: date, project: str | None) -> list[str]:
    """Retourne les IDs de Query dans la fenêtre, filtrées par project (dans Query.params) sans JSON1."""
    rows = s.exec(
        select(Query.id, Query.params).where(
            Query.created_at.between(d_from, d_to + timedelta(days=1))
        )
    ).all()
    if not project:
        return [qid for (qid, _) in rows]
    out = []
    for qid, params_dict in rows:
        if isinstance(params_dict, dict) and params_dict.get("project") == project:
            out.append(qid)
    return out

# -----------------------------
# Routes UI
# -----------------------------
@app.get("/stats")
def stats_page():
    return render_template("stats.html")

# -----------------------------
# API: Overview
# -----------------------------
@app.get("/api/stats/overview")
def api_overview():
    d_from, d_to = _window()
    project = request.args.get("project") or None
    with Session(engine) as s:
        qids = _project_query_ids(s, d_from, d_to, project)
        if project:
            q_count = len(qids)
            if qids:
                s_count = s.exec(
                    select(func.count(Suggestion.id)).where(
                        Suggestion.query_id.in_(qids),
                        Suggestion.created_at.between(d_from, d_to + timedelta(days=1))
                    )
                ).one()
                # assignments & contributors via suggestions liées
                sug_ids = s.exec(select(Suggestion.id).where(Suggestion.query_id.in_(qids))).all()
                sug_ids = [x[0] if isinstance(x, (list, tuple)) else x for x in sug_ids]
                if sug_ids:
                    a_count = s.exec(
                        select(func.count(Assignment.id)).where(
                            Assignment.suggestion_id.in_(sug_ids),
                            Assignment.created_at.between(d_from, d_to + timedelta(days=1))
                        )
                    ).one()
                    contribs = s.exec(
                        select(func.count(func.distinct(Assignment.user_id))).where(
                            Assignment.suggestion_id.in_(sug_ids),
                            Assignment.created_at.between(d_from, d_to + timedelta(days=1))
                        )
                    ).one()
                else:
                    a_count = 0
                    contribs = 0
            else:
                s_count = 0; a_count = 0; contribs = 0
        else:
            q_count = s.exec(
                select(func.count(Query.id)).where(Query.created_at.between(d_from, d_to + timedelta(days=1)))
            ).one()
            s_count = s.exec(
                select(func.count(Suggestion.id)).where(Suggestion.created_at.between(d_from, d_to + timedelta(days=1)))
            ).one()
            a_count = s.exec(
                select(func.count(Assignment.id)).where(Assignment.created_at.between(d_from, d_to + timedelta(days=1)))
            ).one()
            contribs = s.exec(
                select(func.count(func.distinct(Assignment.user_id))).where(
                    Assignment.created_at.between(d_from, d_to + timedelta(days=1))
                )
            ).one()

    return jsonify({
        "counts": {
            "queries": int((q_count or 0)),
            "suggestions": int((s_count[0] if isinstance(s_count, (tuple, list)) else s_count) or 0),
            "assignments": int((a_count[0] if isinstance(a_count, (tuple, list)) else a_count) or 0),
            "contributors": int((contribs[0] if isinstance(contribs, (tuple, list)) else contribs) or 0),
        },
        "rate": {
            "assign_to_resolve_median_days": 3.4,
            "progress_percent": 62.1,
        }
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
    project = request.args.get("project") or None

    with Session(engine) as s:
        if project:
            qids = _project_query_ids(s, d_from, d_to, project)
        # collecte par jour
        days = [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]
        counts = Counter()

        if metric == "queries":
            rows = s.exec(
                select(Query.created_at).where(Query.created_at.between(d_from, d_to + timedelta(days=1)))
            ).all()
            if project:
                # filtrer par qids
                rows_full = s.exec(
                    select(Query.id, Query.created_at).where(Query.created_at.between(d_from, d_to + timedelta(days=1)))
                ).all()
                rows = [created for (qid, created) in rows_full if qid in qids]
            for r in rows:
                created = r if isinstance(r, datetime) else r[0]
                counts[created.date()] += 1

        elif metric == "suggestions":
            stmt = select(Suggestion.query_id, Suggestion.created_at).where(
                Suggestion.created_at.between(d_from, d_to + timedelta(days=1))
            )
            rows = s.exec(stmt).all()
            for qid, created in rows:
                if project and qid not in qids:
                    continue
                counts[created.date()] += 1

        elif metric == "assignments":
            stmt = select(Assignment.suggestion_id, Assignment.created_at).where(
                Assignment.created_at.between(d_from, d_to + timedelta(days=1))
            )
            rows = s.exec(stmt).all()
            # map sug->query pour filtrer par project si besoin
            need_map = project
            sug2q = {}
            if need_map:
                sug2q = {sid: qid for (sid, qid) in s.exec(select(Suggestion.id, Suggestion.query_id)).all()}
            for sid, created in rows:
                if project and sug2q.get(sid) not in qids:
                    continue
                counts[created.date()] += 1

        else:  # contributors (distinct / jour)
            stmt = select(Assignment.suggestion_id, Assignment.user_id, Assignment.created_at).where(
                Assignment.created_at.between(d_from, d_to + timedelta(days=1))
            )
            rows = s.exec(stmt).all()
            sug2q = {}
            if project:
                sug2q = {sid: qid for (sid, qid) in s.exec(select(Suggestion.id, Suggestion.query_id)).all()}
            per_day_users = {d: set() for d in days}
            for sid, uid, created in rows:
                d = created.date()
                if d not in per_day_users:
                    per_day_users[d] = set()
                if project and sug2q.get(sid) not in qids:
                    continue
                per_day_users[d].add(uid)
            for d in days:
                counts[d] = len(per_day_users.get(d, set()))

    points = [{"t": d.isoformat(), "v": int(counts.get(d, 0))} for d in days]
    return jsonify({"metric": metric, "points": points})

# -----------------------------
# API: Top (ex: par projet via params JSON de Query)
# -----------------------------
@app.get("/api/stats/top")
def api_top():
    limit = max(1, min(int(request.args.get("limit", 10)), 50))
    d_from, d_to = _window()
    with Session(engine) as s:
        rows = s.exec(
            select(Query.params).where(Query.created_at.between(d_from, d_to + timedelta(days=1)))
        ).all()
    projects = []
    for r in rows:
        params_dict = r[0] if isinstance(r, (list, tuple)) else r
        proj = params_dict.get("project") if isinstance(params_dict, dict) else None
        projects.append(proj or "(sans projet)")
    items = [{"label": lab, "value": val} for lab, val in Counter(projects).most_common(limit)]
    return jsonify({"dimension": "project", "items": items})

# -----------------------------
# API: Quality (distribution statuts + contenu moyen)
# -----------------------------
@app.get("/api/stats/quality")
def api_quality():
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    project = request.args.get("project") or None

    with Session(engine) as s:
        if project:
            qids = _project_query_ids(s, d_from, d_to, project)
            sug_ids = []
            if qids:
                sug_ids = [sid for (sid,) in s.exec(select(Suggestion.id).where(Suggestion.query_id.in_(qids))).all()]

        # 1) Statuts
        base = select(Assignment.status, func.count())
        if project:
            if not sug_ids:
                dist = {}
            else:
                rows = s.exec(
                    base.where(
                        Assignment.suggestion_id.in_(sug_ids),
                        Assignment.updated_at.between(d_from, end_dt)
                    ).group_by(Assignment.status)
                ).all()
                dist = {str(st or "todo"): int(cnt or 0) for st, cnt in rows}
        else:
            rows = s.exec(
                base.where(Assignment.updated_at.between(d_from, end_dt)).group_by(Assignment.status)
            ).all()
            dist = {str(st or "todo"): int(cnt or 0) for st, cnt in rows}
        todo    = dist.get("todo", 0)
        in_prog = dist.get("in_progress", 0)
        done    = dist.get("done", 0)

        # 2) Longueur moyenne & vues (via Suggestion -> Article)
        base_len = (
            select(func.avg(Article.length))
            .select_from(Suggestion)
            .join(Article, Suggestion.article_id == Article.id)
            .where(Suggestion.created_at.between(d_from, end_dt))
        )
        base_views = (
            select(func.coalesce(func.sum(Article.views_30d), 0))
            .select_from(Suggestion)
            .join(Article, Suggestion.article_id == Article.id)
            .where(Suggestion.created_at.between(d_from, end_dt))
        )
        if project:
            if not qids:
                length_avg = 0
                views_30d_sum = 0
            else:
                length_avg = int((s.exec(base_len.where(Suggestion.query_id.in_(qids))).one_or_none() or 0))
                views_30d_sum = int((s.exec(base_views.where(Suggestion.query_id.in_(qids))).one() or 0))
        else:
            length_avg = int((s.exec(base_len).one_or_none() or 0))
            views_30d_sum = int((s.exec(base_views).one() or 0))

    return jsonify({
        "status": {"todo": todo, "in_progress": in_prog, "done": done},
        "content": {"length_avg": length_avg, "views_30d_sum": views_30d_sum}
    })

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    # Petit log utile pour vérifier où est la DB :
    print(f"[GAWA] DB path: {DB_PATH}")
    app.run(host="0.0.0.0", port=5000, debug=True)