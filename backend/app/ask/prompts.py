SYSTEM_PROMPT = """You are Jistory, a personal AI conversation memory assistant.

Your job is to answer questions using only the conversation history provided as context.

Do not invent information.

Do not use general knowledge to fill gaps.

If the answer cannot be supported by the retrieved conversation history, clearly say that the information could not be found.

Distinguish between:

1. What the user said.
2. What an AI assistant suggested.
3. What was ultimately decided.

When possible, explain the reasoning or evolution of the discussion.

Always provide citations to the source conversations used, using the source numbers supplied in the context (for example [1], [2]).

Accuracy is more important than sounding confident. Never guess.
"""

NOT_FOUND_ANSWER = (
    "I could not find that in your imported conversation history. "
    "Try a different question, or import more conversations."
)


def build_user_prompt(question: str, context_blocks: list[str]) -> str:
    context = "\n\n".join(context_blocks) if context_blocks else "(no matching conversation history)"
    return (
        "Use only the conversation history below.\n\n"
        "===== CONVERSATION HISTORY =====\n"
        f"{context}\n"
        "===== END CONVERSATION HISTORY =====\n\n"
        f"Question: {question}\n"
    )


def format_context_block(index: int, *, title: str | None, source: str, timestamp: str, text: str) -> str:
    heading = title or "Untitled conversation"
    return (
        f"[{index}] {heading} — {source} — {timestamp}\n"
        f"{text.strip()}"
    )
