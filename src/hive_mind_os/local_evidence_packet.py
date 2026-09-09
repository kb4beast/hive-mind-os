"""Pinned source packets and bounded deterministic effects in isolated Git clones.

Model reports are inputs, never execution receipts. This module does not execute
model-supplied commands, authenticate workers, or confer promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit

MAX_CONTENT_BYTES = 140_000
_SECRET_PATH = re.compile(r"(?i)(^|/)(?:\.env(?:\..*)?|secrets?(?:\..*)?|credentials?(?:\..*)?|id_(?:rsa|ed25519))(?:$|/)|\.(?:pem|p12|pfx|key)$")
_SECRET_CONTENT = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\b(?:ghp_|github_pat_|sk-(?:proj-)?)[A-Za-z0-9_-]{16,}|"
    r"(?i:\b(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"']?[A-Za-z0-9_+/=-]{20,})"
)
_SOURCE_SUFFIXES = frozenset({".py", ".md", ".toml", ".json", ".yaml", ".yml", ".txt", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".cs", ".c", ".h", ".cpp", ".sh", ".ps1"})
_CODE_SUFFIXES = _SOURCE_SUFFIXES - {".md", ".toml", ".json", ".yaml", ".yml", ".txt"}
_PRIORITIES = (
    "idea_lineage", "courtroom", "tournament_plan_factory", "tournament_cli",
    "local_dag_runtime", "local_run_authority", "local_codex_worker", "local_evidence_packet",
)


class LocalEvidenceError(ValueError):
    """The requested evidence operation cannot meet its local contract."""


def _git(workspace: Path, *arguments: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(workspace), *arguments],
        input=data, capture_output=True, timeout=60, check=False,
    )
    if result.returncode:
        raise LocalEvidenceError(f"git {arguments[0]} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def _safe_path(workspace: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(character in name for character in "\x00\r\n\t")
            or PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive):
        raise LocalEvidenceError("patch/test path must be repository-relative")
    parts = name.split("/")
    if any(part in {"", ".", ".."} or part.casefold() == ".git"
           or part.rstrip(" .") != part for part in parts):
        raise LocalEvidenceError("unsafe repository path")
    root = workspace.resolve()
    target = root
    for part in parts:
        target /= part
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            raise LocalEvidenceError("symlink or junction targets are forbidden")
    if not target.resolve().is_relative_to(root):
        raise LocalEvidenceError("repository path escapes the isolated workspace")
    return target


def _isolated_clone(workspace: Path) -> Path:
    root = workspace.resolve()
    if not (root / ".git").is_dir() or (root / ".git").is_symlink():
        raise LocalEvidenceError("effects require an isolated clone with its own .git directory")
    top = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != top or _git(root, "remote").strip():
        raise LocalEvidenceError("effects require an isolated clone with no remotes")
    branch = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--quiet", "HEAD"],
                            capture_output=True, timeout=30, check=False)
    if branch.returncode != 1:
        raise LocalEvidenceError("effects require an isolated clone at a detached HEAD")
    return root


def _reject_tracked_symlinks(workspace: Path, paths: list[str]) -> None:
    if not paths:
        return
    for row in _git(workspace, "ls-files", "--stage", "-z", "--", *paths).split(b"\0"):
        if row.startswith(b"120000 "):
            raise LocalEvidenceError("tracked symlink targets are forbidden, including Windows link placeholders")


def build_source_packet(workspace: Path, node_id: str, predecessor_reports: list[dict], *, max_content_bytes: int = MAX_CONTENT_BYTES) -> dict:
    """Read whole UTF-8 blobs from HEAD, recording everything omitted explicitly."""
    if not 1 <= max_content_bytes <= MAX_CONTENT_BYTES:
        raise LocalEvidenceError("source packet budget is outside its supported bound")
    root = workspace.resolve()
    head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    inventory: list[dict[str, Any]] = []
    for entry in _git(root, "ls-tree", "-r", "-l", "-z", "--full-tree", head).split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, blob, size = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8", "surrogateescape")
        inventory.append({"path": name, "mode": mode, "kind": kind,
                          "blob_hash": blob, "size_bytes": int(size) if size != "-" else None})

    tracked_names = {item["path"] for item in inventory}
    def citations(value: Any) -> set[str]:
        if isinstance(value, str):
            return set(re.findall(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+", value)) & tracked_names
        children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        return {name for item in children for name in citations(item)}

    def shared_stem(name: str) -> str:
        return PurePosixPath(name).stem.removeprefix("test_").removesuffix("_test").removesuffix(".test").removesuffix(".spec")

    canonical_reports: list[tuple[int, dict]] = []
    def collect_reports(value: Any, inherited_node: str = "") -> None:
        if isinstance(value, list):
            for entry in value:
                collect_reports(entry, inherited_node)
        elif isinstance(value, dict):
            stage = str(value.get("node_id", inherited_node)).upper()
            if "ideas" in value or "selected_idea_ids" in value:
                rank = 2 if stage.startswith("COURT-") else 1 if stage.startswith("PROPOSE-") else 0
                canonical_reports.append((rank, value))
            # The first worker owns the node report; witness selections do not replace it.
            workers = value.get("workers")
            if isinstance(workers, list) and workers:
                collect_reports(workers[0], stage)
            if isinstance(value.get("report"), dict):
                collect_reports(value["report"], stage)

    cited_names: set[str] = set()
    selected_stems: dict[str, int] = {}
    if any(label in node_id.upper() for label in ("CHALLENGER", "VERIFY", "COURT", "JUDGE", "CROSS", "REVISE")):
        cited_names = citations(predecessor_reports)
        collect_reports(predecessor_reports)
        ranked_reports = sorted(enumerate(canonical_reports), key=lambda item: (item[1][0], item[0]), reverse=True)
        selection = next((report["selected_idea_ids"] for _, (_, report) in ranked_reports
                          if isinstance(report.get("selected_idea_ids"), list)), [])
        for idea_id in selection:
            for _, (_, report) in ranked_reports:
                matching = [idea for idea in report.get("ideas", [])
                            if isinstance(idea, dict) and idea.get("idea_id") == idea_id]
                names = {name for idea in matching for name in citations(idea.get("source"))
                         if PurePosixPath(name).suffix.lower() in _CODE_SUFFIXES}
                if names:
                    for name in sorted(names):
                        selected_stems.setdefault(shared_stem(name), len(selected_stems))
                    break
    cited_code_stems = {shared_stem(name) for name in cited_names
                        if PurePosixPath(name).suffix.lower() in _CODE_SUFFIXES}
    groups = {
        "RUNTIME": ("local_dag_runtime", "local_run_authority", "local_codex_worker"),
        "LEARNING": ("idea_lineage", "courtroom"),
        "ORCHESTRATION": ("tournament_plan_factory", "tournament_cli", "local_dag_runtime"),
        "AGENTS": ("idea_lineage", "tournament_cli"),
        "COURT": ("courtroom", "idea_lineage"), "CROSS": ("courtroom", "idea_lineage"),
    }
    favored = next((value for key, value in groups.items() if key in node_id.upper()), ())

    def priority(item: dict) -> tuple[int, int, str, str]:
        name = item["path"]
        stem = shared_stem(name)
        code = PurePosixPath(name).suffix.lower() in _CODE_SUFFIXES
        if node_id == "BASELINE-001" and name in {
            "docs/architecture/HARDENED_VISION_CONTRACT.md",
            "docs/architecture/CONGLOMERATED_SYSTEM.md", "src/hive_mind_os/founding_docket.py",
        }:
            return (-3, 0, "", name)
        if code and stem in selected_stems:
            return (-2, selected_stems[stem], stem, name)
        if code and stem in cited_code_stems:
            return (-1, 0, stem, name)
        if name in cited_names:
            return (0, 0, "", name)
        if stem in favored:
            return (1, favored.index(stem), "", name)
        if name in {"README.md", "pyproject.toml", "AGENTS.md", "LICENSE"}:
            return (2, 0, "", name)
        if "adr" in name.casefold() or "/decisions/" in name:
            number = re.search(r"(?:ADR[-_]?|(?:^|/))(\d+)", name, re.IGNORECASE)
            ordinal = int(number.group(1)) if number else 0
            return (3 if ordinal >= 77 else 5, -ordinal, "", name)
        if stem in _PRIORITIES:
            return (4, _PRIORITIES.index(stem), "", name)
        return (6 if name.startswith(("src/", "tests/", "test/")) else 7, 0, "", name)

    selected, omitted, content_bytes = [], [], 0
    for item in sorted(inventory, key=priority):
        name, reason = item["path"], None
        if item["kind"] != "blob" or item["mode"] == "120000":
            reason = "symlink or non-file entry"
        elif _SECRET_PATH.search(name):
            reason = "secret-sensitive path"
        elif PurePosixPath(name).suffix.lower() not in _SOURCE_SUFFIXES and name != "LICENSE":
            reason = "outside source/text selection"
        elif item["size_bytes"] > max_content_bytes - content_bytes:
            reason = "whole-file content budget exhausted; file not truncated"
        else:
            try:
                _safe_path(root, name)
                body = _git(root, "cat-file", "blob", item["blob_hash"])
                text = body.decode("utf-8")
                if "\x00" in text:
                    reason = "binary content"
                elif _SECRET_CONTENT.search(text):
                    reason = "secret-like content"
                else:
                    selected.append(dict(item, content=text, sha256=hashlib.sha256(body).hexdigest()))
                    content_bytes += len(body)
            except (UnicodeError, LocalEvidenceError):
                reason = "non-UTF-8 content or unsafe filesystem path"
        if reason:
            omitted.append({"path": name, "blob_hash": item["blob_hash"], "reason": reason})
    return {
        "schema_version": "1", "node_id": node_id, "workspace": str(root), "head": head,
        "inventory": inventory, "selected_files": selected, "omitted_files": omitted,
        "evidence_obligations": [
            "Only listed selected_files were supplied as whole-file content; omitted files remain unreviewed.",
            "Source identity and blob hashes do not establish ingestion, license compatibility, or correctness.",
            "Predecessor reports are attributed assertions, not independent verification receipts.",
        ] if omitted else ["Predecessor reports are attributed assertions, not independent verification receipts."],
        "selected_content_bytes": content_bytes, "max_content_bytes": max_content_bytes,
        "truncated_files": [], "predecessor_reports": predecessor_reports,
    }


def inspect_brain_publication(brain: Path) -> dict:
    """Capture existing Markdown bytes and confined link targets without writing.

    Whole index/idea bodies share the source-packet content limit. Other Markdown
    files still receive hashes and link checks; remote URLs and fragments are not
    fetched or semantically verified. This is an observation, not publication.
    """
    root = brain.resolve()
    if not root.is_dir():
        raise LocalEvidenceError("brain publication directory does not exist")
    obligations: set[str] = set()

    def markdown_paths() -> list[str]:
        names = []
        for directory, children, files in os.walk(root, followlinks=False):
            retained = []
            for child in sorted(children):
                target = Path(directory) / child
                if (target.is_symlink() or getattr(target, "is_junction", lambda: False)()
                        or not target.resolve().is_relative_to(root)):
                    obligations.add(f"Directory link was not followed: {target.relative_to(root).as_posix()}")
                else:
                    retained.append(child)
            children[:] = retained
            names.extend((Path(directory) / name).relative_to(root).as_posix()
                         for name in files if name.casefold().endswith(".md"))
        return sorted(names)

    names = markdown_paths()
    index_paths = [name for name in names if name.casefold() == "index.md"]
    idea_paths = [name for name in names if PurePosixPath(name).name.startswith("idea-")]
    relevant = set(index_paths + idea_paths)
    inventory, selected, omitted, links = [], [], [], []
    fingerprints: dict[str, tuple[int, int, int]] = {}
    changed: set[str] = set()
    link_checked: set[str] = set()
    content_bytes = 0
    inline_links = re.compile(r"(?<!!)\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\s)\n]+))(?:\s+[\"'][^\n]*?[\"'])?\s*\)")
    wiki_links = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")

    def inspect_link(source: str, line: int, label: str, target: str, *, wiki: bool = False) -> dict:
        record: dict[str, Any] = {"source": source, "line": line, "label": label, "target": target,
                                  "resolved_path": None, "status": "unverified"}
        try:
            parsed = urlsplit(target)
            if PureWindowsPath(target).drive or target.startswith(("/", "\\")):
                record["status"] = "outside_brain"
            elif parsed.scheme or parsed.netloc:
                record["status"] = "external_unchecked" if parsed.scheme in {"https", "http", "mailto"} else "unsupported_scheme"
            else:
                local = unquote(parsed.path)
                if "\\" in local or "\x00" in local:
                    raise LocalEvidenceError("unsafe local link")
                if wiki and local and not PurePosixPath(local).suffix:
                    local += ".md"
                target_path = root / source if not local else root / PurePosixPath(source).parent / local
                absolute = Path(os.path.abspath(target_path))
                if not absolute.is_relative_to(root) or not target_path.resolve().is_relative_to(root):
                    record["status"] = "outside_brain"
                else:
                    relative = absolute.relative_to(root).as_posix()
                    destination = _safe_path(root, relative)
                    record["resolved_path"] = relative
                    record["status"] = "verified" if destination.is_file() else "missing"
                if parsed.fragment:
                    obligations.add("Local file targets were checked; heading and block fragments were not verified.")
            if record["status"] == "external_unchecked":
                obligations.add("External URLs were recorded without network requests or verification.")
        except (ValueError, OSError):
            record["status"] = "unsafe_or_unsupported"
        return record

    for name in sorted(names, key=lambda name: (0 if name in index_paths else 1 if name in idea_paths else 2, name)):
        path = root / name
        try:
            _safe_path(root, name)
            before = path.stat()
            hasher, chunks, byte_count = hashlib.sha256(), [], 0
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
                    byte_count += len(chunk)
                    if byte_count <= MAX_CONTENT_BYTES:
                        chunks.append(chunk)
                    else:
                        chunks.clear()
            after = path.stat()
            fingerprint = (after.st_size, after.st_mtime_ns, after.st_ino)
            fingerprints[name] = fingerprint
            if (before.st_size, before.st_mtime_ns, before.st_ino) != fingerprint:
                changed.add(name)
            digest = hasher.hexdigest()
            inventory.append({"path": name, "size_bytes": byte_count, "sha256": digest})
            text = b"".join(chunks).decode("utf-8") if byte_count <= MAX_CONTENT_BYTES else None
            if text is not None:
                # Generated brain links occupy one line. Ignore fenced examples;
                # multiline/reference/HTML links remain outside this parser.
                fenced = False
                for line_number, line in enumerate(text.splitlines(), 1):
                    if line.lstrip().startswith(("```", "~~~")):
                        fenced = not fenced
                        continue
                    if fenced:
                        continue
                    for match in inline_links.finditer(line):
                        links.append(inspect_link(name, line_number, match[1], match[2] or match[3]))
                    for match in wiki_links.finditer(line):
                        target, _, alias = match[1].partition("|")
                        links.append(inspect_link(name, line_number, alias or target, target, wiki=True))
                link_checked.add(name)
            else:
                obligations.add(f"Link inspection omitted for oversized Markdown file: {name}")
            if name in relevant and text is not None and content_bytes + byte_count <= MAX_CONTENT_BYTES:
                selected.append({"path": name, "size_bytes": byte_count, "sha256": digest, "content": text})
                content_bytes += byte_count
            else:
                reason = "whole-file content budget exceeded; file not truncated" if name in relevant else "outside index and idea content selection; hash and available link checks retained"
                omitted.append({"path": name, "sha256": digest, "reason": reason})
        except (OSError, ValueError) as error:
            if not any(item["path"] == name for item in inventory):
                inventory.append({"path": name, "size_bytes": None, "sha256": None})
            omitted.append({"path": name, "sha256": next(item["sha256"] for item in inventory if item["path"] == name),
                            "reason": f"Markdown not safely readable: {type(error).__name__}"})
            obligations.add(f"Content and links remain unverified for {name}")

    current_names = markdown_paths()
    changed.update(set(names) ^ set(current_names))
    for name, fingerprint in fingerprints.items():
        try:
            current = (root / name).stat()
            if (current.st_size, current.st_mtime_ns, current.st_ino) != fingerprint:
                changed.add(name)
        except OSError:
            changed.add(name)
    inventory.sort(key=lambda item: item["path"])
    invalid = [link for link in links if link["status"] not in {"verified", "external_unchecked"}]
    inventory_by_path = {item["path"]: item for item in inventory}
    indexed_ideas = [{"idea_id": link["label"], "path": link["resolved_path"], "status": link["status"],
                      "sha256": inventory_by_path.get(link["resolved_path"], {}).get("sha256")}
                     for link in links if link["source"] in index_paths and link["resolved_path"]
                     and PurePosixPath(link["resolved_path"]).name.startswith("idea-")]
    if not index_paths:
        obligations.add("The publication has no root INDEX.md.")
    if changed:
        obligations.add("Markdown changed during inspection; this is not a consistent filesystem snapshot.")
    obligations.add("Link parsing covers single-line inline Markdown and wiki links; reference-style, multiline, and HTML links are not verified.")
    snapshot = {"brain_directory": str(root), "inventory": inventory, "links": links,
                "changed_during_inspection": sorted(changed)}
    return {
        "schema_version": "1", "brain_directory": str(root),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "snapshot_consistent": not changed, "changed_during_inspection": sorted(changed),
        "inventory": inventory, "selected_files": selected, "omitted_files": omitted,
        "links": links, "invalid_links": invalid, "index_paths": index_paths,
        "indexed_ideas": indexed_ideas, "canonical_idea_ids": list(dict.fromkeys(item["idea_id"] for item in indexed_ideas)),
        "index_and_idea_links_valid": bool(index_paths) and relevant.issubset(link_checked) and not changed
                                      and not any(link["source"] in relevant for link in invalid),
        "selected_content_bytes": content_bytes, "max_content_bytes": MAX_CONTENT_BYTES,
        "truncated_files": [], "evidence_obligations": sorted(obligations),
    }


def _recount_options(patch: str, paths: list[str]) -> tuple[str, ...]:
    # Git recount cannot delimit adjacent traditional multi-file patches without
    # diff --git separators. Preserve their original count-based boundaries.
    return ("--recount",) if len(paths) == 1 or re.search(r"(?m)^diff --git ", patch) else ()


def _patch_paths(workspace: Path, patch: str) -> list[str]:
    if not isinstance(patch, str) or not patch.strip() or "\x00" in patch:
        raise LocalEvidenceError("patch must be a non-empty plain unified diff")
    if re.search(r"(?m)^(?:GIT binary patch|Binary files |rename (?:from|to) |copy (?:from|to) |similarity index )", patch):
        raise LocalEvidenceError("binary, rename, and copy patches are forbidden")
    if re.search(r"(?m)^(?:new file mode|deleted file mode|old mode|new mode) (?!100644$|100755$)", patch):
        raise LocalEvidenceError("patch cannot create symlinks or special file modes")
    paths, old_name, in_hunk = [], None, False
    old_remaining = new_remaining = 0
    for line in patch.splitlines():
        # Unprefixed Git section/hunk markers remain authoritative when a model
        # miscounts a hunk. Counts only locate traditional unified boundaries;
        # Git independently recounts the actual body before any application.
        if line.startswith("diff --git "):
            old_name, in_hunk = None, False
        elif line.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", line)
            if not match:
                raise LocalEvidenceError("invalid plain unified diff hunk header")
            old_remaining, new_remaining = (int(value) if value is not None else 1 for value in match.groups())
            in_hunk = True
        elif in_hunk:
            if line.startswith(" "):
                old_remaining -= 1
                new_remaining -= 1
            elif line.startswith("-"):
                old_remaining -= 1
            elif line.startswith("+"):
                new_remaining -= 1
            in_hunk = old_remaining > 0 or new_remaining > 0
        elif not in_hunk and line.startswith("--- "):
            old_name = line[4:]
            if old_name != "/dev/null":
                if not old_name.startswith("a/"):
                    raise LocalEvidenceError("old patch header requires a/ relative path")
                _safe_path(workspace, old_name[2:])
        elif not in_hunk and line.startswith("+++ "):
            new_name = line[4:]
            if old_name is None:
                raise LocalEvidenceError("patch is missing its old-file header")
            if new_name != "/dev/null":
                if not new_name.startswith("b/"):
                    raise LocalEvidenceError("new patch header requires b/ relative path")
                _safe_path(workspace, new_name[2:])
            if old_name == new_name == "/dev/null":
                raise LocalEvidenceError("patch cannot have two null paths")
            if old_name != "/dev/null" and new_name != "/dev/null" and old_name[2:] != new_name[2:]:
                raise LocalEvidenceError("renaming paths is forbidden")
            paths.append(new_name[2:] if new_name != "/dev/null" else old_name[2:])
    if not paths or len(paths) != len(set(paths)):
        raise LocalEvidenceError("patch requires distinct plain unified file sections")
    # Git parses hunk grammar independently; its interpreted paths must agree.
    parsed = _git(workspace, "apply", *_recount_options(patch, paths), "--numstat", "-z", "-", data=patch.encode("utf-8"))
    actual = []
    for record in parsed.split(b"\0"):
        if record:
            added, deleted, name = record.decode("utf-8").split("\t", 2)
            if not added.isdigit() or not deleted.isdigit():
                raise LocalEvidenceError("binary patch is forbidden")
            _safe_path(workspace, name)
            actual.append(name)
    if sorted(actual) != sorted(paths):
        raise LocalEvidenceError("patch header paths disagree with Git's parsed paths")
    return sorted(paths)


def _changed_paths(workspace: Path) -> list[str]:
    # Compare bytes through Git's normal EOL rules: status can report a stale
    # stat-only modification after a Windows CRLF checkout with optional locks off.
    tracked = _git(workspace, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                   "--name-only", "-z", "HEAD", "--")
    untracked = _git(workspace, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({row.decode("utf-8") for row in (tracked + untracked).split(b"\0") if row})


def apply_proposed_patch(workspace: Path, patch: str, changed_paths: list[str]) -> dict:
    """Check and apply only declared paths in a clean, detached, remote-free clone."""
    root = _isolated_clone(workspace)
    if not isinstance(changed_paths, list) or any(not isinstance(p, str) for p in changed_paths):
        raise LocalEvidenceError("changed_paths must be a list of relative file paths")
    paths = _patch_paths(root, patch)
    if len(changed_paths) != len(set(changed_paths)) or paths != sorted(changed_paths):
        raise LocalEvidenceError("patch paths must exactly match declared changed_paths")
    _reject_tracked_symlinks(root, paths)
    if _changed_paths(root):
        raise LocalEvidenceError("patch application requires a clean isolated workspace")

    def digests() -> dict:
        return {name: hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                for name in paths for target in [_safe_path(root, name)]}

    before = digests()
    encoded = patch.encode("utf-8")
    recount_options = _recount_options(patch, paths)
    _git(root, "apply", *recount_options, "--check", "-", data=encoded)
    _git(root, "apply", *recount_options, "-", data=encoded)
    actual = _changed_paths(root)
    if actual != paths:
        _git(root, "apply", *recount_options, "--reverse", "-", data=encoded)
        raise LocalEvidenceError("applied change set differs from declared paths; patch reversed")
    return {"status": "applied", "head": _git(root, "rev-parse", "HEAD").decode().strip(),
            "patch_sha256": hashlib.sha256(encoded).hexdigest(), "changed_paths": actual,
            "hunk_count_handling": "git apply --recount; original patch bytes preserved" if recount_options else
                                   "git apply; original traditional multi-file boundaries preserved",
            "before_sha256": before, "after_sha256": digests()}


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            result = subprocess.run([str(executable), "/PID", str(process.pid), "/T", "/F"],
                                    capture_output=True, timeout=15, check=False)
            if result.returncode and process.poll() is None:
                raise LocalEvidenceError("process-tree termination failed")
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


def run_focused_checks(workspace: Path, changed_paths: list[str], evidence_directory: Path,
                       timeout_seconds: float) -> dict:
    """Run fixed unittest discovery commands and preserve actual process receipts."""
    root = _isolated_clone(workspace)
    if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise LocalEvidenceError("test timeout must be finite and positive")
    candidates = []
    tests_root = root / "tests"
    if tests_root.is_dir():
        candidates = [p.relative_to(root).as_posix() for p in tests_root.rglob("test_*.py")
                      if p.is_file() and not p.is_symlink()]
    selected = set()
    for name in changed_paths:
        _safe_path(root, name)
        path = PurePosixPath(name)
        if path.name.startswith("test_") and path.suffix == ".py" and (root / name).is_file():
            selected.add(name)
        else:
            for candidate in candidates:
                test_stem = PurePosixPath(candidate).stem
                if test_stem in {f"test_{path.stem}", f"test_{path.parent.name}_{path.stem}"}:
                    selected.add(candidate)
    if not selected:
        return {"status": "no_tests_selected", "checks": [], "total_tests": 0, "all_passed": False,
                "reason": "No corresponding focused unittest files were found; broader validation remains open."}
    _reject_tracked_symlinks(root, sorted(selected))
    evidence_directory = evidence_directory.resolve()
    evidence_directory.mkdir(parents=True, exist_ok=True)
    started, checks = time.monotonic(), []
    environment = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
    options: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
    }
    for number, name in enumerate(sorted(selected), 1):
        _safe_path(root, name)
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            return {"status": "timed_out", "checks": checks,
                    "total_tests": sum(c["test_count"] for c in checks), "all_passed": False,
                    "unexecuted_tests": sorted(selected)[number - 1:]}
        test = PurePosixPath(name)
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(test.parent), "-p", test.name, "-v"]
        stdout_path = evidence_directory / f"check-{number:03d}.stdout.txt"
        stderr_path = evidence_directory / f"check-{number:03d}.stderr.txt"
        timed_out = False
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, shell=False, **options)
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(process)
            except BaseException:
                _kill_tree(process)
                raise
        output, error = stdout_path.read_bytes(), stderr_path.read_bytes()
        counts = re.findall(r"(?m)^Ran (\d+) tests? in ", (output + b"\n" + error).decode("utf-8", "replace"))
        count = int(counts[-1]) if counts else 0
        checks.append({"test_file": name, "command": command, "exit_code": process.returncode,
                       "cwd": str(root), "environment": {"PYTHONPATH": environment["PYTHONPATH"]},
                       "test_count": count, "timed_out": timed_out,
                       "stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
                       "stdout_sha256": hashlib.sha256(output).hexdigest(),
                       "stderr_sha256": hashlib.sha256(error).hexdigest()})
        if timed_out:
            break
    all_passed = len(checks) == len(selected) and all(
        c["exit_code"] == 0 and c["test_count"] > 0 and not c["timed_out"] for c in checks
    )
    return {"status": "passed" if all_passed else "timed_out" if any(c["timed_out"] for c in checks) else "failed",
            "checks": checks, "total_tests": sum(c["test_count"] for c in checks), "all_passed": all_passed,
            "unexecuted_tests": sorted(selected)[len(checks):]}
