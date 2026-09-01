from app.services.songs.analysis import analyze_lyrics


def _statuses(analyzed):
    return [(t.surface, t.status) for line in analyzed.lines for t in line.tokens]


def test_marks_known_unknown_and_skips_junk():
    analyzed = analyze_lyrics("The cat and dog", "en", known_lemmas={"cat"})
    by_surface = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert by_surface["The"] == "skip"  # an article: nothing to look up
    assert by_surface["and"] == "common"  # frequent, but still a word
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


def test_interjections_are_skipped_not_unknown():
    # "Uh, whoo, yeah" are onomatopoeia — skipped, not flagged red as new words.
    analyzed = analyze_lyrics("Uh, whoo, yeah, encore", "en", known_lemmas=set())
    statuses = {
        t.surface.lower(): t.status
        for line in analyzed.lines
        for t in line.tokens
        if t.status != "skip" or t.surface.strip()
    }
    assert statuses["uh"] == "skip"
    assert statuses["whoo"] == "skip"
    assert statuses["yeah"] == "skip"
    assert statuses["encore"] == "unknown"
    assert {u.lemma for u in analyzed.unknown} == {"encore"}  # interjections not offered to learn


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


def test_phrasal_verbs_stay_one_unit():
    # "float up" / "wake up" are one meaning, so they're one clickable unit and
    # translated together — not split into a verb and a stray particle.
    analyzed = analyze_lyrics("I float up and wake up", "en", known_lemmas=set())
    units = [(t.surface, t.lemma, t.status) for line in analyzed.lines for t in line.tokens if t.status != "skip"]
    assert ("float up", "float up", "unknown") in units
    assert ("wake up", "wake up", "unknown") in units
    # the particle never appears on its own
    assert all(t.surface.strip() != "up" for line in analyzed.lines for t in line.tokens if t.status != "skip")


def test_particle_alone_is_not_glued_to_any_word():
    # "the up" isn't a phrasal verb: nothing is merged.
    analyzed = analyze_lyrics("carry the box", "en", known_lemmas=set())
    surfaces = [t.surface for line in analyzed.lines for t in line.tokens if t.status != "skip"]
    assert "carry" in surfaces and all(" " not in s for s in surfaces)


# --- common words ----------------------------------------------------------


def test_frequent_words_are_common_not_skipped():
    """A stopword list is built for search engines, where discarding anything
    frequent is the point. For a learner that throws away real vocabulary, so
    these stay offerable — just not flagged."""
    analyzed = analyze_lyrics("How can I take the pain away?", "en", known_lemmas=set())
    by_surface = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert by_surface["take"] == "common"
    assert by_surface["away"] == "common"
    assert by_surface["pain"] == "unknown"


def test_articles_stay_skipped():
    """The one class with nothing to learn, so it is excluded outright."""
    for article, language in [("the", "en"), ("a", "en"), ("der", "de"), ("el", "es")]:
        analyzed = analyze_lyrics(f"{article} something", language, known_lemmas=set())
        statuses = {t.surface.lower(): t.status for line in analyzed.lines for t in line.tokens}
        assert statuses[article] == "skip", (article, language)


def test_punctuation_and_interjections_stay_skipped():
    """Only real words become offerable; noise must not."""
    analyzed = analyze_lyrics("Uh, yeah!", "en", known_lemmas=set())
    assert all(t.status == "skip" for line in analyzed.lines for t in line.tokens)


def test_a_saved_common_word_shows_as_the_learner_s_own():
    """The vocabulary check runs first: a frequent word they actually saved
    should read as theirs, not be greyed in with the rest."""
    analyzed = analyze_lyrics("take the pain away", "en", known_lemmas={"take"}, learning_lemmas={"away"})
    by_surface = {t.surface: t.status for line in analyzed.lines for t in line.tokens}
    assert by_surface["take"] == "known"
    assert by_surface["away"] == "learning"


def test_common_words_do_not_inflate_the_unknown_list():
    """The per-song "new words" count must keep meaning what it says."""
    analyzed = analyze_lyrics("How can I take the pain away?", "en", known_lemmas=set())
    assert {u.lemma for u in analyzed.unknown} == {"pain"}


def test_common_words_stay_out_of_the_shared_lemma_cache():
    """content_lemmas feeds every user's unknown count; adding frequent words
    would make every song look full of new vocabulary."""
    from app.services.songs.analysis import content_lemmas

    assert content_lemmas("How can I take the pain away?", "en") == ["pain"]
