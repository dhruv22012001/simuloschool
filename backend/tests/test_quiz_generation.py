import pytest

from app.core.config import (
    EASY_QUESTION_COUNT,
    HARD_QUESTION_COUNT,
    MEDIUM_QUESTION_COUNT,
)
from app.models.base import Difficulty
from app.services.quiz_generation import (
    OPTIONS_PER_QUESTION,
    GeneratedQuestion,
    GeneratedQuiz,
    GenerationError,
    _validate,
)


def _question(difficulty: Difficulty, correct_idx: int = 0) -> GeneratedQuestion:
    return GeneratedQuestion(
        difficulty=difficulty,
        text=f"A {difficulty} question?",
        options=[f"option {i}" for i in range(OPTIONS_PER_QUESTION)],
        correct_idx=correct_idx,
    )


def _valid_quiz() -> GeneratedQuiz:
    counts = {
        Difficulty.easy: EASY_QUESTION_COUNT,
        Difficulty.medium: MEDIUM_QUESTION_COUNT,
        Difficulty.hard: HARD_QUESTION_COUNT,
    }
    return GeneratedQuiz(
        questions=[
            _question(d, i % OPTIONS_PER_QUESTION)
            for d, n in counts.items()
            for i in range(n)
        ]
    )


def test_valid_quiz_passes():
    _validate(_valid_quiz())  # does not raise


def test_wrong_tier_counts_rejected():
    quiz = _valid_quiz()
    quiz.questions.pop()  # one hard question short
    with pytest.raises(GenerationError, match="hard questions"):
        _validate(quiz)


def test_correct_idx_out_of_range_rejected():
    quiz = _valid_quiz()
    quiz.questions[0].correct_idx = OPTIONS_PER_QUESTION
    with pytest.raises(GenerationError, match="out of range"):
        _validate(quiz)


def test_wrong_option_count_rejected():
    quiz = _valid_quiz()
    quiz.questions[0].options = ["only one"]
    with pytest.raises(GenerationError, match="options"):
        _validate(quiz)


def test_empty_question_text_rejected():
    quiz = _valid_quiz()
    quiz.questions[0].text = "   "
    with pytest.raises(GenerationError, match="empty text"):
        _validate(quiz)
