"""The chunk counter's high word, hi, through the proofs (ADR 0014).

blake3.bend's counter-taking defs take hi beside their counter, down to
compress8 and compress's second counter word. The generators write the
proofs without it, and this pass adds it to their text, as keyed.py adds
the key: every call of such a def gets hi at its place (compress's 0
becomes hi), and a lemma whose statement then mentions hi takes it as its
last parameter, `for +hi: U32`. A lemma whose statement does not (its
counters fixed by an entry point) passes 0 to the ones it calls."""
import re

from .keyed import close_of, split_args, items

# Where hi goes in each call: the index it takes among the arguments.
POS = {
    "B3.compress8": 4, "B3.chunk.go": 5, "B3.chunk": 3, "B3.c8.go": 5,
    "B3.group": 3, "B3.leaf8": 3, "B3.leaf32": 3, "B3.leaf32.s0": 3,
    "B3.leaf32.s1": 3, "B3.leaf32.s2": 3, "B3.tree8": 8, "B3.tree1": 7,
    "B3.hash.go": 4, "B3.hash.at": 3, "B3.hash1.go": 4, "B3.hash1.at": 3,
    "B3.treeg": 8, "B3.gch": 3, "B3.quad": 3, "B3.quad.s0": 3,
    "B3.quad.s1": 3, "B3.quad.s2": 3, "B3.qtree": 5,
    "Laws.ref.go": 3, "Laws.ref.at": 2, "Laws.ev": 4,
}
for g in ("B3.g4", "B3.g16", "B3.g64"):
    POS.update({g: 3, g + ".s0": 3, g + ".s1": 3, g + ".s2": 3})
CALL_RE = re.compile(r"(?<![\w.])((?:B3|Laws)\.[\w.]+)\(")
HI_RE = re.compile(r"(?<![\w.])hi(?![\w.])")


def xform(s, tok):
    """s with tok as hi in every counter-taking call."""
    out, i = [], 0
    while True:
        m = CALL_RE.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        name, lp = m.group(1), m.end() - 1
        rp = close_of(s, lp)
        args = [xform(a, tok) for a in split_args(s[lp + 1:rp])]
        if name in POS:
            k = POS[name]
            args = args[:k] + [" " + tok] + args[k:]
        elif name == "B3.compress" and args[3].strip() == "0":
            args[3] = args[3].replace("0", tok)
        out.append(name + "(" + ",".join(args) + ")")
        i = rp + 1


def code(text):
    return "".join(l for l in text.splitlines(keepends=True) if not l.lstrip().startswith("#"))


def header(name, text):
    """A def's signature: its parameters and return type, if it has one."""
    m = re.search(r"(?m)^def " + re.escape(name) + r"\(", text)
    rp = close_of(text, m.end() - 1)
    depth = 0
    for j in range(rp + 1, len(text)):
        ch = text[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0 and text[j + 1:j + 2] == "\n":
            return text[m.start():j]
    raise ValueError(name)


def calls(text, names, tok):
    """Appends tok to every call of a name in names (not to a def's own head)."""
    if not names:
        return text
    pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\(")
    out, i = [], 0
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        lp = m.end() - 1
        rp = close_of(text, lp)
        if text[max(0, m.start() - 4):m.start()] == "def ":
            out.append(text[i:lp + 1])
            i = lp + 1
            continue
        inner = calls(text[lp + 1:rp], names, tok)
        sep = ", " if inner.strip() else ""
        out.append(text[i:m.start()] + m.group(1) + "(" + inner + sep + tok + ")")
        i = rp + 1


def add_param(kind, name, text, typed):
    if kind == "law":
        lines = text.splitlines(keepends=True)
        at = max(i for i, l in enumerate(lines) if l.startswith(("law ", "  for ")))
        return "".join(lines[:at + 1]) + "  for +hi: U32\n" + "".join(lines[at + 1:])
    m = re.search(r"(?m)^def " + re.escape(name) + r"\(", text)
    lp = m.end() - 1
    rp = close_of(text, lp)
    sep = ", " if text[lp + 1:rp].strip() else ""
    return text[:rp] + sep + ("+hi: U32" if typed else "hi") + text[rp:]


def transform(body, ext=frozenset()):
    """body with hi threaded; ext: other modules' lemmas that take hi
    (prefixed, C.name). Returns the text and this module's lemmas that do."""
    its = items(body)
    laws = {n for k, n, _ in its if k == "law"}
    stmt = {}
    for k, n, t in its:
        if k == "law":
            stmt[n] = code(t)
        elif k == "def" and n not in laws:
            h = header(n, t)
            ret = h.split("->", 1)[1].strip() if "->" in h else ""
            # a lemma written as a typed def states its fact in its head; a
            # function takes hi whenever its body needs it
            stmt[n] = h if ret.startswith("{") else code(t)
    threaded = set()
    while True:
        new = set()
        for n, s in stmt.items():
            if n in threaded:
                continue
            x = xform(s, "hi")
            if HI_RE.search(x) or (threaded | ext) and calls(x, threaded | ext, "@") != x:
                new.add(n)
        if not new:
            break
        threaded |= new
    out = []
    names = threaded | set(ext)
    for k, n, t in its:
        tok = "hi" if n in threaded else "0"
        x = calls(xform(t, tok), names, tok)
        if n in threaded and k in ("law", "def"):
            typed = k == "def" and n not in laws
            x = add_param(k, n, x, typed)
        out.append(x)
    return "".join(out), threaded


def module(text, imports_end, ext=frozenset()):
    """A whole module: its head (through imports_end) kept, its body threaded."""
    i = text.index(imports_end) + len(imports_end)
    body, threaded = transform(text[i:], ext)
    return text[:i] + body, threaded
