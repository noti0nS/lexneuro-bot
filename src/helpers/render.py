import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer_for_filename
from pygments.util import ClassNotFound

from .ui import CAPTURE_FILE_EXTENSIONS

_LANG_SIGNATURES: dict[str, str] = {
    "python": r"\b(def|class|import|from|print|elif|yield|self)\b",
    "c#": r"\b(var|using|namespace|=>|\.Select\(|\.Where\(|\.ToList\()",
    "javascript": r"\b(function|const|let|console|=>|new )",
    "typescript": r"\b(interface|: string|: number|: boolean|readonly)\b",
    "java": r"\b(public class|System\.out|String\[\]|ArrayList)\b",
    "go": r"\b(func|package|fmt\.|:=|goroutine|chan )",
    "rust": r"\b(fn |let mut|println!|impl |struct |enum )",
    "c++": r"\b(#include|std::|cout|cin|template)\b",
    "c": r"\b(#include|printf\(|malloc|typedef|struct )",
    "ruby": r"\b(def|end|puts|attr_accessor|\.each)\b",
    "php": r"\b(<\?php|echo |\$\w+|function )",
    "swift": r"\b(var |let |func |guard |protocol)\b",
    "kotlin": r"\b(fun |val |var |when |data class)\b",
    "scala": r"\b(def |val |var |object |case class)\b",
    "lua": r"\b(function|local|nil|\.\.)\b",
    "bash": r"\b(echo|export|#!/bin|function |if \[)",
    "sql": r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN)\b",
    "yaml": r"^\w+:\s",
    "json": r"^[\[\{]",
    "html": r"<(!DOCTYPE|html|div|head|body|script|style)",
    "css": r"\{[\s\S]*:[\s\S]*;",
}


def render_code_image(code: str, *, max_lines: int = 200, lang: str | None = None) -> bytes:

    lexer = _get_lexer(code, lang)
    code = _truncate_lines(code, max_lines)

    raw_png = highlight(
        code,
        lexer,
        ImageFormatter(  # pyright: ignore[reportCallIssue]
            style="monokai",
            font_size=18,
            line_numbers=True,
            image_pad=32,
            line_pad=6,
            line_number_bg="#1e1f29",
            line_number_fg="#6c7086",
            dpi=144,
        ),
    )

    code_img = Image.open(BytesIO(raw_png))
    return _post_process(code_img)


def _get_lexer(code: str, lang: str | None = None):
    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            pass
    return _detect_lexer(code)


def _verify_lexer(code: str, lexer_name: str) -> bool:
    name_key = lexer_name.lower().rstrip("0123456789. ")
    pattern = _LANG_SIGNATURES.get(name_key)
    if pattern is None:
        return True
    return bool(re.search(pattern, code))


def _detect_lexer(code: str):
    sample = code[:2000]

    for ext in CAPTURE_FILE_EXTENSIONS:
        try:
            lexer = guess_lexer_for_filename(f"code.{ext}", sample)
            name = lexer.name.lower()
            if name in ("text only", "scdoc", "markdown"):
                continue
            if not _verify_lexer(sample, name):
                continue
            return lexer
        except ClassNotFound:
            continue

    return TextLexer()


def detect_language_name(code: str, *, lang: str | None = None) -> str | None:
    lexer = _get_lexer(code, lang)
    if isinstance(lexer, TextLexer):
        return None
    return lexer.name


def _truncate_lines(code: str, max_lines: int) -> str:
    lines = code.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"# ... truncated at {max_lines} lines")
    return "\n".join(lines)


def _post_process(code_img: Image.Image) -> bytes:
    code_img = code_img.convert("RGBA")

    pad = 36
    blur = 14
    offset = 5
    radius = 10
    shadow_alpha = 90

    cw, ch = code_img.width, code_img.height
    fw = cw + pad * 2 + blur * 2
    fh = ch + pad * 2 + blur * 2

    canvas = _create_gradient(fw, fh, (26, 27, 38), (47, 53, 66))

    shadow = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sx = pad + blur + offset
    sy = pad + blur + offset
    sd.rounded_rectangle(
        [sx - 2, sy - 2, sx + cw + 2, sy + ch + 2],
        radius=radius + 2,
        fill=(0, 0, 0, shadow_alpha),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, shadow)

    cx = pad + blur
    cy = pad + blur
    canvas.paste(code_img, (cx, cy), _rounded_mask(cw, ch, radius))

    buf = BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()


def _rounded_mask(w: int, h: int, radius: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    return mask


def _create_gradient(
    w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> Image.Image:
    img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(img)
    denom = max(h - 1, 1)
    for y in range(h):
        t = y / denom
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return img
