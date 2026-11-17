import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  apiUrl,
  request,
  type Block,
  type Note,
  type Params,
  type Row,
  type Table,
  type View,
} from "../api";
import { useSession } from "../session";
import { toneClasses, toneColor } from "../tone";

/** A view of the current league; ``params`` are its query parameters.
 * While another choice loads, the previous view stays on screen. */
export function useView<V extends View = View>(
  path: string,
  params: Params = {},
  enabled = true,
) {
  const { meta } = useSession();
  const url = apiUrl(`/leagues/${meta.id}${path}`, params);
  return useQuery({
    queryKey: [url],
    queryFn: () => request<V>(url),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** The meta of the view that was asked for: none while a previous view
 * stands in for it, whose choices would not fit. */
export function currentMeta<M>(query: {
  data?: { meta: M };
  isPlaceholderData: boolean;
}): M | undefined {
  return query.isPlaceholderData ? undefined : query.data?.meta;
}

type ViewQuery = {
  data?: View;
  error: Error | null;
  isFetching: boolean;
};

/** A fetched view with its loading and error states. */
export function ViewPanel({
  query,
  pageSize,
  hidden,
}: {
  query: ViewQuery;
  pageSize?: number;
  hidden?: Set<Block>;
}) {
  if (query.error) {
    return <p className="note note-warning">{query.error.message}</p>;
  }
  if (!query.data) return <p className="note note-info">Loading…</p>;
  return (
    <div className={query.isFetching ? "view stale" : "view"}>
      <ViewBlocks view={query.data} pageSize={pageSize} hidden={hidden} />
    </div>
  );
}

const noteKey = (note: Note) => JSON.stringify([note.level, note.spans]);

/** The notes of a view by content: whether each leads its tables. */
function notesOf(view?: View): Map<string, boolean> {
  const blocks = view?.blocks ?? [];
  const table = blocks.findIndex((block) => block.type === "table");
  const notes = new Map<string, boolean>();
  blocks.forEach((block, index) => {
    if (block.type === "note") notes.set(noteKey(block), table < 0 || index < table);
  });
  return notes;
}

/** Views on one page, the first on top. A note that two of them carry
 * word for word is shown once: where the upper view has it when it leads
 * the lower one (a warning), else where the lower view has it (a legend). */
export function ViewStack({ queries }: { queries: ViewQuery[] }) {
  const notes = queries.map((query) => notesOf(query.error ? undefined : query.data));
  return (
    <>
      {queries.map((query, index) => {
        const repeated = (block: Block) =>
          block.type === "note" &&
          notes.some((other, at) => {
            const leads = other.get(noteKey(block));
            if (leads === undefined || at === index) return false;
            return at > index ? !leads : notes[index].get(noteKey(block));
          });
        const hidden = new Set(query.data?.blocks.filter(repeated));
        return <ViewPanel key={index} query={query} hidden={hidden} />;
      })}
    </>
  );
}

/** Shorthand for a view that needs no further handling. */
export function RemoteView(props: {
  path: string;
  params?: Params;
  pageSize?: number;
}) {
  const query = useView(props.path, props.params);
  return <ViewPanel query={query} pageSize={props.pageSize} />;
}

export function ViewBlocks({
  view,
  pageSize,
  hidden,
}: {
  view: View;
  pageSize?: number;
  hidden?: Set<Block>;
}) {
  return (
    <>
      {view.blocks.map(
        (block, index) =>
          !hidden?.has(block) && <BlockView key={index} block={block} pageSize={pageSize} />,
      )}
    </>
  );
}

function BlockView({ block, pageSize }: { block: Block; pageSize?: number }) {
  switch (block.type) {
    case "table":
      return <DataTable key={block.title} table={block} pageSize={pageSize} />;
    case "note":
      return <NoteView note={block} />;
    case "text":
      return <CopyText text={block.text} />;
    case "figure":
      // the address changes with the content, so the browser may keep it
      return <img className="figure" src={block.url} alt={block.title} />;
  }
}

function NoteView({ note }: { note: Note }) {
  const spaced = note.space_before ? " spaced" : "";
  return (
    <p className={`note note-${note.level}${spaced}`}>
      {note.spans.map((span, index) => (
        <span key={index} className={toneClasses(span.tone)}>
          {span.text}
        </span>
      ))}
    </p>
  );
}

function CopyText({ text }: { text: string }) {
  const [state, setState] = useState<"" | "copied" | "failed">("");
  const copy = () =>
    // absent or refused where the page may not use the clipboard
    (navigator.clipboard?.writeText(text) ?? Promise.reject()).then(
      () => setState("copied"),
      () => setState("failed"),
    );
  return (
    <div className="copy">
      <pre>{text}</pre>
      <button onClick={copy}>{state === "copied" ? "Copied" : "Copy"}</button>
      {state === "failed" && (
        <span className="note-warning">
          Copying is not allowed here: select the text instead.
        </span>
      )}
    </div>
  );
}

type Sort = { table: Table; column: number; descending: boolean };

/** The rows ordered by a column: blank cells last, equal ones as they came. */
function sortRows(table: Table, { column, descending }: Sort): Row[] {
  const numeric = table.columns[column].type === "number";
  const blank = ({ cells }: Row) =>
    numeric ? cells[column].value === null : cells[column].text === "";
  const compare = (a: Row, b: Row) =>
    numeric
      ? Number(a.cells[column].value) - Number(b.cells[column].value)
      : a.cells[column].text.localeCompare(b.cells[column].text, undefined, {
          sensitivity: "base",
        });
  return [...table.rows].sort((a, b) =>
    blank(a) || blank(b)
      ? Number(blank(a)) - Number(blank(b))
      : descending
        ? compare(b, a)
        : compare(a, b),
  );
}

function DataTable({ table, pageSize }: { table: Table; pageSize?: number }) {
  const [limit, setLimit] = useState(pageSize);
  const [sort, setSort] = useState<Sort | null>(null);
  // a table that arrives anew is in the order the tool gave it
  if (sort && sort.table !== table) setSort(null);
  const active = sort?.table === table ? sort : null;
  const rows = active ? sortRows(table, active) : table.rows;
  const sortBy = (column: number) =>
    setSort({
      table,
      column,
      descending:
        active?.column === column
          ? !active.descending
          : table.columns[column].type === "number",
    });
  const shown = limit ?? table.rows.length;
  const cells = (row: Row) =>
    row.cells.map((cell, index) => {
      const { align, key } = table.columns[index];
      return typeof cell.tone === "number" ? (
        <td
          key={key}
          className={`${align} graded`}
          style={{ background: toneColor(cell.tone) }}
        >
          {cell.text}
        </td>
      ) : (
        <td key={key} className={`${align} ${toneClasses(cell.tone)}`}>
          {cell.text}
        </td>
      );
    });
  return (
    <figure className="table">
      <figcaption>{table.title}</figcaption>
      <div className="scroll">
        <table aria-label={table.title}>
          <thead>
            <tr>
              <th scope="col" className="right">
                {table.columns.some((column) => column.sortable) ? (
                  <button type="button" title="Original order" onClick={() => setSort(null)}>
                    #
                  </button>
                ) : (
                  "#"
                )}
              </th>
              {table.columns.map((column, index) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`${column.align} ${column.muted ? "tone-muted" : ""}`}
                  aria-sort={
                    active?.column !== index
                      ? undefined
                      : active.descending
                        ? "descending"
                        : "ascending"
                  }
                >
                  {column.sortable ? (
                    <button type="button" onClick={() => sortBy(index)}>
                      {column.name}
                    </button>
                  ) : (
                    column.name
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, shown).map((row, index) => (
              <tr key={index}>
                <td className="right label">{row.label}</td>
                {cells(row)}
              </tr>
            ))}
          </tbody>
          {table.footer.length > 0 && (
            <tfoot>
              {table.footer.map((row, index) => (
                <tr key={index}>
                  <td className="right label">{row.label}</td>
                  {cells(row)}
                </tr>
              ))}
            </tfoot>
          )}
        </table>
      </div>
      {shown < table.rows.length && (
        <button onClick={() => setLimit(shown + (pageSize ?? shown))}>
          Show more ({table.rows.length - shown} left)
        </button>
      )}
    </figure>
  );
}
