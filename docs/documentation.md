# Documentation guidelines

Where documentation goes, what belongs in it, and how it stays true.

## Where a document goes

| Place | For |
| --- | --- |
| [README.md](../README.md) | What the project is and how to install, configure and run it. Nothing else. |
| `docs/` | General and cross-module documentation: anything about more than one module, or about none (what the tools show, the definitions, the architecture, how to contribute, these guidelines). |
| `<folder>/<folder>.md` | A module documents itself, in its own folder, in a file named after the folder: `analysis/analysis.md`, `web/web.md`. |
| next to the module doc | Further docs about one feature of that module, e.g. `analysis/schedule-scoring.md`. Link them from the module doc. |
| [AGENTS.md](../AGENTS.md) | The entry point for coding agents. It points here and holds no knowledge of its own. |

The `<folder>/<folder>.md` rule works at any depth. A subfolder without
its own doc is covered by the doc of the folder above it.

### Which folders have a module doc

- Every layer: each package directly under `src/fantasy_nhl`, plus `web/`
  and `tests/`. A package that only groups other packages (`sources`) is
  covered by the docs of those.
- A subfolder gets its own doc once the doc above it can no longer
  describe it with one table row per file: it has grown past a handful of
  files, or it has concepts of its own. Then its files move out of the
  parent's table.
- Modules directly in the package (`config.py`, `plots.py`) are described
  in [architecture.md](architecture.md).

## One home per fact

Write a fact once, where it belongs, and link to it from elsewhere. Two
copies drift apart.

| Kind of fact | Home |
| --- | --- |
| What a function does, its parameters and result | Its docstring |
| Why a line is the way it is | A comment on that line |
| How a module is organized, its rules, concepts and pitfalls | Its module doc |
| What the user sees; the definitions behind the numbers | [tools.md](tools.md), [methodology.md](methodology.md) |
| How the modules fit together | [architecture.md](architecture.md) |
| How to do a task that spans modules | [contributing.md](contributing.md) |

## A module doc

Sections, in this order; leave one out if it has nothing to say.

1. **Title and purpose.** The folder's name as title, then two to four
   sentences: what the module is for.
2. **Boundaries.** What it may import and what it must not; what it never
   does. This is what keeps the layers apart.
3. **Layout.** A table with one row per source file and what it holds. It
   names every `.py`, `.ts` and `.tsx` file of the folder, and of its
   subfolders that have no doc of their own.
4. **Key concepts.** The ideas someone needs to read the code, in the
   words the code uses.
5. **Extending.** How to add the typical thing (a view, an endpoint, a
   page).
6. **Gotchas.** What has gone wrong before and is not obvious from the
   code.
7. **Tests.** Where the module is tested.

A module doc that grows much past 150 lines usually contains a feature
doc: move that part into its own file next to it.

## Writing

- Describe what is, in the present tense. How it came to be is in the git
  history.
- Give the reason with the rule. A rule without its reason gets broken by
  the first person it inconveniences.
- Call things what the code calls them, in backticks.
- Link files and other docs with relative links. They work in the editor,
  on GitHub and on every branch.
- Do not link to line numbers; they move.
- Keep examples short and real: copy them from the code, or run them.
- Wrap prose at about 75 columns, like the existing docs.

## Keeping it true

Change the documentation in the same commit as the code:

| When you | Update |
| --- | --- |
| add, rename or remove a source file | the Layout table of its module doc |
| change a rule, a concept or a pitfall of a module | its module doc |
| change what a tool shows or how a number is defined | [tools.md](tools.md) or [methodology.md](methodology.md) |
| add a layer, or change what may import what | [architecture.md](architecture.md) and `tests/test_layering.py` |
| add a folder | decide with the rules above whether it needs a doc |

[tests/test_docs.py](../tests/test_docs.py) checks what a machine can:

1. Every relative link in a Markdown file leads to a file that exists,
   and every `#anchor` into a Markdown file to a heading that exists.
2. Every layer has its `<folder>/<folder>.md`.
3. Every module doc names every source file it covers.

Whether the text is still right is checked by whoever reviews the change.
