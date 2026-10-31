// Money arrives from the API as a decimal string ("12345.60") and is formatted
// as a string. It is never turned into a float, so nothing is ever off by a paisa.

let symbol = "₹";
export function setCurrencySymbol(s: string) {
  symbol = s;
}

/** Group an integer string the Indian way: 12,34,567. */
function groupIndian(int: string): string {
  if (int.length <= 3) return int;
  const last3 = int.slice(-3);
  const rest = int.slice(0, -3);
  return `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}`;
}

export function formatMoney(value: string | null | undefined, opts: { symbol?: boolean; compact?: boolean } = {}): string {
  if (value === null || value === undefined || value === "") return "—";
  const raw = String(value).trim();
  const negative = raw.startsWith("-");
  const [intPart, fracPart = ""] = raw.replace(/^[-+]/, "").split(".");
  const cents = (fracPart + "00").slice(0, 2);
  const sign = negative ? "−" : "";
  const sym = opts.symbol === false ? "" : symbol;
  if (opts.compact) {
    const digits = intPart.replace(/^0+(?=\d)/, "");
    if (digits.length > 7) return `${sign}${sym}${shift(digits, 7)} Cr`;
    if (digits.length > 5) return `${sign}${sym}${shift(digits, 5)} L`;
    if (digits.length > 3) return `${sign}${sym}${shift(digits, 3)}K`;
  }
  return `${sign}${sym}${groupIndian(intPart || "0")}.${cents}`;
}

/** "12345678", 7 → "1.23" (string maths, no floats). */
function shift(digits: string, places: number): string {
  const whole = digits.slice(0, digits.length - places);
  const frac = digits.slice(digits.length - places, digits.length - places + 2).replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : whole;
}

/** Compare two decimal strings without floats: -1, 0 or 1. */
export function compareMoney(a: string, b: string): number {
  const norm = (v: string) => {
    const neg = v.startsWith("-");
    const [i, f = ""] = v.replace(/^[-+]/, "").split(".");
    return { neg, i: i.replace(/^0+(?=\d)/, ""), f: (f + "00").slice(0, 2) };
  };
  const x = norm(a);
  const y = norm(b);
  if (x.neg !== y.neg) return x.neg ? -1 : 1;
  const mag = x.i.length !== y.i.length ? (x.i.length > y.i.length ? 1 : -1) : (x.i + x.f).localeCompare(y.i + y.f);
  return x.neg ? -mag : mag;
}

export function isZero(value: string | null | undefined): boolean {
  return !value || /^-?0*(\.0*)?$/.test(value);
}

/** Only for chart axes, where a float is fine for drawing. */
export function toChartNumber(value: string): number {
  return Number(value);
}
