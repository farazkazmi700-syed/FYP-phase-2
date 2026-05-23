from flask import Blueprint, jsonify

from .db import get_db
from .utils import current_user_id, require_login

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/api/analytics/sessions", methods=["GET"])
@require_login
def get_analytics_sessions():
    """Fetch stored chat sessions and messages for analytics analysis."""
    db = get_db()

    # FR14: retrieve stored session data for the logged-in user from the database.
    session_rows = db.execute(
        """
        SELECT id, title, created_at, updated_at
        FROM chat_sessions
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (current_user_id(),),
    ).fetchall()

    message_rows = db.execute(
        """
        SELECT
            messages.id,
            messages.session_id,
            messages.role,
            messages.content,
            messages.topic_label,
            messages.created_at,
            messages.response_time_ms,
            feedback.rating,
            feedback.correctness,
            feedback.length_type
        FROM messages
        LEFT JOIN feedback ON feedback.message_id = messages.id
        WHERE messages.user_id = ?
        ORDER BY messages.created_at ASC
        """,
        (current_user_id(),),
    ).fetchall()

    messages_by_session = {row["id"]: [] for row in session_rows}
    for row in message_rows:
        messages_by_session.setdefault(row["session_id"], []).append(dict(row))

    sessions = []
    for row in session_rows:
        session_data = dict(row)
        session_data["messages"] = messages_by_session.get(row["id"], [])
        sessions.append(session_data)

    return jsonify({"sessions": sessions})
