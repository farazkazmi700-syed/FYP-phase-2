from flask import Blueprint, jsonify, render_template

from .db import get_db
from .utils import current_user, current_user_id, require_login

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics", methods=["GET"])
@require_login
def analytics_dashboard():
    """FR21: display the analytics dashboard page for logged-in users."""
    return render_template("analytics.html", user=current_user())


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
    correctness_counts = {
        "correct_replies_count": 0,
        "partially_correct_replies_count": 0,
        "incorrect_replies_count": 0,
    }

    for session_data in sessions:
        for message in session_data["messages"]:
            correctness = message.get("correctness")
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

            # FR18: count correctness categories from submitted feedback.
            if correctness == "Correct":
                correctness_counts["correct_replies_count"] += 1
            elif correctness == "Partial":
                correctness_counts["partially_correct_replies_count"] += 1
            elif correctness == "Incorrect":
                correctness_counts["incorrect_replies_count"] += 1

            if message.get("response_time_ms") is not None:
                response_times.append(message["response_time_ms"])

            if message.get("rating") is not None:
                ratings.append(message["rating"])

            length_type = message.get("length_type")
            if length_type in length_distribution:
                length_distribution[length_type] += 1

    total_correctness = sum(correctness_counts.values())
    correctness_percentage = None
    if total_correctness:
        weighted_correct = (
            correctness_counts["correct_replies_count"]
            + correctness_counts["partially_correct_replies_count"] * 0.5
        )
        correctness_percentage = round((weighted_correct / total_correctness) * 100, 2)

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
        "correctness_evaluation": {
            **correctness_counts,
            "overall_correctness_percentage": correctness_percentage,
        },
    }


def generate_analytical_tables(sessions: list[dict], metrics: dict) -> dict:
    """FR19: build analytical tables from computed session metrics."""
    reply_correctness_table = []
    rating_counts = {}

    for session_data in sessions:
        for message in session_data["messages"]:
            if message.get("correctness"):
                score = accuracy_score(message.get("correctness"))
                reply_correctness_table.append({
                    "message_id": message["id"],
                    "session_id": message["session_id"],
                    "topic": message.get("topic_label") or "general",
                    "phase": message.get("session_phase"),
                    "correctness": message.get("correctness"),
                    "accuracy": score,
                })

            rating = message.get("rating")
            if rating is not None:
                rating_counts[rating] = rating_counts.get(rating, 0) + 1

    # FR19: expose analytics as simple row-based tables for dashboards/reports.
    return {
        "topic_vs_accuracy": [
            {"topic": topic, "accuracy": accuracy}
            for topic, accuracy in metrics["accuracy_per_topic"].items()
        ],
        "reply_correctness_table": reply_correctness_table,
        "phase_wise_accuracy": [
            {"phase": phase, "accuracy": accuracy}
            for phase, accuracy in metrics["accuracy_per_phase"].items()
        ],
        "response_time_summary": [
            metrics["response_time_statistics"]
        ],
        "rating_distribution": [
            {"rating": rating, "count": count}
            for rating, count in sorted(rating_counts.items())
        ],
        "length_preference": [
            {"length_type": length_type, "count": count}
            for length_type, count in metrics["length_distribution"].items()
        ],
    }


def chart(title: str, chart_type: str, labels: list, values: list) -> dict:
    """FR20: return one chart-ready graph definition."""
    return {
        "title": title,
        "type": chart_type,
        "labels": labels,
        "values": values,
    }


def generate_visual_graphs(sessions: list[dict], metrics: dict, tables: dict) -> dict:
    """FR20: generate visual graph data for analytics charts."""
    topic_counts = {}
    response_labels = []
    response_values = []

    for session_data in sessions:
        for message in session_data["messages"]:
            if message.get("role") == "user":
                topic = message.get("message_domain") or "Machine Learning"
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

            if message.get("response_time_ms") is not None:
                response_labels.append(message.get("created_at") or message["id"])
                response_values.append(message["response_time_ms"])

    # FR20: return graph-ready values for pie, bar, and line charts.
    return {
        "topic_distribution": chart(
            "Topic distribution",
            "pie",
            list(topic_counts.keys()),
            list(topic_counts.values()),
        ),
        "accuracy_per_topic": chart(
            "Accuracy per topic",
            "bar",
            [row["topic"] for row in tables["topic_vs_accuracy"]],
            [row["accuracy"] for row in tables["topic_vs_accuracy"]],
        ),
        "accuracy_vs_phase": chart(
            "Accuracy vs phase",
            "line",
            [row["phase"] for row in tables["phase_wise_accuracy"]],
            [row["accuracy"] for row in tables["phase_wise_accuracy"]],
        ),
        "correctness_per_reply": chart(
            "Correctness per reply",
            "bar",
            [row["message_id"] for row in tables["reply_correctness_table"]],
            [row["accuracy"] for row in tables["reply_correctness_table"]],
        ),
        "response_time_trend": chart(
            "Response time trend",
            "line",
            response_labels,
            response_values,
        ),
        "rating_distribution": chart(
            "Rating distribution",
            "bar",
            [row["rating"] for row in tables["rating_distribution"]],
            [row["count"] for row in tables["rating_distribution"]],
        ),
        "length_preference": chart(
            "Length preference",
            "pie",
            [row["length_type"] for row in tables["length_preference"]],
            [row["count"] for row in tables["length_preference"]],
        ),
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

    metrics = compute_core_metrics(sessions)
    tables = generate_analytical_tables(sessions, metrics)
    return jsonify({
        "sessions": sessions,
        "metrics": metrics,
        "tables": tables,
        "graphs": generate_visual_graphs(sessions, metrics, tables),
    })
