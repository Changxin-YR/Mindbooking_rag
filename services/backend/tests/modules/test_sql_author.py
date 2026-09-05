import sqlalchemy as sa
from sqlalchemy import create_engine

from novel_platform.modules.author.application import AuthorApplication
from novel_platform.modules.author.repository import SqlAuthorRepository


def _repository() -> SqlAuthorRepository:
    metadata = sa.MetaData()
    profiles = sa.Table(
        "author_profiles",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False, unique=True),
        sa.Column("pen_name", sa.String(255), nullable=False),
        sa.Column("normalized_pen_name", sa.String(255), nullable=False),
    )
    sa.Table(
        "author_pen_name_registry",
        metadata,
        sa.Column("normalized_pen_name", sa.String(255), primary_key=True),
        sa.Column("author_profile_id", sa.String(36), sa.ForeignKey(profiles.c.id), nullable=False),
    )
    sa.Table(
        "pen_name_history",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("author_profile_id", sa.String(36), sa.ForeignKey(profiles.c.id), nullable=False),
        sa.Column("pen_name", sa.String(255), nullable=False),
        sa.Column("normalized_pen_name", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return SqlAuthorRepository(engine)


def test_sql_author_repository_persists_profile_rename_and_history() -> None:
    repository = _repository()
    application = AuthorApplication(repository)

    created = application.create_profile("account-1", "  Original Name  ")
    changed = application.change_pen_name(created.id, "New Name")

    assert changed.pen_name == "New Name"
    assert changed.normalized_pen_name == "new name"
    assert repository.pen_name_history(created.id) == ["Original Name", "New Name"]
    assert repository.has_pen_name("original name")
