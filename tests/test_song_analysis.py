from app.services.songs.analysis import analyze_lyrics


def _statuses(analyzed):
    return [(t.surface, t.status) for line in analyzed.lines for t in line.tokens]


def test_marks_known_unknown_and_skips_junk():
    # "the" is a stopword (skip); "cat"/"dog" are words; user knows "cat".
    analyzed = analyze_lyrics("The cat and dog", "en", known_lemmas={"cat"})
    by_surface = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert by_surface["The"] == "skip"  # stopword
    assert by_surface["and"] == "skip"  # stopword
    assert by_surface["cat"] == "known"
    assert by_surface["dog"] == "unknown"


def test_punctuation_and_spaces_are_skip_and_line_is_reconstructable():
    analyzed = analyze_lyrics("Hello, world!", "en", known_lemmas=set())
    line = analyzed.lines[0]
    # concatenating surfaces rebuilds the exact original line
    assert "".join(t.surface for t in line.tokens) == "Hello, world!"
    assert any("," in t.surface and t.status == "skip" for t in line.tokens)


def test_unknown_list_is_deduped_with_example_line():
    lyrics = "wander lonely\nwander again"
    analyzed = analyze_lyrics(lyrics, "en", known_lemmas=set())
    lemmas = {u.lemma for u in analyzed.unknown}
    assert "wander" in lemmas and "lonely" in lemmas
    wander = next(u for u in analyzed.unknown if u.lemma == "wander")
    assert wander.example == "wander lonely"  # first occurrence
    assert sum(u.lemma == "wander" for u in analyzed.unknown) == 1  # deduped


def test_lemmatization_groups_inflections():
    # "occurs" lemmatizes to "occur"; a user who knows "occur" sees it as known.
    analyzed = analyze_lyrics("it occurs", "en", known_lemmas={"occur"})
    statuses = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert statuses["occurs"] == "known"


def test_three_states_known_learning_unknown():
    # cat = mastered (known), dog = in vocab but learning, fox = not in vocab
    analyzed = analyze_lyrics("cat dog fox", "en", known_lemmas={"cat"}, learning_lemmas={"dog"})
    statuses = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert statuses["cat"] == "known"
    assert statuses["dog"] == "learning"
    assert statuses["fox"] == "unknown"
    # only genuinely unknown words go into the unknown list (not learning ones)
    assert {u.lemma for u in analyzed.unknown} == {"fox"}


def test_ukrainian_stopwords_and_words():
    analyzed = analyze_lyrics("я чув пісню", "uk", known_lemmas=set())
    statuses = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert statuses["я"] == "skip"  # stopword (also too short)
    assert statuses["пісню"] == "unknown"
