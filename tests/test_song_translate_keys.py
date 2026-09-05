"""The translation cache key: pure, offline, no database.

Split from the cache tests because these need no event loop — and because the
key is the one thing every hit in the system depends on agreeing with itself.
"""

from app.services.songs.translation_keys import context_hash, normalize_word


def test_word_folds_onto_one_key():
    assert normalize_word("  Straight ") == normalize_word("straight") == "straight"


def test_the_same_word_in_two_lines_is_two_keys():
    """Context is the point: a different line may well mean a different sense."""
    assert context_hash("Fall asleep tonight") != context_hash("A fall from grace")


def test_whitespace_in_a_line_does_not_split_the_key():
    assert context_hash("Fall  asleep\ttonight") == context_hash("Fall asleep tonight")
