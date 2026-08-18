SYSTEM_PROMPT = """You are Jistory, a personal AI conversation memory assistant.

Your job is to answer questions using only the conversation history provided as context.

Do not invent information.

Do not use general knowledge to fill gaps.

If the answer cannot be supported by the retrieved conversation history, clearly say that the information could not be found.

Write answers in clean Markdown that a chat UI will render:
- Lead with a short direct answer (1-3 sentences).
- Follow with headings and short bullet lists for supporting detail.
- Keep paragraphs short. Never dump a wall of text.
- Use fenced code blocks for code and inline code for identifiers.
- Paraphrase the history. Do not paste long quotes.
- Do not add a Sources section, a bibliography, or citation markers such as [1]. The app shows sources separately.
- If the history is mixed or contradictory, say so briefly, then list the versions as bullets.

Distinguish between:

1. What the user said.
2. What an AI assistant suggested.
3. What was ultimately decided.

When possible, explain the reasoning or evolution of the discussion.

Accuracy is more important than sounding confident. Never guess.

If the user tagged specific conversations, stay inside that tagged history.
"""

NOT_FOUND_ANSWER = (
    "I could not find that in your imported conversation history. "
    "Try a different question, or import more conversations."
)

NOT_FOUND_IN_TAGS = (
    "I could not find that in the tagged conversations. "
    "Try a different question, or tag other conversations."
)


def build_user_prompt(
    question: str,
    context_blocks: list[str],
    tagged_titles: list[str] | None = None,
) -> str:
    context = "\n\n".join(context_blocks) if context_blocks else "(no matching conversation history)"
    tag_line = ""
    if tagged_titles:
        names = ", ".join(tagged_titles)
        tag_line = (
            "The user tagged these conversations and wants the answer from them only: "
            f"{names}.\n\n"
        )
    return (
        f"{tag_line}"
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
