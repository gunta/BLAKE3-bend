"""A group, lane by lane: gl.l<l> proves that lane l of group(a, c, t) (eight
full chunks on the 8-lane path) is the scalar chain of chunk c + l, for every
array: loop.l<l> over the sixteen blocks, with a bundle of copies of a."""
from .common import L, CS, CE, WL, fst8, sndm, ldx, FC, wmatch

N = 12  # copies besides the bundle: xr, xf, xz, y0..y7, xe


def gl(l):
    Ll = f"L{l}{{}}"
    w = "(c << 8n : U32)"
    tl = f"(t + {l} : U32)"
    goal = f"{{cv.at({Ll}, Pair.snd(Array<U32>, B3.CV8, B3.group(a, c, t))) == {FC('a', WL(l, w), tl)} : B3.CV}}"
    names = ["xr", "xf", "xz"] + [f"y{j}" for j in range(L)] + ["xe"]
    lines, bi = wmatch("r", names, "  ")
    b = [f"{bi}+e{x} = eq.trans({x}, s, a, e{x}0, es)\n" for x in names]
    symr = "Equal.sym(Array<U32>, xr, a, exr)"
    to_r = lambda x: f"eq.trans({x}, a, xr, e{x}, {symr})"
    for j in range(L):
        b.append(f"{bi}+mm{j} = {sndm(ldx(f'y{j}', WL(j, w)))}\n")
    b.append(f"{bi}+em = ld8.split(xr, {w}, xz, {to_r('xz')}, " + ", ".join(f"y{j}, {to_r(f'y{j}')}" for j in range(L)) + ")\n")
    b.append(f"{bi}+fr = eq.trans({fst8(f'B3.ld8(xr, {w})')}, xr, a, tr(arr => {{{fst8(f'B3.ld8(arr, {w})')} == arr : Array<U32>}}, "
             f"xf, xr, {to_r('xf')}, ld8.fst(xf, {w})), exr)\n")
    mm = ", ".join(f"mm{j}" for j in range(L))
    lp_l = f"cv.at({Ll}, Pair.snd(Array<U32>, B3.CV8, B3.c8.go(16n, B3.ld8(arr, {w}), {w}, B3.IV8(), t, {CS})))"
    lp_r = f"B3.chunk.fin(B3.chunk.go(15n, (a, mm{l}), {WL(l, w)}, cv.at({Ll}, B3.IV8()), {tl}, {CS}, {CE}, 64))"
    b.append(f"{bi}+lp = tr(arr => {{{lp_l} == {lp_r} : B3.CV}}, xr, a, exr, loop.l{l}(15n, a, B3.ld8(xr, {w}), fr, {mm}, em, {w}, B3.IV8(), t, {CS}, bb))\n")
    lpa = lp_l.replace("B3.ld8(arr,", "B3.ld8(a,")
    b.append(f"{bi}%Equal.sym(B3.CV, {lpa}, {lp_r}, lp) :\n{bi}  {{_ == {FC('a', WL(l, w), tl)} : B3.CV}}\n")
    lp_r_hole = f"B3.chunk.fin(B3.chunk.go(15n, (a, _), {WL(l, w)}, cv.at({Ll}, B3.IV8()), {tl}, {CS}, {CE}, 64))"
    b.append(f"{bi}%Equal.cong(Array<U32>, B3.M16, arr => {sndm(ldx('arr', WL(l, w)))}, a, y{l}, Equal.sym(Array<U32>, y{l}, a, ey{l})) :\n"
             f"{bi}  {{{lp_r_hole} == {FC('a', WL(l, w), tl)} : B3.CV}}\n")
    fe = (f"tr(arr => {{B3.ld(arr, {WL(l, w)}) == (arr, {sndm(ldx('arr', WL(l, w)))}) : Array<U32> & B3.M16}}, "
          f"xe, a, exe, ld.eta(xe, {WL(l, w)}))")
    lp_r2 = f"B3.chunk.fin(B3.chunk.go(15n, (a, {sndm(ldx('a', WL(l, w)))}), {WL(l, w)}, cv.at({Ll}, B3.IV8()), {tl}, {CS}, {CE}, 64))"
    fc_hole = f"B3.chunk.fin(B3.chunk.go(15n, _, {WL(l, w)}, B3.IV(), {tl}, {CS}, {CE}, 64))"
    b.append(f"{bi}%Equal.sym(Array<U32> & B3.M16, {ldx('a', WL(l, w))}, (a, {sndm(ldx('a', WL(l, w)))}), {fe}) :\n"
             f"{bi}  {{{lp_r2} == {fc_hole} : B3.CV}}\n")
    b.append(f"{bi}{{==}}\n")
    return (f"\ndef gl.l{l}.h2(-a: Array<U32>, +c: U32, +t: U32, -s: Array<U32>, +es: {{s == a : Array<U32>}}, "
            f"r: Wits(s, {N}n), bb: Bun(a, 15n)) -> {goal}:\n" + "".join(lines) + "".join(b) + f'''
def gl.l{l}.h1(-a: Array<U32>, +c: U32, +t: U32, r: BunS(a, 15n)) -> {goal}:
  match r:
    case (s, r2):
      match r2:
        case (+es, bb):
          gl.l{l}.h2(a, c, t, s, es, wits({N - 1}n, s), bb)

# Lane {l} of a group is the scalar chain of its chunk {l}.
law gl.l{l}:
  for a: Array<U32>
  for +c: U32
  for +t: U32
  {goal}

def gl.l{l}(a, c, t):
  gl.l{l}.h1(a, c, t, bun(15n, a))
''')


def text():
    return "".join(gl(l) for l in range(L))
