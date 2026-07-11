# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`img_evaluation` evaluates Wire-Cell Toolkit (WCT) 3D imaging reconstruction performance (charge/position
accuracy, track angle, blob size) for ProtoDUNE-HD and ProtoDUNE-VD. It is a research-notebook style
directory of analysis/plotting scripts plus their (large, dated) result artifacts — not a shipped
application. It is **not** version-controlled (no `.git` here, and the parent `WireCell/` workspace has no
umbrella repo either), so there is no safety net for deletions or moves.

**Read `README.md` in this directory first.** It is a maintained, factual map of the exact on-disk layout
and a "Known issues" section (stale hardcoded paths from an old `img_BlobDepoFill` rename, a duplicate
geometry file, an explicitly author-labeled "wrong version" 1.6GB result dump, etc.) — check it before
assuming any given script's paths are still valid. This file complements it with run commands and the
code architecture; don't duplicate README's directory-by-directory inventory here.

The workspace root `../CLAUDE.md` covers conventions shared across the whole multi-project workspace
(the shared venv, sibling sub-projects like `wire-cell-python`). This file is scoped to `img_evaluation`
specifically.

## Running scripts

There is no installed test runner or CI for this directory. Validate changes by re-running the relevant
numbered study script against sample data and inspecting the resulting plots/ROOT/HDF5 output.

```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"   # workspace root, NOT img_evaluation/ itself
python pdhd-wct-sim/2_single_track_analysis/track_evaluation.py   # example driver script
```

Driver scripts under `pdhd-wct-sim/`, `pdvd-wct-sim/`, and `wct_cfgs/` import shared code as
`from utils.xxx import ...`; this only resolves because `PYTHONPATH` is set to the workspace root
(`/home/yujin/projects/WireCell`), one level up from this directory. `pyproject.toml` also declares a
setuptools package (`pip install -e .` regenerates `img_evaluation.egg-info/`), but that is **not** how
scripts actually consume `utils/` in practice — the `PYTHONPATH` convention above is the real mechanism.
`.vscode/settings.json` and `launch.json` already point the interpreter/debugger and `PYTHONPATH` at the
right places — mirror that pattern if adding new run configs.

`requirements.txt` lists the actual third-party imports seen across all `.py` files in this directory
(numpy, scipy, matplotlib, networkx, pandas, shapely) plus an editable install of `../wire-cell-python`
for the `wirecell` namespace package — it documents what's used, it is not consumed by tooling directly
(the venv is shared workspace-wide; see root `CLAUDE.md`).

Producing new cluster-graph/depo input data (rather than analyzing existing dumps) goes through WCT
itself: `wct_cfgs/img_yujin/run_img.sh` runs `wire-cell` against a Jsonnet job graph
(`wct-sim-nf-sp-img-bdf.jsonnet`) then converts output to the Bee 3D event-display format via
`wct-img-2-bee-hd-bdf.py`. That script currently hardcodes an old machine's absolute paths
(`/nfs/data/1/yujin/...`) — treat it as a template to adapt, not something to run as-is.

## Architecture

`utils/` is the only real shared package in this project; everything else is a one-off driver script that
imports from it. Per workspace convention, one-off study logic should **not** be merged back into
`utils/` — keep numbered/dated driver scripts composing small functions from here instead.

- **`utils/load_data.py`** — the common entry point most other code starts from. Two data shapes:
  - `load_generation_data(depo_file, gen_index)`: depos (energy depositions) via `wirecell.gen.depos.stream`,
    keyed by generation index.
  - `load_cluster_data(cluster_file, event_index)` + `load_graph_nodes(cgraph, type_code, filter_func)`:
    cluster graphs via `wirecell.img.tap.load`, returned as `networkx` graphs. Nodes carry a `code`
    attribute for their type (`'b'` = blob, plus slices/measurements/etc.) — `load_graph_nodes` is how
    downstream code filters to a specific node type.
- **`utils/wire_utils.py`** — parses WCT JSON wire-geometry stores (anode/face/plane/wire hierarchy),
  including fixing wire-in-plane ordering/orientation to match the C++ `plane_fixer`, and decoding packed
  `WirePlaneId`s. Needed by anything that maps blobs/depos back to physical wire positions.
- **`utils/slice_utils.py`** — slice-level helpers used across evaluation/inspection code.
- **`utils/evaluation/`** — `charge_analysis.py` and `img_evaluation.py` (name collides with the
  top-level project name; cosmetic only, not a bug) implement the actual accuracy-metric computations
  (charge/position comparison between depos and reconstructed blobs).
- **`utils/inspection/`** — `depos_inspect.py`, `graph_inspect.py`: lower-level introspection/debugging
  helpers for looking at raw depos or cluster-graph contents.
- **`utils/vis/`** — plotting helpers (`transverse_plots.py`, `longitudinal_plots.py`, `point_depo_3d.py`,
  `wires_vis.py`) shared across study scripts. Two of these (`longitudinal_plots.py`,
  `transverse_plots.py`) still contain a stale `PROJECT_HOME=".../img_BlobDepoFill"` `sys.path.append`
  left over from the project rename — dead code, see README's Known Issues.
- **`pdhd-wct-sim/<N>_<study_name>/`** and **`pdvd-wct-sim/<study_name>/`** — the actual studies. Each
  numbered PDHD folder has its own driver script(s) (e.g. `track_evaluation.py`, `track_angle_compare.py`)
  that call into `utils/` and read/write that folder's own result dumps. Scripts and result data are
  interleaved (no consistent `scripts/`+`data/` split) except in `pdvd-wct-sim/`, which is already split
  into `data/`+`png/`+`scr/` per study.
- **`wct_cfgs/`** — Jsonnet WCT job-graph configs and shell drivers that *produce* the cluster-graph/depo
  files the study scripts consume (upstream of everything else here), plus the wire-geometry JSON files
  under `wct_cfgs/detector_geo/`.

## Known gotchas when editing or running scripts here

(Full detail and current status in README.md's "Known issues" section — this is the short version.)

- **32 of the ~49 `.py` files hardcode absolute paths** under the old, no-longer-existing project root
  `img_BlobDepoFill` — expect `FileNotFoundError` running these unmodified; check/fix the path before
  assuming a script "should just work".
- **No version control** in this tree or its parent workspace — be extra cautious with any destructive
  file operation (moves, deletes, overwrites of result dumps); there is nothing to `git checkout` back to.
- **`pdhd-wct-sim/3_tracks_angle_charge_evaluation/old_wrong_ver/`** (1.6 GB) is explicitly labeled "wrong
  version" by its own author but was never deleted — don't treat it as a canonical data source, and don't
  clean it up unless asked (kept for reference per current direction).
- Two byte-identical copies of the PDHD wire geometry exist
  (`pdhd-wct-sim/protodunehd-wires-larsoft-v1.json.bz2` and
  `wct_cfgs/detector_geo/protodunehd-wires-larsoft-v1.json.bz2`) — either works, but don't assume editing
  one updates the other.


디렉터리에 새로운 파일이 추가되어 README.md에 추가가 필요한 상황이면 추가 및 수정한다.

## Code Generation & Documentation Guidelines
- **Header Documentation**: Whenever modifying or generating code scripts, always include a brief summary and usage instructions at the very top of the file as comments.
  - **Summary**: A concise explanation of what the script does and its role in the evaluation pipeline.
  - **Usage**: Clear instructions or command examples on how to run or import the script (including required arguments or environment setups if applicable).
- **Language Constraint**: 
  - All source code, including header documentation, inline comments, docstrings, variable names, and log messages, must be written **strictly in English**. Do not use any other languages within the code files.
- **Tone**: Keep descriptions direct, objective, and clear. Avoid using analogies.

## Language & Tone Guidelines (Updated)
Language: Provide technical explanations and conceptual guidance in Korean. Use English primarily for code comments, variable names, and refining text templates.

Tone & Style: The tone adapts dynamically based on the type of content being delivered to balance clarity with readability:

Narrative & Flow (설명 및 흐름): When explaining concepts, walking through logic, or guiding the user through a process, use a polite and gentle honorific style (해요체/하십시오체, ending in -습니다, -요). Keep it warm, approachable, and natural.

Structured Information (정보 정리 및 분석): When presenting structured lists, summaries, code analysis, pros/cons, or factual specifications, switch to a concise and objective narrative style (해라체/평서체, ending in -이다, -한다). Avoid conversational filler in these sections to ensure high scannability.

Clarity: Keep explanations direct and well-structured, using clear and everyday language while avoiding overly abstract jargon.



# Wire-Cell Project Documentation Style Guide for Claude Code

## 1. Overall Tone & Manner
* **Objective and Concise Engineering Tone**: Focus strictly on facts, metrics, causal relationships, and code functionalities, eliminating subjective descriptions.
* **Declarative and Direct Endings**: Structure sentences concisely, typically using direct, present-tense phrasing to maintain clarity and brevity. In Korean, this means 평서체/해라체 (endings like `-이다`, `-한다`) throughout every `.md` file — this applies uniformly to narrative/conceptual passages and to structured/tabular passages alike. The 해요체 vs. 해라체 tone-switching rule in "Language & Tone Guidelines" is about live chat replies to the user, not file content; no `.md` file should ever switch into 해요체/하십시오체, regardless of what it's explaining.
* **One Sentence Per Line**: Break lines at sentence boundaries, not at a column width. Every sentence in a prose paragraph starts on its own line, even if that makes the line long. This applies to all `.md` files project-wide, not just docs/.
* **Contextual Orientation**: Always begin documents with a `## Summary` (or `## 요약`) heading — a real H2 section, not a bold `Summary:`-prefixed paragraph — so the reader immediately grasps the scope of the work. An optional runnable usage snippet may follow as a plain code block; it does not need its own bold `Usage:` label or heading.
* **No Horizontal Rules Between Sections**: Do not separate `##` sections with `---`. Heading hierarchy alone is sufficient; a `---` before every section header is visual noise once the header numbers are in place.

## 2. Component & Code Reference Conventions
* **Strict Use of Inline Code Blocks (` ` `)**: Wrap the following technical entities in backticks to clearly distinguish them from prose:
    * Class names and structures (e.g., `PlaneGeometry`, `BlobDepoFill`).
    * Functions and method names (e.g., `true_blob_polygon()`, `load_graph_nodes()`).
    * Variables, parameters, constants, and data field keys (e.g., `nsigma`, `start`, `val`, `nthreshold=3.6`).
    * Graph node identification tags (e.g., `'b'`, `'w'`).
* **Explicit Repository File Paths**: When mentioning internal toolkit components or configuration pipelines, provide precise relative repository paths (relative to the relevant repo root, not the absolute host path).
    * *Example*: `wire-cell-toolkit/img/src/BlobDepoFill.cxx`
    * *Example*: `wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2`

## 3. Structural & Layout Patterns
* **Hierarchical Header Formatting**: Follow a strict markdown header hierarchy using `#` for document titles, `##` for major sections, and `###` for sub-sections.
* **Numbered Sections and Cross-References**: Number every `##`/`###` heading (`## 3. Title`, `### 3.1 Title`). Refer to a section as bare `§N.M` inside tables and short list items. In standalone prose sentences, use an Obsidian-style wikilink instead — `[[filename#anchor|§N.M]]` — where `filename` is the target doc's basename without `.md` (this works both for self-references within the same document and for references to a different doc in `docs/`). When a section is inserted, removed, or moved, renumber every subsequent heading and update every `§` cross-reference in the file — `grep -n "§" <file>` before considering the edit done.
* **Tabular Summaries (Markdown Tables)**: Use tables for quick-reference listings — a class's fields/accessors, a directory's file-by-file role, or a set of comparison metrics. Do not use a table to explain a function's or method's full behavior; use the per-function prose pattern below instead.
* **Per-Function/Method Deep-Dive Format**: When asked to document what a function or method actually does (as opposed to a one-line summary of what it's for), write a bold inline signature line — **`func_name(args)`** — a one-line description, followed by one or more prose paragraphs naming the real variables, control flow (early returns, clamping, fallback branches), and — where relevant — why the code is written that way (an earlier approach that was tried and replaced, a WCT convention being matched, etc.).
* **Nested Bullet Points**: Organize detailed feature specifications, operational steps, or data models using nested bullet points to illustrate structural depth.
* **Purpose-Driven Blockquotes (`>`)**:
    * Use blockquotes at the very top of a document to denote file synchronization logs, author credits, or tracking metadata.
    * Use them within the body text to isolate and emphasize critical algorithmic constraints, definitions, or high-priority warnings.
* **Docs Follow Code Structure**: When code is split out of a module into a new file, split its documentation the same way — create a doc for the new file and leave a short pointer paragraph (not a silent deletion) where the detailed explanation used to live in the old doc.

## 4. Mathematical Expressions & Units
* **LaTeX Inline Equations**: Enclose any mathematical variables, coordinate axes, or equations within single dollar signs (`$`) when embedded in prose for proper italicized rendering.
    * *Example*: $t, q, x, y, z, L, T$ data fields, $y-z$ plane boundary lines.
* **Standardized Physical Units**: Append physical units (`mm`, `km`, `us`) immediately after numerical values without spaces to preserve scientific notation standards.

## 5. Troubleshooting & Limitations Framework
* **Causal Debugging Logs**: Document bugs, geometric distortions, or algorithmic flaws by tracing a logical sequence: `Initial Implementation/Symptom -> Root Cause Analysis -> Resolution/Correction -> Results`.
* **Honest Accounting of Known Limitations**: Maintain a dedicated section for unresolved side effects (e.g., `Time Offset Miscalibration`) or numerical approximations. Pair each limitation with an explicit "Next Steps" roadmap.
* **Session Metadata Tail**: Developer logs may end with execution environment stamps (software versions, Session ID, `cwd`, login method). This tail is appended automatically by project tooling, not written by hand — never add one manually when authoring or editing a doc, and never strip one that's already present.

## 6. Strict Prohibition of Emojis
* **Zero-Emoji Policy**: Under no circumstances should emojis be used anywhere in the documentation, including headers, list items, or tables. 
* **Maintain Professionalism**: Use only pure text, structural formatting, and standard Markdown syntax to guide the reader's eye and organize data, ensuring a clean and professional engineering log appearance.