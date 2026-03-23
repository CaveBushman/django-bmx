from html import escape
from html.parser import HTMLParser


ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "div",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

VOID_TAGS = {"br", "hr", "img"}
DROP_WITH_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed"}

ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height"},
    "figure": {"class"},
    "div": {"class"},
    "p": {"class"},
    "table": {"class"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

ALLOWED_CLASS_PREFIXES = ("image", "media", "table")
ALLOWED_TARGETS = {"_blank", "_self"}


def _is_safe_url(value):
    if not value:
        return False

    normalized = value.strip().lower()
    if normalized.startswith(("http://", "https://", "mailto:", "tel:")):
        return True
    if normalized.startswith(("/", "#", "../", "./")):
        return True
    return False


def _sanitize_attributes(tag, attrs):
    allowed_attrs = ALLOWED_ATTRIBUTES.get(tag, set())
    sanitized = []

    for key, value in attrs:
        key = (key or "").lower()
        if key not in allowed_attrs:
            continue

        value = value or ""

        if key in {"href", "src"} and not _is_safe_url(value):
            continue

        if key == "target":
            if value not in ALLOWED_TARGETS:
                continue
            sanitized.append((key, value))
            if value == "_blank":
                sanitized.append(("rel", "noopener noreferrer"))
            continue

        if key == "rel":
            continue

        if key == "class":
            classes = [
                item
                for item in value.split()
                if item.startswith(ALLOWED_CLASS_PREFIXES)
            ]
            if not classes:
                continue
            value = " ".join(classes)

        sanitized.append((key, value))

    return sanitized


class SafeHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return
        if tag not in ALLOWED_TAGS:
            return

        rendered_attrs = []
        for key, value in _sanitize_attributes(tag, attrs):
            rendered_attrs.append(f' {key}="{escape(value, quote=True)}"')

        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}{''.join(rendered_attrs)}>")
            return
        self.parts.append(f"<{tag}{''.join(rendered_attrs)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.drop_depth:
            self.parts.append(escape(data))

    def handle_entityref(self, name):
        if not self.drop_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.drop_depth:
            self.parts.append(f"&#{name};")

    def get_html(self):
        return "".join(self.parts)


def sanitize_rich_html(value):
    if value in (None, ""):
        return value

    parser = SafeHtmlParser()
    parser.feed(value)
    parser.close()
    return parser.get_html()
