"""Small value-redacting accidental-secret guard; not a security certification."""
import argparse
from collections import Counter
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})\b",
    "Google credential": r"\b(?:AIza[0-9A-Za-z_-]{25,}|ya29\.[0-9A-Za-z._-]{20,}|GOCSPX-[0-9A-Za-z_-]{10,})",
    "provider key": r"\bsk-(?:proj-|live-|or-v1-)?[A-Za-z0-9_-]{24,}",
    "AWS key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
    "credential literal": r"(?i)[\"'](?:access_token|refresh_token|client_secret|api_key|password)[\"']\s*[:=]\s*[\"'][A-Za-z0-9_./+\-=]{24,}[\"']",
}
PRIVATE_PATH = re.compile(r"(?i)(?:^|/)(?:\.env(?:\..*)?|(?:client_secret|credentials)[^/]*\.json|[^/]*-oauth\.json|tokens?\.json|[^/]+\.local\.json|[^/]+\.(?:pem|p12|pfx|key)|id_rsa|id_ed25519)$")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def findings(data):
    try:
        content = data.decode("utf-8")
    except UnicodeError:
        return []  # Binary media require separate review; this is a text-secret guard.
    found = []
    for label, pattern in PATTERNS.items():
        found += [(content.count("\n", 0, m.start()) + 1, label) for m in re.finditer(pattern, content)]
    for match in re.finditer(r"[\"']([A-Za-z0-9+/=_-]{32,})[\"']", content):
        value = match.group(1)
        entropy = -sum((n / len(value)) * math.log2(n / len(value)) for n in Counter(value).values())
        # Fixed Git object IDs are public integrity references, not credentials.
        if entropy >= 4.2 and not re.fullmatch(r"[0-9a-f]{40,64}", value):
            found.append((content.count("\n", 0, match.start()) + 1, "high-entropy literal; inspect privately"))
    return found


def private_path(path):
    if path.endswith(".example") or ".example." in path:
        return False
    return bool(PRIVATE_PATH.search(path) or (path.startswith("data/") and path != "data/README.md"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also scan reachable Git history; output never includes values")
    args = parser.parse_args()
    problems = []
    paths = sorted(set(git("ls-files", "--cached", "--others", "--exclude-standard").decode().splitlines()))
    for name in paths:
        path = ROOT / name
        if path.is_file():
            if private_path(name):
                problems.append(f"{name}: private-looking path must not be published")
            problems += [f"{name}:{line}: {label} (value redacted)" for line, label in findings(path.read_bytes())]
    scanned_blobs = 0
    if args.history:
        paths_by_blob = {}
        for commit in git("rev-list", "--all").decode().splitlines():
            for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
                if not entry:
                    continue
                metadata, name = entry.split(b"\t", 1)
                name = name.decode()
                oid = metadata.decode().split()[2]
                if private_path(name):
                    problems.append(f"{commit[:12]}:{name}: private-looking historical path")
                paths_by_blob.setdefault(oid, name)
        for oid, name in paths_by_blob.items():
            problems += [f"{oid[:12]}:{name}:{line}: {label} (value redacted)" for line, label in findings(git("cat-file", "blob", oid))]
            scanned_blobs += 1
    if problems:
        raise SystemExit("\n".join(sorted(set(problems))))
    print(f"No matching text credentials/private paths in {len(paths)} current files" + (f" and {scanned_blobs} historical blobs." if args.history else "."))


if __name__ == "__main__":
    main()
