import re

import pytest

from companion.persona import load_examples
from companion.reply import Mood

TAG = re.compile(rf"^\[mood:({'|'.join(m.value for m in Mood)})\] \S")
CONTRACTION = re.compile(r"\b\w+'(?:t|re|ll|ve|d|m)\b|\b(?:it|that|what|he|she|there)'s\b", re.IGNORECASE)

EXAMPLES = load_examples()
BOT_LINES = [m["content"] for c in EXAMPLES for m in c if m["role"] == "assistant"]


def test_every_conversation_alternates_and_ends_with_the_bot():
    for conversation in EXAMPLES:
        roles = [m["role"] for m in conversation]
        assert roles == ["user", "assistant"] * (len(roles) // 2), conversation


@pytest.mark.parametrize("line", BOT_LINES)
def test_bot_lines_open_with_a_mood_tag_and_use_no_contractions(line):
    assert TAG.match(line), line
    assert not CONTRACTION.search(line), line


def test_questions_stay_rare_so_the_model_does_not_learn_a_question_habit():
    asking = sum("?" in line for line in BOT_LINES)
    assert asking / len(BOT_LINES) <= 0.25


def test_malformed_line_is_reported_with_its_text(tmp_path):
    bad = tmp_path / "examples.txt"
    bad.write_text("you: hi\nbto: [mood:happy] typo in speaker\n")
    with pytest.raises(ValueError, match="bto"):
        load_examples(bad)
