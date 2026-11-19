// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import {
  errorText,
  type LeagueMeta,
  type Note,
  type PlanView,
  type Table,
  type View,
} from "./api";
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

/** A table typed as the backend does: a column of numbers is a number
 * column. ``unsortable`` names the columns that do not sort. */
function table(
  title: string,
  names: string[],
  rows: (string | number | null)[][],
  unsortable: string[] = [],
): Table {
  return {
    type: "table",
    key: "",
    title,
    columns: names.map((name, index) => ({
      key: name,
      name,
      type:
        rows.length > 0 && rows.every((row) => typeof (row[index] ?? 0) === "number")
          ? "number"
          : "text",
      align: "left",
      muted: false,
      sortable: !unsortable.includes(name),
    })),
    rows: rows.map((cells, index) => ({
      label: String(index + 1),
      cells: cells.map((value) => ({ text: String(value ?? ""), value, tone: null })),
    })),
    footer: [],
  };
}

function plan(team: string, ids: number[], extra: Partial<PlanView["meta"]> = {}): PlanView {
  return {
    blocks: [
      table(
        `Roster of ${team}`,
        ["Player"],
        ids.map((id) => [`${team} ${id}`]),
        ["Player"],
      ),
    ],
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

/** Open the app at an address; ``staleTime`` as the real app has one. */
function open(address: string, staleTime = 0) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
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

const tableOf = (title: string) => within(screen.getByRole("table", { name: title }));

/** A column of a table's body as shown, top to bottom (0 is the # column). */
function shown(title: string, column: number) {
  const body = (screen.getByRole("table", { name: title }) as HTMLTableElement).tBodies[0];
  return [...body.rows].map((row) => row.cells[column].textContent);
}

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
    blocks: [
      table(
        "Candidates",
        ["Player", "Fit"],
        Array.from({ length: 20 }, (_, i) => [`Free ${i + 1}`, i]),
      ),
    ],
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
  // a sort orders all the candidates, not the ones shown
  fireEvent.click(screen.getByRole("button", { name: "Fit" }));
  expect(shown("Candidates", 1)[0]).toBe("Free 20");
  expect(screen.queryByText("Free 5")).toBeNull();
  fireEvent.click(screen.getByText("Show more (5 left)"));
  expect(screen.getByText("Free 5")).toBeTruthy();
});

test("a click on a header sorts the table, one on # restores its order", async () => {
  const standings = table(
    "Standings",
    ["Player", "Luck"],
    [
      ["bravo", 0.1],
      ["Alpha", null],
      ["Charlie", 0.5],
      ["Delta", 0.1],
    ],
  );
  standings.footer = [
    { label: "", cells: [{ text: "(avg)", value: "(avg)", tone: null }, { text: "9", value: 9, tone: null }] },
  ];
  serve({ ...BASICS, [`${LEAGUE}/standings/accumulated`]: { blocks: [standings] } });
  open("/test-league/standings/accumulated");
  const header = (name: string) => screen.getByRole("columnheader", { name });

  // numbers start with the largest; equal ones stay as they came, blanks last
  fireEvent.click(await screen.findByRole("button", { name: "Luck" }));
  expect(shown("Standings", 1)).toEqual(["Charlie", "bravo", "Delta", "Alpha"]);
  expect(shown("Standings", 0)).toEqual(["3", "1", "4", "2"]); // the rank stays with its row
  expect(header("Luck").getAttribute("aria-sort")).toBe("descending");
  fireEvent.click(screen.getByRole("button", { name: "Luck" }));
  expect(shown("Standings", 1)).toEqual(["bravo", "Delta", "Charlie", "Alpha"]);
  expect(header("Luck").getAttribute("aria-sort")).toBe("ascending");

  // text starts at A, in either case
  fireEvent.click(screen.getByRole("button", { name: "Player" }));
  expect(shown("Standings", 1)).toEqual(["Alpha", "bravo", "Charlie", "Delta"]);
  expect(header("Luck").getAttribute("aria-sort")).toBeNull();
  expect(screen.getByText("(avg)").closest("tfoot")).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "#" }));
  expect(shown("Standings", 1)).toEqual(["bravo", "Alpha", "Charlie", "Delta"]);
  expect(header("Player").getAttribute("aria-sort")).toBeNull();
});

test("what the tool marks does not sort", async () => {
  const grades = table("Grades", ["Player", "Kept"], [["Alpha", "1/2"]], ["Kept"]);
  const pairing = table("Pairing", ["Player", "Cats"], [["Alpha", 3]], ["Player", "Cats"]);
  serve({ ...BASICS, [`${LEAGUE}/standings/accumulated`]: { blocks: [grades, pairing] } });
  open("/test-league/standings/accumulated");

  expect(await screen.findByText("Grades")).toBeTruthy();
  expect(tableOf("Grades").getAllByRole("button").map((button) => button.textContent)).toEqual([
    "#",
    "Player",
  ]);
  expect(tableOf("Pairing").queryAllByRole("button")).toEqual([]);
});

test("a table that arrives changed is back in the tool's order", async () => {
  let luck = 0.1;
  const asked = serve({
    ...BASICS,
    [`${LEAGUE}/reload`]: {},
    [`${LEAGUE}/standings/luck`]: () => ({
      blocks: [table("Luck ranking", ["Player", "Luck"], [["Alpha", luck], ["Bravo", 0.5]])],
    }),
  });
  open("/test-league/standings/luck");
  const reloaded = async (times: number) => {
    fireEvent.click(screen.getByText("Reload from ESPN"));
    await waitFor(() => {
      expect(asked.filter((url) => url.endsWith("/standings/luck"))).toHaveLength(times + 1);
      expect(document.querySelector(".view.stale")).toBeNull();
    });
  };

  fireEvent.click(await screen.findByRole("button", { name: "Luck" }));
  expect(shown("Luck ranking", 1)).toEqual(["Bravo", "Alpha"]);
  await reloaded(1); // with the same answer
  expect(shown("Luck ranking", 1)).toEqual(["Bravo", "Alpha"]);
  luck = 0.2;
  await reloaded(2);
  expect(shown("Luck ranking", 2)).toEqual(["0.2", "0.5"]);
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

const REVIEW_OPTIONS = {
  drafted: true,
  players: [
    { id: 7, label: "Sniper (C, Alpha)", goalie: false },
    { id: 8, label: "Grinder (LW, Bravo)", goalie: false },
  ],
  groups: [],
  cells: [
    { key: "pct", label: "Percentiles" },
    { key: "rate", label: "Per-game rates" },
  ],
};
const RANKING = `${LEAGUE}/review/leaders?stats=blended&scope=all&group=F&sort=Score&cells=pct`;

function note(text: string, level = "info"): Note {
  return { type: "note", level, space_before: false, spans: [{ text, tone: null }] };
}

/** The table titles and notes of the page, top to bottom. */
const outline = () =>
  [...document.querySelectorAll("main figcaption, main p.note")].map(
    (element) => element.textContent,
  );

test("players, roster, draft recap and transactions are pages of their own", async () => {
  const titled = (title: string) => ({ blocks: [table(title, [], [])] });
  serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: REVIEW_OPTIONS,
    [RANKING]: titled("Top forwards"),
    [`${LEAGUE}/review/outlook?stats=blended`]: titled("Outlook"),
    [`${LEAGUE}/review/origins?stats=blended`]: titled("Origins"),
    [`${LEAGUE}/review/draft-grades?stats=blended`]: titled("Grades"),
    [`${LEAGUE}/review/draft-return?stats=blended`]: titled("Hits"),
    [`${LEAGUE}/review/pickups?stats=blended`]: titled("Pickups"),
    [`${LEAGUE}/review/trades?stats=blended`]: titled("Trades"),
  });
  open("/test-league/players");
  const choose = (view: string) =>
    fireEvent.change(screen.getByLabelText("View"), { target: { value: view } });
  const views = () =>
    [...(screen.getByLabelText("View") as HTMLSelectElement).options].map(
      (option) => option.text,
    );

  expect(await screen.findByRole("table", { name: "Top forwards" })).toBeTruthy();
  expect(views()).toEqual(["Player ranking", "Compare players"]);

  fireEvent.click(screen.getByRole("link", { name: "Roster" }));
  await waitFor(() => expect(outline()).toEqual(["Outlook", "Origins"]));
  expect(address()).toBe("/test-league/roster");
  expect(views()).toEqual(["League", "One team"]);

  fireEvent.click(screen.getByRole("link", { name: "Draft recap" }));
  expect(await screen.findByRole("table", { name: "Grades" })).toBeTruthy();
  expect(views()).toEqual(["Draft grades vs ADP", "Draft hits & busts"]);
  choose("draft-return");
  expect(await screen.findByRole("table", { name: "Hits" })).toBeTruthy();
  expect(address()).toBe("/test-league/draft?view=draft-return");

  fireEvent.click(screen.getByRole("link", { name: "Transactions" }));
  expect(await screen.findByRole("table", { name: "Pickups" })).toBeTruthy();
  expect(views()).toEqual(["Waiver pickups", "Trade haul"]);
  choose("trades");
  expect(await screen.findByRole("table", { name: "Trades" })).toBeTruthy();
});

test("the roster page stacks two views and says a shared note once", async () => {
  const warning = note("No stats this season", "warning");
  const legend = note("Score legend");
  const drafted = { blocks: [warning, table("Alpha picks", [], []), note("Value legend")] };
  const emptied = { blocks: [note("Bravo has an empty roster.", "warning")] };
  serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: REVIEW_OPTIONS,
    [`${LEAGUE}/review/outlook?stats=blended`]: {
      blocks: [warning, table("Outlook", [], []), note("Outlook legend")],
    },
    [`${LEAGUE}/review/origins?stats=blended`]: {
      blocks: [warning, table("Origins", [], []), legend],
    },
    [`${LEAGUE}/review/team?stats=blended&team=0&cells=pct`]: {
      blocks: [warning, table("Alpha roster", [], []), legend],
    },
    [`${LEAGUE}/review/team?stats=blended&team=0&cells=pct&source=draft`]: drafted,
    [`${LEAGUE}/review/gaps?stats=blended&team=0&cells=pct`]: {
      blocks: [warning, table("Drops", [], []), table("Free agents", [], []), legend],
    },
    [`${LEAGUE}/review/team?stats=blended&team=0&cells=rate&source=draft`]: {
      blocks: [table("Alpha picks per game", [], [])],
    },
    [`${LEAGUE}/review/gaps?stats=blended&team=0&cells=rate`]: {
      blocks: [table("Drops per game", [], [])],
    },
    [`${LEAGUE}/review/team?stats=blended&team=1&cells=rate`]: emptied,
    [`${LEAGUE}/review/gaps?stats=blended&team=1&cells=rate`]: emptied,
  });
  open("/test-league/roster");
  const choose = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const shows = (...expected: string[]) =>
    waitFor(() => {
      expect(outline()).toEqual(expected);
      expect(document.querySelector(".view.stale")).toBeNull();
    });

  // the warning stays on top, each view keeps the legend only it has
  await shows("No stats this season", "Outlook", "Outlook legend", "Origins", "Score legend");

  // the legend of both views closes the page
  choose("View", "team");
  await shows("No stats this season", "Alpha roster", "Drops", "Free agents", "Score legend");
  expect(address()).toBe("/test-league/roster?view=team");

  // only the upper view follows the rosters choice
  choose("Rosters", "draft");
  await shows(
    "No stats this season",
    "Alpha picks",
    "Value legend",
    "Drops",
    "Free agents",
    "Score legend",
  );

  // one team's tables carry the ranking's columns: both follow their cells
  choose("Cells show", "rate");
  await shows("Alpha picks per game", "Drops per game");
  expect(address()).toBe("/test-league/roster?view=team&source=draft&cells=rate");

  // what both views say instead of tables is said once
  choose("Rosters", "current");
  choose("Team", "1");
  await shows("Bravo has an empty roster.");
});

test("stacked views load and fail as one", async () => {
  const failed = () =>
    Response.json({ detail: "The request to ESPN failed (Timeout)." }, { status: 502 });
  let answer = (_: unknown) => {};
  const asked = serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: () =>
      new Promise((resolve) => (answer = resolve)),
    [`${LEAGUE}/review/origins?stats=blended`]: { blocks: [table("Origins", [], [])] },
    [`${LEAGUE}/review/outlook?stats=blended&source=draft`]: failed,
    [`${LEAGUE}/review/team?stats=blended&team=0&cells=pct&source=draft`]: failed,
    [`${LEAGUE}/review/gaps?stats=blended&team=0&cells=pct`]: failed,
  });
  open("/test-league/roster?source=draft");

  // the linked rosters as drafted wait to hear that there was a draft
  await waitFor(() => expect(outline()).toEqual(["Loading…", "Origins"]));
  expect(asked).not.toContain(`${LEAGUE}/review/outlook?stats=blended`);
  answer(REVIEW_OPTIONS);
  await waitFor(() =>
    expect(outline()).toEqual(["The request to ESPN failed (Timeout).", "Origins"]),
  );

  fireEvent.change(screen.getByLabelText("View"), { target: { value: "team" } });
  await waitFor(() => expect(outline()).toEqual(["The request to ESPN failed (Timeout)."]));
});

test("players: a failed options request is shown and can be retried", async () => {
  let fail = true;
  serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: () =>
      fail
        ? Response.json({ detail: "The request to ESPN failed (Timeout)." }, { status: 502 })
        : REVIEW_OPTIONS,
  });
  open("/test-league/players?view=compare");

  expect(await screen.findByText("The request to ESPN failed (Timeout).")).toBeTruthy();
  expect(screen.queryByText("Pick two to four skaters or goalies.")).toBeNull();
  fail = false;
  fireEvent.click(screen.getByText("Try again"));
  expect(await screen.findByText("Pick two to four skaters or goalies.")).toBeTruthy();

  // picking a player puts its id into the address
  fireEvent.change(screen.getByLabelText("Add a player"), {
    target: { value: "Sniper (C, Alpha)" },
  });
  expect(address()).toBe("/test-league/players?view=compare&players=7");
  expect(screen.getByRole("button", { name: "Sniper (C, Alpha) ×" })).toBeTruthy();
});

test("players: a comparison asks for the ranking's rows in the cells chosen", async () => {
  const compared = `${LEAGUE}/review/compare?stats=blended&players=7&players=8`;
  serve({
    ...BASICS,
    [`${LEAGUE}/review/options?stats=blended`]: REVIEW_OPTIONS,
    [`${compared}&cells=pct`]: { blocks: [table("Percentiles", [], [])] },
    [`${compared}&cells=rate`]: { blocks: [table("Per game", [], [])] },
  });
  open("/test-league/players?view=compare&players=7&players=8");

  expect(await screen.findByRole("table", { name: "Percentiles" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Cells show"), { target: { value: "rate" } });
  expect(await screen.findByRole("table", { name: "Per game" })).toBeTruthy();
  expect(address()).toBe("/test-league/players?view=compare&players=7&players=8&cells=rate");
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

const HISTORY_OPTIONS = {
  seasons: ["2023-24", "2024-25", "2025-26"],
  players: [
    { id: 1, label: "Alex Center (C, EDM)" },
    { id: 6, label: "Gus Goalie (G, WPG)" },
  ],
};
const historyOf = (player: number, columns: string, cells: string) =>
  `/api/history/player?player=${player}&columns=${columns}&cells=${cells}`;
const seasons = (title: string) => ({ blocks: [table(title, ["Season"], [["2025-26"]])] });
/** A view as the page asks for it: without and with the current season. */
const twice = (url: string, view: View) => ({ [url]: view, [`${url}&current=true`]: view });

test("history: no league is asked for, the choices are in the address", async () => {
  const asked = serve({
    "/api/leagues": LEAGUES,
    "/api/history/players": HISTORY_OPTIONS,
    ...twice(historyOf(1, "fantasy", "total"), seasons("Alex, totals")),
    ...twice(historyOf(1, "fantasy", "rate"), seasons("Alex, per game")),
    ...twice(historyOf(6, "fantasy", "rate"), seasons("Gus, per game")),
    ...twice(historyOf(6, "all", "rate"), seasons("Gus, everything per game")),
  });
  open("/history?player=1");
  expect(await screen.findByText("Alex, totals")).toBeTruthy();
  const player = () => screen.getByLabelText("Player") as HTMLInputElement;
  expect(player().value).toBe("Alex Center (C, EDM)");
  expect(asked.filter((url) => url.startsWith("/api/leagues/"))).toEqual([]);
  // what belongs to a loaded league is not offered
  expect(screen.queryByLabelText("Player stats")).toBeNull();
  expect(screen.queryByText("Reload from ESPN")).toBeNull();

  fireEvent.change(screen.getByLabelText("Cells show"), { target: { value: "rate" } });
  expect(await screen.findByText("Alex, per game")).toBeTruthy();
  expect(address()).toBe("/history?player=1&cells=rate");

  // a name is taken once it is one of the list
  fireEvent.change(player(), { target: { value: "Gus" } });
  expect(address()).toBe("/history?player=1&cells=rate");
  fireEvent.change(player(), { target: { value: "Gus Goalie (G, WPG)" } });
  expect(await screen.findByText("Gus, per game")).toBeTruthy();
  expect(address()).toBe("/history?cells=rate&player=6");

  fireEvent.change(screen.getByLabelText("Columns"), { target: { value: "all" } });
  expect(await screen.findByText("Gus, everything per game")).toBeTruthy();
  expect(address()).toBe("/history?cells=rate&player=6&columns=all");
  fireEvent.change(screen.getByLabelText("Columns"), { target: { value: "fantasy" } });
  expect(address()).toBe("/history?cells=rate&player=6");
});

test("history: the current season joins the stored ones and can be refreshed", async () => {
  const stored = historyOf(1, "fantasy", "total");
  const refresh = "/api/history/current/refresh";
  let arrive = () => {};
  const download = new Promise<void>((resolve) => (arrive = resolve));
  let downloads = 0;
  let reachable = true;
  const unreachable = () =>
    Response.json(
      { detail: "Unable to read 'season' from the NHL stats API." },
      { status: 502 },
    );
  serve({
    "/api/leagues": LEAGUES,
    "/api/history/players": HISTORY_OPTIONS,
    [stored]: seasons("Alex, stored"),
    [`${stored}&current=true`]: async () => {
      await download;
      return reachable ? seasons(`Alex, download ${downloads}`) : unreachable();
    },
    [refresh]: () => {
      if (!reachable) return unreachable();
      downloads += 1;
      return { season: "2026-27", loaded_at: "2026-11-19T14:05:00+01:00" };
    },
  });
  open("/history?player=1");
  // the stored seasons do not wait for the NHL
  expect(await screen.findByText("Alex, stored")).toBeTruthy();
  expect(screen.getByText("Reading the current season…")).toBeTruthy();
  arrive();
  expect(await screen.findByText("Alex, download 0")).toBeTruthy();
  expect(screen.queryByText("Alex, stored")).toBeNull();
  expect(screen.queryByText("Reading the current season…")).toBeNull();

  fireEvent.click(screen.getByText("Refresh current season"));
  expect(await screen.findByText("Alex, download 1")).toBeTruthy();
  const sent = vi.mocked(fetch).mock.calls.find(([url]) => url === refresh);
  expect(sent?.[1]?.method).toBe("POST");

  reachable = false;
  fireEvent.click(screen.getByText("Refresh current season"));
  expect(
    await screen.findByText("Unable to read 'season' from the NHL stats API."),
  ).toBeTruthy();
  expect(screen.getByText("Alex, download 1")).toBeTruthy();
  cleanup();

  // a view with the current season that fails leaves the stored seasons
  open("/history?player=1");
  expect(
    await screen.findByText(
      "The current season is not shown: Unable to read 'season' from the NHL stats API.",
    ),
  ).toBeTruthy();
  expect(screen.getByText("Alex, stored")).toBeTruthy();
});

test("history and a league's pages lead to each other, the league is loaded once", async () => {
  const asked = serve({
    ...BASICS,
    "/api/history/players": HISTORY_OPTIONS,
    [`${LEAGUE}/standings/luck`]: { blocks: [table("Luck here", ["Player"], [])] },
  });
  const luck = () => screen.getByText("Luck ranking").getAttribute("href");
  open("/test-league/standings/luck", 60_000);
  expect(await screen.findByText("Luck here")).toBeTruthy();

  fireEvent.click(screen.getByText("Player history"));
  expect(await screen.findByText(/Pick a player .* 2023-24 to 2025-26/)).toBeTruthy();
  expect(address()).toBe("/history");
  // the menu leads back into the league that was open
  expect(luck()).toBe("/test-league/standings/luck");
  fireEvent.click(screen.getByText("Luck ranking"));
  expect(await screen.findByText("Luck here")).toBeTruthy();
  expect(screen.getByText("Reload from ESPN")).toBeTruthy();
  expect(asked.filter((url) => url === LEAGUE)).toHaveLength(1);

  // on the history page another league only changes where the menu leads
  fireEvent.click(screen.getByText("Player history"));
  fireEvent.change(screen.getByLabelText("League"), { target: { value: "old-league" } });
  expect(address()).toBe("/history");
  expect(luck()).toBe("/old-league/standings/luck");
  expect(asked).not.toContain("/api/leagues/old-league");
});

test("history: reachable without ESPN and without leagues, its problems are said", async () => {
  serve({
    "/api/leagues": LEAGUES,
    [LEAGUE]: () =>
      Response.json({ detail: "The request to ESPN failed (Timeout)." }, { status: 502 }),
    "/api/history/players": { seasons: [], players: [] },
  });
  open("/test-league/standings/luck");
  expect(await screen.findByText("The request to ESPN failed (Timeout).")).toBeTruthy();
  fireEvent.click(screen.getByText("Player history"));
  expect(await screen.findByText(/No NHL seasons are stored yet/)).toBeTruthy();
  expect(screen.queryByLabelText("Player")).toBeNull();
  cleanup();

  let broken = true;
  serve({
    "/api/leagues": [],
    "/api/history/players": () =>
      broken
        ? Response.json({ detail: "'season_20252026.csv' cannot be read." }, { status: 500 })
        : HISTORY_OPTIONS,
  });
  open("/history");
  expect(await screen.findByText("'season_20252026.csv' cannot be read.")).toBeTruthy();
  expect(screen.queryByLabelText("League")).toBeNull();
  broken = false;
  fireEvent.click(screen.getByText("Try again"));
  expect(await screen.findByText(/Pick a player/)).toBeTruthy();
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
