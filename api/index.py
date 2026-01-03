import io
from http.server import BaseHTTPRequestHandler

try:
    import cgi
except ImportError:
    from legacy_cgi import cgi

import mammoth
from bs4 import BeautifulSoup, Comment, NavigableString
from bs4.formatter import HTMLFormatter


ALLOWED = {
    "br",
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
        target = text.lower().strip()
        # Search all tags for case-insensitive text match
        for tag in root.find_all(True):
            tag_text = tag.get_text()
            if target in tag_text.lower():
                # Find the parent block-level element
                block_tag = tag
                while block_tag and getattr(block_tag, "name", None) not in {"li","h1","h2","h3","h4","h5","h6","blockquote","pre"}:
                    block_tag = block_tag.parent
                return block_tag or tag
        return None

    for m in markers:
        t = find_first_tag_containing_ci(m)
        if t:
            t.insert_before(soup.new_string("\n\n"))


def split_sections(html: str) -> dict:
    """Split HTML into sections at the DOM level, not string level."""
    soup = BeautifulSoup(html, "html.parser")
    formatter = HTMLFormatter(indent=4)

    markers = [
        ("foreign investors:", "thresholds"),
        ("authority in charge", "procedures"),
        ("standard of review", "standard"),
    ]

    sections = {
        "jurisdiction": "",
        "thresholds": "",
        "procedures": "",
        "standard": "",
    }

    # Get all top-level nodes (elements and text nodes)
    root = soup.body if soup.body else soup
    all_nodes = list(root.children)

    # Find which node index contains each marker
    marker_positions = []  # list of (node_index, marker_name, section_key)
    for marker_text, section_key in markers:
        target = marker_text.lower()
        for i, node in enumerate(all_nodes):
            node_text = node.get_text().lower() if hasattr(node, 'get_text') else str(node).lower()
            if target in node_text:
                marker_positions.append((i, marker_text, section_key))
                break

    # Sort by node index
    marker_positions.sort(key=lambda x: x[0])

    # Build sections by collecting nodes between markers
    section_names = ["jurisdiction"] + [m[2] for m in marker_positions]
    split_indices = [0] + [m[0] for m in marker_positions] + [len(all_nodes)]

    for i, section_name in enumerate(section_names):
        start_idx = split_indices[i]
        end_idx = split_indices[i + 1]

        # Collect nodes for this section
        section_soup = BeautifulSoup("", "html.parser")
        for node in all_nodes[start_idx:end_idx]:
            # Deep copy the node to avoid modifying original
            if hasattr(node, 'name'):
                section_soup.append(BeautifulSoup(str(node), "html.parser"))
            else:
                section_soup.append(NavigableString(str(node)))

        sections[section_name] = section_soup.prettify(formatter=formatter)

    return sections


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    formatter = HTMLFormatter(indent=4)

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

    # Convert empty paragraphs to <br> (before unwrapping)
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
        # Format HTML with proper indentation
        return soup.body.prettify(formatter=formatter)
    return soup.prettify(formatter=formatter)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            ctype, pdict = cgi.parse_header(self.headers.get("content-type", ""))
            if ctype != "multipart/form-data":
                self._send(400, "Expected multipart/form-data", "text/plain; charset=utf-8")
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
                self._send(400, "Missing form field: file", "text/plain; charset=utf-8")
                return

            fileitem = form["file"]
            filename = getattr(fileitem, "filename", "") or ""
            if not filename.lower().endswith(".docx"):
                self._send(400, "Please upload a .docx file", "text/plain; charset=utf-8")
                return

            data = fileitem.file.read()

            # Underline -> <u>
            result = mammoth.convert_to_html(io.BytesIO(data), style_map="u => u")
            cleaned = clean_html(result.value)
            
            # Split into sections with valid HTML
            sections = split_sections(cleaned)
            
            # Return as JSON
            import json
            self._send(200, json.dumps(sections), "application/json; charset=utf-8")

        except Exception as e:
            self._send(500, f"Server error: {e}", "text/plain; charset=utf-8")

    def do_GET(self):
        self._send(405, "POST only", "text/plain; charset=utf-8")

    def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
