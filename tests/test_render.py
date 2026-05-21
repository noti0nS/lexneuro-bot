from src.helpers.render import detect_language_name


class TestDetectLanguageSnippet:
    def test_python(self) -> None:
        code = "class Foo:\n    def bar(self):\n        import os\n"
        assert detect_language_name(code) == "Python"

    def test_javascript(self) -> None:
        code = "const x = () => console.log('hi');\n"
        result = detect_language_name(code)
        assert result is not None

    def test_go(self) -> None:
        code = 'func main() {\n    fmt.Println("hello")\n}\n'
        result = detect_language_name(code)
        assert result is not None

    def test_rust(self) -> None:
        code = (
            "use std::collections::HashMap;\n\n"
            "fn main() {\n"
            "    let mut map = HashMap::new();\n"
            '    map.insert("key", 42);\n'
            '    println!("{:?}", map);\n'
            "}\n"
        )
        result = detect_language_name(code)
        assert result is not None

    def test_html(self) -> None:
        code = "<!DOCTYPE html>\n<html><body><h1>Hello</h1></body></html>\n"
        result = detect_language_name(code)
        assert result is not None

    def test_bash(self) -> None:
        code = '#!/bin/bash\necho "Hello, World!"\nexport VAR=1\n'
        result = detect_language_name(code)
        assert result is not None

    def test_php(self) -> None:
        code = '<?php\necho "Hello, $name!";\n?>\n'
        result = detect_language_name(code)
        assert result is not None

    def test_empty_code_returns_none(self) -> None:
        assert detect_language_name("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert detect_language_name("   \n\n  ") is None


class TestDetectLanguageWithFilename:
    def test_py_extension(self) -> None:
        code = "x = 1\n"
        result = detect_language_name(code, filename="app.py")
        assert result == "Python"

    def test_js_extension(self) -> None:
        code = "const x = 1;\n"
        result = detect_language_name(code, filename="index.js")
        assert result == "JavaScript"

    def test_rs_extension(self) -> None:
        code = "let x = 5;\n"
        result = detect_language_name(code, filename="main.rs")
        assert result == "Rust"

    def test_go_extension(self) -> None:
        code = "package main\n"
        result = detect_language_name(code, filename="main.go")
        assert result == "Go"

    def test_filename_overrides_guess(self) -> None:
        code = "x = 1\n"
        result = detect_language_name(code, filename="config.yaml")
        assert result == "YAML"

    def test_no_extension_falls_back_to_guess_lexer(self) -> None:
        code = "#!/bin/bash\necho hello\nexport FOO=1\n"
        result = detect_language_name(code, filename="untitled")
        assert result is not None


class TestDetectLanguageWithLangOverride:
    def test_lang_override(self) -> None:
        code = "irrelevant code"
        result = detect_language_name(code, lang="python")
        assert result == "Python"

    def test_lang_override_ignores_filename(self) -> None:
        code = "irrelevant code"
        result = detect_language_name(code, lang="python", filename="x.js")
        assert result == "Python"
