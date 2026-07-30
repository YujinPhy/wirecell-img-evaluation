# Coding Style Preferences

A general-purpose style guide, distilled from patterns observed consistently across
real projects rather than derived speculatively. Captures the patterns to follow, and
the ones to avoid, so new code matches this style by default instead of drifting into
a different one project by project.

## Preferred Patterns

### File / module structure
- Every module opens with a triple-quoted docstring describing its purpose, and often
  a `Structure:` or `Usage:` block showing an actual runnable invocation (env setup,
  example CLI flags) rather than an abstract description.
- Long entry-point scripts are split into commented sections with a consistent divider,
  e.g. `# ==== Section Name ====`. Used to group related functions without introducing
  submodules for what's still fundamentally one script.
- Entry-point scripts that import sibling local packages/modules fix up `sys.path` (or
  equivalent) explicitly near the top, so the script runs correctly regardless of the
  caller's current working directory.
- `if __name__ == "__main__":` block is a straight-line sequence of pipeline calls
  (parse args -> load/collect -> process -> save/report) with no unnecessary `main()`
  wrapper for small scripts.

### Docstrings
- Google-style `Args:` / `Returns:` sections, including precise nested-type
  descriptions (`tuple[str, str]`, `list[dict]`, `dict[str, list[dict]]`) even when
  the function signature itself carries no type hints.
- Docstrings explain **why**, not what: subtle invariants, unit/coordinate-system
  mismatches, "gotchas" a caller could get wrong — not a restatement of the code.
- Docstrings cross-reference sibling functions and specific doc files by name/section
  to keep code and write-ups in sync, instead of duplicating explanations.
- Mixed-language docstrings are fine when the author is bilingual: use the language
  that's most natural for higher-level workflow/analysis narrative, and the other for
  technical/API-level detail, in the same docstring rather than segregated into
  separate files.

### Naming & constants
- Global constants are `ALL_CAPS`, declared near the top of the script, each with an
  inline unit/meaning comment when the value is a physical or domain quantity (e.g.
  `TIMEOUT = 30  # [seconds]`, `MAX_RETRIES = 3`).
- Functions are named as verbs describing the transform they perform (`load_data`,
  `filter_records`, `compute_stats`, `classify_item`), not nouns.
- Module-private helpers only used within one file are prefixed with `_` and not
  exported, even if the module has no `__all__`.

### CLI / argparse
- `argparse` defaults are always the module-level constant, and the help string embeds
  that same default textually, e.g. `default=TIMEOUT, help="... (default: %.2f)" %
  TIMEOUT` — the default is visible in `--help` without reading the source.
- Mode-dependent required arguments are validated manually after `parse_args()` via
  `parser.error(...)` (e.g. one mode requiring extra flags another mode doesn't),
  rather than argparse subparsers, when the modes mostly share the same flag set.

### Logging / status output
- Plain `print()` with bracketed uppercase status tokens: `[INFO]`, `[WARNING]`,
  `[ERROR]`, plus domain-specific tags where useful (e.g. `[ANALYSIS]`). No `logging`
  module unless the project's scale genuinely needs handlers/levels/config.
- Failure paths in loader/parsing functions log a `print(f"[ERROR] ...")` and return
  `None` rather than letting the exception propagate; callers check `if x is None: ...
  skip/continue`. Reserve raised exceptions for programmer errors, not expected I/O
  failures.
- `except Exception as e:` (never bare `except:`), often after a narrower exception is
  checked first — always logs before returning a fallback.

### Functions over classes
- Prefer plain functions operating on dicts/arrays/dataframes over classes. Reach for
  a class only for genuinely stateful objects (e.g. something that holds derived state
  computed once and queried many times) — never purely for namespacing or one-shot
  logic that a function already expresses.
- Helpers are factored out only once actually shared by 2+ callers, not preemptively —
  three similar lines in two places is fine until a third caller shows up.

### Plotting
- `matplotlib` by default unless the task specifically calls for something else.
- Route plot output through one shared save helper, e.g. `save_and_show(fig,
  output_dir, filename, ...)`: `output_dir` and `filename` are always kept as separate
  arguments (never a single combined path), the extension is auto-appended, the
  directory is created if missing, and the figure is always explicitly closed after
  saving to avoid leaking open figures across batch-plotting loops.
- Saves use a fixed `dpi` and `bbox_inches='tight'`.

### Data I/O
- Default to the lightest dependency that solves the problem: stdlib `csv` +
  `numpy`/plain dicts for simple tabular I/O, reaching for `pandas` (or similar)
  only once the task actually needs its features (joins, groupby, etc.), not by
  default.
- `numpy` is used for vectorized math, but plain Python `for` loops are used freely
  for I/O/grouping/classification logic — no forced vectorization of control flow
  that's clearer as a loop.

### Units & domain quantities
- Any domain-specific quantity (physical units, currency, durations) is annotated at
  the point of definition/use — in constant comments, docstrings, axis labels, and log
  messages — rather than left as a bare number.

## Prohibited / Avoided Patterns

- **No emojis** anywhere in code, comments, docstrings, or log output.
- **No plotting library switching mid-project** — pick one (default `matplotlib`) and
  stay consistent; don't mix in seaborn/plotly/bokeh without a specific reason.
- **No heavy dependencies for simple needs** — don't reach for `pandas` or similar
  just to write a CSV or hold a small in-memory table.
- **No bare `except:`** — always catch a specific/general `Exception` and log it.
- **No `logging` module** by default — plain `print()` with bracketed status tags,
  unless the project's scale genuinely needs configurable handlers/levels.
- **No PEP 484 type hints in function signatures** — typing information is documented
  in the docstring's `Args:`/`Returns:` sections instead.
- **No combined output-directory+filename path argument** in save/plot functions —
  keep them as two separate parameters.
- **No premature abstraction/classes** for logic used in only one place — functions
  stay as plain functions until actually reused by a second caller.
- **No silent overwrite of prior markdown history** in Plan/Report-style docs —
  updates are appended under a new dated header (`### [YYYY-MM-DD] ...`) rather than
  replacing existing content.
- **No magic numbers without a named, meaning/unit-commented constant** at module
  scope for anything reused as a default or threshold.
