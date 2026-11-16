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
}: {
  query: ViewQuery;
  pageSize?: number;
}) {
  if (query.error) {
    return <p className="note note-warning">{query.error.message}</p>;
  }
  if (!query.data) return <p className="note note-info">Loading…</p>;
  return (
    <div className={query.isFetching ? "view stale" : "view"}>
      <ViewBlocks view={query.data} pageSize={pageSize} />
    </div>
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

export function ViewBlocks({ view, pageSize }: { view: View; pageSize?: number }) {
  return (
    <>
      {view.blocks.map((block, index) => (
        <BlockView key={index} block={block} pageSize={pageSize} />
      ))}
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

function DataTable({ table, pageSize }: { table: Table; pageSize?: number }) {
  const [limit, setLimit] = useState(pageSize);
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
                #
              </th>
              {table.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`${column.align} ${column.muted ? "tone-muted" : ""}`}
                >
                  {column.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.slice(0, shown).map((row, index) => (
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
