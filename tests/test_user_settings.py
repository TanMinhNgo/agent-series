"""Account personalization remains available across workspaces."""

from agent_core.knowledge.personalization import PersonalizationService
from agent_core.persistence.models import Base, User, UserPreference, Workspace, current_user_id, current_workspace_id
from agent_core.persistence.database import Database


def test_account_preferences_cross_workspace_and_auto_learn_toggle():
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine, tables=[User.__table__, Workspace.__table__, UserPreference.__table__])
    with database.session() as session:
        session.add(User(id="u", email="u@example.com"))
        session.add_all([Workspace(id="w1", name="One"), Workspace(id="w2", name="Two")])
        session.commit()
    service = PersonalizationService(database)
    user_token = current_user_id.set("u")
    workspace_token = current_workspace_id.set("w1")
    try:
        service.update_settings("u", {"custom_instructions": "Trả lời bằng tiếng Việt", "auto_learn": True})
        service.observe_user_message("React backend API")
        current_workspace_id.set("w2")
        assert "Trả lời bằng tiếng Việt" in service.context()
        service.update_settings("u", {"auto_learn": False})
        service.observe_user_message("React backend API")
        with database.session() as session:
            profile = service._account_profile(session, "u")
            assert profile.topic_counts["software_engineering"] == 1
        assert "Cá nhân hóa từ hành vi" not in service.context()
        service.clear_learned("u")
        assert service.context().endswith("Trả lời bằng tiếng Việt")
    finally:
        current_workspace_id.reset(workspace_token)
        current_user_id.reset(user_token)
