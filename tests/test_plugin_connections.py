from datetime import UTC, datetime, timedelta

from agent_core.persistence.store import Base, ConnectorRepository, Database, Plugin, User, WorkspaceRepository, current_user_id


def _with_user(user_id: str):
    return current_user_id.set(user_id)


def test_plugin_and_connector_connections_are_isolated_per_user(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'connections.db'}")
    Base.metadata.create_all(database.engine)
    with database.session() as session:
        session.add_all([User(id="user-a", email="a@example.com"), User(id="user-b", email="b@example.com")])
        session.commit()

    workspace = WorkspaceRepository(database)
    connectors = ConnectorRepository(database)
    first = _with_user("user-a")
    try:
        plugin_a = workspace.create(Plugin, slug="google-workspace", name="Google", catalog_slug="google-workspace")
        connection_a = connectors.save_connection(
            "google-workspace", "ciphertext-a", "a@example.com", ["scope-a"], datetime.now(UTC) + timedelta(hours=1)
        )
    finally:
        current_user_id.reset(first)

    second = _with_user("user-b")
    try:
        plugin_b = workspace.create(Plugin, slug="google-workspace", name="Google", catalog_slug="google-workspace")
        connection_b = connectors.save_connection(
            "google-workspace", "ciphertext-b", "b@example.com", ["scope-b"], datetime.now(UTC) + timedelta(hours=1)
        )
        assert connectors.get_connection("google-workspace").id == connection_b.id
        assert workspace.get_plugin_by_catalog_slug("google-workspace").id == plugin_b.id
    finally:
        current_user_id.reset(second)

    again_first = _with_user("user-a")
    try:
        assert connectors.get_connection("google-workspace").id == connection_a.id
        assert workspace.get_plugin_by_catalog_slug("google-workspace").id == plugin_a.id
    finally:
        current_user_id.reset(again_first)


def test_admin_plugin_connection_metadata_never_selects_tokens(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'admin-connections.db'}")
    Base.metadata.create_all(database.engine)
    with database.session() as session:
        session.add(User(id="user-a", email="a@example.com"))
        session.commit()
    token = _with_user("user-a")
    try:
        ConnectorRepository(database).save_connection("google-workspace", "secret-ciphertext", "a@example.com", ["one", "two"], None)
    finally:
        current_user_id.reset(token)

    rows, total = ConnectorRepository(database).list_connection_metadata(0, 10)

    assert total == 1
    assert rows == [
        {
            "id": rows[0]["id"],
            "connector_slug": "google-workspace",
            "status": "connected",
            "scopes": ["one", "two"],
            "expires_at": None,
            "created_at": rows[0]["created_at"],
            "updated_at": rows[0]["updated_at"],
            "user_id": "user-a",
            "user_email": "a@example.com",
        }
    ]
    assert "encrypted_token" not in rows[0]
