"""keyed.bend: the CPU tree's proof again, for BLAKE3's keyed and
key-derivation modes (blake3.bend's .k defs, which are the default mode's
with the key and the mode flag threaded through).

It is cpu.bend transformed, not written twice: every default-mode call
becomes its .k twin, with the key written as its eight words (k0..k7, so
key8 unfolds the way IV8 does) and the flag kf or-ed into every
compression's flags; the lemmas that then mention the key or the flag, or
call one that does, take k0..k7 and kf; the rest stay cpu.bend's (C.)."""
import re

KEYW = [f"k{i}" for i in range(8)]
KEY = "B3.CV{" + ", ".join(KEYW) + "}"
EXTRA = KEYW + ["kf"]

# Default-mode name -> (keyed name, what changes in the call).
APPEND_KEY = ("key",)
CALLS = {
    "B3.chunk.go": ("B3.chunk.go.k", "kf"),
    "B3.chunk": ("B3.chunk.k", "key"),
    "B3.parent": ("B3.parent.k", "key"),
    "B3.tree1": ("B3.tree1.k", "key"),
    "B3.compress": ("B3.compress", "flags"),
    "B3.compress8": ("B3.compress8.k", "flags"),
    "B3.compress8.p": ("B3.compress8.p.k", "flags"),
    "B3.c8.go": ("B3.c8.go.k", "kf"),
    "B3.group": ("B3.group.k", "key"),
    "B3.par8": ("B3.par8.k", "key"),
    "B3.fold8": ("B3.fold8.k", "key"),
    "B3.leaf8.fin": ("B3.leaf8.fin.k", "key"),
    "B3.leaf8": ("B3.leaf8.k", "key"),
    "B3.leaf32.s0": ("B3.leaf32.s0.k", "key"),
    "B3.leaf32.s1": ("B3.leaf32.s1.k", "key"),
    "B3.leaf32.s2": ("B3.leaf32.s2.k", "key"),
    "B3.leaf32.s3": ("B3.leaf32.s3.k", "key"),
    "B3.leaf32": ("B3.leaf32.k", "key"),
    "B3.tree8": ("B3.tree8.k", "key"),
    "B3.hash.go": ("B3.hash8.go.k", "key"),
    "B3.hash.at": ("B3.hash8.at.k", "key"),
    "B3.IV": (KEY, "const"),
    "B3.IV8": (f"B3.key8({KEY})", "const"),
    "Laws.par.ref": ("par.ref.k", "key"),
    "Laws.ref.go": ("ref.go.k", "key"),
    "Laws.ref.at": ("ref.at.k", "key"),
    "Laws.ev": ("Laws.ev.k", "key"),
    "C.cpu.at": ("cpu.at", "words"),
}
CALL_RE = re.compile(r"(?<![\w.])((?:B3|Laws|C)\.[\w.]+)\(")
OPEN, CLOSE = "([{", ")]}"


def close_of(s, i):
    """The index of the bracket closing the one at s[i]."""
    depth = 0
    for j in range(i, len(s)):
        ch = s[j]
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced: " + s[i:i + 80])


def split_args(s):
    """Top-level comma-separated parts of s, each with its own whitespace."""
    parts, depth, start = [], 0, 0
    for j, ch in enumerate(s):
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[start:j])
            start = j + 1
    parts.append(s[start:])
    return parts if s.strip() else []


def xform(s):
    """s with every default-mode call made its keyed twin."""
    out, i = [], 0
    while True:
        m = CALL_RE.search(s, i)
        if not m:
            out.append(s[i:])
            return "".join(out)
        out.append(s[i:m.start()])
        name, lp = m.group(1), m.end() - 1
        rp = close_of(s, lp)
        args = [xform(a) for a in split_args(s[lp + 1:rp])]
        if name in CALLS:
            new, how = CALLS[name]
            if how == "const":
                out.append(new)
            else:
                if how == "kf":
                    args = args + [" kf"]
                elif how == "key":
                    args = args + [" " + KEY, " kf"]
                elif how == "words":
                    args = args + [" " + v for v in EXTRA]
                elif how == "flags":
                    last = args[-1]
                    ws = last[:len(last) - len(last.lstrip())]
                    args = args[:-1] + [f"{ws}({last.strip()} .|. kf : U32)"]
                out.append(new + "(" + ",".join(args) + ")")
        else:
            out.append(name + "(" + ",".join(args) + ")")
        i = rp + 1


ITEM_RE = re.compile(r"(?m)^(?=law |def |type )")
HEAD_RE = re.compile(r"^(law|def|type) ([\w.]+)")


def items(body):
    """The top-level items, each with the comment lines above it."""
    out, lead = [], ""
    for c in ITEM_RE.split(body):
        if not c.strip():
            lead += c
            continue
        lines = c.splitlines(keepends=True)
        k = len(lines)
        while k > 0 and (not lines[k - 1].strip() or lines[k - 1].startswith("#")):
            k -= 1
        text = lead + "".join(lines[:k])
        lead = "".join(lines[k:])
        hm = re.search(r"(?m)^(law|def|type) ([\w.]+)", text)
        if hm:
            out.append((hm.group(1), hm.group(2), text))
        else:
            lead = text + lead
    return out


def refs(text, names):
    pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w.])")
    return {m.group(1) for m in pat.finditer(text)}


def thread_calls(text, needs):
    """Appends k0..k7, kf to every call of a lemma in needs."""
    pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in sorted(needs, key=len, reverse=True)) + r")\(")
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
        inner = thread_calls(text[lp + 1:rp], needs)
        sep = ", " if inner.strip() else ""
        out.append(text[i:m.start()] + m.group(1) + "(" + inner + sep + ", ".join(EXTRA) + ")")
        i = rp + 1


def thread_header(kind, name, text, has_law):
    """Adds the key words and the flag to a law's binders or a def's params."""
    if kind == "law":
        lines = text.splitlines(keepends=True)
        at = max(i for i, l in enumerate(lines) if l.startswith(("law ", "  for ")))
        add = "".join(f"  for +{v}: U32\n" for v in EXTRA)
        return "".join(lines[:at + 1]) + add + "".join(lines[at + 1:])
    m = re.search(r"(?m)^def " + re.escape(name) + r"\(", text)
    lp = m.end() - 1
    rp = close_of(text, lp)
    inner = text[lp + 1:rp]
    if has_law:
        new = ", ".join(EXTRA)
    else:
        new = ", ".join(f"+{v}: U32" for v in EXTRA)
    sep = ", " if inner.strip() else ""
    return text[:rp] + sep + new + text[rp:]


def prefix_c(text, names):
    """cpu.bend's lemmas the mode leaves alone, referenced as C.name."""
    if not names:
        return text
    pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w.])")
    return "".join(l if l.lstrip().startswith("#") else pat.sub(r"C.\1", l) for l in text.splitlines(keepends=True))


def transform(body, roots=None, keep_as="C."):
    """The mode's lemmas (those from roots, if given), the rest as keep_as."""
    its = items(body)
    names = {n for k, n, _ in its if k in ("law", "def", "type")}
    laws = {n for k, n, _ in its if k == "law"}
    new = {}
    needs = set()
    for k, n, t in its:
        x = xform(t)
        new[(k, n)] = x
        if x != t:
            needs.add(n)
    graph = {}
    for k, n, t in its:
        graph.setdefault(n, set()).update(refs(new[(k, n)], names) - {n})
    changed = True
    while changed:
        changed = False
        for n, rs in graph.items():
            if n not in needs and rs & needs:
                needs.add(n)
                changed = True
    if roots is not None:
        live, todo = set(), list(roots)
        while todo:
            n = todo.pop()
            if n in live:
                continue
            live.add(n)
            todo += [m for m in graph.get(n, ()) if m in needs]
        needs = needs & live
    out = []
    keep = names - needs
    for k, n, t in its:
        if n not in needs:
            continue
        x = thread_calls(new[(k, n)], needs)
        x = thread_header(k, n, x, n in laws)
        out.append(prefix_c(x, keep).replace("C.C.", "C.") if keep_as == "C." else prefix_s(x, keep, keep_as))
    return "".join(out), needs


def prefix_s(text, names, pre):
    if not names:
        return text
    pat = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w.])")
    return "".join(l if l.lstrip().startswith("#") else pat.sub(pre + r"\1", l) for l in text.splitlines(keepends=True))


HEAD = '''\
# The keyed tree, for every input
# ===============================
#
# GENERATED by tools/gen_laws.py (tools/proofs/keyed.py): edit the generator.
#
# keyed.at: for every array, span, key and mode flag, the CPU's keyed 8-lane
# tree (hash8.at.k: what the library's engine runs for keyed hashing and
# key derivation) is blake3.bend's scalar keyed tree (hash.at.k). The proof
# is cpu.bend's, transformed by tools/proofs/keyed.py: each default-mode
# def is its .k twin, the key is written as its eight words k0..k7 (so key8
# unfolds as IV8 does) and the flag kf is or-ed into every compression's
# flags. Lemmas the mode does not touch are cpu.bend's (C.).

import Base
import ../blake3.bend as B3
import ../LAWS.bend as Laws
import ./words.bend as A
import ./cpu.bend as C

# Lane l of par8.k: the keyed parent of the right two lanes.
def par.ref.k(l: Laws.Lane, +x: B3.CV8, +y: B3.CV8, +key: B3.CV, +kf: U32) -> B3.CV:
  match l:
''' + "".join(f"    case Laws.L{l}{{}}:\n      B3.parent.k(Laws.cv.at(Laws.L{2 * (l % 4)}{{}}, {'x' if l < 4 else 'y'}), "
              f"Laws.cv.at(Laws.L{2 * (l % 4) + 1}{{}}, {'x' if l < 4 else 'y'}), 0, key, kf)\n" for l in range(8)) + '''
# The scalar keyed tree over a span, at depth k (Laws.ref.go's twin).
def ref.go.k(+k: Nat, a: Array<U32>, +cb: U32, +hi: U32, +nch: U32, +last: U32, +rf: U32, +key: B3.CV, +kf: U32) -> B3.CV:
  match k:
    case 0n:
      B3.chunk.k(a, 0, cb, hi, nch, last, rf, key, kf)
    case 1n+p:
      B3.tree1.k(~Laws.share, 1n+p, B3.big(1n+p, nch), Laws.share(a), 0, nch, cb, hi, nch, last, rf, key, kf)

def ref.at.k(a: Array<U32>, +cb: U32, +hi: U32, +nch: U32, +last: U32, +rf: U32, +key: B3.CV, +kf: U32) -> B3.CV:
  ref.go.k(B3.depth(nch), a, cb, hi, nch, last, rf, key, kf)
'''


def top():
    span = "cb, hi, nch, last, rf"
    h8 = lambda a, key: f"B3.hash8.at.k(~Laws.share, {a}, {span}, {key}, kf)"
    hk = lambda a, key: f"B3.hash.at.k(~Laws.share, {a}, {span}, {key}, kf)"
    rg = lambda a, key, k="B3.depth(nch)": f"ref.go.k({k}, {a}, {span}, {key}, kf)"
    goal = f"{{{h8('a', 'key')} == {hk('a', 'key')} : B3.CV}}"
    goalK = f"{{{h8('a', KEY)} == {hk('a', KEY)} : B3.CV}}"
    return f'''
# ref.go.k at the span's depth is blake3.bend's own hash.at.k.
law ref.hash.k:
  for +k: Nat
  for a: Array<U32>
  for +cb: U32
  for +hi: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +key: B3.CV
  for +kf: U32
  {{{rg('a', 'key', 'k')} == B3.tree1.k(~Laws.share, k, B3.big(k, nch), Laws.share(a), 0, nch, {span}, key, kf) : B3.CV}}

def ref.hash.k(k, a, cb, hi, nch, last, rf, key, kf):
  match k:
    case 0n:
      %Equal.sym(Array<U32> & Array<U32>, Array.clone(U32, a), (a, a), C.clone.dup(a)) :
        {{B3.chunk.k(a, 0, {span}, key, kf) == B3.tree1.k(~Laws.share, 0n, B3.big(0n, nch), _, 0, nch, {span}, key, kf) : B3.CV}}
      {{==}}
    case 1n+p:
      _ = a
      {{==}}

def keyed.at.h(-a: Array<U32>, +cb: U32, +hi: U32, +nch: U32, +last: U32, +rf: U32, +key: B3.CV, +kf: U32, w: C.Wits(a, 2n)) -> {goal}:
  match key:
    case B3.CV{{{", ".join(KEYW)}}}:
      match w:
        case (z1, w1):
          match w1:
            case (+ez10, w1b):
              match w1b:
                case (z2, w2):
                  match w2:
                    case (+ez20, w2b):
                      _ = w2b
                      Equal.trans(B3.CV, {h8('a', KEY)}, {rg('a', KEY)}, {hk('a', KEY)},
                        C.tr(arr => {{{h8('arr', KEY)} == {rg('arr', KEY)} : B3.CV}}, z1, a, ez10, cpu.at(z1, cb, nch, last, rf, hi, {", ".join(EXTRA)})),
                        C.tr(arr => {{{rg('arr', KEY)} == {hk('arr', KEY)} : B3.CV}}, z2, a, ez20, ref.hash.k(B3.depth(nch), z2, {span}, {KEY}, kf)))

# The CPU's keyed tree is the scalar keyed tree, for every array, span, key
# and mode flag.
law keyed.at:
  for a: Array<U32>
  for +cb: U32
  for +hi: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +key: B3.CV
  for +kf: U32
  {goal}

def keyed.at(a, cb, hi, nch, last, rf, key, kf):
  keyed.at.h(a, cb, hi, nch, last, rf, key, kf, C.wits(1n, a))
'''


SPEC_TOP = f'''
# The keyed tree is BLAKE3's keyed tree: ev.k of tree(digits) over the
# span's chunks, each leaf a keyed chunk and each node a keyed parent.
law keyed.spec:
  for a: Array<U32>
  for +cb: U32
  for +hi: U32
  for +nch: U32
  for +last: U32
  for +rf: U32
  for +key: B3.CV
  for +kf: U32
  {{B3.hash8.at.k(~Laws.share, a, cb, hi, nch, last, rf, key, kf) ==
    Laws.ev.k(Laws.tree(Laws.digits(B3.depth(nch), Nat.sub(U32.to_nat(nch), 1n), [])), Laws.share(a), 0, cb, hi, nch, last, rf, key, kf) : B3.CV}}

def keyed.spec(a, cb, hi, nch, last, rf, key, kf):
  match key:
    case B3.CV{{{", ".join(KEYW)}}}:
      cpu.spec(a, cb, nch, last, rf, hi, {", ".join(EXTRA)})
'''


def text(cpu, spec):
    body = cpu[cpu.index("import ./words.bend as A\n") + len("import ./words.bend as A\n"):]
    out, _ = transform(body)
    sbody = spec[spec.index("import ./gpu.bend as G\n") + len("import ./gpu.bend as G\n"):]
    sout, _ = transform(sbody, roots={"cpu.spec"}, keep_as="S.")
    head = HEAD.replace("import ./cpu.bend as C\n", "import ./cpu.bend as C\nimport ./spec.bend as S\n")
    return head + out + top() + sout + SPEC_TOP
