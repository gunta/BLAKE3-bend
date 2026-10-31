#!/usr/bin/env python3
"""Everything turboblake copies or mirrors from elsewhere, and what changed
there since we last took it. The list and the pins are upstreams.json.

  upstream.py status            one line per upstream; exits 3 if any moved
  upstream.py report [OUT]      the brief for the agent (.upstream/REPORT.md):
                                for each upstream that moved, its new commits,
                                the diff of every file we copy or watch, and
                                our own changes to the copies (ours to keep)
  upstream.py apply [NAME...]   takes the vendored files: a three-way merge of
                                pin -> latest into ours (conflict markers
                                where both changed), and the fork's copies
  upstream.py pin NAME [REF]    records REF (default: the latest release, or
                                the installed Bend2) as taken

Kinds: fork (this repository; scripts/sync-upstream.sh merges it, and its pin
is the merge base with HEAD, or with $UPSTREAM_BASE), vendored (files copied, maybe changed), api (a package
whose API a binding mirrors: reported, never copied), toolchain (Bend2).
Clones are cached in .upstream/cache; nothing here commits.
"""
import fnmatch
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "upstreams.json"
WORK = ROOT / ".upstream"
CACHE = WORK / "cache"
BEND = os.environ.get("BEND", str(pathlib.Path.home() / ".bend/bin/bend"))
MAX_DIFF = 600  # lines of diff per file in the report


def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def load():
    return json.loads(MANIFEST.read_text())


def version_key(tag):
    return [int(n) for n in re.findall(r"\d+", tag)]


class Upstream:
    """One entry of upstreams.json, fetched: base (what we have), head (the
    newest), in the git directory gd."""

    def __init__(self, name, e, fetch=True):
        self.name, self.e, self.kind = name, e, e["kind"]
        self.gd = None
        self.base = self.head = self.base_label = self.head_label = None
        self.note = ""
        if self.kind == "toolchain":
            self.base = self.base_label = e["pin"]
            self.head = self.head_label = bend_version()
            return
        if self.kind == "fork":
            self.gd = ROOT
            remote = e["remote"]
            if git("remote", "get-url", remote, check=False).strip() == "":
                git("remote", "add", remote, e["repo"])
            if fetch:
                git("fetch", "--quiet", "--tags", remote)
            ref = f"{remote}/{e['branch']}"
            ours = os.environ.get("UPSTREAM_BASE", "HEAD")
            self.base = git("merge-base", ours, ref).strip()
            self.head = git("rev-parse", ref).strip()
            self.base_label = describe(self.gd, self.base)
            self.head_label = describe(self.gd, self.head)
            return
        self.gd = CACHE / name
        if not (self.gd / ".git").exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", e["repo"], str(self.gd)], check=True)
        elif fetch:
            git("fetch", "--quiet", "--tags", "--force", "origin", cwd=self.gd)
        tags = [t for t in git("tag", cwd=self.gd).split() if re.match(e["tags"], t)]
        latest = max(tags, key=version_key)
        self.base_label, self.head_label = e["pin"], latest
        self.base = git("rev-parse", e["pin"] + "^{commit}", cwd=self.gd).strip()
        self.head = git("rev-parse", latest + "^{commit}", cwd=self.gd).strip()
        unreleased = git("rev-list", "--count", f"{latest}..origin/HEAD", cwd=self.gd).strip()
        if unreleased != "0":
            self.note = f"{unreleased} commit(s) on its default branch after {latest}, unreleased"

    @property
    def moved(self):
        return self.base != self.head

    def commits(self):
        if self.kind == "toolchain":
            return []
        return git("log", "--oneline", "--no-merges", f"{self.base}..{self.head}", cwd=self.gd).splitlines()

    def changed(self):
        if self.kind == "toolchain":
            return []
        return git("diff", "--name-only", self.base, self.head, cwd=self.gd).splitlines()

    def watched(self):
        """Changed files we copy or watch, each with why it matters."""
        e = self.e
        rules = dict(e.get("watch", {}))
        for local, up in e.get("files", {}).items():
            rules[up] = f"copied to {local}"
        out = []
        for f in self.changed():
            hits = [why for pat, why in rules.items() if not pat.startswith("!") and fnmatch.fnmatch(f, pat)]
            if any(pat.startswith("!") and fnmatch.fnmatch(f, pat[1:]) for pat in rules):
                continue
            if hits:
                out.append((f, hits[0]))
        return out

    def show(self, rev, path):
        r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=self.gd, capture_output=True)
        return r.stdout if r.returncode == 0 else None


def describe(gd, rev):
    d = git("describe", "--tags", "--always", rev, cwd=gd, check=False).strip()
    return d or rev[:12]


def bend_version():
    try:
        out = subprocess.run([BEND, "version"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return "not installed"
    m = re.search(r"\d+\.\d+\.\d+", out)
    return m.group(0) if m else out.strip()


def bend_notice():
    try:
        return json.loads((pathlib.Path(BEND).parents[1] / "check.json").read_text()).get("notice", "")
    except (OSError, ValueError):
        return ""


def fetch_all(names=None):
    m = load()
    return [Upstream(n, e) for n, e in m.items() if not names or n in names]


def cmd_status(args):
    ups = fetch_all(args)
    for u in ups:
        state = "moved" if u.moved else "current"
        extra = ""
        if u.kind != "toolchain" and u.moved:
            extra = f", {len(u.commits())} commit(s), {len(u.watched())} file(s) we copy or watch"
        if u.kind == "toolchain" and bend_notice():
            extra = f" ({bend_notice()})"
        if u.note:
            extra += f"; {u.note}"
        print(f"{u.name:16} {u.kind:9} {u.base_label} -> {u.head_label}  {state}{extra}")
    return 3 if any(u.moved for u in ups) else 0


def fence(text, lang="diff"):
    lines = text.splitlines()
    if len(lines) > MAX_DIFF:
        lines = lines[:MAX_DIFF] + [f"... {len(lines) - MAX_DIFF} more lines (git diff in the cache or the repo)"]
    return f"```{lang}\n" + "\n".join(lines) + "\n```\n"


def our_delta(u, local, up):
    """Our changes to a copied file: upstream at the pin -> ours."""
    base = u.show(u.base, up) or b""
    with tempfile.NamedTemporaryFile(suffix=pathlib.Path(up).suffix) as t:
        t.write(base)
        t.flush()
        r = subprocess.run(["diff", "-u", "--label", f"{u.base_label}:{up}", "--label", local, t.name, str(ROOT / local)],
                           capture_output=True, text=True)
    return r.stdout


def cmd_report(args):
    out = pathlib.Path(args[0]) if args else WORK / "REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    ups = fetch_all()
    w = []
    w.append("# Upstream report\n")
    w.append("What moved in everything turboblake copies or mirrors "
             "(scripts/upstream/upstreams.json), for the agent to decide what to "
             "adopt (scripts/upstream/AGENT.md).\n")
    w.append("| upstream | kind | have | newest | state |\n|---|---|---|---|---|")
    for u in ups:
        w.append(f"| {u.name} | {u.kind} | {u.base_label} | {u.head_label} | {'**moved**' if u.moved else 'current'} |")
    w.append("")
    for u in ups:
        if not u.moved:
            continue
        e = u.e
        w.append(f"## {u.name}: {u.base_label} -> {u.head_label}\n")
        w.append(e.get("why", "") + "\n")
        if u.note:
            w.append(f"Also: {u.note}.\n")
        if u.kind == "toolchain":
            w.append(f"Installed Bend2 is {u.head_label}, pinned {u.base_label}. "
                     "Everything Bend emits must be regenerated, proved and re-raced "
                     "with it (AGENT.md, Bend2).\n")
            continue
        if "repo" in e:
            w.append(f"Compare: {e['repo']}/compare/{u.base}...{u.head}\n")
        commits = u.commits()
        w.append(f"### {len(commits)} commit(s)\n")
        w.append(fence("\n".join(commits[:300]), ""))
        w.append("### Files changed\n")
        w.append(fence(git("diff", "--stat=100", u.base, u.head, cwd=u.gd), ""))
        watched = u.watched()
        if watched:
            w.append("### Files we copy or watch\n")
            for f, why in watched:
                w.append(f"- `{f}`: {why}")
            w.append("")
            for f, _ in watched:
                w.append(f"#### `{f}`\n")
                w.append(fence(git("diff", u.base, u.head, "--", f, cwd=u.gd)))
        for local, up in e.get("files", {}).items():
            d = our_delta(u, local, up)
            if d:
                w.append(f"### Our changes to `{local}` (keep them when taking upstream's)\n")
                w.append(fence(d))
        if e.get("mirrors"):
            w.append("Our files that mirror this API: " + ", ".join(f"`{m}`" for m in e["mirrors"]) + "\n")
    out.write_text("\n".join(w))
    print(f"wrote {out}")
    return 0


def merge_file(u, local, up):
    """Three-way merge of a vendored file. Returns 'same', 'taken', 'merged' or
    'conflict' (markers left in the file)."""
    base, theirs = u.show(u.base, up), u.show(u.head, up)
    path = ROOT / local
    ours = path.read_bytes() if path.exists() else None
    if theirs is None:
        return "deleted upstream"
    if base == theirs:
        return "same"
    if ours is None or ours == base:
        path.write_bytes(theirs)
        return "taken"
    with tempfile.TemporaryDirectory() as d:
        b, t = pathlib.Path(d, "base"), pathlib.Path(d, "theirs")
        b.write_bytes(base or b"")
        t.write_bytes(theirs)
        r = subprocess.run(["git", "merge-file", "-L", "ours", "-L", f"pin {u.base_label}", "-L", f"upstream {u.head_label}",
                            str(path), str(b), str(t)])
    return "conflict" if r.returncode else "merged"


def cmd_apply(args):
    ups = fetch_all(args)
    conflicts = 0
    for u in ups:
        for local, src in u.e.get("copies", {}).items():
            a, b = ROOT / src, ROOT / local
            if a.read_bytes() != b.read_bytes():
                b.write_bytes(a.read_bytes())
                print(f"{u.name}: {local} <- {src}")
        if u.kind != "vendored" or not u.moved:
            continue
        for local, up in u.e["files"].items():
            r = merge_file(u, local, up)
            conflicts += r == "conflict"
            print(f"{u.name}: {local} <- {up} @ {u.head_label}: {r}")
    if conflicts:
        print(f"{conflicts} file(s) with conflict markers: resolve them", file=sys.stderr)
    return 1 if conflicts else 0


def cmd_pin(args):
    if not args:
        sys.exit("usage: upstream.py pin NAME [REF]")
    m = load()
    name = args[0]
    if name not in m:
        sys.exit(f"no upstream {name} (have: {', '.join(m)})")
    if m[name]["kind"] == "fork":
        sys.exit(f"{name} is merged with git: its pin is the merge base")
    u = Upstream(name, m[name], fetch=False)
    ref = args[1] if len(args) > 1 else u.head_label
    m[name]["pin"] = ref
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    print(f"{name} pinned at {ref}")
    return 0


def main():
    cmds = {"status": cmd_status, "report": cmd_report, "apply": cmd_apply, "pin": cmd_pin}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    sys.exit(cmds[sys.argv[1]](sys.argv[2:]))


if __name__ == "__main__":
    main()
