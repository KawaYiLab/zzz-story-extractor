from zzz_story.clean import clean_text


def test_gender_variants():
    cleaned = clean_text("{M#哥哥}{F#姐姐}", "F")
    assert cleaned.text == "姐姐"
    assert cleaned.variants == {"M": "哥哥", "F": "姐姐"}

    cleaned = clean_text("{F#铃}{M#哲}", "M")
    assert cleaned.text == "哲"


def test_layout_variant():
    cleaned = clean_text("{LAYOUT_MOBILE#手机}{LAYOUT_CONTROLLER#手柄}", "F")
    assert "手机" in cleaned.text
    assert "手柄" not in cleaned.text


def test_tags_and_newlines():
    cleaned = clean_text("你好<color=#FFAF2C>世界</color>\r\n第二行", "F")
    assert cleaned.text == "你好世界\n第二行"


def test_common_prefix_variant():
    cleaned = clean_text("前缀{M#甲}{F#乙}后缀", "F")
    assert cleaned.text == "前缀乙后缀"
    assert cleaned.variants == {"M": "前缀甲后缀", "F": "前缀乙后缀"}


def test_no_variant_is_none():
    cleaned = clean_text("普通文本", "F")
    assert cleaned.text == "普通文本"
    assert cleaned.variants is None


def test_layout_variant_preserves_inline_position():
    raw = "前缀{LAYOUT_MOBILE#甲}{LAYOUT_CONTROLLER#乙}中间{LAYOUT_MOBILE#丙}{LAYOUT_CONTROLLER#丁}后缀"
    assert clean_text(raw).text == "前缀甲中间丙后缀"
