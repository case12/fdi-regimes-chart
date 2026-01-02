import io
import cgi
from http.server import BaseHTTPRequestHandler

import mammoth
from bs4 import BeautifulSoup, Comment, NavigableString


ALLOWED = {
    "p", "br",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "b", "em", "i", "u",
    "a",
    "blockquote",
    "code", "pre",
    "font",
}

KEEP_ATTRS = {
    "a": {"href"},
    "font": {"size"},
}


def insert_section_newlines(soup: BeautifulSoup, root) -> None:
    markers = [
        "Foreign investors:",     # Thresholds
        "Authority in Charge",    # Procedures
        "Standard of Review",     # Standard of Review / Penalties
    ]

    def find_first_tag_containing_ci(text: str):
        target = text.lower()
        s = root.find(string=lambda t: isinstance(t, str) and target in t.lower())
        if not s:
            return None
        tag = s.parent
        while tag and getattr(tag, "name", None) not in {"p","li","h1","h2","h3","h4","h5","h6","blockquote","pre"}:
            tag = tag.parent
        return tag or s.parent

    for m in markers:
        t = find_first_tag_containing_ci(m)
        if t:
            t.insert_before(soup.new_string("\n\n"))


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove comments
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    root = soup.body if soup.body else soup

    # Convert \n inside text nodes to <br>
    for node in list(root.descendants):
        if isinstance(node, NavigableString) and "\n" in node:
            parts = str(node).split("\n")
            new_nodes = []
            for i, part in enumerate(parts):
                if part:
                    new_nodes.append(part)
                if i < len(parts) - 1:
                    new_nodes.append(soup.new_tag("br"))
            node.replace_with(*new_nodes)

    # Convert empty paragraphs to <br>
    for p in list(root.find_all("p")):
        if not p.get_text(strip=True) and not p.find(True):
            p.replace_with(soup.new_tag("br"))

    # Strip unwanted tags/attributes
    for tag in list(root.find_all(True)):
        name = tag.name.lower()
        if name not in ALLOWED:
            tag.unwrap()
            continue
        allowed_attrs = KEEP_ATTRS.get(name, set())
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in allowed_attrs}

    # Every <li> font size 20px
    for li in root.find_all("li"):
        li["style"] = "font-size: 20px"

    # Wrap ONLY first line of the first text-containing element in <font size="+2">
    for tag in root.find_all(True):
        if not tag.get_text(strip=True):
            continue

        new_contents = []
        wrapped = False

        for child in list(tag.contents):
            if wrapped:
                new_contents.append(child)
                continue

            if getattr(child, "name", None) == "br":
                new_contents.append(child)
                wrapped = True
                continue

            if isinstance(child, NavigableString):
                text = str(child)
                font = soup.new_tag("font", size="+2")
                font.string = text
                new_contents.append(font)
                wrapped = True
                continue

            font = soup.new_tag("font", size="+2")
            font.append(child)
            new_contents.append(font)
            wrapped = True

        tag.clear()
        for n in new_contents:
            tag.append(n)
        break

    # Literal blank lines between sections (source formatting)
    insert_section_newlines(soup, root)

    if soup.body:
        return "".join(str(x) for x in soup.body.contents)
    return str(root)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            ctype, pdict = cgi.parse_header(self.headers.get("content-type", ""))
            if ctype != "multipart/form-data":
                self._send(400, "Expected multipart/form-data")
                return

            # cgi.FieldStorage needs these
            pdict["boundary"] = pdict["boundary"].encode("utf-8")
            pdict["CONTENT-LENGTH"] = int(self.headers.get("content-length", 0))

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("content-type"),
                },
                keep_blank_values=True,
            )

            if "file" not in form:
                self._send(400, "Missing form field: file")
                return

            fileitem = form["file"]
            filename = getattr(fileitem, "filename", "") or ""
            if not filename.lower().endswith(".docx"):
                self._send(400, "Please upload a .docx file")
                return

            data = fileitem.file.read()

            # Underline -> <u>
            result = mammoth.convert_to_html(io.BytesIO(data), style_map="u => u")
            cleaned = clean_html(result.value)

            self._send(200, cleaned)

        except Exception as e:
            self._send(500, f"Server error: {e}")

    def do_GET(self):
        self._send(405, "POST only")

    def _send(self, status: int, body: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
