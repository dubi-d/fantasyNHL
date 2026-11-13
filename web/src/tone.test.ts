import { expect, test } from "vitest";

import { apiUrl } from "./api";
import { toneClasses, toneColor } from "./tone";

test("diverging tones follow the terminal gradient", () => {
  expect(toneColor(0)).toBe("rgb(60,60,60)");
  expect(toneColor(1)).toBe("rgb(0,135,0)");
  expect(toneColor(-1)).toBe("rgb(175,0,0)");
  expect(toneColor(0.5)).toBe("rgb(30,98,30)");
  expect(toneColor(-3)).toBe("rgb(175,0,0)");
});

test("tags become classes", () => {
  expect(toneClasses("muted danger")).toBe("tone-muted tone-danger");
  expect(toneClasses(null)).toBe("");
});

test("api addresses skip empty parameters and repeat lists", () => {
  expect(
    apiUrl("/leagues/a/streaming/plan", {
      team: 0,
      week: null,
      sort: "",
      streamers: ["Ann B", "Cy"],
    }),
  ).toBe("/api/leagues/a/streaming/plan?team=0&streamers=Ann+B&streamers=Cy");
  expect(apiUrl("/leagues")).toBe("/api/leagues");
});
