"""Streamlit UI for persisted multi-provider chat and local PDF RAG."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st
from streamlit_js_eval import get_local_storage, set_local_storage

from agent_core.agent import Agent
from agent_core.config import Settings, load_settings
from agent_core.knowledge import KnowledgeService, build_knowledge_tool
from agent_core.providers import build_client
from agent_core.storage import ChatRepository, Database
from agent_core.tools import build_default_registry


THEME_STORAGE_KEY = "agent-series.theme"
THEME_OPTIONS = {"System": "system", "Light": "light", "Dark": "dark"}

st.set_page_config(page_title="Agent RAG", page_icon="✦", layout="wide", initial_sidebar_state="expanded")


def get_browser_theme() -> str:
    """Hydrate the theme from localStorage without blocking the first render."""
    stored_theme = get_local_storage(THEME_STORAGE_KEY, component_key="read-agent-series-theme")
    if "theme" not in st.session_state:
        st.session_state.theme = "system"
    if stored_theme in THEME_OPTIONS.values() and stored_theme != st.session_state.get("browser_theme_value"):
        st.session_state.theme = stored_theme
        st.session_state.browser_theme_value = stored_theme
    return st.session_state.theme


def inject_chat_styles(theme: str) -> None:
    """Apply a compact ChatGPT-inspired shell using Streamlit native controls."""
    theme_css = {
        "light": """
          --app-bg:#ffffff; --sidebar:#f7f7f8; --surface:#ffffff; --surface-muted:#f5f5f6;
          --ink:#1f1f22; --muted:#6f7078; --line:#e6e6e9; --hover:#ececef;
          --input-border:#d8d8dd; --focus:#8a8b93; --accent:#202123; --accent-ink:#ffffff;
          --code-bg:#f5f5f7; --shadow:0 8px 28px rgb(15 15 20 / .08);
        """,
        "dark": """
          --app-bg:#212121; --sidebar:#171717; --surface:#2a2a2d; --surface-muted:#303034;
          --ink:#f4f4f5; --muted:#a6a6ae; --line:#3b3b40; --hover:#303034;
          --input-border:#4a4a50; --focus:#a6a6ae; --accent:#f4f4f5; --accent-ink:#202124;
          --code-bg:#19191b; --shadow:0 10px 32px rgb(0 0 0 / .28);
        """,
    }
    selected_tokens = theme_css["dark"] if theme == "dark" else theme_css["light"]
    system_tokens = theme_css["dark"] if theme == "system" else ""

    st.markdown(
        f"""
        <style>
          :root {{ {selected_tokens} }}
          {'@media (prefers-color-scheme: dark) { :root {' + system_tokens + '} }' if system_tokens else ''}

          .stApp {{ background:var(--app-bg); color:var(--ink); }}
          header[data-testid="stHeader"] {{ display:none; }}
          [data-testid="stSidebar"] {{ background:var(--sidebar); border-right:1px solid var(--line); }}
          [data-testid="stSidebar"] > div:first-child {{ padding:.8rem .65rem 1.3rem; }}
          [data-testid="stSidebar"] .stButton > button {{
            border:0; box-shadow:none; background:transparent; color:var(--ink); border-radius:10px;
            min-height:2.4rem; text-align:left; padding:.45rem .65rem;
          }}
          [data-testid="stSidebar"] .stButton > button:hover {{ background:var(--hover); }}
          [data-testid="stSidebar"] .stButton > button:active {{ transform:scale(.99); }}
          [data-testid="stSidebar"] [data-testid="stExpander"],
          [data-testid="stSidebar"] [data-testid="stExpander"] details {{ border:0; background:transparent; }}
          [data-testid="stSidebar"] [data-testid="stRadio"] label {{ color:var(--ink); font-size:.85rem; }}

          .block-container {{ max-width:860px; padding:1.35rem 1.5rem 11rem; }}
          .agent-topbar {{ display:flex; align-items:center; gap:.65rem; min-height:2.35rem; margin-bottom:1.2rem; }}
          .agent-mark {{ width:27px; height:27px; border-radius:9px; background:var(--accent); color:var(--accent-ink); display:grid; place-items:center; font-size:14px; font-weight:700; }}
          .agent-name {{ color:var(--ink); font-size:16px; font-weight:650; letter-spacing:-.015em; }}
          .agent-model {{ color:var(--muted); font-size:13px; margin-left:auto; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
          .sidebar-brand {{ color:var(--ink); font-weight:650; font-size:16px; padding:.25rem .55rem .8rem; letter-spacing:-.02em; }}
          .sidebar-label {{ color:var(--muted); font-size:11px; font-weight:650; letter-spacing:.07em; text-transform:uppercase; margin:1rem .55rem .35rem; }}
          .sidebar-foot {{ color:var(--muted); font-size:12px; padding:.8rem .55rem 0; }}
          .knowledge-row {{ color:var(--muted); font-size:12px; padding:.25rem .15rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

          [data-testid="stChatMessage"] {{ background:transparent; padding:1rem 0; gap:.8rem; }}
          [data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {{ color:var(--ink); font-size:15px; line-height:1.7; max-width:760px; }}
          [data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"] {{ background:var(--surface-muted); color:var(--ink); }}
          [data-testid="stChatMessage"] pre {{ background:var(--code-bg) !important; border:1px solid var(--line); border-radius:12px; }}
          [data-testid="stChatMessage"] code {{ color:var(--ink); }}
          [data-testid="stStatusWidget"] {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; color:var(--ink); }}

          .welcome {{ min-height:52vh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }}
          .welcome h1 {{ color:var(--ink); font-size:clamp(26px,4vw,34px); letter-spacing:-.05em; margin:0 0 .5rem; font-weight:680; }}
          .welcome p {{ color:var(--muted); font-size:15px; margin:0; max-width:34rem; line-height:1.55; }}

          [data-testid="stChatInput"] {{ max-width:860px; margin:0 auto; padding:0 1.5rem 1.2rem; background:linear-gradient(180deg,transparent,var(--app-bg) 25%); }}
          [data-testid="stChatInput"] textarea {{
            color:var(--ink) !important; border:1px solid var(--input-border) !important; border-radius:18px !important;
            box-shadow:var(--shadow) !important; background:var(--surface) !important;
            padding:.85rem 3.1rem .85rem 1rem !important; min-height:54px !important;
          }}
          [data-testid="stChatInput"] textarea::placeholder {{ color:var(--muted) !important; }}
          [data-testid="stChatInput"] textarea:focus {{ border-color:var(--focus) !important; box-shadow:0 0 0 3px color-mix(in srgb,var(--focus) 18%,transparent),var(--shadow) !important; }}
          [data-testid="stChatInput"] button {{ background:var(--accent) !important; color:var(--accent-ink) !important; }}

          .st-key-composer_toolbar {{
            position:fixed; z-index:40; bottom:4.9rem; left:max(22rem,calc(50% - 504px));
            width:min(820px,calc(100vw - 24rem)); padding:.15rem .5rem; border:1px solid var(--line);
            border-bottom:0; border-radius:14px 14px 0 0; background:var(--surface); box-shadow:0 -5px 18px rgb(0 0 0 / .04);
          }}
          .st-key-composer_toolbar [data-testid="stSelectbox"] label {{ display:none; }}
          .st-key-composer_toolbar [data-testid="stSelectbox"] > div > div {{ background:transparent; border:0; min-height:2rem; color:var(--muted); font-size:.78rem; }}
          .st-key-composer_toolbar .stButton > button {{ border:0; background:transparent; color:var(--muted); min-height:2rem; padding:.25rem .45rem; font-size:.78rem; }}
          .st-key-composer_toolbar .stButton > button:hover {{ background:var(--hover); color:var(--ink); }}

          @media (max-width: 850px) {{
            .block-container {{ padding:.9rem 1rem 10.5rem; }}
            .agent-model {{ display:none; }}
            .st-key-composer_toolbar {{ left:.8rem; width:calc(100vw - 1.6rem); }}
            [data-testid="stChatInput"] {{ padding:0 .8rem .8rem; }}
          }}
          @media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior:auto !important; transition:none !important; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_database(url: str) -> Database:
    return Database(url)


@st.cache_resource
def get_knowledge(url: str, directory: str, model: str) -> KnowledgeService:
    return KnowledgeService(get_database(url), __import__("pathlib").Path(directory), model)


def make_agent(settings: Settings, knowledge: KnowledgeService, history: list[dict]) -> Agent:
    agent = Agent(
        build_client(settings), build_default_registry(build_knowledge_tool(knowledge)), max_steps=settings.max_steps
    )
    agent.history = history
    return agent


def ingest_uploaded_pdfs(knowledge: KnowledgeService, files: Iterable[object]) -> list[str]:
    """Persist and index PDFs submitted from the native chat composer."""
    messages: list[str] = []
    for uploaded in files:
        document, created = knowledge.upload(uploaded.name, uploaded.getvalue())
        document = knowledge.index(document.id) if created or document.status != "ready" else document
        if document.status != "ready":
            raise RuntimeError(f"Không thể index {document.original_name}: {document.error}")
        messages.append(f"{document.original_name} ({document.page_count} trang)")
    return messages


theme = get_browser_theme()
inject_chat_styles(theme)

try:
    base_settings = load_settings()
    database = get_database(base_settings.database_url)
    chats = ChatRepository(database)
    knowledge = get_knowledge(base_settings.database_url, str(base_settings.knowledge_dir), base_settings.embedding_model)
    configured_models = base_settings.configured_provider_models()
    if not configured_models:
        raise RuntimeError("Chưa có provider nào có API key và model allowlist hợp lệ trong .env.")
    chat_list = chats.list()
except Exception as exc:  # noqa: BLE001
    st.error(f"Không thể khởi động ứng dụng: {exc}")
    st.info("Hãy chạy `docker compose up -d`, `alembic upgrade head`, rồi kiểm tra `.env`.")
    st.stop()

if "active_chat_id" not in st.session_state:
    initial = chat_list[0] if chat_list else chats.create(base_settings.provider, base_settings.active_model)
    st.session_state.active_chat_id = initial.id

active_chat = chats.get(st.session_state.active_chat_id)
if active_chat is None:
    active_chat = chats.create(base_settings.provider, base_settings.active_model)
    st.session_state.active_chat_id = active_chat.id

current_settings = base_settings.with_provider_model(active_chat.provider, active_chat.model)
history = chats.history(active_chat.id)
agent = make_agent(current_settings, knowledge, history)

with st.sidebar:
    st.markdown('<div class="sidebar-brand">✦ Local Agent</div>', unsafe_allow_html=True)
    if st.button("+  New chat", use_container_width=True):
        chat = chats.create(current_settings.provider, current_settings.active_model)
        st.session_state.active_chat_id = chat.id
        st.rerun()

    st.markdown('<div class="sidebar-label">Chats</div>', unsafe_allow_html=True)
    for chat in chat_list:
        title = chat.title.strip() or "Cuộc trò chuyện mới"
        if st.button(title[:42], key=f"chat-{chat.id}", use_container_width=True, type="secondary"):
            if chat.id != active_chat.id:
                st.session_state.active_chat_id = chat.id
                st.rerun()

    st.markdown('<div class="sidebar-label">Knowledge</div>', unsafe_allow_html=True)
    documents = knowledge.list_documents()
    if documents:
        for document in documents:
            state = "Ready" if document.status == "ready" else document.status
            st.markdown(f'<div class="knowledge-row">{state} · {document.original_name}</div>', unsafe_allow_html=True)
    else:
        st.caption("Đính kèm PDF trong ô chat để tạo knowledge base.")

    st.markdown('<div class="sidebar-label">Appearance</div>', unsafe_allow_html=True)
    selected_theme_label = st.radio(
        "Theme",
        list(THEME_OPTIONS),
        index=list(THEME_OPTIONS.values()).index(theme),
        horizontal=True,
        label_visibility="collapsed",
    )
    selected_theme = THEME_OPTIONS[selected_theme_label]
    if selected_theme != theme:
        st.session_state.theme = selected_theme
        st.session_state.browser_theme_value = selected_theme
        set_local_storage(THEME_STORAGE_KEY, selected_theme, component_key="save-agent-series-theme")
        st.rerun()

    st.markdown(
        f'<div class="sidebar-foot">{current_settings.provider} · {current_settings.active_model}</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div class="agent-topbar"><span class="agent-mark">✦</span><span class="agent-name">Local Agent</span><span class="agent-model">{current_settings.active_model}</span></div>',
    unsafe_allow_html=True,
)

visible_messages = [
    message for message in agent.history if message["role"] in {"user", "assistant"} and not message.get("tool_calls")
]
if not visible_messages:
    st.markdown(
        "<div class='welcome'><h1>How can I help you today?</h1><p>Ask about your documents, reason through a task, or start a new idea.</p></div>",
        unsafe_allow_html=True,
    )

for message in visible_messages:
    with st.chat_message(message["role"]):
        st.markdown(message.get("content", ""))

with st.container(key="composer_toolbar"):
    toolbar_provider, toolbar_model, toolbar_apply = st.columns([1.15, 2.6, 0.9])
    with toolbar_provider:
        selected_provider = st.selectbox(
            "Provider",
            list(configured_models),
            index=list(configured_models).index(active_chat.provider),
            key="composer_provider",
            label_visibility="collapsed",
        )
    with toolbar_model:
        available_models = list(configured_models[selected_provider])
        selected_model = st.selectbox(
            "Model",
            available_models,
            index=available_models.index(active_chat.model) if active_chat.model in available_models else 0,
            key="composer_model",
            label_visibility="collapsed",
        )
    with toolbar_apply:
        apply_model = st.button("Apply", key="apply_composer_model", use_container_width=True)

if apply_model:
    if selected_provider == active_chat.provider:
        if selected_model != active_chat.model:
            chats.update_model(active_chat.id, selected_provider, selected_model)
            st.rerun()
    else:
        chat = chats.create(selected_provider, selected_model)
        st.session_state.active_chat_id = chat.id
        st.rerun()

submission = st.chat_input(
    "Hỏi về tài liệu đã index hoặc đặt câu hỏi bất kỳ...",
    accept_file="multiple",
    file_type=["pdf"],
    max_upload_size=25,
)

if submission:
    prompt = submission.text
    uploaded_files = submission.files
    indexed_files: list[str] = []

    if uploaded_files:
        with st.status("Đang thêm tài liệu vào knowledge base...", expanded=True) as upload_status:
            try:
                indexed_files = ingest_uploaded_pdfs(knowledge, uploaded_files)
                upload_status.update(label="Đã index tài liệu", state="complete", expanded=False)
            except Exception as exc:  # noqa: BLE001
                upload_status.update(label="Không thể index tài liệu", state="error")
                st.error(str(exc))

    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
            if indexed_files:
                st.caption(f"Đã đính kèm: {', '.join(indexed_files)}")
        with st.chat_message("assistant"):
            status = st.status("Agent đang suy nghĩ...", expanded=True)

            def on_step(event: dict) -> None:
                if event["type"] == "tool_call":
                    status.write(f"Đang dùng `{event['name']}` với `{event['args']}`")
                else:
                    status.write(f"Đã nhận kết quả: {event['result'][:300]}")

            try:
                result = agent.run(prompt, on_step=on_step)
                chats.replace_history(active_chat.id, agent.history)
                status.update(label="Đã xong", state="complete", expanded=False)
                st.markdown(result.text)
            except Exception as exc:  # noqa: BLE001
                status.update(label="Có lỗi", state="error")
                st.error(f"Lỗi khi gọi model: {exc}")
    elif indexed_files:
        st.success(f"Đã sẵn sàng truy vấn: {', '.join(indexed_files)}")
