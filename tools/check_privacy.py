"""Check the publication tree/history without printing matching private values."""
import argparse
from pathlib import Path, PurePosixPath
import json
import re
import subprocess

if __package__:
    from .build_brand import icon
else:
    from build_brand import icon

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"AGENTS.md", "README.md", "PRIVACY.md", "SECURITY.md", "LICENSE", ".gitignore", "hacs.json", "pytest.ini", "requirements-dev.txt"}
SKIP_LOCAL = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
BRAND = "custom_components/nrg/brand/icon.png"
EMAIL = re.compile(r"[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
RULES = {
    "private network address": re.compile(r"(?<![\w.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\w.])"),
    "network-derived entity ID": re.compile(r"\b(?:sensor|binary_sensor)\.[a-z0-9_]*(?:192_168_|10_\d{1,3}_\d{1,3}_)\d+"),
    "private host": re.compile(r"\b[a-z0-9.-]+\.home\.arpa\b", re.I),
    "personal filesystem path": re.compile(r"/(?:var/home|home|Users)/[A-Za-z0-9_.-]+/"),
    "GitHub credential": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "credential assignment": re.compile(r'''(?i)(?:password|api[_-]?key|access[_-]?token|long_lived_token)\s*[=:]\s*["'][A-Za-z0-9_./+\-=]{20,}["']'''),
}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def allowed_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    if name in ROOT_FILES or name in {".github/CODEOWNERS", BRAND, "custom_components/nrg/assets/guide.html"}:
        return True
    if not path.parts or any(part.startswith(".") for part in path.parts[1:]):
        return False
    if path.parts[0] == "custom_components":
        if len(path.parts) < 3 or path.parts[1] != "nrg":
            return False
        if len(path.parts) == 3:
            return path.suffix == ".py" or path.name in {"manifest.json", "strings.json", "dashboard-package.yaml"}
        if len(path.parts) == 4 and path.parts[2] == "translations":
            return path.suffix == ".json"
        return name in {"custom_components/nrg/dashboards/nrg-home.yaml", "custom_components/nrg/dashboards/nrg-settings.yaml"}
    if path.parts[0] == "docs":
        return path.suffix == ".md"
    if path.parts[0] in {"tests", "tools"}:
        return path.suffix == ".py"
    return (len(path.parts) == 3 and path.parts[:2] == (".github", "workflows") and path.suffix in {".yaml", ".yml"}
            or path.parts == (".github", "dependabot.yml"))


def check_text(text, indicators=(), *, check_emails=True):
    findings = []
    for label, pattern in RULES.items():
        for match in pattern.finditer(text):
            findings.append((text.count("\n", 0, match.start()) + 1, label))
    if check_emails:
        for match in EMAIL.finditer(text):
            address = match[0].lower()
            domain = address.rsplit("@", 1)[1]
            if (domain not in {"users.noreply.github.com", "example.com", "example.org", "example.invalid"}
                    and address != "noreply@github.com"):
                findings.append((text.count("\n", 0, match.start()) + 1, "non-placeholder email address"))
    folded = text.casefold()
    for indicator in indicators:
        if indicator and (position := folded.find(indicator.casefold())) >= 0:
            findings.append((text.count("\n", 0, position) + 1, "owner-supplied private indicator"))
    return sorted(set(findings))


def check_file(name, content, indicators=()):
    if not allowed_path(name):
        return [(0, "file outside publication allowlist")]
    if name == BRAND:
        return [] if content == icon() else [(0, "brand image differs from reproducible generic artwork")]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [(0, "unexpected binary file")]
    if "\x00" in text:
        return [(0, "unexpected binary content")]
    return check_text(text, indicators)


def scan(root, *, history=False, indicators=()):
    findings, checked = [], 0
    try:
        git(root, "rev-parse", "--show-toplevel")
    except subprocess.CalledProcessError:
        names = [str(p.relative_to(root)) for p in root.rglob("*")
                 if p.is_file() and not set(p.relative_to(root).parts) & SKIP_LOCAL]
        repository = False
    else:
        names = [name.decode() for name in git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0") if name]
        repository = True
    for name in names:
        path = root / name
        if path.is_symlink():
            findings.append((name, 0, "symlinks are not publication assets"))
            continue
        if not path.is_file():
            findings.append((name, 0, "tracked file missing from working tree"))
            continue
        checked += 1
        findings.extend((name, line, label) for line, label in check_file(name, path.read_bytes(), indicators))
    seen = set()
    if repository:
        # The index is the next commit's content, which may differ from disk.
        for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not record:
                continue
            info, name = record.split(b"\t", 1)
            mode, oid, stage = info.decode().split()
            name = name.decode()
            if stage != "0":
                findings.append((f"index:{name}", 0, "unresolved merge in publication index"))
                continue
            if mode not in {"100644", "100755"}:
                findings.append((f"index:{name}", 0, "non-regular tracked file"))
                continue
            seen.add((name, oid))
            checked += 1
            content = git(root, "cat-file", "blob", oid)
            findings.extend((f"index:{name}", line, label) for line, label in check_file(name, content, indicators))
    if history and not repository:
        findings.append(("history", 0, "Git history unavailable"))
    if history and repository:
        if git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
            findings.append(("history", 0, "shallow Git history; fetch full history before publication"))
        commits = git(root, "rev-list", "--all").decode().splitlines()
        for commit in commits:
            identity = git(root, "show", "-s", "--format=%an%n%ae%n%cn%n%ce", commit).decode()
            fields = identity.splitlines()
            dependabot = (len(fields) == 4 and fields[0].casefold() in {"dependabot", "dependabot[bot]"}
                          and fields[1].casefold().endswith("@users.noreply.github.com")
                          and fields[3].casefold().endswith("@users.noreply.github.com"))
            message = git(root, "show", "-s", "--format=%B", commit).decode()
            findings.extend((f"commit {commit[:12]} metadata", line, label) for line, label in check_text(identity, indicators))
            # Dependabot release notes quote upstream public contact addresses;
            # keep secret/private-indicator checks, but don't misclassify those as
            # the commit author's personal address.
            findings.extend((f"commit {commit[:12]} message", line, label)
                            for line, label in check_text(message, indicators, check_emails=not dependabot))
            for record in git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
                if not record:
                    continue
                info, name = record.split(b"\t", 1)
                mode, kind, oid = info.decode().split()
                name = name.decode()
                if mode != "100644" and mode != "100755":
                    findings.append((f"history:{name}", 0, "non-regular tracked file"))
                    continue
                if (name, oid) in seen:
                    continue
                seen.add((name, oid))
                checked += 1
                content = git(root, "cat-file", "blob", oid)
                findings.extend((f"history:{name}", line, label) for line, label in check_file(name, content, indicators))
        tags = git(root, "for-each-ref", "--format=%(objecttype) %(objectname)", "refs/tags").decode().splitlines()
        seen_tags = set()
        for tag in tags:
            kind, oid = tag.split()
            while kind == "tag" and oid not in seen_tags:
                seen_tags.add(oid)
                metadata = git(root, "cat-file", "tag", oid).decode()
                findings.extend((f"tag {oid[:12]} metadata", line, label) for line, label in check_text(metadata, indicators))
                # Follow nested annotated tags as well as ordinary release tags.
                oid = metadata.splitlines()[0].removeprefix("object ")
                kind = git(root, "cat-file", "-t", oid).decode().strip()
    return checked, sorted(set(findings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--history", action="store_true", help="Check all reachable revisions and commit metadata")
    parser.add_argument("--deny-file", type=Path, help="Local-only JSON list of private strings; never add this file to Git")
    args = parser.parse_args()
    indicators = json.loads(args.deny_file.read_text()) if args.deny_file else []
    if not isinstance(indicators, list) or not all(isinstance(value, str) for value in indicators):
        parser.error("The deny file must contain a JSON list of strings")
    checked, findings = scan(args.root.resolve(), history=args.history, indicators=indicators)
    for name, line, label in findings:
        print(f"{name}:{line}: {label}")
    print(f"Privacy check: {checked} file revisions checked; {len(findings)} findings.")
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()
