import { describe, expect, it } from "vitest";
import { compareMoney, formatMoney, isZero } from "./money";

describe("formatMoney", () => {
  it("groups the Indian way and keeps two decimals", () => {
    expect(formatMoney("1234567.5")).toBe("₹12,34,567.50");
    expect(formatMoney("999")).toBe("₹999.00");
    expect(formatMoney("0.1")).toBe("₹0.10");
  });
  it("handles negatives and empties", () => {
    expect(formatMoney("-500.00")).toBe("−₹500.00");
    expect(formatMoney(null)).toBe("—");
  });
  it("compacts lakhs and crores without floats", () => {
    expect(formatMoney("12345678.00", { compact: true })).toBe("₹1.23 Cr");
    expect(formatMoney("450000.00", { compact: true })).toBe("₹4.5 L");
    expect(formatMoney("2500.00", { compact: true })).toBe("₹2.5K");
  });
});

describe("compareMoney", () => {
  it("compares decimal strings", () => {
    expect(compareMoney("10.00", "9.99")).toBe(1);
    expect(compareMoney("0.10", "0.1")).toBe(0);
    expect(compareMoney("-1", "1")).toBe(-1);
    expect(isZero("0.00")).toBe(true);
    expect(isZero("0.01")).toBe(false);
  });
});
