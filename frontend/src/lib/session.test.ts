import { afterEach, expect, test, vi } from "vitest";
import { clearSession, readSession, saveSession, tokenFor } from "./session";

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
  window.localStorage.clear();
});

test("reads nothing when nothing is saved", () => {
  expect(readSession()).toBeNull();
});

test("saves and reads the ID and token together", () => {
  saveSession({ id: "abc", token: "secret" });

  expect(readSession()).toEqual({ id: "abc", token: "secret" });
});

test("clears both values", () => {
  saveSession({ id: "abc", token: "secret" });
  clearSession();

  expect(readSession()).toBeNull();
});

test("stores only in sessionStorage, not localStorage or cookies", () => {
  saveSession({ id: "abc", token: "secret" });

  expect(window.sessionStorage.length).toBeGreaterThan(0);
  expect(window.localStorage.length).toBe(0);
  expect(document.cookie).toBe("");
});

test("reading returns nothing when only part of the pair is stored", () => {
  window.sessionStorage.setItem("osa.session", JSON.stringify({ id: "abc" }));
  expect(readSession()).toBeNull();

  window.sessionStorage.setItem("osa.session", "not json");
  expect(readSession()).toBeNull();
});

test("tokenFor returns the token only for the stored ID", () => {
  saveSession({ id: "abc", token: "secret" });

  expect(tokenFor("abc")).toBe("secret");
  expect(tokenFor("other")).toBeNull();
});

test("behaves as nothing stored when sessionStorage throws", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("blocked");
  });

  expect(() => saveSession({ id: "abc", token: "secret" })).not.toThrow();
  expect(readSession()).toBeNull();
  expect(tokenFor("abc")).toBeNull();
  expect(() => clearSession()).not.toThrow();
});
