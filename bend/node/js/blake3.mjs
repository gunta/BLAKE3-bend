function word_to_u32(w) {
  let x = 0;
  for (let i = 0; w.$ === "WCon"; i++) {
    x |= Number(w.head) << i;
    w = w.tail;
  }
  return x >>> 0;
}

function u32_to_word(x) {
  let w = {$: "WNil"};
  for (let i = 31; i >= 0; i--) {
    w = {$: "WCon", head: ((x >>> i) & 1) === 1, tail: w};
  }
  return w;
}

function cmp_new(a, b) {
  return {$: a < b ? "LT" : a === b ? "EQ" : "GT"};
}

function nat_divmod(a, b) {
  return b === 0 ? {$: "Tuple", fst: 0, snd: a}
    : {$: "Tuple", fst: Math.trunc(a / b), snd: a % b};
}

function nat_chk(n) {
  if (n > 281474976710655) {
    throw "bend: a Nat past the largest immediate 2^48-1";
  }
  return n;
}

function nat_in(n) {
  if (!Number.isInteger(n) || n < 0 || n > 2 ** 53) {
    throw "bend: expected a Nat host number: an integer from 0 to 2^53";
  }
  return n;
}

function f32_show(x) {
  let s = "nan";
  for (let p = 1; x === x && p <= 9 && f32_round(s) !== x; p += 1) {
    s = String(Number(x.toExponential(p - 1)));
  }
  return (Object.is(x, -0) ? "-0" : s).replace("Infinity", "inf");
}

function f32_bits(x) {
  return new Uint32Array(new Float32Array([x]).buffer)[0];
}

function f32_from_bits(u) {
  return new Float32Array(new Uint32Array([u]).buffer)[0];
}

function f32_read(s) {
  const re = /^[\t\n\v\f\r ]*[+-]?((\d+(?:\.\d*)?|\.\d+)(e[+-]?\d+)?|inf(inity)?|nan)$/i;
  const v = f32_round(s.replace(/inf\w*/i, "Infinity"));
  return re.test(s) ? {$: "Some", value: v} : {$: "None"};
}

const f32_round = function f32_round(s) {
  const d = Number(s);
  const a = Math.abs(d);
  const f = Math.fround(a);
  const g = 2 * a - Math.min(f, 2 ** 128);
  if (g === f || Math.fround(g) !== g || g === Infinity) {
    return Math.sign(d) * f;
  }
  let k = 0;
  while (a * 2 ** k % 1 !== 0) {
    k += 1;
  }
  const [, i, r, e] = /(\d*)\.?(\d*)(?:e([+-]?\d+))?$/i.exec(s);
  const n = Number(e ?? 0) - r.length;
  const x = BigInt(i + r) * 2n ** BigInt(k) * 10n ** BigInt(Math.max(n, 0));
  const y = BigInt(a * 2 ** k) * 10n ** BigInt(Math.max(-n, 0));
  return Math.sign(d) * (x === y || x > y !== g > f ? f : g);
};

const char_new = function char_new(c) {
  return c < 55296 || c >= 57344 && c <= 1114111 ? String.fromCodePoint(c) : String.fromCharCode(56320, c >>> 22, c >>> 11 & 2047, c & 2047);
};

function char_len(s, at = 0) {
  return s[at] === "\uDC00" ? 4 : s.codePointAt(at) > 0xFFFF ? 2 : 1;
}

function char_code(s) {
  return s.length < 4 ? s.codePointAt(0)
    : (s.charCodeAt(1) << 22 | s.charCodeAt(2) << 11 | s.charCodeAt(3)) >>> 0;
}

function string_contains(s, p) {
  // A match must start at a Char boundary, not inside a packed U32 code.
  for (let at = 0; at <= s.length; at += char_len(s, at)) {
    if (s.startsWith(p, at)) {
      return true;
    }
  }
  return false;
}

function str_out(s) {
  return s.replace(/\uDC00[^]{3}/gu, "\uFFFD");
}

function str_in(s) {
  return s.replace(/\p{Cs}/gu, "\uFFFD");
}

// Array
// =====

function array_new(d, v) {
  if (d > 31) {
    throw "bend: an array past the deepest block class 31";
  }
  return Array(2 ** d).fill(v);
}

function array_node(a, b) {
  if (a.length !== b.length) {
    throw "bend: runtime fail-stop";
  }
  return a.concat(b);
}

function array_rmw(a, i, f) {
  const at = i % a.length;
  const old = a[at];
  a[at] = f(old);
  return {$: "Tuple", fst: a, snd: old};
}

// Run
// ===

function run_tail(f, x) {
  return {$: "$JMP", f: f.j?.f === f ? f.j : f, x};
}

function run_clo(j) {
  const f = (x) => run_loop(j(x));
  f.j = j;
  j.f = f;
  return f;
}

function run_loop(r) {
  while (r !== null && typeof r === "object" && r.$ === "$JMP") {
    r = r.f(r.x);
  }
  return r;
}

function run_lib(f, n) {
  return (...a) => a.length < n ? run_lib((...b) => f(...a, ...b), n - a.length)
    : run_loop(f(...a));
}

// Effect
// ======

const $0eff = Object.create(null);

function io_eff(k, run) {
  if (arguments.length > 2) {
    throw new Error("bend: " + k + " takes no need: an effect that waits parks itself");
  }
  if (k in $0eff) {
    throw new Error("bend: two effects register " + k);
  }
  $0eff[k] = run;
}
// Program
// =======

function $b3scalar_CHUNK_START() {
  return 1;
}

function $b3scalar_CHUNK_END() {
  return 2;
}

function $b3scalar_PARENT() {
  return 4;
}

function $b3scalar_ROOT() {
  return 8;
}

function $b3scalar_IV() {
  return {$: "CV", "h0": 1779033703, "h1": 3144134277, "h2": 1013904242, "h3": 2773480762, "h4": 1359893119, "h5": 2600822924, "h6": 528734635, "h7": 1541459225};
}

function $b3scalar_rotr16(_x_0) {
  const _x_1 = (16 >= 32 ? 0 : (_x_0 >>> 16) >>> 0);
  const _x_2 = (16 >= 32 ? 0 : (_x_0 << 16) >>> 0);
  return ((_x_1 | _x_2) >>> 0);
}

function $b3scalar_rotr12(_x_0) {
  const _x_1 = (12 >= 32 ? 0 : (_x_0 >>> 12) >>> 0);
  const _x_2 = (20 >= 32 ? 0 : (_x_0 << 20) >>> 0);
  return ((_x_1 | _x_2) >>> 0);
}

function $b3scalar_rotr8(_x_0) {
  const _x_1 = (8 >= 32 ? 0 : (_x_0 >>> 8) >>> 0);
  const _x_2 = (24 >= 32 ? 0 : (_x_0 << 24) >>> 0);
  return ((_x_1 | _x_2) >>> 0);
}

function $b3scalar_rotr7(_x_0) {
  const _x_1 = (7 >= 32 ? 0 : (_x_0 >>> 7) >>> 0);
  const _x_2 = (25 >= 32 ? 0 : (_x_0 << 25) >>> 0);
  return ((_x_1 | _x_2) >>> 0);
}

function $b3scalar_ld_s15(_r_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0, _m13_0, _m14_0) {
  const _a_0 = _r_0["fst"];
  const _m15_0 = _r_0["snd"];
  return {$: "Tuple", "fst": _a_0, "snd": {$: "M16", "m0": _m0_0, "m1": _m1_0, "m2": _m2_0, "m3": _m3_0, "m4": _m4_0, "m5": _m5_0, "m6": _m6_0, "m7": _m7_0, "m8": _m8_0, "m9": _m9_0, "m10": _m10_0, "m11": _m11_0, "m12": _m12_0, "m13": _m13_0, "m14": _m14_0, "m15": _m15_0}};
}

function $b3scalar_ld_s14(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0, _m13_0) {
  const _a_0 = _r_0["fst"];
  const _m14_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 15) >>> 0);
  return $b3scalar_ld_s15({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0, _m13_0, _m14_0);
}

function $b3scalar_ld_s13(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0) {
  const _a_0 = _r_0["fst"];
  const _m13_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 14) >>> 0);
  return $b3scalar_ld_s14({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0, _m13_0);
}

function $b3scalar_ld_s12(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0) {
  const _a_0 = _r_0["fst"];
  const _m12_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 13) >>> 0);
  return $b3scalar_ld_s13({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0, _m12_0);
}

function $b3scalar_ld_s11(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0) {
  const _a_0 = _r_0["fst"];
  const _m11_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 12) >>> 0);
  return $b3scalar_ld_s12({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0, _m11_0);
}

function $b3scalar_ld_s10(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0) {
  const _a_0 = _r_0["fst"];
  const _m10_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 11) >>> 0);
  return $b3scalar_ld_s11({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0, _m10_0);
}

function $b3scalar_ld_s9(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0) {
  const _a_0 = _r_0["fst"];
  const _m9_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 10) >>> 0);
  return $b3scalar_ld_s10({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0, _m9_0);
}

function $b3scalar_ld_s8(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0) {
  const _a_0 = _r_0["fst"];
  const _m8_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 9) >>> 0);
  return $b3scalar_ld_s9({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0, _m8_0);
}

function $b3scalar_ld_s7(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0) {
  const _a_0 = _r_0["fst"];
  const _m7_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 8) >>> 0);
  return $b3scalar_ld_s8({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0, _m7_0);
}

function $b3scalar_ld_s6(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0) {
  const _a_0 = _r_0["fst"];
  const _m6_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 7) >>> 0);
  return $b3scalar_ld_s7({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0, _m6_0);
}

function $b3scalar_ld_s5(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0) {
  const _a_0 = _r_0["fst"];
  const _m5_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 6) >>> 0);
  return $b3scalar_ld_s6({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0, _m5_0);
}

function $b3scalar_ld_s4(_r_0, _w_0, _m0_0, _m1_0, _m2_0, _m3_0) {
  const _a_0 = _r_0["fst"];
  const _m4_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 5) >>> 0);
  return $b3scalar_ld_s5({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0, _m4_0);
}

function $b3scalar_ld_s3(_r_0, _w_0, _m0_0, _m1_0, _m2_0) {
  const _a_0 = _r_0["fst"];
  const _m3_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 4) >>> 0);
  return $b3scalar_ld_s4({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0, _m3_0);
}

function $b3scalar_ld_s2(_r_0, _w_0, _m0_0, _m1_0) {
  const _a_0 = _r_0["fst"];
  const _m2_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 3) >>> 0);
  return $b3scalar_ld_s3({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0, _m2_0);
}

function $b3scalar_ld_s1(_r_0, _w_0, _m0_0) {
  const _a_0 = _r_0["fst"];
  const _m1_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 2) >>> 0);
  return $b3scalar_ld_s2({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0, _m1_0);
}

function $b3scalar_ld_s0(_r_0, _w_0) {
  const _a_0 = _r_0["fst"];
  const _m0_0 = _r_0["snd"];
  const _x_0 = ((_w_0 + 1) >>> 0);
  return $b3scalar_ld_s1({$: "Tuple", fst: _a_0, snd: _a_0[_x_0 % _a_0.length]}, _w_0, _m0_0);
}

function $b3scalar_ld(_a_0, _w_0) {
  return $b3scalar_ld_s0({$: "Tuple", fst: _a_0, snd: _a_0[_w_0 % _a_0.length]}, _w_0);
}

function $b3scalar_round(_s_0, _m_0) {
  const _v0_0_0 = _s_0["v0"];
  const _v1_0_0 = _s_0["v1"];
  const _v2_0_0 = _s_0["v2"];
  const _v3_0_0 = _s_0["v3"];
  const _v4_0_0 = _s_0["v4"];
  const _v5_0_0 = _s_0["v5"];
  const _v6_0_0 = _s_0["v6"];
  const _v7_0_0 = _s_0["v7"];
  const _v8_0_0 = _s_0["v8"];
  const _v9_0_0 = _s_0["v9"];
  const _v10_0_0 = _s_0["v10"];
  const _v11_0_0 = _s_0["v11"];
  const _v12_0_0 = _s_0["v12"];
  const _v13_0_0 = _s_0["v13"];
  const _v14_0_0 = _s_0["v14"];
  const _v15_0_0 = _s_0["v15"];
  const _m0_0 = _m_0["m0"];
  const _m1_0 = _m_0["m1"];
  const _m2_0 = _m_0["m2"];
  const _m3_0 = _m_0["m3"];
  const _m4_0 = _m_0["m4"];
  const _m5_0 = _m_0["m5"];
  const _m6_0 = _m_0["m6"];
  const _m7_0 = _m_0["m7"];
  const _m8_0 = _m_0["m8"];
  const _m9_0 = _m_0["m9"];
  const _m10_0 = _m_0["m10"];
  const _m11_0 = _m_0["m11"];
  const _m12_0 = _m_0["m12"];
  const _m13_0 = _m_0["m13"];
  const _m14_0 = _m_0["m14"];
  const _m15_0 = _m_0["m15"];
  const _x_0 = ((_v0_0_0 + _v4_0_0) >>> 0);
  const _v0_1_0 = ((_x_0 + _m0_0) >>> 0);
  const _v12_1_0 = ($b3scalar_rotr16(((_v12_0_0 ^ _v0_1_0) >>> 0)));
  const _v8_1_0 = ((_v8_0_0 + _v12_1_0) >>> 0);
  const _v4_1_0 = ($b3scalar_rotr12(((_v4_0_0 ^ _v8_1_0) >>> 0)));
  const _x_1 = ((_v0_1_0 + _v4_1_0) >>> 0);
  const _v0_2_0 = ((_x_1 + _m1_0) >>> 0);
  const _v12_2_0 = ($b3scalar_rotr8(((_v12_1_0 ^ _v0_2_0) >>> 0)));
  const _v8_2_0 = ((_v8_1_0 + _v12_2_0) >>> 0);
  const _v4_2_0 = ($b3scalar_rotr7(((_v4_1_0 ^ _v8_2_0) >>> 0)));
  const _x_2 = ((_v1_0_0 + _v5_0_0) >>> 0);
  const _v1_1_0 = ((_x_2 + _m2_0) >>> 0);
  const _v13_1_0 = ($b3scalar_rotr16(((_v13_0_0 ^ _v1_1_0) >>> 0)));
  const _v9_1_0 = ((_v9_0_0 + _v13_1_0) >>> 0);
  const _v5_1_0 = ($b3scalar_rotr12(((_v5_0_0 ^ _v9_1_0) >>> 0)));
  const _x_3 = ((_v1_1_0 + _v5_1_0) >>> 0);
  const _v1_2_0 = ((_x_3 + _m3_0) >>> 0);
  const _v13_2_0 = ($b3scalar_rotr8(((_v13_1_0 ^ _v1_2_0) >>> 0)));
  const _v9_2_0 = ((_v9_1_0 + _v13_2_0) >>> 0);
  const _v5_2_0 = ($b3scalar_rotr7(((_v5_1_0 ^ _v9_2_0) >>> 0)));
  const _x_4 = ((_v2_0_0 + _v6_0_0) >>> 0);
  const _v2_1_0 = ((_x_4 + _m4_0) >>> 0);
  const _v14_1_0 = ($b3scalar_rotr16(((_v14_0_0 ^ _v2_1_0) >>> 0)));
  const _v10_1_0 = ((_v10_0_0 + _v14_1_0) >>> 0);
  const _v6_1_0 = ($b3scalar_rotr12(((_v6_0_0 ^ _v10_1_0) >>> 0)));
  const _x_5 = ((_v2_1_0 + _v6_1_0) >>> 0);
  const _v2_2_0 = ((_x_5 + _m5_0) >>> 0);
  const _v14_2_0 = ($b3scalar_rotr8(((_v14_1_0 ^ _v2_2_0) >>> 0)));
  const _v10_2_0 = ((_v10_1_0 + _v14_2_0) >>> 0);
  const _v6_2_0 = ($b3scalar_rotr7(((_v6_1_0 ^ _v10_2_0) >>> 0)));
  const _x_6 = ((_v3_0_0 + _v7_0_0) >>> 0);
  const _v3_1_0 = ((_x_6 + _m6_0) >>> 0);
  const _v15_1_0 = ($b3scalar_rotr16(((_v15_0_0 ^ _v3_1_0) >>> 0)));
  const _v11_1_0 = ((_v11_0_0 + _v15_1_0) >>> 0);
  const _v7_1_0 = ($b3scalar_rotr12(((_v7_0_0 ^ _v11_1_0) >>> 0)));
  const _x_7 = ((_v3_1_0 + _v7_1_0) >>> 0);
  const _v3_2_0 = ((_x_7 + _m7_0) >>> 0);
  const _v15_2_0 = ($b3scalar_rotr8(((_v15_1_0 ^ _v3_2_0) >>> 0)));
  const _v11_2_0 = ((_v11_1_0 + _v15_2_0) >>> 0);
  const _v7_2_0 = ($b3scalar_rotr7(((_v7_1_0 ^ _v11_2_0) >>> 0)));
  const _x_8 = ((_v0_2_0 + _v5_2_0) >>> 0);
  const _v0_3_0 = ((_x_8 + _m8_0) >>> 0);
  const _v15_3_0 = ($b3scalar_rotr16(((_v15_2_0 ^ _v0_3_0) >>> 0)));
  const _v10_3_0 = ((_v10_2_0 + _v15_3_0) >>> 0);
  const _v5_3_0 = ($b3scalar_rotr12(((_v5_2_0 ^ _v10_3_0) >>> 0)));
  const _x_9 = ((_v0_3_0 + _v5_3_0) >>> 0);
  const _v0_4_0 = ((_x_9 + _m9_0) >>> 0);
  const _v15_4_0 = ($b3scalar_rotr8(((_v15_3_0 ^ _v0_4_0) >>> 0)));
  const _v10_4_0 = ((_v10_3_0 + _v15_4_0) >>> 0);
  const _v5_4_0 = ($b3scalar_rotr7(((_v5_3_0 ^ _v10_4_0) >>> 0)));
  const _x_10 = ((_v1_2_0 + _v6_2_0) >>> 0);
  const _v1_3_0 = ((_x_10 + _m10_0) >>> 0);
  const _v12_3_0 = ($b3scalar_rotr16(((_v12_2_0 ^ _v1_3_0) >>> 0)));
  const _v11_3_0 = ((_v11_2_0 + _v12_3_0) >>> 0);
  const _v6_3_0 = ($b3scalar_rotr12(((_v6_2_0 ^ _v11_3_0) >>> 0)));
  const _x_11 = ((_v1_3_0 + _v6_3_0) >>> 0);
  const _v1_4_0 = ((_x_11 + _m11_0) >>> 0);
  const _v12_4_0 = ($b3scalar_rotr8(((_v12_3_0 ^ _v1_4_0) >>> 0)));
  const _v11_4_0 = ((_v11_3_0 + _v12_4_0) >>> 0);
  const _v6_4_0 = ($b3scalar_rotr7(((_v6_3_0 ^ _v11_4_0) >>> 0)));
  const _x_12 = ((_v2_2_0 + _v7_2_0) >>> 0);
  const _v2_3_0 = ((_x_12 + _m12_0) >>> 0);
  const _v13_3_0 = ($b3scalar_rotr16(((_v13_2_0 ^ _v2_3_0) >>> 0)));
  const _v8_3_0 = ((_v8_2_0 + _v13_3_0) >>> 0);
  const _v7_3_0 = ($b3scalar_rotr12(((_v7_2_0 ^ _v8_3_0) >>> 0)));
  const _x_13 = ((_v2_3_0 + _v7_3_0) >>> 0);
  const _v2_4_0 = ((_x_13 + _m13_0) >>> 0);
  const _v13_4_0 = ($b3scalar_rotr8(((_v13_3_0 ^ _v2_4_0) >>> 0)));
  const _v8_4_0 = ((_v8_3_0 + _v13_4_0) >>> 0);
  const _v7_4_0 = ($b3scalar_rotr7(((_v7_3_0 ^ _v8_4_0) >>> 0)));
  const _x_14 = ((_v3_2_0 + _v4_2_0) >>> 0);
  const _v3_3_0 = ((_x_14 + _m14_0) >>> 0);
  const _v14_3_0 = ($b3scalar_rotr16(((_v14_2_0 ^ _v3_3_0) >>> 0)));
  const _v9_3_0 = ((_v9_2_0 + _v14_3_0) >>> 0);
  const _v4_3_0 = ($b3scalar_rotr12(((_v4_2_0 ^ _v9_3_0) >>> 0)));
  const _x_15 = ((_v3_3_0 + _v4_3_0) >>> 0);
  const _v3_4_0 = ((_x_15 + _m15_0) >>> 0);
  const _v14_4_0 = ($b3scalar_rotr8(((_v14_3_0 ^ _v3_4_0) >>> 0)));
  const _v9_4_0 = ((_v9_3_0 + _v14_4_0) >>> 0);
  const _v4_4_0 = ($b3scalar_rotr7(((_v4_3_0 ^ _v9_4_0) >>> 0)));
  return {$: "S16", "v0": _v0_4_0, "v1": _v1_4_0, "v2": _v2_4_0, "v3": _v3_4_0, "v4": _v4_4_0, "v5": _v5_4_0, "v6": _v6_4_0, "v7": _v7_4_0, "v8": _v8_4_0, "v9": _v9_4_0, "v10": _v10_4_0, "v11": _v11_4_0, "v12": _v12_4_0, "v13": _v13_4_0, "v14": _v14_4_0, "v15": _v15_4_0};
}

function $b3scalar_perm(_m_0) {
  const _m0_0 = _m_0["m0"];
  const _m1_0 = _m_0["m1"];
  const _m2_0 = _m_0["m2"];
  const _m3_0 = _m_0["m3"];
  const _m4_0 = _m_0["m4"];
  const _m5_0 = _m_0["m5"];
  const _m6_0 = _m_0["m6"];
  const _m7_0 = _m_0["m7"];
  const _m8_0 = _m_0["m8"];
  const _m9_0 = _m_0["m9"];
  const _m10_0 = _m_0["m10"];
  const _m11_0 = _m_0["m11"];
  const _m12_0 = _m_0["m12"];
  const _m13_0 = _m_0["m13"];
  const _m14_0 = _m_0["m14"];
  const _m15_0 = _m_0["m15"];
  return {$: "M16", "m0": _m2_0, "m1": _m6_0, "m2": _m3_0, "m3": _m10_0, "m4": _m7_0, "m5": _m0_0, "m6": _m4_0, "m7": _m13_0, "m8": _m1_0, "m9": _m11_0, "m10": _m12_0, "m11": _m5_0, "m12": _m9_0, "m13": _m14_0, "m14": _m15_0, "m15": _m8_0};
}

function $b3scalar_out(_s_0) {
  const _v0_0 = _s_0["v0"];
  const _v1_0 = _s_0["v1"];
  const _v2_0 = _s_0["v2"];
  const _v3_0 = _s_0["v3"];
  const _v4_0 = _s_0["v4"];
  const _v5_0 = _s_0["v5"];
  const _v6_0 = _s_0["v6"];
  const _v7_0 = _s_0["v7"];
  const _v8_0 = _s_0["v8"];
  const _v9_0 = _s_0["v9"];
  const _v10_0 = _s_0["v10"];
  const _v11_0 = _s_0["v11"];
  const _v12_0 = _s_0["v12"];
  const _v13_0 = _s_0["v13"];
  const _v14_0 = _s_0["v14"];
  const _v15_0 = _s_0["v15"];
  return {$: "CV", "h0": ((_v0_0 ^ _v8_0) >>> 0), "h1": ((_v1_0 ^ _v9_0) >>> 0), "h2": ((_v2_0 ^ _v10_0) >>> 0), "h3": ((_v3_0 ^ _v11_0) >>> 0), "h4": ((_v4_0 ^ _v12_0) >>> 0), "h5": ((_v5_0 ^ _v13_0) >>> 0), "h6": ((_v6_0 ^ _v14_0) >>> 0), "h7": ((_v7_0 ^ _v15_0) >>> 0)};
}

function $b3scalar_compress(_cv_0, _m1_0, _t0_0, _t1_0, _blen_0, _flags_0) {
  const _h0_0 = _cv_0["h0"];
  const _h1_0 = _cv_0["h1"];
  const _h2_0 = _cv_0["h2"];
  const _h3_0 = _cv_0["h3"];
  const _h4_0 = _cv_0["h4"];
  const _h5_0 = _cv_0["h5"];
  const _h6_0 = _cv_0["h6"];
  const _h7_0 = _cv_0["h7"];
  const _m2_0 = ($b3scalar_perm(_m1_0));
  const _m3_0 = ($b3scalar_perm(_m2_0));
  const _m4_0 = ($b3scalar_perm(_m3_0));
  const _m5_0 = ($b3scalar_perm(_m4_0));
  const _m6_0 = ($b3scalar_perm(_m5_0));
  const _m7_0 = ($b3scalar_perm(_m6_0));
  const _s0_0 = {$: "S16", "v0": _h0_0, "v1": _h1_0, "v2": _h2_0, "v3": _h3_0, "v4": _h4_0, "v5": _h5_0, "v6": _h6_0, "v7": _h7_0, "v8": 1779033703, "v9": 3144134277, "v10": 1013904242, "v11": 2773480762, "v12": _t0_0, "v13": _t1_0, "v14": _blen_0, "v15": _flags_0};
  return $b3scalar_out(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(_s0_0, _m1_0)), _m2_0)), _m3_0)), _m4_0)), _m5_0)), _m6_0)), _m7_0)));
}

function $b3scalar_chunk_go($0, $1, $2, $3, $4, $5, $6, $7) {
  for (;;) {
    {
      const _n_0 = $0;
      const _r_0 = $1;
      const _w_0 = $2;
      const _cv_0 = $3;
      const _ctr_0 = $4;
      const _fl_0 = $5;
      const _endf_0 = $6;
      const _lastlen_0 = $7;
      if (_n_0 === 0) {
        const _a_0 = _r_0["fst"];
        const _m_0 = _r_0["snd"];
        return {$: "Tuple", "fst": _a_0, "snd": ($b3scalar_compress(_cv_0, _m_0, _ctr_0, 0, _lastlen_0, ((_fl_0 | _endf_0) >>> 0)))};
      } else {
        const _p_0 = (_n_0 - 1);
        const _a_1 = _r_0["fst"];
        const _m_1 = _r_0["snd"];
        const _w2_0 = ((_w_0 + 16) >>> 0);
        $0 = _p_0;
        $1 = ($b3scalar_ld(_a_1, _w2_0));
        $2 = _w2_0;
        $3 = ($b3scalar_compress(_cv_0, _m_1, _ctr_0, 0, 64, _fl_0));
        $4 = _ctr_0;
        $5 = 0;
        $6 = _endf_0;
        $7 = _lastlen_0;
        continue;
      }
    }
  }
}

function $b3scalar_chunk_fin(_r_0) {
  const _cv_0 = _r_0["snd"];
  return _cv_0;
}

function $b3scalar_chunk(_a_0, _c_0, _cb_0, _nch_0, _last_0, _rf_0) {
  const _w_0 = (8 >= 32 ? 0 : (_c_0 << 8) >>> 0);
  const _x_0 = ((_c_0 + 1) >>> 0);
  const _x_1 = ($Bool_to_u32((_x_0 === _nch_0)));
  const _m_0 = ((0 - _x_1) >>> 0);
  const _x_2 = (~_m_0 >>> 0);
  const _x_3 = ((_last_0 & _m_0) >>> 0);
  const _x_4 = ((1024 & _x_2) >>> 0);
  const _rem_0 = ((_x_3 | _x_4) >>> 0);
  const _x_5 = ((_rem_0 + 63) >>> 0);
  const _nb_0 = ($U32_max((6 >= 32 ? 0 : (_x_5 >>> 6) >>> 0), 1));
  const _x_6 = ((_nb_0 - 1) >>> 0);
  const _x_7 = (6 >= 32 ? 0 : (_x_6 << 6) >>> 0);
  const _lastlen_0 = ((_rem_0 - _x_7) >>> 0);
  const _x_8 = ((_nb_0 - 1) >>> 0);
  const _x_9 = ($b3scalar_CHUNK_END());
  return $b3scalar_chunk_fin(($b3scalar_chunk_go(_x_8, ($b3scalar_ld(_a_0, _w_0)), _w_0, ($b3scalar_IV()), ((_cb_0 + _c_0) >>> 0), ($b3scalar_CHUNK_START()), ((_x_9 | _rf_0) >>> 0), _lastlen_0)));
}

function $b3scalar_parent(_l_0, _r_0, _rf_0) {
  const _l0_0 = _l_0["h0"];
  const _l1_0 = _l_0["h1"];
  const _l2_0 = _l_0["h2"];
  const _l3_0 = _l_0["h3"];
  const _l4_0 = _l_0["h4"];
  const _l5_0 = _l_0["h5"];
  const _l6_0 = _l_0["h6"];
  const _l7_0 = _l_0["h7"];
  const _r0_0 = _r_0["h0"];
  const _r1_0 = _r_0["h1"];
  const _r2_0 = _r_0["h2"];
  const _r3_0 = _r_0["h3"];
  const _r4_0 = _r_0["h4"];
  const _r5_0 = _r_0["h5"];
  const _r6_0 = _r_0["h6"];
  const _r7_0 = _r_0["h7"];
  const _x_0 = ($b3scalar_PARENT());
  return $b3scalar_compress(($b3scalar_IV()), {$: "M16", "m0": _l0_0, "m1": _l1_0, "m2": _l2_0, "m3": _l3_0, "m4": _l4_0, "m5": _l5_0, "m6": _l6_0, "m7": _l7_0, "m8": _r0_0, "m9": _r1_0, "m10": _r2_0, "m11": _r3_0, "m12": _r4_0, "m13": _r5_0, "m14": _r6_0, "m15": _r7_0}, 0, 0, 64, ((_x_0 | _rf_0) >>> 0));
}

function $b3scalar_big(_k_0, _n_0) {
  if (_k_0 === 0) {
    return false;
  } else {
    const _p_0 = (_k_0 - 1);
    const _x_0 = (_p_0 >= 32 ? 0 : (1 << _p_0) >>> 0);
    return (_n_0 > _x_0);
  }
}

function $b3scalar_chunks(_len_0) {
  const _x_0 = ((_len_0 + 1023) >>> 0);
  return $U32_max((10 >= 32 ? 0 : (_x_0 >>> 10) >>> 0), 1);
}

function $b3scalar_depth_go(_b_0, _n_0) {
  if (_b_0) {
    return 0;
  } else {
    return nat_chk(($U32_log2(((_n_0 - 1) >>> 0))) + 1);
  }
}

function $b3scalar_depth(_n_0) {
  return $b3scalar_depth_go((_n_0 <= 1), _n_0);
}

function $b3scalar_KEYED_HASH() {
  return 16;
}

function $b3scalar_DERIVE_KEY_CONTEXT() {
  return 32;
}

function $b3scalar_DERIVE_KEY_MATERIAL() {
  return 64;
}

function $b3scalar_chunk_go_k($0, $1, $2, $3, $4, $5, $6, $7, $8) {
  for (;;) {
    {
      const _n_0 = $0;
      const _r_0 = $1;
      const _w_0 = $2;
      const _cv_0 = $3;
      const _ctr_0 = $4;
      const _fl_0 = $5;
      const _endf_0 = $6;
      const _lastlen_0 = $7;
      const _kf_0 = $8;
      if (_n_0 === 0) {
        const _a_0 = _r_0["fst"];
        const _m_0 = _r_0["snd"];
        const _x_0 = ((_fl_0 | _endf_0) >>> 0);
        return {$: "Tuple", "fst": _a_0, "snd": ($b3scalar_compress(_cv_0, _m_0, _ctr_0, 0, _lastlen_0, ((_x_0 | _kf_0) >>> 0)))};
      } else {
        const _p_0 = (_n_0 - 1);
        const _a_1 = _r_0["fst"];
        const _m_1 = _r_0["snd"];
        const _w2_0 = ((_w_0 + 16) >>> 0);
        $0 = _p_0;
        $1 = ($b3scalar_ld(_a_1, _w2_0));
        $2 = _w2_0;
        $3 = ($b3scalar_compress(_cv_0, _m_1, _ctr_0, 0, 64, ((_fl_0 | _kf_0) >>> 0)));
        $4 = _ctr_0;
        $5 = 0;
        $6 = _endf_0;
        $7 = _lastlen_0;
        $8 = _kf_0;
        continue;
      }
    }
  }
}

function $b3scalar_chunk_k(_a_0, _c_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0) {
  const _w_0 = (8 >= 32 ? 0 : (_c_0 << 8) >>> 0);
  const _x_0 = ((_c_0 + 1) >>> 0);
  const _x_1 = ($Bool_to_u32((_x_0 === _nch_0)));
  const _m_0 = ((0 - _x_1) >>> 0);
  const _x_2 = (~_m_0 >>> 0);
  const _x_3 = ((_last_0 & _m_0) >>> 0);
  const _x_4 = ((1024 & _x_2) >>> 0);
  const _rem_0 = ((_x_3 | _x_4) >>> 0);
  const _x_5 = ((_rem_0 + 63) >>> 0);
  const _nb_0 = ($U32_max((6 >= 32 ? 0 : (_x_5 >>> 6) >>> 0), 1));
  const _x_6 = ((_nb_0 - 1) >>> 0);
  const _x_7 = (6 >= 32 ? 0 : (_x_6 << 6) >>> 0);
  const _lastlen_0 = ((_rem_0 - _x_7) >>> 0);
  const _x_8 = ((_nb_0 - 1) >>> 0);
  const _x_9 = ($b3scalar_CHUNK_END());
  return $b3scalar_chunk_fin(($b3scalar_chunk_go_k(_x_8, ($b3scalar_ld(_a_0, _w_0)), _w_0, _key_0, ((_cb_0 + _c_0) >>> 0), ($b3scalar_CHUNK_START()), ((_x_9 | _rf_0) >>> 0), _lastlen_0, _kf_0)));
}

function $b3scalar_parent_k(_l_0, _r_0, _rf_0, _key_0, _kf_0) {
  const _l0_0 = _l_0["h0"];
  const _l1_0 = _l_0["h1"];
  const _l2_0 = _l_0["h2"];
  const _l3_0 = _l_0["h3"];
  const _l4_0 = _l_0["h4"];
  const _l5_0 = _l_0["h5"];
  const _l6_0 = _l_0["h6"];
  const _l7_0 = _l_0["h7"];
  const _r0_0 = _r_0["h0"];
  const _r1_0 = _r_0["h1"];
  const _r2_0 = _r_0["h2"];
  const _r3_0 = _r_0["h3"];
  const _r4_0 = _r_0["h4"];
  const _r5_0 = _r_0["h5"];
  const _r6_0 = _r_0["h6"];
  const _r7_0 = _r_0["h7"];
  const _x_0 = ($b3scalar_PARENT());
  const _x_1 = ((_x_0 | _rf_0) >>> 0);
  return $b3scalar_compress(_key_0, {$: "M16", "m0": _l0_0, "m1": _l1_0, "m2": _l2_0, "m3": _l3_0, "m4": _l4_0, "m5": _l5_0, "m6": _l6_0, "m7": _l7_0, "m8": _r0_0, "m9": _r1_0, "m10": _r2_0, "m11": _r3_0, "m12": _r4_0, "m13": _r5_0, "m14": _r6_0, "m15": _r7_0}, 0, 0, 64, ((_x_1 | _kf_0) >>> 0));
}

function $b3scalar_chunk_root_go($0, $1, $2, $3, $4, $5, $6, $7) {
  for (;;) {
    {
      const _n_0 = $0;
      const _r_0 = $1;
      const _w_0 = $2;
      const _cv_0 = $3;
      const _ctr_0 = $4;
      const _fl_0 = $5;
      const _lastlen_0 = $6;
      const _kf_0 = $7;
      if (_n_0 === 0) {
        const _m_0 = _r_0["snd"];
        const _x_0 = ($b3scalar_CHUNK_END());
        const _x_1 = ((_fl_0 | _x_0) >>> 0);
        return {$: "Root", "cv": _cv_0, "m": _m_0, "blen": _lastlen_0, "fl": ((_x_1 | _kf_0) >>> 0)};
      } else {
        const _p_0 = (_n_0 - 1);
        const _a_1 = _r_0["fst"];
        const _m_1 = _r_0["snd"];
        const _w2_0 = ((_w_0 + 16) >>> 0);
        $0 = _p_0;
        $1 = ($b3scalar_ld(_a_1, _w2_0));
        $2 = _w2_0;
        $3 = ($b3scalar_compress(_cv_0, _m_1, _ctr_0, 0, 64, ((_fl_0 | _kf_0) >>> 0)));
        $4 = _ctr_0;
        $5 = 0;
        $6 = _lastlen_0;
        $7 = _kf_0;
        continue;
      }
    }
  }
}

function $b3scalar_chunk_root(_a_0, _cb_0, _last_0, _key_0, _kf_0) {
  const _x_0 = ((_last_0 + 63) >>> 0);
  const _nb_0 = ($U32_max((6 >= 32 ? 0 : (_x_0 >>> 6) >>> 0), 1));
  const _x_1 = ((_nb_0 - 1) >>> 0);
  const _x_2 = (6 >= 32 ? 0 : (_x_1 << 6) >>> 0);
  const _lastlen_0 = ((_last_0 - _x_2) >>> 0);
  const _x_3 = ((_nb_0 - 1) >>> 0);
  return $b3scalar_chunk_root_go(_x_3, ($b3scalar_ld(_a_0, 0)), 0, _key_0, _cb_0, ($b3scalar_CHUNK_START()), _lastlen_0, _kf_0);
}

function $b3scalar_parent_root(_l_0, _r_0, _key_0, _kf_0) {
  const _l0_0 = _l_0["h0"];
  const _l1_0 = _l_0["h1"];
  const _l2_0 = _l_0["h2"];
  const _l3_0 = _l_0["h3"];
  const _l4_0 = _l_0["h4"];
  const _l5_0 = _l_0["h5"];
  const _l6_0 = _l_0["h6"];
  const _l7_0 = _l_0["h7"];
  const _r0_0 = _r_0["h0"];
  const _r1_0 = _r_0["h1"];
  const _r2_0 = _r_0["h2"];
  const _r3_0 = _r_0["h3"];
  const _r4_0 = _r_0["h4"];
  const _r5_0 = _r_0["h5"];
  const _r6_0 = _r_0["h6"];
  const _r7_0 = _r_0["h7"];
  const _x_0 = ($b3scalar_PARENT());
  return {$: "Root", "cv": _key_0, "m": {$: "M16", "m0": _l0_0, "m1": _l1_0, "m2": _l2_0, "m3": _l3_0, "m4": _l4_0, "m5": _l5_0, "m6": _l6_0, "m7": _l7_0, "m8": _r0_0, "m9": _r1_0, "m10": _r2_0, "m11": _r3_0, "m12": _r4_0, "m13": _r5_0, "m14": _r6_0, "m15": _r7_0}, "blen": 64, "fl": ((_x_0 | _kf_0) >>> 0)};
}

function $b3scalar_out2(_s_0, _c_0) {
  const _v0_0 = _s_0["v0"];
  const _v1_0 = _s_0["v1"];
  const _v2_0 = _s_0["v2"];
  const _v3_0 = _s_0["v3"];
  const _v4_0 = _s_0["v4"];
  const _v5_0 = _s_0["v5"];
  const _v6_0 = _s_0["v6"];
  const _v7_0 = _s_0["v7"];
  const _v8_0 = _s_0["v8"];
  const _v9_0 = _s_0["v9"];
  const _v10_0 = _s_0["v10"];
  const _v11_0 = _s_0["v11"];
  const _v12_0 = _s_0["v12"];
  const _v13_0 = _s_0["v13"];
  const _v14_0 = _s_0["v14"];
  const _v15_0 = _s_0["v15"];
  const _h0_0 = _c_0["h0"];
  const _h1_0 = _c_0["h1"];
  const _h2_0 = _c_0["h2"];
  const _h3_0 = _c_0["h3"];
  const _h4_0 = _c_0["h4"];
  const _h5_0 = _c_0["h5"];
  const _h6_0 = _c_0["h6"];
  const _h7_0 = _c_0["h7"];
  return {$: "Tuple", "fst": {$: "CV", "h0": ((_v0_0 ^ _v8_0) >>> 0), "h1": ((_v1_0 ^ _v9_0) >>> 0), "h2": ((_v2_0 ^ _v10_0) >>> 0), "h3": ((_v3_0 ^ _v11_0) >>> 0), "h4": ((_v4_0 ^ _v12_0) >>> 0), "h5": ((_v5_0 ^ _v13_0) >>> 0), "h6": ((_v6_0 ^ _v14_0) >>> 0), "h7": ((_v7_0 ^ _v15_0) >>> 0)}, "snd": {$: "CV", "h0": ((_v8_0 ^ _h0_0) >>> 0), "h1": ((_v9_0 ^ _h1_0) >>> 0), "h2": ((_v10_0 ^ _h2_0) >>> 0), "h3": ((_v11_0 ^ _h3_0) >>> 0), "h4": ((_v12_0 ^ _h4_0) >>> 0), "h5": ((_v13_0 ^ _h5_0) >>> 0), "h6": ((_v14_0 ^ _h6_0) >>> 0), "h7": ((_v15_0 ^ _h7_0) >>> 0)}};
}

function $b3scalar_compress_xof(_cv_0, _m1_0, _t0_0, _t1_0, _blen_0, _flags_0) {
  const _h0_0 = _cv_0["h0"];
  const _h1_0 = _cv_0["h1"];
  const _h2_0 = _cv_0["h2"];
  const _h3_0 = _cv_0["h3"];
  const _h4_0 = _cv_0["h4"];
  const _h5_0 = _cv_0["h5"];
  const _h6_0 = _cv_0["h6"];
  const _h7_0 = _cv_0["h7"];
  const _m2_0 = ($b3scalar_perm(_m1_0));
  const _m3_0 = ($b3scalar_perm(_m2_0));
  const _m4_0 = ($b3scalar_perm(_m3_0));
  const _m5_0 = ($b3scalar_perm(_m4_0));
  const _m6_0 = ($b3scalar_perm(_m5_0));
  const _m7_0 = ($b3scalar_perm(_m6_0));
  const _s0_0 = {$: "S16", "v0": _h0_0, "v1": _h1_0, "v2": _h2_0, "v3": _h3_0, "v4": _h4_0, "v5": _h5_0, "v6": _h6_0, "v7": _h7_0, "v8": 1779033703, "v9": 3144134277, "v10": 1013904242, "v11": 2773480762, "v12": _t0_0, "v13": _t1_0, "v14": _blen_0, "v15": _flags_0};
  return $b3scalar_out2(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(($b3scalar_round(_s0_0, _m1_0)), _m2_0)), _m3_0)), _m4_0)), _m5_0)), _m6_0)), _m7_0)), {$: "CV", "h0": _h0_0, "h1": _h1_0, "h2": _h2_0, "h3": _h3_0, "h4": _h4_0, "h5": _h5_0, "h6": _h6_0, "h7": _h7_0});
}

function $b3scalar_root_out(_r_0, _t0_0, _t1_0) {
  const _cv_0 = _r_0["cv"];
  const _m_0 = _r_0["m"];
  const _blen_0 = _r_0["blen"];
  const _fl_0 = _r_0["fl"];
  const _x_0 = ($b3scalar_ROOT());
  return $b3scalar_compress_xof(_cv_0, _m_0, _t0_0, _t1_0, _blen_0, ((_fl_0 | _x_0) >>> 0));
}

function $b3scalar_tail(_len_0, _n_0) {
  const _x_0 = ((_n_0 - 1) >>> 0);
  const _x_1 = (10 >= 32 ? 0 : (_x_0 << 10) >>> 0);
  return ((_len_0 - _x_1) >>> 0);
}

function $b3scalar_hex_pick(_b_0, _d_0) {
  if (_b_0) {
    return char_new(((_d_0 + 48) >>> 0));
  } else {
    return char_new(((_d_0 + 87) >>> 0));
  }
}

function $b3scalar_hex_digit(_d_0) {
  return $b3scalar_hex_pick((_d_0 < 10), _d_0);
}

function $b3scalar_hex_byte(_x_0, _s_0) {
  const _x_1 = (4 >= 32 ? 0 : (_x_0 >>> 4) >>> 0);
  return (($b3scalar_hex_digit(((_x_1 & 15) >>> 0))) + (($b3scalar_hex_digit(((_x_0 & 15) >>> 0))) + _s_0));
}

function $b3scalar_hex_word(_x_0, _s_0) {
  return $b3scalar_hex_byte(_x_0, ($b3scalar_hex_byte((8 >= 32 ? 0 : (_x_0 >>> 8) >>> 0), ($b3scalar_hex_byte((16 >= 32 ? 0 : (_x_0 >>> 16) >>> 0), ($b3scalar_hex_byte((24 >= 32 ? 0 : (_x_0 >>> 24) >>> 0), _s_0)))))));
}

function $b3scalar_hex_onto(_cv_0, _s_0) {
  const _h0_0 = _cv_0["h0"];
  const _h1_0 = _cv_0["h1"];
  const _h2_0 = _cv_0["h2"];
  const _h3_0 = _cv_0["h3"];
  const _h4_0 = _cv_0["h4"];
  const _h5_0 = _cv_0["h5"];
  const _h6_0 = _cv_0["h6"];
  const _h7_0 = _cv_0["h7"];
  return $b3scalar_hex_word(_h0_0, ($b3scalar_hex_word(_h1_0, ($b3scalar_hex_word(_h2_0, ($b3scalar_hex_word(_h3_0, ($b3scalar_hex_word(_h4_0, ($b3scalar_hex_word(_h5_0, ($b3scalar_hex_word(_h6_0, ($b3scalar_hex_word(_h7_0, _s_0)))))))))))))));
}

function $b3scalar_hex(_cv_0) {
  return $b3scalar_hex_onto(_cv_0, "");
}

function $fork(_a_0) {
  return $Array_fork(_a_0);
}

function $IV() {
  return $b3scalar_IV();
}

function $hash(_a_0, _len_0) {
  return $b3scalar_hash_0(_a_0, _len_0);
}

function $span(_a_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0) {
  return $b3scalar_hash_at_k_0(_a_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0);
}

function $parent(_l_0, _r_0, _key_0, _kf_0) {
  return $b3scalar_parent_k(_l_0, _r_0, 0, _key_0, _kf_0);
}

function $chunk_root(_a_0, _cb_0, _last_0, _key_0, _kf_0) {
  return $b3scalar_chunk_root(_a_0, _cb_0, _last_0, _key_0, _kf_0);
}

function $parent_root(_l_0, _r_0, _key_0, _kf_0) {
  return $b3scalar_parent_root(_l_0, _r_0, _key_0, _kf_0);
}

function $root_out(_r_0, _t0_0, _t1_0) {
  return $b3scalar_root_out(_r_0, _t0_0, _t1_0);
}

function $Bool_to_u32(_b_0) {
  if (!_b_0) {
    return 0;
  } else {
    return 1;
  }
}

function $U32_max(_a_0, _b_0) {
  return $Bool_pick((_a_0 < _b_0), _b_0, _a_0);
}

function $U32_log2(_n_0) {
  return $U32_log2_go(5, _n_0, 0);
}

function $Array_fork(_a_0) {
  return {$: "Tuple", "fst": _a_0, "snd": _a_0};
}

function $b3scalar_hash_0(_a_0, _len_0) {
  const _n_0 = ($b3scalar_chunks(_len_0));
  return $b3scalar_hash_at_0(_a_0, 0, _n_0, ($b3scalar_tail(_len_0, _n_0)), ($b3scalar_ROOT()));
}

function $b3scalar_hash_at_k_0(_a_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0) {
  const _k_0 = ($b3scalar_depth(_nch_0));
  return $b3scalar_tree1_k_0(_k_0, ($b3scalar_big(_k_0, _nch_0)), ($fork(_a_0)), 0, _nch_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0);
}

function $Bool_pick(_c_0, _a_0, _b_0) {
  if (!_c_0) {
    return _b_0;
  } else {
    return _a_0;
  }
}

function $U32_log2_go($0, $1, $2) {
  for (;;) {
    {
      const _k_0 = $0;
      const _n_0 = $1;
      const _b_0 = $2;
      if (_k_0 === 0) {
        return _b_0;
      } else {
        const _p_0 = (_k_0 - 1);
        const _x_0 = (_p_0 >= 32 ? 0 : (1 << _p_0) >>> 0);
        const _s_0 = _x_0;
        const _x_1 = (_s_0 >= 32 ? 0 : (_n_0 >>> _s_0) >>> 0);
        const _x_2 = ($Bool_to_u32((_x_1 !== 0)));
        const _t_0 = nat_chk(_s_0 * _x_2);
        $0 = _p_0;
        $1 = (_t_0 >= 32 ? 0 : (_n_0 >>> _t_0) >>> 0);
        $2 = nat_chk(_b_0 + _t_0);
        continue;
      }
    }
  }
}

function $b3scalar_hash_at_0(_a_0, _cb_0, _nch_0, _last_0, _rf_0) {
  const _k_0 = ($b3scalar_depth(_nch_0));
  return $b3scalar_tree1_0(_k_0, ($b3scalar_big(_k_0, _nch_0)), ($fork(_a_0)), 0, _nch_0, _cb_0, _nch_0, _last_0, _rf_0);
}

function $b3scalar_tree1_k_0($0, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10) {
  for (;;) {
    {
      const _k_0 = $0;
      const _b_0 = $1;
      const _aa_0 = $2;
      const _c_0 = $3;
      const _n_0 = $4;
      const _cb_0 = $5;
      const _nch_0 = $6;
      const _last_0 = $7;
      const _rf_0 = $8;
      const _key_0 = $9;
      const _kf_0 = $10;
      if (_k_0 === 0) {
        const _a1_0 = _aa_0["fst"];
        return $b3scalar_chunk_k(_a1_0, _c_0, _cb_0, _nch_0, _last_0, _rf_0, _key_0, _kf_0);
      } else {
        const _p_0 = (_k_0 - 1);
        if (!_b_0) {
          $0 = _p_0;
          $1 = ($b3scalar_big(_p_0, _n_0));
          $2 = _aa_0;
          $3 = _c_0;
          $4 = _n_0;
          $5 = _cb_0;
          $6 = _nch_0;
          $7 = _last_0;
          $8 = _rf_0;
          $9 = _key_0;
          $10 = _kf_0;
          continue;
        } else {
          const _a1_1 = _aa_0["fst"];
          const _a2_1 = _aa_0["snd"];
          const _h_0 = (_p_0 >= 32 ? 0 : (1 << _p_0) >>> 0);
          const _n2_0 = ((_n_0 - _h_0) >>> 0);
          const _l_0 = ($b3scalar_tree1_k_0(_p_0, ($b3scalar_big(_p_0, _h_0)), ($fork(_a1_1)), _c_0, _h_0, _cb_0, _nch_0, _last_0, 0, _key_0, _kf_0));
          const _r_0 = ($b3scalar_tree1_k_0(_p_0, ($b3scalar_big(_p_0, _n2_0)), ($fork(_a2_1)), ((_c_0 + _h_0) >>> 0), _n2_0, _cb_0, _nch_0, _last_0, 0, _key_0, _kf_0));
          return $b3scalar_parent_k(_l_0, _r_0, _rf_0, _key_0, _kf_0);
        }
      }
    }
  }
}

function $b3scalar_tree1_0($0, $1, $2, $3, $4, $5, $6, $7, $8) {
  for (;;) {
    {
      const _k_0 = $0;
      const _b_0 = $1;
      const _aa_0 = $2;
      const _c_0 = $3;
      const _n_0 = $4;
      const _cb_0 = $5;
      const _nch_0 = $6;
      const _last_0 = $7;
      const _rf_0 = $8;
      if (_k_0 === 0) {
        const _a1_0 = _aa_0["fst"];
        return $b3scalar_chunk(_a1_0, _c_0, _cb_0, _nch_0, _last_0, _rf_0);
      } else {
        const _p_0 = (_k_0 - 1);
        if (!_b_0) {
          $0 = _p_0;
          $1 = ($b3scalar_big(_p_0, _n_0));
          $2 = _aa_0;
          $3 = _c_0;
          $4 = _n_0;
          $5 = _cb_0;
          $6 = _nch_0;
          $7 = _last_0;
          $8 = _rf_0;
          continue;
        } else {
          const _a1_1 = _aa_0["fst"];
          const _a2_1 = _aa_0["snd"];
          const _h_0 = (_p_0 >= 32 ? 0 : (1 << _p_0) >>> 0);
          const _n2_0 = ((_n_0 - _h_0) >>> 0);
          const _l_0 = ($b3scalar_tree1_0(_p_0, ($b3scalar_big(_p_0, _h_0)), ($fork(_a1_1)), _c_0, _h_0, _cb_0, _nch_0, _last_0, 0));
          const _r_0 = ($b3scalar_tree1_0(_p_0, ($b3scalar_big(_p_0, _n2_0)), ($fork(_a2_1)), ((_c_0 + _h_0) >>> 0), _n2_0, _cb_0, _nch_0, _last_0, 0));
          return $b3scalar_parent(_l_0, _r_0, _rf_0);
        }
      }
    }
  }
}
export default {
  "b3scalar:CHUNK_START": run_lib(() => run_loop($b3scalar_CHUNK_START()), 0),
  "b3scalar:CHUNK_END": run_lib(() => run_loop($b3scalar_CHUNK_END()), 0),
  "b3scalar:PARENT": run_lib(() => run_loop($b3scalar_PARENT()), 0),
  "b3scalar:ROOT": run_lib(() => run_loop($b3scalar_ROOT()), 0),
  "b3scalar:IV": run_lib(() => run_loop($b3scalar_IV()), 0),
  "b3scalar:rotr16": run_lib((a0) => run_loop($b3scalar_rotr16(a0)), 1),
  "b3scalar:rotr12": run_lib((a0) => run_loop($b3scalar_rotr12(a0)), 1),
  "b3scalar:rotr8": run_lib((a0) => run_loop($b3scalar_rotr8(a0)), 1),
  "b3scalar:rotr7": run_lib((a0) => run_loop($b3scalar_rotr7(a0)), 1),
  "b3scalar:ld.s15": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15) => run_loop($b3scalar_ld_s15(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15)), 16),
  "b3scalar:ld.s14": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15) => run_loop($b3scalar_ld_s14(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15)), 16),
  "b3scalar:ld.s13": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14) => run_loop($b3scalar_ld_s13(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14)), 15),
  "b3scalar:ld.s12": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13) => run_loop($b3scalar_ld_s12(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13)), 14),
  "b3scalar:ld.s11": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12) => run_loop($b3scalar_ld_s11(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12)), 13),
  "b3scalar:ld.s10": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11) => run_loop($b3scalar_ld_s10(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11)), 12),
  "b3scalar:ld.s9": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10) => run_loop($b3scalar_ld_s9(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10)), 11),
  "b3scalar:ld.s8": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8,a9) => run_loop($b3scalar_ld_s8(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9)), 10),
  "b3scalar:ld.s7": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8) => run_loop($b3scalar_ld_s7(a0,a1,a2,a3,a4,a5,a6,a7,a8)), 9),
  "b3scalar:ld.s6": run_lib((a0,a1,a2,a3,a4,a5,a6,a7) => run_loop($b3scalar_ld_s6(a0,a1,a2,a3,a4,a5,a6,a7)), 8),
  "b3scalar:ld.s5": run_lib((a0,a1,a2,a3,a4,a5,a6) => run_loop($b3scalar_ld_s5(a0,a1,a2,a3,a4,a5,a6)), 7),
  "b3scalar:ld.s4": run_lib((a0,a1,a2,a3,a4,a5) => run_loop($b3scalar_ld_s4(a0,a1,a2,a3,a4,a5)), 6),
  "b3scalar:ld.s3": run_lib((a0,a1,a2,a3,a4) => run_loop($b3scalar_ld_s3(a0,a1,a2,a3,a4)), 5),
  "b3scalar:ld.s2": run_lib((a0,a1,a2,a3) => run_loop($b3scalar_ld_s2(a0,a1,a2,a3)), 4),
  "b3scalar:ld.s1": run_lib((a0,a1,a2) => run_loop($b3scalar_ld_s1(a0,a1,a2)), 3),
  "b3scalar:ld.s0": run_lib((a0,a1) => run_loop($b3scalar_ld_s0(a0,a1)), 2),
  "b3scalar:ld": run_lib((a0,a1) => run_loop($b3scalar_ld(a0,a1)), 2),
  "b3scalar:round": run_lib((a0,a1) => run_loop($b3scalar_round(a0,a1)), 2),
  "b3scalar:perm": run_lib((a0) => run_loop($b3scalar_perm(a0)), 1),
  "b3scalar:out": run_lib((a0) => run_loop($b3scalar_out(a0)), 1),
  "b3scalar:compress": run_lib((a0,a1,a2,a3,a4,a5) => run_loop($b3scalar_compress(a0,a1,a2,a3,a4,a5)), 6),
  "b3scalar:chunk.go": run_lib((a0,a1,a2,a3,a4,a5,a6,a7) => run_loop($b3scalar_chunk_go(nat_in(a0),a1,a2,a3,a4,a5,a6,a7)), 8),
  "b3scalar:chunk.fin": run_lib((a0) => run_loop($b3scalar_chunk_fin(a0)), 1),
  "b3scalar:chunk": run_lib((a0,a1,a2,a3,a4,a5) => run_loop($b3scalar_chunk(a0,a1,a2,a3,a4,a5)), 6),
  "b3scalar:parent": run_lib((a0,a1,a2) => run_loop($b3scalar_parent(a0,a1,a2)), 3),
  "b3scalar:big": run_lib((a0,a1) => run_loop($b3scalar_big(nat_in(a0),a1)), 2),
  "b3scalar:chunks": run_lib((a0) => run_loop($b3scalar_chunks(a0)), 1),
  "b3scalar:depth.go": run_lib((a0,a1) => run_loop($b3scalar_depth_go(a0,a1)), 2),
  "b3scalar:depth": run_lib((a0) => run_loop($b3scalar_depth(a0)), 1),
  "b3scalar:KEYED_HASH": run_lib(() => run_loop($b3scalar_KEYED_HASH()), 0),
  "b3scalar:DERIVE_KEY_CONTEXT": run_lib(() => run_loop($b3scalar_DERIVE_KEY_CONTEXT()), 0),
  "b3scalar:DERIVE_KEY_MATERIAL": run_lib(() => run_loop($b3scalar_DERIVE_KEY_MATERIAL()), 0),
  "b3scalar:chunk.go.k": run_lib((a0,a1,a2,a3,a4,a5,a6,a7,a8) => run_loop($b3scalar_chunk_go_k(nat_in(a0),a1,a2,a3,a4,a5,a6,a7,a8)), 9),
  "b3scalar:chunk.k": run_lib((a0,a1,a2,a3,a4,a5,a6,a7) => run_loop($b3scalar_chunk_k(a0,a1,a2,a3,a4,a5,a6,a7)), 8),
  "b3scalar:parent.k": run_lib((a0,a1,a2,a3,a4) => run_loop($b3scalar_parent_k(a0,a1,a2,a3,a4)), 5),
  "b3scalar:chunk.root.go": run_lib((a0,a1,a2,a3,a4,a5,a6,a7) => run_loop($b3scalar_chunk_root_go(nat_in(a0),a1,a2,a3,a4,a5,a6,a7)), 8),
  "b3scalar:chunk.root": run_lib((a0,a1,a2,a3,a4) => run_loop($b3scalar_chunk_root(a0,a1,a2,a3,a4)), 5),
  "b3scalar:parent.root": run_lib((a0,a1,a2,a3) => run_loop($b3scalar_parent_root(a0,a1,a2,a3)), 4),
  "b3scalar:out2": run_lib((a0,a1) => run_loop($b3scalar_out2(a0,a1)), 2),
  "b3scalar:compress.xof": run_lib((a0,a1,a2,a3,a4,a5) => run_loop($b3scalar_compress_xof(a0,a1,a2,a3,a4,a5)), 6),
  "b3scalar:root.out": run_lib((a0,a1,a2) => run_loop($b3scalar_root_out(a0,a1,a2)), 3),
  "b3scalar:tail": run_lib((a0,a1) => run_loop($b3scalar_tail(a0,a1)), 2),
  "b3scalar:hex.pick": run_lib((a0,a1) => str_out(run_loop($b3scalar_hex_pick(a0,a1))), 2),
  "b3scalar:hex.digit": run_lib((a0) => str_out(run_loop($b3scalar_hex_digit(a0))), 1),
  "b3scalar:hex.byte": run_lib((a0,a1) => str_out(run_loop($b3scalar_hex_byte(a0,str_in(a1)))), 2),
  "b3scalar:hex.word": run_lib((a0,a1) => str_out(run_loop($b3scalar_hex_word(a0,str_in(a1)))), 2),
  "b3scalar:hex.onto": run_lib((a0,a1) => str_out(run_loop($b3scalar_hex_onto(a0,str_in(a1)))), 2),
  "b3scalar:hex": run_lib((a0) => str_out(run_loop($b3scalar_hex(a0))), 1),
  "fork": run_lib((a0) => run_loop($fork(a0)), 1),
  "IV": run_lib(() => run_loop($IV()), 0),
  "hash": run_lib((a0,a1) => run_loop($hash(a0,a1)), 2),
  "span": run_lib((a0,a1,a2,a3,a4,a5,a6) => run_loop($span(a0,a1,a2,a3,a4,a5,a6)), 7),
  "parent": run_lib((a0,a1,a2,a3) => run_loop($parent(a0,a1,a2,a3)), 4),
  "chunk.root": run_lib((a0,a1,a2,a3,a4) => run_loop($chunk_root(a0,a1,a2,a3,a4)), 5),
  "parent.root": run_lib((a0,a1,a2,a3) => run_loop($parent_root(a0,a1,a2,a3)), 4),
  "root.out": run_lib((a0,a1,a2) => run_loop($root_out(a0,a1,a2)), 3),
};
