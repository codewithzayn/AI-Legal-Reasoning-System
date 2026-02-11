"""
Relevancy check for generated answers.
Uses a compact representation (truncated answer + cited sources) to stay within LLM context limits.
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Max characters of the answer to send (keeps context small)
MAX_ANSWER_CHARS = 1400

# Citation patterns: KKO:YYYY:N, KHO:..., § N, [§ 4], etc.
CITE_PATTERNS = [
    r"KKO\s*:\s*\d{4}\s*:\s*\d+",
    r"KHO\s*[:\s]*\d{4}[^\s]*\s*\d+",
    r"\[\s*§\s*\d+[a-z]?\s*\]",
    r"§\s*\d+[a-z]?(?:\s+momentti)?",
]


def _compact_answer(answer: str, max_chars: int = MAX_ANSWER_CHARS) -> str:
    """
    Build a compact representation for the relevancy LLM:
    - Truncated answer (first max_chars)
    - Plus a line listing cited sources extracted from the full answer (so we don't send full text).
    """
    if not answer or not answer.strip():
        return ""

    # Extract citation-like refs from the full answer (so we capture sources even if they appear after truncation)
    seen = set()
    for pat in CITE_PATTERNS:
        for m in re.finditer(pat, answer, re.IGNORECASE):
            ref = m.group(0).strip()
            # Normalize for dedup
            n = re.sub(r"\s+", " ", ref)
            if n not in seen:
                seen.add(n)
    refs_line = "Lähteet vastauksessa: " + ", ".join(sorted(seen)) if seen else ""

    truncated = answer.strip()
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars].rsplit(maxsplit=1)[0] + " […]"

    if refs_line:
        truncated += "\n\n" + refs_line
    return truncated


RELEVANCY_SYSTEM = """You are a relevancy and correctness checker for a Finnish legal Q&A system. You receive:
1) The user's question (KYSYMYS)
2) A compact excerpt of the system's answer (truncated to save space) and the list of sources cited in the full answer.

Your task: Rate 1-5 how well the answer is both relevant AND legally sound. Consider:

RELEVANCE:
- Does the answer address what was asked (e.g. jurisdiction vs. sentencing vs. liability), or does it mix in unrelated legal issues?
- Is the answer focused or does it drift to other topics?

CORRECT USE OF SOURCES (important):
- If the question is "when" or "under what conditions" something applies, the answer should be based on the provision that governs that (e.g. the relevant §). If it only cites cases that deal with the opposite situation (e.g. when something is transferred out or excluded) without clearly explaining the governing rule, that is a flaw — lower the score.
- If the answer uses a cited case to support a rule that the case actually contradicts (e.g. says "case X shows that A applies" when case X held that B applies instead), that is a serious flaw — score no higher than 2.
- Appropriate sources and correct application of precedent should increase the score.

Output ONLY valid JSON with two keys:
- "score": integer 1-5 (1=off-topic or clearly misuses sources, 5=relevant, focused, and correct use of sources)
- "reason": one short sentence in Finnish explaining the score (e.g. "Vastaus keskittyy kysymykseen ja käyttää lähteitä oikein." or "Ennakkotapaus käytetty väärin päin; vastaus ei perustu kysymykseen 'milloin' vastaavaan pykälään.")

Example: {"score": 3, "reason": "Vastaus on aiheesta, mutta ennakkotapauksen käyttö on harhaanjohtava tai puuttuu vastaava pykälä."}
"""


async def check_relevancy(query: str, answer: str) -> dict:
    """
    Check how relevant the generated answer is to the user query.
    Sends only a compact representation (truncated answer + cited sources) to respect context limits.

    Returns:
        {"score": int 1-5, "reason": str}
        On parse/API error: {"score": 0, "reason": "Relevanssin tarkistus epäonnistui."}
    """
    compact = _compact_answer(answer)
    if not compact:
        return {"score": 0, "reason": "Tyhjä vastaus."}

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=150)
    user_content = f"KYSYMYS:\n{query}\n\nVASTAUKSEN TIivistelmä / ote:\n{compact}"

    try:
        response = await llm.ainvoke([SystemMessage(content=RELEVANCY_SYSTEM), HumanMessage(content=user_content)])
        text = (response.content or "").strip()
        # Allow markdown code block
        if "```" in text:
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        data = json.loads(text)
        score = int(data.get("score", 0))
        score = max(score, 1)
        score = min(score, 5)
        reason = str(data.get("reason", "")) or "—"
        logger.info(f"Relevancy check: score={score}, reason={reason[:80]}")
        return {"score": score, "reason": reason}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Relevancy check failed: {e}")
        return {"score": 0, "reason": "Relevanssin tarkistus epäonnistui."}
