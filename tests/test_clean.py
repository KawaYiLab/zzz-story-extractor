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


def test_layout_preserves_nested_format_arguments():
    raw = "{LAYOUT_MOBILE#移动{0}步}{LAYOUT_CONTROLLER#按下按钮{0}}"
    assert clean_text(raw).text == "移动{0}步"


def test_gender_inside_layout_and_layout_inside_gender():
    raw = "前{LAYOUT_MOBILE#{M#哥哥}{F#姐姐}}{LAYOUT_CONTROLLER#按键}后"
    assert clean_text(raw, "M").variants == {"M": "前哥哥后", "F": "前姐姐后"}
    assert clean_text("{M#{LAYOUT_MOBILE#甲}{LAYOUT_CONTROLLER#乙}}{F#丙}", "M").text == "甲"


def test_break_tags_and_literal_angle_placeholders():
    assert clean_text("<b>你好</b><br/>我是<PLAYER>，a < b > c").text == "你好\n我是<PLAYER>，a < b > c"
    assert clean_text("<noparse><b>原样</b></noparse>").text == "<b>原样</b>"


def test_malformed_variants_remain_reviewable():
    raw = "前{LAYOUT_MOBILE#未闭合{0}"
    assert clean_text(raw).text == raw
    assert clean_text("{M#未闭合").text == "{M#未闭合"


def test_ruby_keeps_base_and_annotation_in_readable_form():
    assert clean_text("因为<ruby> <rt>这个世界</rt> 他们</ruby>很可爱").text == "因为他们（这个世界）很可爱"
    assert clean_text("<ruby>汉<rt>hàn</rt></ruby>").text == "汉（hàn）"
    assert clean_text("<ruby>相同<rt>相同</rt></ruby>").text == "相同"
    assert clean_text("<noparse><ruby>原样</ruby></noparse>").text == "<ruby>原样</ruby>"
