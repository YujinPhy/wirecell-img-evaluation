# `wirecell.img` Reference

## Summary

A reference inventory of every img-related function, class, and CLI command in `../wire-cell-python/wirecell/img/` (the `wirecell-img` package), and how this repository (`wirecell-img-evaluation`) currently consumes it.
This is documentation only; there is nothing to execute here.
To use the package itself, activate the shared venv and set `PYTHONPATH` as described in this repo's `CLAUDE.md`, then `import wirecell.img.<module>` or run the `wirecell-img` CLI:

```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"
wirecell-img --help
```

Source root: `wire-cell-python/wirecell/img/` (package `wirecell.img`, console-script entry point `wirecell-img = wirecell.img.__main__:main`, declared in `wire-cell-python/setup.py` and `pyproject.toml`).

Companion doc in the source repo: `wire-cell-python/docs/img.org` (short, CLI-usage-only; this file is a fuller function-level inventory).

## 1. Package layout

| File | Role |
|---|---|
| `tap.py` | Cluster-file I/O: load a cluster graph archive (zip/tar/json) into a `networkx.Graph`. |
| `clusters.py` | `ClusterMap`: indexing/lookup helper over a loaded cluster graph. |
| `converter.py` | Coordinate transforms (undrift depos/blobs) and conversion to ParaView/VTK objects, blob point sampling. |
| `plots.py` | Low-level 2D histogram (`Hist2D`) and activity/blob-coverage plotting used by several CLI commands. |
| `plot_blobs.py` | Per-graph blob plotters (`plot_x/y/z/t/tx/ty/tz/views`) used by `wirecell-img plot-blobs`. |
| `plot_depos_blobs.py` | Combined depo+blob plotters (`plot_xz`, `plot_outlines`, `plot_views`) used by `wirecell-img plot-depos-blobs`. |
| `dump_blobs.py` | Per-blob signature dump (channel/tick ranges) for debugging. |
| `dump_bb_clusters.py` | Connected-blob-cluster signature dump, built on `dump_blobs.bsignature`. |
| `anidfg.py` | Unrelated to imaging results: animates a `TbbFlow` `dfg`-log data-flow graph into a GIF (`gvanim`). Kept in this package only because it's exposed via the same CLI. |
| `__main__.py` | `wirecell-img` Click CLI; wires all of the above into subcommands (see §10). |
| `__init__.py` | Empty. |

Data model: a **cluster graph** is a `networkx.Graph` whose nodes carry a single-letter `code` attribute identifying the node type.

| code | type | notes |
|---|---|---|
| `b` | blob | has `corners` (Nx3 or Nx4 array, `[t or x, y, z]`), `span` (thickness), `val`/`unc` (charge/uncertainty), `bounds` (per-view min/max wire-in-plane), `faceid`, `sliceid`. |
| `s` | slice | has `start`/`span` (time), `signal` (list of `{ident, val, unc}` per channel). |
| `m` | measure | per-view charge measurement, `val`/`unc`/`wpid`. |
| `w` | wire | `chid`, `seg`, `wpid`, `index`, `tail{x,y,z}`, `head{x,y,z}`. |
| `c` | channel | `ident`, `wpid`, `index` (only present when constructed from a JSON cluster file or via `add_activity`). |
| `a` | activity | raw per-channel/per-slice values; only appears in the "cluster arrays" (numpy) file variant and is coalesced into `c`/`signal` on load, see `tap.pg2nx`. |

## 2. `tap.py` — 클러스터 파일을 읽어오는 모듈

`tap.py`는 디스크에 저장된 클러스터 파일(cluster file)을 파이썬에서 다루기 쉬운 `networkx.Graph` 형태로 바꿔주는 역할을 한다.
`wirecell.img`를 쓰는 코드는 거의 다 여기서 출발한다고 보면 된다.

**`load(filename, **kwds)`** — 가장 중요한 함수다.

파일 하나를 받아서, 그 안에 들어있는 클러스터 그래프(cluster graph)들을 하나씩 순서대로 반환(yield)한다.
파일 확장자를 보고 아래 두 방식 중 하나로 자동 분기한다.

- 확장자가 `.json`, `.json.gz`, `.json.bz2`, `.jsonnet`이면 JSON 파일로 보고 `load_jsio`를 호출한다(`wirecell.util.jsio`로 파싱).
- 그 외(주로 zip이나 tar 압축 파일)면 아카이브(archive) 파일로 보고 `load_ario`를 호출한다(`wirecell.util.ario`로 파싱).
  이때 아카이브 안의 클러스터 그래프가 JSON으로 저장되어 있는지, 아니면 numpy 배열 모음("cluster arrays" 스키마)으로 저장되어 있는지를 자동으로 판별해서, 후자라면 `pg2nx`로 변환해준다.

정리하면, 클러스터 파일은 내부 저장 형식이 JSON일 수도 있고 numpy 배열 모음일 수도 있는데, 이 차이를 신경 쓰지 않고 `load()` 하나만 호출하면 항상 같은 모양의 `networkx.Graph`를 얻을 수 있다.

**`make_nxgraph(name, dat)`** — JSON으로 표현된 클러스터 그래프(`{"nodes": [...], "edges": [...]}` 형태의 딕셔너리)를 `networkx.Graph`로 만들어주는 내부 함수다.

**`make_pggraph(name, dat)` / `PgFiller` / `pg2nx(name, pg)`** — "cluster arrays" 스키마(노드/엣지 종류별로 numpy 배열이 따로 저장된 형식)를 먼저 PyG(PyTorch Geometric)의 `HeteroData`와 비슷한 중간 구조로 바꾸고(`make_pggraph`), 그 중간 구조를 다시 `make_nxgraph`가 만드는 것과 동일한 모양의 `networkx.Graph`로 변환한다(`pg2nx`).

`PgFiller`는 이 변환 작업을 실제로 수행하는 헬퍼 클래스다.
세 가지 모두 사용자가 직접 호출할 일은 거의 없고, `load()` 내부에서 쓰이는 부품이라고 이해하면 된다.

**`slice_channels(gr, snode)`** — 슬라이스(slice) 노드 하나를 주면, 그 슬라이스에 속한 blob들을 거쳐, 다시 그 blob들에 속한 measure들을 거쳐서 도달 가능한 channel 노드들을 모아 반환한다.

**`group_keys(arf)`** — 아카이브 안에 들어있는 파일 목록(키)을 훑어서, 하나의 JSON 파일에 해당하는 키인지, 아니면 클러스터 하나를 이루는 여러 numpy 배열 키 묶음(`cluster_<n>_<kind>` 형태)인지를 그룹으로 묶어주는 내부 함수다.

이 저장소(`wirecell-img-evaluation`)의 `scripts/utils/load.py`에 있는 `load_cluster_data` 함수가 내부적으로 호출하는 것이 바로 이 `wirecell.img.tap.load`다.

## 3. `clusters.py` — `ClusterMap`

`ClusterMap(gr)`는 로드된 클러스터 그래프를 감싸서 생성 시점에 조회용 인덱스를 만든다.

- `channel(key)` — channel node by ident (int) or by `(wpid, index)` tuple.
- `wire_chanseg(chan, seg)` — wire node by `(channel id, segment)`.
- `wire_wip(wpid, wip)` — wire node by `(wire-plane id, wire-in-plane index)`.
- `wire_wid(wpid, wid)` — wire node by `(wire-plane id, wire ident)`.
  기존에 있던 버그 하나를 갖고 있다: 본문에서 `wid` 대신 정의되지 않은 `wip`를 참조하므로, 고치지 않고는 이 메서드에 의존하면 안 된다.
- `find(typecode=None, **kwds)` — nodes matching arbitrary attribute equality, optionally restricted to a type code.
- `nodes_oftype(typecode)` / `data_oftype(typecode)` — all nodes (or their data dicts) of a given code.
- `neighbors_oftype(node, typecode)` — a node's neighbors restricted to a type code.

이 저장소의 `scripts/utils/blob_inspect.py`가 이미 `wirecell.img.clusters`를 직접 임포트해서 쓴다.

## 4. `converter.py` — coordinate transforms & export

좌표/undrift 변환:

- `undrift_points(pts, speed, t0, time_index=0)` — generic time→space conversion for an array of points.
- `undrift_depos(depos, speed, time, drift_index=0)` — converts a depo dict-of-arrays (as from `wirecell.gen.depos`) from time back to a drift-space `x` coordinate; also takes `abs(q)`.
- `undrift_blobs(cgraph, speed, time, x0=0, drift_index=0)` — same, but walks every blob node's `corners` in a cluster graph (or list of graphs) and rescales `span` by `abs(speed)`.
  This is what the CLI's `-B/--undrift-blobs` and `-D/--undrift-depos` options (see §10) call.

기하 헬퍼:

- `extrude(pts, dx)` — extrude a 2D point ring along X by `dx` to build a 3D cell (prism), used to turn a blob's 2D cross-section polygon into a 3D VTK cell.
- `orderpoints(pointset)` — sort a blob's corner points by angle about their centroid, so they form a valid (non-self-intersecting) polygon.

ParaView/VTK export (requires `tvtk`, i.e. Mayavi; only imported inside these functions):

- `depos2pts(depos)` — depos → `tvtk.PolyData` (point cloud with `charge`, `time`, `DT`, `DL` scalar arrays).
- `clusters2blobs(gr)` — cluster graph → `tvtk.UnstructuredGrid` of extruded-polygon blob volumes, with all scalar blob attributes (charge, uncertainty, etc.) attached as cell arrays.
- `clusters2views(gr)` — cluster graph → dict of `tvtk.ImageData` (one per wire-plane id), reconstructed channel-activity images built by walking measure→blob→slice→signal.
- `get_blob(gr, node)` / `get_slice(gr, bnode)` / `get_neighbors_oftype(gr, node, code, with_data=False)` — small graph-walking helpers used by the above.
  `get_neighbors_oftype` has a latent bug: its `with_data=False` branch appends to an undefined name `retu` instead of `ret` and will raise `NameError` if hit.

Blob → point-cloud sampling (used for Bee export, see `bee-blobs` in §10):

- `blob_center(bdat)` — single point at a blob's centroid, `[x,y,z,q]`.
- `blob_uniform_sample(bdat, density)` — random points uniformly filling the blob's cross-section polygon (via `shapely`) times its thickness, count driven by `density` (points per volume).
- `blobpoints(gr, sample_method=blob_center)` — apply a sampling function to every blob node in a graph and stack results into one `Nx4` array.

## 5. `plots.py` — activity/blob 2D histograms

- `Hist2D(nx, xmin, xmax, ny, ymin, ymax)` — minimal 2D histogram class (`fill`, `imshow`, `extent`, `like()` to make an empty histogram with the same binning).
- `activity(cm, amin)` — given a `ClusterMap`, build a channel-vs-slice `Hist2D` of raw signal activity (`>= amin`), used for `wirecell-img activity` / `blob-activity-stats` / `blob-activity-mask`.
- `blobs(cm, hist, value=False)` — fill a `Hist2D` with blob coverage: unity per covered channel/slice pixel, or (if `value=True`) blob charge divided evenly across its covered wires.
- `mask_blobs(a, b, sel, extent, vmin, invert, clabel, **kwds)` — render an activity array `a` masked by a selector applied to array `b` (e.g. "mask activity where blobs found it"); returns `(fig, ax)`.
  Backs `wirecell-img blob-activity-mask`.
- `wire_blob_slice(cm, sliceid)` — per-face plot of one slice's wires (colored by signal) with blob outlines overlaid; backs `wirecell-img wire-slice-activity`.

## 6. `plot_blobs.py` — single-graph blob plots

Registered in the CLI as `wirecell-img plot-blobs -p <name>` (option choices auto-derived from every `plot_*` function in this module).

- `plot_x` / `plot_y` / `plot_z` — histogram of a blob's first-corner coordinate along that axis.
- `plot_t` — histogram of blob (slice) start times.
- `plot_tx` / `plot_ty` / `plot_tz` — scatter of mean blob position along an axis vs. slice time.
- `plot_views` — 2x3 grid: charge density projected onto each pair of wire-plane views, plus charge density vs. time for each view, as `Rectangle` patch collections.

`subplots(nrows=1, ncols=1)` is a local `plt.subplots(..., tight_layout=True)` wrapper.

## 7. `plot_depos_blobs.py` — combined depo + blob plots

Registered in the CLI as `wirecell-img plot-depos-blobs -p <name>` (same auto-discovery pattern).
Takes a `deposets` generator and a `clusters` generator together.

- `plot_xz(depos, cgraph)` — simple scatter overlay of blob centers and depo positions in X-Z.
- `plot_outlines(depos, cgraph, lims=None, include=("depos","blobs"))` — depos drawn as charge-colored ellipses (sized by longitudinal/transverse diffusion `L`/`T`), blobs drawn as charge-colored rectangles, in all three 2D projections (XY, YZ, ZX).
- `plot_views(depos, cgraph)` — 4x2 grid of per-view (U/V/W) x per-face wire-in-plane vs. time activity images built directly from blob bounds/charge/slice-time, plus a bottom row of time histograms.

Helper accessors also in this module: `blob_nodes`, `blob_faces`, `blob_coord`, `blob_charge`, `blob_centers`, `blob_corners`, `blob_bounds`, `blob_slices`.
Note `wires_pimpos(cgraph)` in this module is broken/unused dead code (references undefined `dat.append` on a `dict`, and node attribute names `plane`/`wip` that don't exist in the current schema — do not call it).

## 8. `dump_blobs.py` / `dump_bb_clusters.py` — debug signature dumps

- `dump_blobs.bsignature(gr, bnode, tick=500)` — for one blob node, returns `[tmin, tmax, umin, umax, vmin, vmax, wmin, wmax, qU, qV, qW]` (time bucketed by `tick`, per-view wire-in-plane range and summed channel signal).
  Returns `None` if any view has no wire neighbors.
- `dump_blobs.dump_blobs(gr, sigfile=None, dumpfile="/dev/stdout")` — computes `bsignature` for every blob in a graph, sorts, and writes a human-readable dump (optionally also saves the raw array via `numpy.save` to `sigfile`).
  Backs `wirecell-img dump-blobs`.
- `dump_bb_clusters.csignature(gr, bc)` — same idea but aggregated over one connected component of blobs (`bc`), combining per-blob `bsignature`s into cluster-level min/max/charge totals.
- `dump_bb_clusters.dump_bb_clusters(gr)` — finds connected components of the blob-only subgraph and prints a sorted signature per cluster.
  Backs `wirecell-img dump-bb-clusters`.

## 9. `anidfg.py` — data-flow-graph animation (not imaging-result-related)

Parses `TbbFlow` "dfg" log lines (`parse_log`, `parse_ts`) and turns node enter/exit and edge connect events into an animated graph GIF via the `gvanim` package (`generate_graph`, `render_graph`).
Backs `wirecell-img anidfg`.
Included here for completeness since it ships in the same package/CLI, but it visualizes WCT's internal execution graph, not depos/blobs, so it is unlikely to be relevant to this repo's evaluation work.

## 10. CLI commands (`wirecell-img ...`)

All defined in `__main__.py`, grouped under the `wirecell-img` Click group.
Common decorators: `@cluster_file` adds a `cluster-file` argument plus `-B/--undrift-blobs SPEED,TIME`; `@deposet_file` adds a `depo-file` argument plus `-D/--undrift-depos SPEED,TIME` and `-g/--generation`.

| Command | Purpose |
|---|---|
| `plot-depos-blobs -p <plot> DEPO_FILE CLUSTER_FILE PLOT_FILE` | Run a `plot_depos_blobs.py` plotter, save one page. |
| `plot-blobs -p <plot> CLUSTER_FILE` | Run a `plot_blobs.py` plotter over every graph in the file (multi-page). |
| `dump-blobs CLUSTER_FILE` | `dump_blobs.dump_blobs` text dump, optional `-s/--signals` numpy save. |
| `dump-bb-clusters CLUSTER_FILE` | `dump_bb_clusters.dump_bb_clusters` text dump. |
| `inspect CLUSTER_FILE` | Structural summary of a cluster file: node/edge counts by type code, value stats for blobs/channels/measures/slices, wire seg/wpid counts. |
| `paraview-blobs CLUSTER_FILE OUT.vtu` | `converter.clusters2blobs` → `.vtu` per graph (needs `tvtk`). |
| `paraview-activity CLUSTER_FILE OUT.vti` | `converter.clusters2views` → one `.vti` per wire-plane (needs `tvtk`). |
| `paraview-depos DEPO_FILE OUT.vtp` | `converter.depos2pts` → `.vtp` (needs `tvtk`); see also `wirecell-gen plot-depos`. |
| `bee-blobs -o OUT.json CLUSTER_FILES...` | Blob point clouds (center or uniform sampling) → Bee 3D-event-display JSON, grouped by connected blob component as `cluster_id`. This is the command family this repo's `wct_cfgs/img_yujin/wct-img-2-bee-hd-bdf.py` wraps/adapts. |
| `bee-flashes -o OUTDIR INPUT...` | Optical-flash `ITensorSet` archive → per-event Bee flash-match JSON (`opflash_tensor_*` keys). |
| `activity -o OUT.png CLUSTER_FILE` | `plots.activity` channel-vs-slice heatmap plot. |
| `blob-activity-stats CLUSTER_FILE` | Prints coverage stats: `atot`, `btot`, `qtot`, `afound`/`amissed` (+ fractions), `nbpix`. |
| `blob-activity-mask -o OUT.png CLUSTER_FILE` | `plots.mask_blobs` — visualize activity found/missed by blobs as a mask. |
| `wire-slice-activity -o OUT.png -s SLICEID CLUSTER_FILE` | `plots.wire_blob_slice` — one slice's wires + blob outlines, per face. |
| `anidfg -o OUT.gif LOGFILE` | `anidfg` module — TbbFlow dfg log → animated GIF (see §9). |
| `transform-depos DEPOS` | Apply rotate/locate/move transforms to a depo file (about center-of-charge), independent of cluster graphs. |

Run `wirecell-img <command> --help` for full option lists; several options above are abbreviated.

## 11. Current usage inside `wirecell-img-evaluation`

As of this writing, only two files in this repo import `wirecell.img` directly.

- `scripts/utils/load.py` → `import wirecell.img.tap as tap` (cluster-graph loading).
- `scripts/utils/blob_inspect.py` → `import wirecell.img.clusters as clusters` (`ClusterMap` lookups).

The older `pdhd-wct-sim/`/`pdvd-wct-sim/` trees (gitignored, superseded per `README.md`) use the same two entry points via `utils/load_data.py`'s `load_cluster_data` / `load_graph_nodes`, which wrap `wirecell.img.tap.load` directly rather than going through `ClusterMap`.

None of this repo's own code currently calls into `converter.py`'s undrift/ParaView helpers, `plots.py`, the `plot_blobs.py`/`plot_depos_blobs.py` plotters, or the `dump_blobs.py`/`dump_bb_clusters.py` debug dumps — those are only reached indirectly via the `wirecell-img` CLI (e.g. `wct_cfgs/img_yujin/`'s Bee-conversion workflow, which reimplements rather than calls `bee-blobs`).
They are candidate building blocks (`ClusterMap`, `converter.undrift_blobs`, `plots.activity`/`plots.blobs` for found/missed-activity accounting) for evaluation scripts that currently reimplement similar logic ad hoc.
