"""Check source syntax, example JSON, and local documentation links; no providers."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.current = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            attrs = dict(attrs)
            self.active = "src" not in attrs and attrs.get("type", "") not in {"application/json", "application/ld+json"}
            self.current = []

    def handle_data(self, data):
        if self.active:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.current))
            self.active = False


def main():
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    errors = []
    scripts = 0
    for name in sorted(set(paths)):
        path = ROOT / name
        if not path.is_file() or path.suffix not in {".py", ".json", ".js", ".html", ".md"}:
            continue
        content = path.read_text(encoding="utf-8")
        try:
            if path.suffix == ".py":
                compile(content, name, "exec")
            elif name.endswith(".example.json"):
                json.loads(content)
            elif path.suffix in {".js", ".html"}:
                parser = Scripts()
                if path.suffix == ".html":
                    parser.feed(content)
                    chunks = parser.scripts
                else:
                    chunks = [content]
                for i, chunk in enumerate(chunks, 1):
                    result = subprocess.run(["node", "--check"], input=chunk, text=True, capture_output=True, check=False)
                    if result.returncode:
                        errors.append(f"{name}, script {i}: {result.stderr}")
                    scripts += 1
            elif path.suffix == ".md":
                for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", content):
                    target = match.group(1).split(' "')[0].split("#")[0]
                    if not target or "://" in target or target.startswith("mailto:"):
                        continue
                    if target.startswith("/") or not (path.parent / target).exists():
                        line = content.count("\n", 0, match.start()) + 1
                        errors.append(f"{name}:{line}: broken/nonportable link: {target}")
        except (SyntaxError, UnicodeError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Python syntax, example JSON, local links, and {scripts} JavaScript scripts passed.")


if __name__ == "__main__":
    main()
