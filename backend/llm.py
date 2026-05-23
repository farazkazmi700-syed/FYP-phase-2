import requests

from .config import Config


class GroqAPIError(RuntimeError):
    """Raised when the Groq API request fails."""


def build_llm_messages(context_rows) -> list:
    """FR8: build the model prompt from the complete multi-turn session context."""
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful, accurate, and concise AI assistant. "
                "Continue the current session naturally across multiple turns and topics. "
                "Provide clear, structured responses. If you are unsure, say so honestly."
            ),
        }
    ] + [{"role": row["role"], "content": row["content"]} for row in context_rows]


def query_llama(messages: list) -> str:
    """FR9: send the user query/context to the configured LLaMA 3 model."""
    if not Config.GROQ_API_KEY:
        return "GROQ_API_KEY is not configured. Please add it to your .env file."

    # FR9: Groq exposes LLaMA 3 through an OpenAI-compatible chat endpoint.
    headers = {
        "Authorization": f"Bearer {Config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    # FR9: the complete chat context is sent so LLaMA 3 can generate the next
    # assistant response for the active conversation.
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
        # FR9: return the generated LLaMA 3 text for the frontend to display.
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout as exc:
        raise GroqAPIError("Request timed out. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise GroqAPIError(f"API error: {exc}") from exc
    except (KeyError, IndexError) as exc:
        raise GroqAPIError("Unexpected response format from the API.") from exc
