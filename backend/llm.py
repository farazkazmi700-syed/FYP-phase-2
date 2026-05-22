import requests

from .config import Config


class GroqAPIError(RuntimeError):
    """Raised when the Groq API request fails."""


def build_llm_messages(context_rows) -> list:
    """Build the OpenAI-compatible message list sent to Groq."""
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful, accurate, and concise AI assistant. "
                "Provide clear, structured responses. If you are unsure, say so honestly."
            ),
        }
    ] + [{"role": row["role"], "content": row["content"]} for row in context_rows]


def query_llama(messages: list) -> str:
    """Send the current conversation context to Groq and return the assistant text."""
    if not Config.GROQ_API_KEY:
        return "GROQ_API_KEY is not configured. Please add it to your .env file."

    headers = {
        "Authorization": f"Bearer {Config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": Config.LLAMA_MODEL,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False,
    }

    try:
        response = requests.post(Config.GROQ_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout as exc:
        raise GroqAPIError("Request timed out. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise GroqAPIError(f"API error: {exc}") from exc
    except (KeyError, IndexError) as exc:
        raise GroqAPIError("Unexpected response format from the API.") from exc
