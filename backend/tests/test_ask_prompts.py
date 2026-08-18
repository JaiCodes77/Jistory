from app.ask.prompts import SYSTEM_PROMPT, build_user_prompt


def test_system_prompt_asks_for_readable_markdown() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "markdown" in lowered
    assert "sources separately" in lowered
    assert "[1]" in SYSTEM_PROMPT or "citation" in lowered


def test_user_prompt_keeps_history_and_question() -> None:
    prompt = build_user_prompt("What did I decide?", ["[1] Grafana — ChatGPT — 2024\nUse Prometheus."])
    assert "What did I decide?" in prompt
    assert "CONVERSATION HISTORY" in prompt
    assert "Prometheus" in prompt
