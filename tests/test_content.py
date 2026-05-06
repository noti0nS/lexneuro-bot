from src.helpers.content import sanitize_discord_markdown


def test_plain_text_unchanged():
    assert sanitize_discord_markdown("Hello world") == "Hello world"


def test_empty_string():
    assert sanitize_discord_markdown("") == ""


def test_allowed_bold():
    assert sanitize_discord_markdown("**bold**") == "**bold**"


def test_allowed_italic_star():
    assert sanitize_discord_markdown("*italic*") == "*italic*"


def test_allowed_italic_underscore():
    assert sanitize_discord_markdown("_italic_") == "_italic_"


def test_allowed_underline():
    assert sanitize_discord_markdown("__underline__") == "__underline__"


def test_allowed_strikethrough():
    assert sanitize_discord_markdown("~~strikethrough~~") == "~~strikethrough~~"


def test_allowed_inline_code():
    assert sanitize_discord_markdown("`code`") == "`code`"


def test_allowed_code_block():
    text = "```python\nprint('hello')\n```"
    assert sanitize_discord_markdown(text) == text


def test_allowed_blockquote():
    assert sanitize_discord_markdown("> quote") == "> quote"


def test_allowed_h1():
    assert sanitize_discord_markdown("# Heading 1") == "# Heading 1"


def test_allowed_h2():
    assert sanitize_discord_markdown("## Heading 2") == "## Heading 2"


def test_allowed_h3():
    assert sanitize_discord_markdown("### Heading 3") == "### Heading 3"


def test_h4_stripped():
    assert sanitize_discord_markdown("#### Heading 4") == "Heading 4"


def test_h5_stripped():
    assert sanitize_discord_markdown("##### Heading 5") == "Heading 5"


def test_h6_stripped():
    assert sanitize_discord_markdown("###### Heading 6") == "Heading 6"


def test_many_hashes_stripped():
    assert sanitize_discord_markdown("######## Heading") == "Heading"


def test_h4_in_code_block_preserved():
    text = "```\n#### Not a heading\n```"
    assert sanitize_discord_markdown(text) == text


def test_h4_in_inline_code_preserved():
    assert sanitize_discord_markdown("`#### Not a heading`") == "`#### Not a heading`"


def test_latex_inline_stripped():
    assert sanitize_discord_markdown("$x^2$") == "x^2"


def test_latex_display_stripped():
    result = sanitize_discord_markdown("$$x^2 + y^2$$")
    assert "$$" not in result
    assert "x^2 + y^2" in result


def test_latex_paren_stripped():
    result = sanitize_discord_markdown("\\(E = mc^2\\)")
    assert "\\(" not in result
    assert "\\)" not in result


def test_latex_bracket_stripped():
    result = sanitize_discord_markdown("\\[E = mc^2\\]")
    assert "\\[" not in result
    assert "\\]" not in result


def test_latex_command_removed():
    assert sanitize_discord_markdown("\\alpha") == ""


def test_latex_command_with_arg_removed():
    assert sanitize_discord_markdown("\\textbf{bold}") == "bold"


def test_latex_frac_removed():
    result = sanitize_discord_markdown("$\\frac{a}{b}$")
    assert "\\frac" not in result
    assert "$" not in result


def test_html_tags_stripped():
    assert sanitize_discord_markdown("<b>text</b>") == "text"


def test_html_self_closing_stripped():
    assert sanitize_discord_markdown("line<br>break") == "linebreak"


def test_html_with_attributes_stripped():
    assert sanitize_discord_markdown('<a href="url">link</a>') == "link"


def test_table_separator_removed():
    text = "| --- | --- |\n| a | b |"
    result = sanitize_discord_markdown(text)
    assert "---" not in result
    assert "a | b" in result


def test_table_data_row_converted():
    assert sanitize_discord_markdown("| cell1 | cell2 |") == "cell1 | cell2"


def test_table_full_removed():
    text = "| Header 1 | Header 2 |\n| --- | --- |\n| Data 1 | Data 2 |"
    result = sanitize_discord_markdown(text)
    assert "---" not in result
    assert "Header 1 | Header 2" in result
    assert "Data 1 | Data 2" in result


def test_horizontal_rule_dash():
    assert sanitize_discord_markdown("---") == ""


def test_horizontal_rule_asterisk():
    assert sanitize_discord_markdown("***") == ""


def test_horizontal_rule_underscore():
    assert sanitize_discord_markdown("___") == ""


def test_horizontal_rule_not_inline_bold_italic():
    assert sanitize_discord_markdown("***text***") == "**text**"


def test_horizontal_rule_long():
    assert sanitize_discord_markdown("----------") == ""


def test_combined_bold_italic():
    assert sanitize_discord_markdown("***bold italic***") == "**bold italic**"


def test_combined_underline_bold():
    assert sanitize_discord_markdown("__**bold**__") == "**bold**"


def test_combined_bold_underline():
    assert sanitize_discord_markdown("**__underline__**") == "**underline**"


def test_combined_strikethrough_italic():
    assert sanitize_discord_markdown("~~*italic*~~") == "*italic*"


def test_combined_italic_strikethrough():
    assert sanitize_discord_markdown("*~~strikethrough~~*") == "*strikethrough*"


def test_combined_strikethrough_bold():
    assert sanitize_discord_markdown("~~**bold**~~") == "**bold**"


def test_combined_bold_strikethrough():
    assert sanitize_discord_markdown("**~~strikethrough~~**") == "**strikethrough**"


def test_combined_underline_strikethrough():
    assert sanitize_discord_markdown("__~~strikethrough~~__") == "__strikethrough__"


def test_combined_strikethrough_underline():
    assert sanitize_discord_markdown("~~__underline__~~") == "~~underline~~"


def test_footnote_removed():
    assert sanitize_discord_markdown("text[^1]") == "text"


def test_footnote_definition_removed():
    text = "Some text\n[^1]: Footnote definition\nMore text"
    result = sanitize_discord_markdown(text)
    assert "[^1]" not in result
    assert "Footnote definition" not in result or "[^1]" not in result


def test_task_list_unchecked():
    assert sanitize_discord_markdown("- [ ] task") == "- task"


def test_task_list_checked():
    assert sanitize_discord_markdown("- [x] done") == "- done"


def test_task_list_checked_uppercase():
    assert sanitize_discord_markdown("- [X] done") == "- done"


def test_nested_blockquote_flattened():
    assert sanitize_discord_markdown("> > nested") == "> nested"


def test_triple_nested_blockquote_flattened():
    assert sanitize_discord_markdown("> > > deep") == "> deep"


def test_code_block_preserves_content():
    text = "before\n```python\n#### comment\n```\nafter"
    result = sanitize_discord_markdown(text)
    assert "#### comment" in result
    assert "before" in result
    assert "after" in result


def test_inline_code_preserves_content():
    assert sanitize_discord_markdown("use `####` for h4") == "use `####` for h4"


def test_excess_blank_lines_collapsed():
    assert sanitize_discord_markdown("a\n\n\n\nb") == "a\n\nb"


def test_multiple_transformations():
    text = "#### Title\n\n$$x^2$$\n\n<sub>text</sub>"
    result = sanitize_discord_markdown(text)
    assert "####" not in result
    assert "$$" not in result
    assert "<sub>" not in result
    assert "Title" in result
    assert "x^2" in result


def test_table_with_alignment():
    text = "| :---: | ---: |\n| center | right |"
    result = sanitize_discord_markdown(text)
    assert "---" not in result
    assert "center | right" in result


def test_latex_sum_in_display():
    result = sanitize_discord_markdown("$$\\sum_{i=0}^{n} x_i$$")
    assert "$$" not in result
    assert "\\sum" not in result


def test_html_comment_removed():
    assert sanitize_discord_markdown("before<!-- comment -->after") == "beforeafter"


def test_multiple_inline_latex():
    result = sanitize_discord_markdown("$a$ and $b$")
    assert "a" in result
    assert "b" in result
    assert "$" not in result


def test_horizontal_rule_with_spaces():
    assert sanitize_discord_markdown("- - -") == ""


def test_plain_text_with_special_chars():
    assert (
        sanitize_discord_markdown("Hello, world! 2 + 2 = 4.")
        == "Hello, world! 2 + 2 = 4."
    )


def test_allowed_blockquote_triple_arrow():
    assert sanitize_discord_markdown(">>> text") == ">>> text"


def test_math_in_inline_code_preserved():
    assert sanitize_discord_markdown("`$x^2$`") == "`$x^2$`"


def test_table_separator_with_colons():
    text = "| :--- | :---: | ---: |\n| left | center | right |"
    result = sanitize_discord_markdown(text)
    assert "---" not in result
