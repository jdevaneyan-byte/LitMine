import os

from sqlalchemy import create_engine, event, Column, Integer, String, Text, DateTime, ForeignKey, Boolean, text as _sa_text
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from datetime import datetime, timezone

# Database location is overridable via env var so deployments/tests can point
# at a different file without editing code. Defaults to a local SQLite file.
DB_PATH = os.getenv("LITMINE_DB", "litmine.db")


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    topic = Column(String(500), nullable=False)
    description = Column(Text, default="")
    literature_type = Column(String(20), default="Both")  # Review | Research | Both
    review_type = Column(String(100), default="Narrative review")
    inclusion_criteria = Column(Text, default="")
    exclusion_criteria = Column(Text, default="")
    search_strategy = Column(Text, default="")
    ai_search_strategy = Column(Text, default="")
    chosen_title = Column(String(1000), nullable=True)
    stage = Column(Integer, default=1)  # 1=landscape, 2=title, 3=collect, 4=export
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    landscape_articles = relationship(
        "LandscapeArticle", back_populates="project", cascade="all, delete-orphan"
    )
    analysis = relationship(
        "LandscapeAnalysis",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    collected_articles = relationship(
        "CollectedArticle", back_populates="project", cascade="all, delete-orphan"
    )
    curated_reviews = relationship(
        "CuratedReview", back_populates="project", cascade="all, delete-orphan"
    )
    cited_articles = relationship(
        "CitedArticle", back_populates="project", cascade="all, delete-orphan"
    )


class LandscapeArticle(Base):
    __tablename__ = "landscape_articles"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(1000), nullable=False)
    doi = Column(String(255), nullable=True)
    abstract = Column(Text, default="")
    authors = Column(String(1000), default="")
    year = Column(Integer, nullable=True)
    source = Column(String(50), nullable=False)
    url = Column(String(1000), nullable=True)
    is_relevant = Column(Boolean, nullable=True)  # None=unfiltered, True=keep, False=exclude
    decision = Column(String(20), default="unscreened")
    decision_reason = Column(Text, default="")
    tags = Column(String(500), default="")
    notes = Column(Text, default="")

    project = relationship("Project", back_populates="landscape_articles")


class LandscapeAnalysis(Base):
    __tablename__ = "landscape_analysis"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    full_text = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="analysis")


class CollectedArticle(Base):
    __tablename__ = "collected_articles"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(1000), nullable=False)
    doi = Column(String(255), nullable=True)
    abstract = Column(Text, default="")
    authors = Column(String(1000), default="")
    year = Column(Integer, nullable=True)
    source = Column(String(50), nullable=False)
    url = Column(String(1000), nullable=True)
    pub_type = Column(String(60), default="")  # normalized publication type from the source
    citation_count = Column(Integer, nullable=True)  # global citations (OpenAlex/S2)
    notes = Column(Text, default="")
    tags = Column(String(500), default="")
    screening_status = Column(String(20), default="unscreened")
    decision_reason = Column(Text, default="")
    pdf_path = Column(String(1000), nullable=True)
    imported_from = Column(String(100), default="")
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="collected_articles")


class CuratedReview(Base):
    """A review article curated by the user (e.g. imported from Excel) that we will
    extract references from. Each curated review has a stable ID; cited articles
    are tagged to that ID."""

    __tablename__ = "curated_reviews"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String(1000), nullable=False)
    doi = Column(String(255), nullable=True)
    year = Column(Integer, nullable=True)
    journal = Column(String(500), default="")
    theme = Column(String(500), default="")
    importance = Column(String(50), default="")  # e.g. Core / Extended
    notes = Column(Text, default="")
    url = Column(String(1000), default="")
    imported_from = Column(String(255), default="")
    extraction_status = Column(String(30), default="pending")  # pending / running / done / failed / no_refs
    references_total = Column(Integer, default=0)
    references_kept = Column(Integer, default=0)
    references_rejected = Column(Integer, default=0)
    extraction_error = Column(Text, default="")
    last_extracted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="curated_reviews")
    cited_articles = relationship(
        "CitedArticle", back_populates="curated_review", cascade="all, delete-orphan"
    )


class CitedArticle(Base):
    """A reference extracted from a curated review.
    `is_review` flags references that are themselves review articles.
    `rejected_reason` is set when the article was filtered out (e.g. pre-2019)."""

    __tablename__ = "cited_articles"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    curated_review_id = Column(Integer, ForeignKey("curated_reviews.id"), nullable=False)
    title = Column(String(1000), nullable=False)
    doi = Column(String(255), nullable=True)
    year = Column(Integer, nullable=True)
    authors = Column(String(1000), default="")
    venue = Column(String(500), default="")
    abstract = Column(Text, default="")
    url = Column(String(1000), default="")
    is_review = Column(Boolean, default=False)
    is_book = Column(Boolean, default=False)
    publication_types = Column(String(255), default="")
    source = Column(String(50), default="")  # which API surfaced it
    status = Column(String(20), default="kept")  # kept / rejected
    rejected_reason = Column(Text, default="")
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="cited_articles")
    curated_review = relationship("CuratedReview", back_populates="cited_articles")


# check_same_thread=False is required because background search/extraction
# runs in daemon threads that share this engine; WAL mode + a busy timeout
# (set in the connect handler below) make concurrent reads/writes safe.
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """Enable WAL so background-thread writes don't block UI reads, and wait
    a few seconds before raising 'database is locked' under contention."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    # Lightweight migrations for existing local SQLite databases.
    migrations = [
        ("projects", "literature_type", "VARCHAR(20) DEFAULT 'Both'"),
        ("projects", "review_type", "VARCHAR(100) DEFAULT 'Narrative review'"),
        ("projects", "inclusion_criteria", "TEXT DEFAULT ''"),
        ("projects", "exclusion_criteria", "TEXT DEFAULT ''"),
        ("projects", "search_strategy", "TEXT DEFAULT ''"),
        ("projects", "ai_search_strategy", "TEXT DEFAULT ''"),
        ("projects", "updated_at", "DATETIME"),
        ("landscape_articles", "is_relevant", "BOOLEAN"),
        ("landscape_articles", "decision", "VARCHAR(20) DEFAULT 'unscreened'"),
        ("landscape_articles", "decision_reason", "TEXT DEFAULT ''"),
        ("landscape_articles", "tags", "VARCHAR(500) DEFAULT ''"),
        ("landscape_articles", "notes", "TEXT DEFAULT ''"),
        ("collected_articles", "tags", "VARCHAR(500) DEFAULT ''"),
        ("collected_articles", "screening_status", "VARCHAR(20) DEFAULT 'identified'"),
        ("collected_articles", "decision_reason", "TEXT DEFAULT ''"),
        ("collected_articles", "pdf_path", "VARCHAR(1000)"),
        ("collected_articles", "imported_from", "VARCHAR(100) DEFAULT ''"),
        ("collected_articles", "pub_type", "VARCHAR(60) DEFAULT ''"),
        ("collected_articles", "citation_count", "INTEGER"),
        ("cited_articles", "is_book", "BOOLEAN DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, column, spec in migrations:
            try:
                conn.execute(_sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {spec}"))
                conn.commit()
            except Exception:
                pass  # Column already exists or old SQLite cannot apply a default expression.

        # One-time relabel: older rows used "identified"/""/NULL for the
        # not-yet-screened state; unify them to "unscreened" so the screening
        # vocabulary is consistent with the UI. Idempotent.
        try:
            conn.execute(
                _sa_text(
                    "UPDATE collected_articles SET screening_status = 'unscreened' "
                    "WHERE screening_status IS NULL OR screening_status = '' "
                    "OR screening_status = 'identified'"
                )
            )
            conn.commit()
        except Exception:
            pass

        # Partial unique indexes prevent the same DOI being saved twice within
        # one project, while still allowing many rows with no DOI (empty/NULL).
        # Created only if the existing data is already clean; if a legacy DB
        # somehow has duplicates the CREATE fails and is skipped (no crash).
        partial_unique_indexes = [
            ("ux_collected_proj_doi", "collected_articles"),
            ("ux_curated_proj_doi", "curated_reviews"),
        ]
        for index_name, table in partial_unique_indexes:
            try:
                conn.execute(
                    _sa_text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                        f"ON {table} (project_id, doi) WHERE doi IS NOT NULL AND doi != ''"
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()  # duplicates present or unsupported; skip enforcement


def new_session():
    return SessionFactory()
