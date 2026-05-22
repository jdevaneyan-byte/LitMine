import { describe, expect, it } from "vitest";
import { parseTerms } from "./parseTerms";

describe("parseTerms", () => {
  it("splits on newlines", () => {
    expect(parseTerms("a\nb\nc")).toEqual(["a", "b", "c"]);
  });
  it("splits on commas", () => {
    expect(parseTerms("a, b, c")).toEqual(["a", "b", "c"]);
  });
  it("splits on mixed commas and newlines", () => {
    expect(parseTerms("a, b\nc,d")).toEqual(["a", "b", "c", "d"]);
  });
  it("preserves multi-word phrases", () => {
    expect(parseTerms("liposomal drug delivery, nanoparticle")).toEqual([
      "liposomal drug delivery",
      "nanoparticle",
    ]);
  });
  it("strips numbered list markers", () => {
    expect(parseTerms("1. alpha, 2) beta\n3. gamma")).toEqual(["alpha", "beta", "gamma"]);
  });
  it("strips bullet markers", () => {
    expect(parseTerms("- alpha\n• beta\n* gamma")).toEqual(["alpha", "beta", "gamma"]);
  });
  it("trims whitespace and drops empties", () => {
    expect(parseTerms("  a  ,, \n , b ")).toEqual(["a", "b"]);
  });
  it("de-duplicates case-insensitively, keeping first casing", () => {
    expect(parseTerms("Alpha, alpha, ALPHA, beta")).toEqual(["Alpha", "beta"]);
  });
  it("returns [] for empty input", () => {
    expect(parseTerms("   ")).toEqual([]);
  });
});
