import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, session

from .db import get_db
from .llm import GroqAPIError, build_llm_messages, query_llama
from .utils import current_user, current_user_id, json_payload, require_login

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat")
@require_login
def chat():
    """Render the chat page without loading saved conversations."""
    return render_template(
        "chat.html",
        user=current_user(),
        username=session.get("username"),
    )


def session_title(first_message: str | None = None) -> str:
    """Return a short title for a chat session."""
    if not first_message:
        return "New Chat"
    return first_message[:40] + ("..." if len(first_message) > 40 else "")


def create_chat_session(db, first_message: str | None = None) -> tuple[str, str]:
    """FR7: create a unique private session for one independent conversation."""
    session_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (session_id, current_user_id(), session_title(first_message), timestamp, timestamp),
    )
    return session_id, timestamp


def rename_session_from_first_message(db, session_id: str, first_message: str) -> None:
    """FR7: replace the temporary title once the session receives its first turn."""
    existing_messages = db.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if existing_messages and existing_messages["total"] == 0:
        db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (session_title(first_message), datetime.utcnow().isoformat(), session_id),
        )


def user_owns_session(session_id: str) -> bool:
    """FR7: validate that the active browser conversation belongs to this user."""
    row = get_db().execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id()),
    ).fetchone()
    return row is not None


@chat_bp.route("/chat/session/new", methods=["POST"])
@require_login
def new_chat_session():
    """FR7: generate a unique session ID before the first chat message is sent."""
    db = get_db()
    session_id, timestamp = create_chat_session(db)
    db.commit()
    return jsonify({
        "session_id": session_id,
        "created_at": timestamp,
    })


@chat_bp.route("/chat/send", methods=["POST"])
@require_login
def send_message_frontend():
    """FR7: save one turn inside the active independent conversation session."""
    payload = json_payload()
    content = payload.get("content", "").strip()
    session_id = payload.get("session_id")
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    db = get_db()
    if session_id:
        if not user_owns_session(session_id):
            return jsonify({"error": "Conversation not found."}), 404
        timestamp = datetime.utcnow().isoformat()
        rename_session_from_first_message(db, session_id, content)
    else:
        # Backward compatibility: clients that do not pre-create a session still
        # get an isolated UUID conversation on their first message.
        session_id, timestamp = create_chat_session(db, content)

    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (user_msg_id, session_id, current_user_id(), "user", content, timestamp),
    )

    # FR7: only messages from this session are sent to the model, so each chat
    # keeps its own conversation state independent from other sessions.
    context_rows = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    try:
        assistant_content = query_llama(build_llm_messages(context_rows))
    except GroqAPIError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 502

    reply_ts = datetime.utcnow().isoformat()
    assistant_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (assistant_msg_id, session_id, current_user_id(), "assistant", assistant_content, reply_ts),
    )
    db.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (reply_ts, session_id))
    db.commit()

    return jsonify({
        "session_id": session_id,
        "user_message_id": user_msg_id,
        "message_id": assistant_msg_id,
        "response": assistant_content,
        "timestamp": reply_ts,
    })
