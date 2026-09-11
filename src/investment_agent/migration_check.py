from __future__ import annotations

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from investment_agent.storage import make_engine


def verify_migration_heads(
    current_heads: tuple[str, ...],
    expected_heads: tuple[str, ...],
) -> None:
    if set(current_heads) != set(expected_heads):
        raise RuntimeError(
            "Database migration heads do not match the image: "
            f"current={','.join(current_heads) or 'none'} "
            f"expected={','.join(expected_heads) or 'none'}"
        )


def main() -> int:
    alembic_config = Config("alembic.ini")
    expected_heads = tuple(ScriptDirectory.from_config(alembic_config).get_heads())
    engine = make_engine()
    with engine.connect() as connection:
        current_heads = tuple(
            MigrationContext.configure(connection).get_current_heads()
        )
    verify_migration_heads(current_heads, expected_heads)
    print(f"Verified migration head: {','.join(current_heads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
