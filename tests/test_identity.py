import pytest

from flaming.vision import ReadError
from identity import verify_character

PROFILE = {"character": {"name": "NotFamAnymor", "class": "Illium"}, "class_info": {"name": "Illium"}}


def result(name, job="Illium"):
    return {"character_name": name, "character_class": job}


@pytest.mark.parametrize("shown", ["NotFamAny..", "NotFamAny.", "NotFamAny...", "NotFamAny…", "notfamany.."])
def test_long_names_cut_off_by_character_info_match_with_their_class(shown):
    # Live report: Character Info shows "NotFamAny.." for NotFamAnymor; OCR may read 1-3 dots.
    verify_character(result(shown), PROFILE)


def test_cut_off_names_still_need_the_class_and_a_real_prefix():
    with pytest.raises(ReadError, match="start of this long name"):
        verify_character(result("NotFamAny...", "Lynn"), PROFILE)
    with pytest.raises(ReadError, match="Select the logged-in character"):
        verify_character(result("NotFamOther..."), PROFILE)
    # Too little of the name is visible to identify anyone.
    with pytest.raises(ReadError, match="Select the logged-in character"):
        verify_character(result("Not..."), PROFILE)


def test_exact_and_lookalike_names_are_unchanged():
    verify_character(result("NotFamAnymor", ""), PROFILE)
    verify_character(result("N0tFamAnym0r"), PROFILE)
    with pytest.raises(ReadError, match="OCR lookalikes"):
        verify_character(result("N0tFamAnym0r", "Lynn"), PROFILE)
    with pytest.raises(ReadError, match="Select the logged-in character"):
        verify_character(result("SomeoneElse"), PROFILE)
