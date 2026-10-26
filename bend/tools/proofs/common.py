"""Names and term builders shared by the proof generators.

The proofs are Bend text built from these: a term is a string, a motive is
a goal with `_` where a rewrite lands. Names from LAWS.bend (Lane, cv.at,
share, ...) are written bare and prefixed with `Laws.` by `laws_names`.
"""
import re

L = 8
CS, CE = "B3.CHUNK_START()", "B3.CHUNK_END()"


def B(v):
    return "True{}" if v else "False{}"


def fa(a, b, c):
    """One full adder: (sum, carry)."""
    return a ^ b ^ c, (a & b) | (a & c) | (b & c)


def TN(x):
    return f"U32.to_nat({x})"


def WL(l, x):
    """Word offset of lane l's chunk from x (256 words a chunk)."""
    return x if l == 0 else f"({x} + {256 * l} : U32)"


def snd8(r):
    return f"Pair.snd(Array<U32>, B3.B128, {r})"


def fst8(r):
    return f"Pair.fst(Array<U32>, B3.B128, {r})"


def sndm(r):
    return f"Pair.snd(Array<U32>, B3.M16, {r})"


def ldx(a, i):
    return f"B3.ld({a}, {i})"


def X(a, w, j):
    """Lane j's block of the 8-lane load at w, as the scalar loader's."""
    return sndm(ldx(a, WL(j, w)))


def FC(a, w, t):
    """The CV of a full chunk at word w with counter t: chunk's own chain."""
    return f"B3.chunk.fin(B3.chunk.go(15n, B3.ld({a}, {w}), {w}, B3.IV(), {t}, {CS}, {CE}, 64))"


def F8(ys, rf):
    """fold8's three levels of parents over eight CVs."""
    p = lambda a, b: f"B3.parent({a}, {b}, 0)"
    return f"B3.parent({p(p(ys[0], ys[1]), p(ys[2], ys[3]))}, {p(p(ys[4], ys[5]), p(ys[6], ys[7]))}, {rf})"


def wmatch(var, names, ind):
    """Opens a Wits(_, len(names)) parameter `var` into copies `names`, with
    `+e<name>0 : {name == ..}`. Returns the lines and the body's indent."""
    lines = [f"{ind}match {var}:\n"]
    for i, x in enumerate(names, 1):
        lines.append(f"{ind}  case ({x}, {var}{i}):\n")
        lines.append(f"{ind}    match {var}{i}:\n")
        lines.append(f"{ind}      case (+e{x}0, {var}{i}b):\n")
        ind = ind + "        "
        if i < len(names):
            lines.append(f"{ind}match {var}{i}b:\n")
        else:
            lines.append(f"{ind}_ = {var}{i}b\n")
    return lines, ind


LAWS_USED = ["Lane", "Lane.u32", "L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7",
             "cv.at", "m.at", "par.ref", "share", "ref.go"]


def laws_names(text):
    """Prefixes the LAWS.bend names the proofs use with `Laws.`."""
    pat = re.compile(r"(?<![\w.])(" + "|".join(
        re.escape(n) for n in sorted(LAWS_USED, key=len, reverse=True)) + r")(?![\w.])")
    return "".join(l if l.lstrip().startswith("#") else pat.sub(r"Laws.\1", l)
                   for l in text.splitlines(keepends=True))
