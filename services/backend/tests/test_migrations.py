import importlib.util
from pathlib import Path


def _load_content_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0003_content_review_reading.py"
    spec = importlib.util.spec_from_file_location("content_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_content_timestamp_column_is_named_for_alembic() -> None:
    assert _load_content_migration()._timestamp().name == "created_at"


def test_refund_migration_follows_wallet_and_defines_snapshot_revision() -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0006_refund.py"
    spec = importlib.util.spec_from_file_location("refund_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0005_wallet_commerce"
    assert module.revision == "0006_refund"


def test_later_migrations_form_a_single_linear_head() -> None:
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    loaded = {}
    for name in (
        "0007_governance.py",
        "0008_author_finance.py",
        "0009_operation_legal.py",
        "0010_reader_experience.py",
    ):
        path = versions / name
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[module.revision] = module.down_revision
    assert loaded == {
        "0007_governance": "0006_refund",
        "0008_author_finance": "0007_governance",
        "0009_operation_legal": "0008_author_finance",
        "0010_reader_experience": "0009_operation_legal",
    }
