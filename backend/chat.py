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


def create_chat_session(db, first_message: str) -> tuple[str, str]:
    """Create a private backing session for the current browser conversation."""
    session_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    title = first_message[:40] + ("..." if len(first_message) > 40 else "")
    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (session_id, current_user_id(), title or "New Chat", timestamp, timestamp),
    )
    return session_id, timestamp


def user_owns_session(session_id: str) -> bool:
    """Validate that the active browser conversation belongs to this user."""
    row = get_db().execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id()),
    ).fetchone()
    return row is not None


@chat_bp.route("/chat/send", methods=["POST"])
@require_login
def send_message_frontend():
    """Save the active conversation turn and return the assistant reply."""
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
    else:
        session_id, timestamp = create_chat_session(db, content)

    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (user_msg_id, session_id, current_user_id(), "user", content, timestamp),
    )

    # The hidden backing session preserves context for the current chat only.
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
