from flask import Blueprint, jsonify

from .db import get_db
from .utils import current_user_id, require_login

analytics_bp = Blueprint("analytics", __name__)


def phase_for_message(index: int, total_messages: int) -> str:
    """FR16: split a session timeline into start, middle, and end phases."""
    if total_messages <= 1:
        return "Start phase"

    progress = index / (total_messages - 1)
    if progress < 0.34:
        return "Start phase"
    if progress < 0.67:
        return "Middle phase"
    return "End phase"


def segment_session_messages(messages: list[dict]) -> dict:
    """FR16: group stored session messages by conversation phase."""
    phases = {
        "Start phase": [],
        "Middle phase": [],
        "End phase": [],
    }
    total_messages = len(messages)

    for index, message in enumerate(messages):
        phase = phase_for_message(index, total_messages)
        message["session_phase"] = phase
        phases[phase].append(message)

    return phases


def accuracy_score(correctness: str | None) -> float | None:
    """FR17: convert feedback correctness into a numeric accuracy score."""
    scores = {
        "Correct": 1.0,
        "Partial": 0.5,
        "Incorrect": 0.0,
    }
    return scores.get(correctness)


def average(values: list[float]) -> float | None:
    """FR17: return a rounded average when metric values exist."""
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def compute_core_metrics(sessions: list[dict]) -> dict:
    """FR17: compute accuracy, timing, rating, and length analytics."""
    accuracy_per_reply = []
    accuracy_by_topic = {}
    accuracy_by_phase = {
        "Start phase": [],
        "Middle phase": [],
        "End phase": [],
    }
    response_times = []
    ratings = []
    length_distribution = {
        "Short": 0,
        "To the Point": 0,
        "Lengthy": 0,
    }

    for session_data in sessions:
        for message in session_data["messages"]:
            score = accuracy_score(message.get("correctness"))
            if score is not None:
                accuracy_per_reply.append({
                    "message_id": message["id"],
                    "session_id": message["session_id"],
                    "accuracy": score,
                })
                topic = message.get("topic_label") or "general"
                phase = message.get("session_phase") or "Start phase"
                accuracy_by_topic.setdefault(topic, []).append(score)
                accuracy_by_phase.setdefault(phase, []).append(score)

            if message.get("response_time_ms") is not None:
                response_times.append(message["response_time_ms"])

            if message.get("rating") is not None:
                ratings.append(message["rating"])

            length_type = message.get("length_type")
            if length_type in length_distribution:
                length_distribution[length_type] += 1

    # FR17: summarize grouped lists into concise analytics values.
    return {
        "accuracy_per_reply": accuracy_per_reply,
        "accuracy_per_topic": {
            topic: average(scores)
            for topic, scores in accuracy_by_topic.items()
        },
        "accuracy_per_phase": {
            phase: average(scores)
            for phase, scores in accuracy_by_phase.items()
        },
        "response_time_statistics": {
            "count": len(response_times),
            "average_ms": average(response_times),
            "minimum_ms": min(response_times) if response_times else None,
            "maximum_ms": max(response_times) if response_times else None,
        },
        "rating_averages": {
            "count": len(ratings),
            "average": average(ratings),
        },
        "length_distribution": length_distribution,
    }


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
            messages.message_domain,
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
        # FR16: divide every session into start, middle, and end message groups.
        session_data["phases"] = segment_session_messages(session_data["messages"])
        sessions.append(session_data)

    return jsonify({
        "sessions": sessions,
        "metrics": compute_core_metrics(sessions),
    })
