"""
GAWA V6 – App Flask + SQLModel (SQLite)
--------------------------------------
- UI: /stats (stats.html), /results (results.html)
- API stats: /api/stats/overview, /api/stats/timeseries, /api/stats/top, /api/stats/quality, /api/catalog/projects
- API résultats: /api/results/search
- Catalogue bandeaux: /api/catalog/banners
"""
from __future__ import annotations

import io
import csv
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4

from flask import Flask, jsonify, request, render_template, Response
from sqlmodel import SQLModel, Field, create_engine, Session, select, Column, JSON
from sqlalchemy import func, asc, desc, or_

# -----------------------------
# Config / DB
# -----------------------------
DB_URL = "sqlite:///gawa.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})
app = Flask(__name__)

# -----------------------------
# Helpers généraux
# -----------------------------
def utcnow() -> datetime:
    """Datetime timezone-aware (UTC)."""
    return datetime.now(timezone.utc)

def _scalar(row):
    try:
        return row[0]
    except Exception:
        return row

def _get_str(name: str, default: str = "") -> str:
    return request.args.get(name, default)

def _get_int(name: str, default: int = 0, minv: Optional[int] = None, maxv: Optional[int] = None) -> int:
    try:
        v = int(request.args.get(name, default))
    except Exception:
        v = default
    if minv is not None and v < minv:
        v = minv
    if maxv is not None and v > maxv:
        v = maxv
    return v

def _get_float(name: str, default: float = 0.0, minv: Optional[float] = None, maxv: Optional[float] = None) -> float:
    try:
        v = float(request.args.get(name, default))
    except Exception:
        v = default
    if minv is not None and v < minv:
        v = minv
    if maxv is not None and v > maxv:
        v = maxv
    return v

# -----------------------------
# Modèles
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
    banners: List[str] = Field(sa_column=Column(JSON), default_factory=list)  # liste de codes de bandeaux
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
# Catalogue WikiProjets
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
PROJECT_LABELS = {p["slug"]: p["label"] for p in PROJECTS}
ALLOWED_PROJECT_SLUGS = set(PROJECT_LABELS.keys())

@app.get("/api/catalog/projects")
def api_catalog_projects():
    return jsonify({"projects": PROJECTS})

# Petit catalogue "propre" de codes de bandeaux pour l’autocomplétion
_BANNER_CATALOG = [
    "wikifier", "sources", "sources manquantes", "ébauche", "neutralité", "admissibilité",
    "à sourcer", "mise en forme", "actualisation", "style", "relecture", "orphan", "à illustrer",
    "à recycler", "travail inédit", "copyvio", "pertinence", "ton", "désorganisation"
]

@app.get("/api/catalog/banners")
def api_catalog_banners():
    q = (_get_str("q","") or "").strip().lower()
    items = _BANNER_CATALOG
    if q:
        items = [b for b in _BANNER_CATALOG if q in b.lower()]
    return jsonify({"items": items[:30]})

# -----------------------------
# Init & seed (démo)
# -----------------------------
def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

# --- Auto-migration légère : s'assure que la colonne Article.banners existe ---
def ensure_schema() -> None:
    # On utilise une transaction explicite pour pouvoir ALTER/UPDATE proprement
    from sqlalchemy import text
    with engine.begin() as conn:
        # Lister les colonnes actuelles de la table article
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(article);")]
        if "banners" not in cols:
            # SQLite accepte JSON comme alias de TEXT : parfait pour stocker un tableau JSON
            conn.exec_driver_sql("ALTER TABLE article ADD COLUMN banners JSON;")
            conn.exec_driver_sql("UPDATE article SET banners='[]' WHERE banners IS NULL;")
            # (facultatif) si tu veux un index simple sur la présence de données :
            # conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_article_banners ON article (banners);")

# --- Light migration: ajoute des colonnes manquantes si la DB existe déjà ---
def _column_exists(table: str, column: str) -> bool:
    # PRAGMA table_info retourne: cid, name, type, notnull, dflt_value, pk
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table});").fetchall()
        cols = {r[1] for r in rows}
    return column in cols

def light_migrate() -> None:
    """
    Migration légère pour SQLite :
    - ajoute article.banners (JSON/TEXT) si absent, et l'initialise à []
    """
    if not _column_exists("article", "banners"):
        app.logger.info("[GAWA] Light migrate: adding article.banners")
        with engine.begin() as conn:
            # Sur SQLite, JSON est stocké en TEXT ; SQLAlchemy s'occupe du (de)sérialiser
            conn.exec_driver_sql("ALTER TABLE article ADD COLUMN banners TEXT")
            conn.exec_driver_sql("UPDATE article SET banners='[]' WHERE banners IS NULL")

def seed_if_empty() -> None:
    """Seed simple avec diversité de projets et quelques bandeaux."""
    with Session(engine) as s:
        row = s.exec(select(func.count(Query.id))).one()
        any_query = int(_scalar(row) or 0)
        if any_query > 0:
            return

        users = [User(username=f"User{i}") for i in range(1, 7)]
        s.add_all(users)
        s.commit()

        proj_cycle = [p["slug"] for p in PROJECTS][:6]
        today = datetime.now(timezone.utc).date()

        for i in range(30):
            d = today - timedelta(days=29 - i)
            proj = proj_cycle[i % len(proj_cycle)]
            q = Query(
                label=f"Auto query {i}",
                params={"project": proj},
                created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
            )
            s.add(q)

            for j in range(5):
                banners = []
                if j % 3 == 0:
                    banners = ["wikifier", "sources"]
                elif j % 3 == 1:
                    banners = ["ébauche"]
                else:
                    banners = ["sources manquantes"]

                art = Article(
                    title=f"Article {i}-{j}",
                    wiki="frwiki",
                    length=1500 + i * 10 + j * 3,
                    views_30d=1000 + (i * 27) + j * 11,
                    banners=banners,
                    last_seen=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                )
                s.add(art)

                sug = Suggestion(
                    query_id=q.id,
                    article_id=art.id,
                    score=50 + j + i * 0.1,
                    created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    reasons={"note": "seed demo"},
                )
                s.add(sug)

                # 0..2 sur 5 suggestions: créent des assignations
                if j < 2:
                    u = users[(i + j) % len(users)]
                    st = "done" if (i + j) % 3 == 0 else ("in_progress" if (i + j) % 3 == 1 else "todo")
                    asg = Assignment(
                        suggestion_id=sug.id,
                        user_id=u.id,
                        status=st,
                        created_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                        updated_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    )
                    s.add(asg)
        s.commit()

create_db_and_tables()
ensure_schema()
light_migrate()
seed_if_empty()

# -----------------------------
# Fenêtrage (dates)
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
# UI
# -----------------------------
@app.get("/stats")
def stats_page():
    return render_template("stats.html")

@app.get("/results")
def results_page():
    return render_template("results.html")

# -----------------------------
# API stats (inchangé)
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
        else:
            stmt = (
                select(func.date(Assignment.created_at), func.count(func.distinct(Assignment.user_id)))
                .where(Assignment.created_at.between(d_from, end_dt))
                .group_by(func.date(Assignment.created_at))
                .order_by(func.date(Assignment.created_at))
            )
        rows = s.exec(stmt).all()

    points = [{"t": r[0], "v": int(r[1])} for r in rows]
    return jsonify({"metric": metric, "points": points})

@app.get("/api/stats/top")
def api_top():
    limit = max(1, min(int(request.args.get("limit", 10)), 50))
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        rows = s.exec(
            select(Query.params).where(Query.created_at.between(d_from, end_dt))
        ).all()
    projects = []
    for row in rows:
        params = row[0] if isinstance(row, (list, tuple)) else row
        proj = params.get("project") if isinstance(params, dict) else None
        projects.append(proj or "(sans projet)")
    items = [{"label": lab, "value": cnt} for lab, cnt in Counter(projects).most_common(limit)]
    return jsonify({"dimension": "project", "items": items})

@app.get("/api/stats/quality")
def api_quality():
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)
    with Session(engine) as s:
        rows = s.exec(
            select(Assignment.status, func.count())
            .where(Assignment.updated_at.between(d_from, end_dt))
            .group_by(Assignment.status)
        ).all()
        dist = {str(st or "todo"): int(cnt or 0) for st, cnt in rows}

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
# API résultats — compatible avec ton gabarit
# -----------------------------
def _order_clause(sort_key: str):
    mapping = {
        "date_desc":   desc(Suggestion.created_at),
        "score_desc":  desc(Suggestion.score),
        "views_desc":  desc(Article.views_30d),
        "length_desc": desc(Article.length),
        "date_asc":    asc(Suggestion.created_at),
        "score_asc":   asc(Suggestion.score),
        "views_asc":   asc(Article.views_30d),
        "length_asc":  asc(Article.length),
    }
    return mapping.get(sort_key or "date_desc", desc(Suggestion.created_at))

@app.get("/api/results/search")
def api_results_search():
    d_from, d_to = _window()
    end_dt = d_to + timedelta(days=1)

    q_text  = _get_str("q", "").strip()
    project = _get_str("project", "").strip().upper()
    banner  = _get_str("banner", "").strip()
    status  = _get_str("status", "").strip()  # "", "unassigned", "todo", "in_progress", "done"
    sort    = _get_str("sort", "date_desc").strip().lower()
    size    = _get_int("size", 20, 1, 100)
    page    = _get_int("page", 1, 1)

    order_clause = _order_clause(sort)

    # LEFT JOIN sur Assignment pour pouvoir déduire le statut ; on déduplique ensuite côté Python
    stmt = (
        select(Suggestion, Article, Query, Assignment.status)
        .join(Article, Suggestion.article_id == Article.id)
        .join(Query, Suggestion.query_id == Query.id)
        .join(Assignment, Assignment.suggestion_id == Suggestion.id, isouter=True)
        .where(Suggestion.created_at.between(d_from, end_dt))
        .order_by(order_clause, Suggestion.id)
    )
    if project and project in ALLOWED_PROJECT_SLUGS:
        stmt = stmt.where(func.json_extract(Query.params, "$.project") == project)
    if q_text:
        # ILIKE pour SQLAlchemy ; sur SQLite, LIKE est souvent case-insensitive (ASCII)
        stmt = stmt.where(Article.title.ilike(f"%{q_text}%"))

    with Session(engine) as s:
        rows = s.exec(stmt).all()

    # Déduplication + calcul du statut agrégé + filtre bandeau/status
    status_weight = {"done": 3, "in_progress": 2, "todo": 1}
    collected: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def banner_match(banners_list: List[str]) -> bool:
        if not banner:
            return True
        if not banners_list:
            return False
        bq = banner.lower()
        for b in banners_list:
            if b and (bq in b.lower() or b.lower().startswith(bq)):
                return True
        return False

    for sug, art, q, asg_status in rows:
        # statut agrégé par suggestion (priorité done > in_progress > todo ; sinon unassigned)
        prev = collected.get(sug.id)
        cur_status = (asg_status or "").strip() if asg_status else ""
        if prev:
            # mettre à jour le "meilleur" statut rencontré
            prev_w = status_weight.get(prev["status"], 0)
            cur_w = status_weight.get(cur_status, 0)
            if cur_w > prev_w:
                prev["status"] = cur_status
            continue

        proj = None
        try:
            proj = (q.params or {}).get("project")
        except Exception:
            proj = None

        # Pré-filtre bandeaux
        banners_list = getattr(art, "banners", None) or []
        if not banner_match(banners_list):
            continue

        collected[sug.id] = {
            "suggestion_id": sug.id,
            "title": art.title,
            "project": proj,
            "project_label": PROJECT_LABELS.get(proj or "", None),
            "status": cur_status or "unassigned",
            "score": float(sug.score) if sug.score is not None else 0.0,
            "length": art.length or 0,
            "views_30d": art.views_30d or 0,
            "date": (sug.created_at.date().isoformat() if isinstance(sug.created_at, datetime) else str(sug.created_at)),
        }

    # Filtre sur le statut demandé
    if status:
        status = status.lower()
        collected = OrderedDict(
            (k, v) for k, v in collected.items()
            if (status == "unassigned" and v["status"] == "unassigned") or
               (status in {"todo", "in_progress", "done"} and v["status"] == status)
        )

    items_all = list(collected.values())
    total = len(items_all)
    pages = max(1, (total + size - 1) // size)
    page = min(page, pages)
    start = (page - 1) * size
    end = start + size
    items = items_all[start:end]

    return jsonify({
        "total": total,
        "page": page,
        "pages": pages,
        "size": size,
        "items": items
    })

# -----------------------------
# Favicon (supprime le 404 bruyant)
# -----------------------------
@app.get("/favicon.ico")
def favicon():
    return ("", 204)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    print(f"[GAWA] DB url: {DB_URL}")
    app.run(host="0.0.0.0", port=5000, debug=True)