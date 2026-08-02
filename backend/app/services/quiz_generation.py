"""Transcript -> tiered MCQ quiz, via the Claude API.

Produces exactly EASY/MEDIUM/HARD_QUESTION_COUNT questions per video (the locked
product rule). Claude is forced into a JSON schema, so the result is validated
structurally before we ever touch the database; the count and answer-index
checks below cover what JSON Schema can't express.
"""

import logging

import anthropic
from pydantic import BaseModel, Field

from app.core.config import (
    EASY_QUESTION_COUNT,
    HARD_QUESTION_COUNT,
    MEDIUM_QUESTION_COUNT,
    settings,
)
from app.models.base import Difficulty

logger = logging.getLogger(__name__)

OPTIONS_PER_QUESTION = 4

# Transcripts are truncated so a long lesson can't blow past the context window.
MAX_TRANSCRIPT_CHARS = 400_000


class GeneratedQuestion(BaseModel):
    difficulty: Difficulty
    text: str = Field(description="The question stem, answerable from the lesson alone.")
    options: list[str] = Field(description=f"Exactly {OPTIONS_PER_QUESTION} answer choices.")
    correct_idx: int = Field(description="0-based index into options of the single correct answer.")


class GeneratedQuiz(BaseModel):
    questions: list[GeneratedQuestion]


class GenerationError(RuntimeError):
    pass


SYSTEM_PROMPT = f"""You write multiple-choice quizzes for school students from lesson \
video transcripts.

Produce exactly {EASY_QUESTION_COUNT} easy, {MEDIUM_QUESTION_COUNT} medium, and \
{HARD_QUESTION_COUNT} hard questions — no more, no fewer.

Rules for every question:
- Answerable from the transcript alone. Never rely on outside knowledge.
- Exactly {OPTIONS_PER_QUESTION} options with exactly one correct answer; the other three \
must be plausible to a student who did not understand the lesson.
- Vary which index holds the correct answer.
- No "all of the above", "none of the above", or options that reference other options.
- Write at the reading level of the students the lesson targets.

Difficulty means depth of understanding, not obscurity:
- easy: recall of a fact or definition stated directly in the lesson.
- medium: connecting two ideas, or applying a stated rule to a simple new case.
- hard: reasoning about why something works, or applying the concept to an unfamiliar case."""


def _build_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise GenerationError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _validate(quiz: GeneratedQuiz) -> None:
    expected = {
        Difficulty.easy: EASY_QUESTION_COUNT,
        Difficulty.medium: MEDIUM_QUESTION_COUNT,
        Difficulty.hard: HARD_QUESTION_COUNT,
    }
    for difficulty, want in expected.items():
        got = sum(1 for q in quiz.questions if q.difficulty == difficulty)
        if got != want:
            raise GenerationError(f"expected {want} {difficulty} questions, got {got}")

    for i, q in enumerate(quiz.questions):
        if len(q.options) != OPTIONS_PER_QUESTION:
            raise GenerationError(f"question {i} has {len(q.options)} options")
        if not 0 <= q.correct_idx < len(q.options):
            raise GenerationError(f"question {i} has correct_idx {q.correct_idx} out of range")
        if not q.text.strip():
            raise GenerationError(f"question {i} has empty text")


def generate_quiz(title: str, transcript: str) -> GeneratedQuiz:
    """Call Claude once, retrying once if the returned quiz fails validation."""
    client = _build_client()
    transcript = transcript[:MAX_TRANSCRIPT_CHARS]
    user_prompt = (
        f"Lesson title: {title}\n\n"
        f"Transcript:\n<transcript>\n{transcript}\n</transcript>\n\n"
        "Write the quiz."
    )

    last_error: Exception | None = None
    for attempt in (1, 2):
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=GeneratedQuiz,
        )
        if response.stop_reason == "refusal":
            raise GenerationError("model declined to generate questions for this lesson")
        quiz = response.parsed_output
        if quiz is None:
            last_error = GenerationError("model returned no parseable quiz")
        else:
            try:
                _validate(quiz)
                return quiz
            except GenerationError as err:
                last_error = err
        logger.warning(
            "quiz generation attempt failed", extra={"ctx": {"attempt": attempt}}
        )

    raise GenerationError(f"quiz generation failed after 2 attempts: {last_error}")
