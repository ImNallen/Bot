import pytest

from companion.reply import Mood, MoodEvent, ReplyParser, SentenceEvent, to_speech


def run(chunks: list[str]) -> list:
    parser = ReplyParser()
    events = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    events.extend(parser.finish())
    return events


def chars(text: str) -> list[str]:
    return list(text)


def test_mood_tag_then_sentences():
    assert run(["[mood:happy] Hello hello hello. You sleep good, question?"]) == [
        MoodEvent(Mood.HAPPY),
        SentenceEvent("Hello hello hello."),
        SentenceEvent("You sleep good, question?"),
    ]


def test_same_events_when_streamed_one_character_at_a_time():
    text = "[mood:sad] Bad idea. Tired brain makes bugs! Sleep now."
    assert run(chars(text)) == run([text])


def test_mood_is_emitted_before_any_text_arrives():
    parser = ReplyParser()
    assert parser.feed("[mo") == []
    assert parser.feed("od:annoyed]") == [MoodEvent(Mood.ANNOYED)]


def test_missing_tag_defaults_to_neutral_and_keeps_text():
    assert run(["Canberra. Not Sydney."]) == [
        MoodEvent(Mood.NEUTRAL),
        SentenceEvent("Canberra."),
        SentenceEvent("Not Sydney."),
    ]


def test_unknown_mood_defaults_to_neutral():
    assert run(["[mood:ecstatic] Yes."])[0] == MoodEvent(Mood.NEUTRAL)


def test_empty_reply_still_reports_a_mood():
    assert run([]) == [MoodEvent(Mood.NEUTRAL)]


def test_sentence_is_released_as_soon_as_it_is_complete():
    parser = ReplyParser()
    parser.feed("[mood:neutral] First part")
    assert parser.feed(" done. Second") == [SentenceEvent("First part done.")]


def test_decimal_numbers_do_not_split():
    assert run(["[mood:neutral] Model is 3.5 GB. Fits fine."])[1:] == [
        SentenceEvent("Model is 3.5 GB."),
        SentenceEvent("Fits fine."),
    ]


def test_last_sentence_without_punctuation_is_flushed_on_finish():
    assert run(["[mood:neutral] Okay. I listen"])[-1] == SentenceEvent("I listen")


@pytest.mark.parametrize(
    "raw, spoken",
    [
        ("**Spaces.** Four.", "Spaces. Four."),
        ("- first item", "first item"),
        ("1. step one", "step one"),
        ("## Heading", "Heading"),
        ("Use `cProfile` first.", "Use cProfile first."),
        ("See [docs](https://example.com) now.", "See docs now."),
        ("Good good good 🎉🚀", "Good good good"),
        ("Stray [mood:happy] tag.", "Stray tag."),
    ],
)
def test_markup_and_emoji_never_reach_speech(raw, spoken):
    assert to_speech(raw) == spoken


def test_markdown_list_becomes_separate_clean_sentences():
    assert run(["[mood:neutral] Try this:\n- profile it\n- fix slow part\n"])[1:] == [
        SentenceEvent("Try this:"),
        SentenceEvent("profile it"),
        SentenceEvent("fix slow part"),
    ]


def test_emoji_only_sentence_is_dropped():
    assert run(["[mood:happy] Yes. 🎉🎉 \nDone."])[1:] == [SentenceEvent("Yes."), SentenceEvent("Done.")]
