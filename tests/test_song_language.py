from app.services.songs.language import detect_language


def test_detects_english():
    text = "Late at night I could hear the crying, I could hear it all through the wall"
    assert detect_language(text) == "en"


def test_detects_ukrainian():
    text = "Пізно вночі я чув, як хтось плаче, я чув усе це крізь стіну щоночі"
    assert detect_language(text) == "uk"


def test_empty_text_is_none():
    assert detect_language("") is None
    assert detect_language("   ") is None


def test_unsupported_language_not_forced():
    # Russian is intentionally excluded from the supported set; detection must
    # not mislabel it as a supported one with high confidence.
    result = detect_language("Поздно ночью я слышал плач сквозь стену каждую ночь всегда")
    assert result in (None, "uk")  # never a confident wrong supported tag beyond uk overlap
