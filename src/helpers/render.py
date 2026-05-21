from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import (
    TextLexer,
    get_lexer_by_name,
    get_lexer_for_filename,
    guess_lexer,
)
from pygments.util import ClassNotFound


def render_code_image(
    code: str,
    *,
    max_lines: int = 200,
    lang: str | None = None,
    filename: str | None = None,
) -> bytes:

    lexer = _get_lexer(code, lang, filename=filename)
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


def _get_lexer(code: str, lang: str | None = None, *, filename: str | None = None):
    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            pass
    return _detect_lexer(code, filename=filename)


def _detect_lexer(code: str, *, filename: str | None = None):
    sample = code[:2000]
    if not sample.strip():
        return TextLexer()

    if filename:
        try:
            return get_lexer_for_filename(filename, sample, stripnl=False)
        except ClassNotFound:
            pass

    try:
        return guess_lexer(sample)
    except ClassNotFound:
        return TextLexer()


def detect_language_name(
    code: str, *, lang: str | None = None, filename: str | None = None
) -> str | None:
    lexer = _get_lexer(code, lang, filename=filename)
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
