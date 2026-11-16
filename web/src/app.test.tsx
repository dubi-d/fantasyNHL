// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { errorText, type LeagueMeta, type PlanView, type Table, type View } from "./api";
import { App } from "./App";
import { SessionProvider } from "./session";

const LEAGUE = "/api/leagues/test-league";
const LEAGUES = [
  { id: "old-league", name: "Old League", year: 2026, default: false },
  { id: "test-league", name: "Test League", year: 2027, default: true },
];
const META: LeagueMeta = {
  ...LEAGUES[1],
  teams: ["Alpha", "Bravo"],
  current_week: 5,
  completed_matchups: 4,
  weeks: [1, 2, 3, 4, 5, 6].map((week) => ({
    week,
    label: `Matchup ${week}`,
    completed: week <= 4,
  })),
  categories: [],
  calibration: null,
  loaded_at: "2026-11-13T09:05:00+01:00",
  warnings: [],
};

function table(title: string, names: string[], rows: (string | number)[][]): Table {
  return {
    type: "table",
    key: "",
    title,
    columns: names.map((name) => ({
      key: name,
      name,
      type: "text",
      align: "left",
      muted: false,
    })),
    rows: rows.map((cells, index) => ({
      label: String(index + 1),
      cells: cells.map((value) => ({ text: String(value), value, tone: null })),
    })),
    footer: [],
  };
}

function plan(team: string, ids: number[], extra: Partial<PlanView["meta"]> = {}): PlanView {
  return {
    blocks: [table(`Roster of ${team}`, ["Player"], ids.map((id) => [`${team} ${id}`]))],
    meta: {
      roster: ids.map((id) => ({ id, name: `${team} ${id}` })),
      days: [],
      finished: false,
      has_open_days: false,
      ...extra,
    },
  };
}

type Answer = unknown | (() => unknown | Promise<unknown>);

/** Answer the app's requests from a table of address -> JSON (or a
 * function giving it, or a Response); everything else is a 404. */
function serve(routes: Record<string, Answer>) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      asked.push(url);
      const answer = routes[url];
      const body = typeof answer === "function" ? await answer() : answer;
      if (body instanceof Response) return body;
      if (body === undefined) return Response.json({ detail: `no ${url}` }, { status: 404 });
      return Response.json(body);
    }),
  );
  return asked;
}

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname + location.search}</output>;
}

function open(address: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[address]}>
        <SessionProvider>
          <App />
        </SessionProvider>
        <Address />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const address = () => screen.getByTestId("address").textContent;
const BASICS = { "/api/leagues": LEAGUES, [LEAGUE]: META };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

test("a new tab opens on the default league and shows the view's blocks", async () => {
  const standings = table("Standings", ["Player", "Luck"], [["Alpha", 0.33]]);
  standings.rows[0].cells[1].tone = 1;
  standings.footer = [
    { label: "", cells: [{ text: "(avg)", value: "(avg)", tone: null }, { text: "0", value: 0, tone: null }] },
  ];
  const view: View = {
    blocks: [
      standings,
      { type: "note", level: "info", space_before: false, spans: [{ text: "A legend", tone: "strong" }] },
      { type: "figure", kind: "power_rankings", title: "Form", url: `${LEAGUE}/x/figures/0.png?v=abc`, data: {} },
    ],
  };
  serve({ ...BASICS, [`${LEAGUE}/standings/accumulated`]: view });
  open("/");

  expect(await screen.findByText("Standings")).toBeTruthy();
  expect(address()).toBe("/test-league/standings/accumulated");
  expect(screen.getByRole("columnheader", { name: "Luck" })).toBeTruthy();
  expect(screen.getByText("0.33").style.background).toBe("rgb(0, 135, 0)");
  expect(screen.getByText("(avg)").closest("tfoot")).toBeTruthy();
  expect(screen.getByText("A legend").className).toBe("tone-strong");
  // the address of a figure carries its content mark: no cache busting here
  expect(screen.getByAltText("Form").getAttribute("src")).toBe(
    `${LEAGUE}/x/figures/0.png?v=abc`,
  );
  const loaded = new Date(META.loaded_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  expect(screen.getByText(`as of ${loaded}`)).toBeTruthy();
  expect(sessionStorage.getItem("league")).toBe("test-league");
});

test("old addresses and the league switch keep the page", async () => {
  serve({
    ...BASICS,
    "/api/leagues/old-league": { ...META, ...LEAGUES[0] },
    [`${LEAGUE}/standings/luck`]: { blocks: [table("Luck here", ["Player"], [])] },
    "/api/leagues/old-league/standings/luck": { blocks: [table("Luck there", ["Player"], [])] },
  });
  open("/standings/luck");
  expect(await screen.findByText("Luck here")).toBeTruthy();
  expect(address()).toBe("/test-league/standings/luck");

  fireEvent.change(screen.getByLabelText("League"), { target: { value: "old-league" } });
  expect(await screen.findByText("Luck there")).toBeTruthy();
  expect(address()).toBe("/old-league/standings/luck");
});

test("the planner never offers the roster of another team's plan", async () => {
  let answerBravo = (_: PlanView) => {};
  const bravo = new Promise<PlanView>((resolve) => (answerBravo = resolve));
  const asked = serve({
    ...BASICS,
    [`${LEAGUE}/streaming/plan?week=5&team=0`]: plan("Alpha", [101, 102]),
    [`${LEAGUE}/streaming/plan?week=5&team=0&streamers=102`]: () =>
      new Promise((resolve) => setTimeout(() => resolve(plan("Alpha", [101, 102])), 20)),
    [`${LEAGUE}/streaming/plan?week=5&team=1`]: () => bravo,
  });
  open("/test-league/streaming");

  // marking a streamer: in the address, and the choices stay while it loads
  fireEvent.click(await screen.findByLabelText("Alpha 102"));
  expect(address()).toBe("/test-league/streaming?streamers=102");
  expect((screen.getByLabelText("Alpha 102") as HTMLInputElement).checked).toBe(true);
  await waitFor(() =>
    expect(asked).toContain(`${LEAGUE}/streaming/plan?week=5&team=0&streamers=102`),
  );

  // another team: its streamers start empty and nothing is offered yet
  fireEvent.change(screen.getByLabelText("Your team"), { target: { value: "1" } });
  expect(address()).toBe("/test-league/streaming?week=5&team=1");
  expect(screen.queryByLabelText("Alpha 102")).toBeNull();
  expect(screen.getByText("Roster of Alpha")).toBeTruthy(); // still on screen, dimmed
  answerBravo(plan("Bravo", [201]));
  expect(await screen.findByLabelText("Bravo 201")).toBeTruthy();
  expect(localStorage.getItem("team:test-league")).toBe("1");
});

test("a linked planner address is restored, candidates page by page", async () => {
  const candidates: View = {
    blocks: [table("Candidates", ["Player"], Array.from({ length: 20 }, (_, i) => [`Free ${i + 1}`]))],
  };
  serve({
    ...BASICS,
    [`${LEAGUE}/streaming/plan?week=2&team=1&simulate=10`]: plan("Bravo", [201], {
      finished: true,
      has_open_days: true,
      days: [{ period: 10, label: "Wed 14" }],
    }),
    [`${LEAGUE}/streaming/candidates?week=2&team=1&simulate=10&stats=blended`]: candidates,
  });
  open("/test-league/streaming?week=2&team=1&simulate=10&candidates=1");

  expect(await screen.findByText("Free 15")).toBeTruthy();
  expect((screen.getByLabelText("Matchup") as HTMLSelectElement).value).toBe("2");
  expect(
    (screen.getByLabelText("Week is over — simulate it from") as HTMLSelectElement).value,
  ).toBe("10");
  expect(screen.queryByText("Free 16")).toBeNull();
  fireEvent.click(screen.getByText("Show more (5 left)"));
  expect(screen.getByText("Free 20")).toBeTruthy();
});

test("selections follow the league after a reload", async () => {
  let completed = 4;
  const asked = serve({
    "/api/leagues": LEAGUES,
    [LEAGUE]: () => ({ ...META, completed_matchups: completed }),
    [`${LEAGUE}/reload`]: {},
    [`${LEAGUE}/standings/power-rankings?window=4`]: { blocks: [table("Window 4", [], [])] },
    [`${LEAGUE}/standings/power-rankings?window=2`]: { blocks: [table("Window 2", [], [])] },
  });
  open("/test-league/standings/power-rankings");
  expect(await screen.findByText("Window 4")).toBeTruthy();

  completed = 2; // as if another season had been loaded
  fireEvent.click(screen.getByText("Reload from ESPN"));
  expect(await screen.findByText("Window 2")).toBeTruthy();
  expect(asked).toContain(`${LEAGUE}/reload`);
});

test("review: a failed options request is shown and can be retried", async () => {
  let fail = true;
  serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: () =>
      fail
        ? Response.json({ detail: "The request to ESPN failed (Timeout)." }, { status: 502 })
        : { drafted: true, players: [{ id: 7, label: "Sniper (C, Alpha)", goalie: false }], groups: [], cells: [] },
  });
  open("/test-league/review?view=compare");

  expect(await screen.findByText("The request to ESPN failed (Timeout).")).toBeTruthy();
  expect(screen.queryByText("Pick two to four skaters or goalies.")).toBeNull();
  fail = false;
  fireEvent.click(screen.getByText("Try again"));
  expect(await screen.findByText("Pick two to four skaters or goalies.")).toBeTruthy();

  // picking a player puts its id into the address
  fireEvent.change(screen.getByLabelText("Add a player"), {
    target: { value: "Sniper (C, Alpha)" },
  });
  expect(address()).toBe("/test-league/review?view=compare&players=7");
  expect(screen.getByRole("button", { name: "Sniper (C, Alpha) ×" })).toBeTruthy();
});

test("problems are said: no leagues, a league that does not load, warnings", async () => {
  serve({ "/api/leagues": [] });
  open("/");
  expect(await screen.findByText(/No leagues are configured/)).toBeTruthy();
  cleanup();

  serve({
    "/api/leagues": LEAGUES,
    [LEAGUE]: Response.json({ detail: "The request to ESPN failed (Timeout)." }, { status: 502 }),
    "/api/leagues/old-league": {
      ...META,
      ...LEAGUES[0],
      warnings: ["ESPN's calendar could not be read: matchups have no dates."],
    },
    "/api/leagues/old-league/standings/accumulated": { blocks: [] },
  });
  open("/");
  expect(await screen.findByText("The request to ESPN failed (Timeout).")).toBeTruthy();
  // the other league stays reachable
  fireEvent.change(screen.getByLabelText("League"), { target: { value: "old-league" } });
  expect(await screen.findByText(/matchups have no dates/)).toBeTruthy();
});

test("errors of the server read as one line", () => {
  expect(errorText("Unknown league")).toBe("Unknown league");
  expect(
    errorText([
      { loc: ["query", "week"], msg: "Input should be a valid integer" },
      { loc: ["query", "team"], msg: "Field required" },
    ]),
  ).toBe("week: Input should be a valid integer; team: Field required");
});
