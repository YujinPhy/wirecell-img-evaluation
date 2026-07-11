# Project Structure  

This document serves as a map of the current project structure, written to orient anyone (including future-me) landing in this directory. It is descriptive, not aspirational.

This repository is structured to benchmark the charge and position reconstruction accuracy, as well as the overall performance of the Wire-Cell 3D imaging algorithm. The directory tree reflects the workflow of this evaluation: generate a Wire-Cell simulation config (`wire-cell-cfg/`), run it (`sh_scripts/`), then inspect/plot the resulting depos and clusters (`scripts/`).

## Environment
The evaluation workflow is built on **Python**. To ensure all dependencies and workspace paths are correctly resolved, the environment must be configured as follows before running any scripts:
```bash
source ../wire-cell-python/venv/bin/activate    # placed at workspace root, not img_evaluation/ itself
```

## Top-level layout

```
img_evaluation/
├── .git/               # Git repository metadata
├── .gitignore          # Specifies intentionally untracked files to ignore
├── CLAUDE.md            # Project guide, build/test commands, and code style rules
├── README.md            # This file
│
├── docs/                # Reference documentation for external dependencies, plus write-ups of work done in this repo
│   ├── wirecell_img_reference.md   # Inventory of ../wire-cell-python's wirecell.img package (functions, classes, wirecell-img CLI)
│   ├── wirecell_gen_reference.md   # Inventory of ../wire-cell-python's wirecell.gen package (functions, classes, wirecell-gen CLI)
│   ├── wirecell_depo_reference.md  # Depo data model, .npz file format, and C++ pipeline (../wire-cell-toolkit/gen, iface, aux, sio)
│   ├── wirecell_wires_reference.md # wirecell.util.wires schema/persist: wire-geometry data model (Detector/Anode/Face/Plane/Wire/Point) and file I/O
│   ├── true_blob_prototype.md      # Design + code walkthrough for the depo-based "true blob" prototype (utils/true_blob.py)
│   ├── wires_geometry_walkthrough.md # PlaneGeometry/build_plane_geometries/face_sensitive_bounds walked through with a single point-depo example (utils/wires.py)
│   ├── position_shape_evaluation.md # IoU/centroid/time-overlap/charge-error metrics comparing true blob vs. reco blob (utils/eval/position_shape.py)
│   └── time_offset_calibration.md  # Root-cause analysis + calibration of BlobDepoFill's time_offset (utils/time_offset.py, pdhd_time_offset_check.py)
│
├── data/                # (gitignored) Datasets generated from Wire-Cell runs
│   ├── pdhd/            # Datasets for ProtoDUNE-Horizontal Drift (ProtoDUNE-HD)
│   └── pdvd/            # Datasets for ProtoDUNE-Vertical Drift (ProtoDUNE-VD)
│
├── results/             # Analysis and performance evaluation results (plots, metrics)
│   ├── pdhd/             # Evaluation outputs for ProtoDUNE-HD
│   └── pdvd/             # Evaluation outputs for ProtoDUNE-VD
│
├── scripts/              # Analysis, inspection, and visualization scripts
│   └── utils/            # Shared utility modules
│
├── sh_scripts/           # Shell entry points: run WCT, convert to Bee, upload, log
│
└── wire-cell-cfg/        # Wire-Cell Toolkit configuration files (WCT Jsonnet, geometry, Bee tooling)
```

`data/` is entirely gitignored (raw/derived simulation output: `.root`, `.tar.gz`, `.zip`, `.json*`, etc.), but each run also drops a small `run-<timestamp>.json` record (CFG path, track/anode parameters, Bee viewer URL) next to the data — see `sh_scripts/run_single_trk.sh` / `run_single_point.sh`. Those `.json` files are gitignored too, but are the quickest way to see what a given data directory actually contains.

`from_jay/`, `pdhd-wct-sim/`, and `pdvd-wct-sim/` still exist on disk but are gitignored and superseded by `wire-cell-cfg/` + `sh_scripts/` + `scripts/`; they're kept around only as historical reference and are not part of the current workflow.

## Sub-level layouts
### `img_evaluation/scripts`
This directory centralizes all analysis, inspection, and visualization code for the performance evaluation.

```
img_evaluation/scripts/
├── pdhd_single_point_analysis.py   # CLI entry point: inspects + plots one anode's depo/cluster/BDF run
│                                    #   usage: python pdhd_single_point_analysis.py <data_dir under data/pdhd, or full path>
├── pdhd_true_blob_check.py         # Builds depo-based "true blobs" and validates them against reco blobs for test_point_depo (see docs/true_blob_prototype.md)
├── pdhd_time_offset_check.py       # Computes + validates BlobDepoFill's calibrated time_offset for PDHD (see docs/time_offset_calibration.md)
├── geometry_validation.py          # Educational walkthrough of wire-store schema + PlaneGeometry mechanics (synthetic example, no depo data)
├── depo_wire_validation.py         # Validates that PlaneGeometry/true_blob_polygon select the correct wires for real depo positions
└── utils/
    ├── load.py                     # Depo / cluster-graph / wire-geometry loading (wraps wirecell.gen.depos, wirecell.img.tap)
    ├── slicer.py                   # Binning class + Gaussian PDF/CDF/interval-integration utilities
    ├── wires.py                    # Wire-store loading + PlaneGeometry (pitch axis, strip polygons) + face_sensitive_bounds (sensitive-volume clip) (docs/wires_geometry_walkthrough.md)
    ├── true_blob.py                # Depo -> independent ground-truth blob polygon/time-slice/charge (docs/true_blob_prototype.md)
    ├── time_offset.py              # Analytic baseline + narrow residual scan for BlobDepoFill's time_offset (docs/time_offset_calibration.md)
    ├── depo_inspect.py             # Console reports for depo (Gen0 post-drift / Gen1 pre-drift) data
    ├── blob_inspect.py             # Console reports for cluster-graph nodes (graph/slices/blobs/wires)
    ├── report_format.py            # Shared banner/rule formatting (WIDTH, print_banner, print_rule) used by the *_inspect modules
    ├── eval/
    │   └── position_shape.py       # true-vs-reco blob comparison: IoU/centroid-distance/time-overlap/charge-error (docs/position_shape_evaluation.md)
    └── vis/
        ├── plot_utils.py           # Shared save_and_show() helper (output_dir + filename, makedirs, optional plt.show())
        ├── longitudinal_plots.py   # Drift-time charge density plots: depo (Gaussian) vs. reco blobs vs. true BDF blobs
        ├── transverse_plots.py     # Y-Z plane charge distribution plots for one slice (depo Gaussian, wires, blob outlines)
        ├── true_blob_plots.py      # Overlay plots of true blob vs. reco blob polygons over the depo's true (unsnapped) nsigma boundary on a black background, plus nearest_reco_blob matching
        └── depo_3d.py              # 3D Gaussian ellipsoid plots of a single depo (spatial, and drift-time-converted)
```

Not yet ported/implemented: the per-slice charge accounting used by `plot_longitudinal_charge_distribution` / `plot_transverse_charge_distribution` (`summrize_slice_charges`, `print_slice_charge_summary`, expected at `utils/evaluation/charge_analysis.py`) does not exist yet, so those two composite plot calls in `pdhd_single_point_analysis.py` are currently non-functional until that module is written.

### `img_evaluation/sh_scripts`
Shell entry points that drive one evaluation run end-to-end: compile+run a Wire-Cell Jsonnet config (`wire-cell-cfg/pdhd/...`), convert the resulting cluster files to Bee format, upload to the Bee viewer, and (for the single-run scripts) record the run's parameters + viewer URL as a `run-<timestamp>.json` file alongside the data.

```
img_evaluation/sh_scripts/
├── run_single_trk.sh             # Single parameterized track (angle/length/position/charge/anodes set via shell vars at the top)
├── run_single_point.sh           # Same as above, tuned for a single point deposition (tiny track length, large charge)
├── run_img_points.sh             # Scans a grid of point-depo (X,Y,Z) positions
├── run_img_localized_points.sh   # Scans a localized spherical cluster of point-depo positions around several centers
└── run_img_track_angles.sh       # Scans track angle (theta_xz) at a fixed track length
```

`run_single_trk.sh` and `run_single_point.sh` point at the current `wire-cell-cfg/pdhd/` layout and are kept working. `run_img_points.sh`, `run_img_localized_points.sh`, and `run_img_track_angles.sh` still reference the older `img_BlobDepoFill` output paths and jsonnet filenames (`wct-sim-nf-sp-img-bdf-points.jsonnet`, `wct-sim-nf-sp-img-bdf-tracks.jsonnet`) and have not been updated to the current layout yet.

### `img_evaluation/wire-cell-cfg/`
This directory manages the configuration files and detector geometry assets required by the Wire-Cell Toolkit (WCT) to execute or validate the 3D imaging environment.

```
img_evaluation/wire-cell-cfg/
├── det_geo/                        # Detector wire geometry files
│   ├── protodunehd-wires-larsoft-v1.json.bz2   # Wire geometry for ProtoDUNE-HD
│   └── protodunevd-wires-larsoft-v3.json.bz2   # Wire geometry for ProtoDUNE-VD
│
├── pdhd/                            # WCT Jsonnet + Bee-conversion tooling for ProtoDUNE-HD
│   ├── wct-sim-nf-sp-img-bdf.jsonnet   # Sim -> NF/SP -> Img -> BlobDepoFill pipeline; track/anode geometry via jsonnet TLAs
│   ├── img.jsonnet                     # Customized imaging pipeline (adds cluster_fanout/blob_depo_fill/sink helpers over the stock WCT img.jsonnet)
│   ├── wct-img-2-bee-hd-bdf.py         # Converts (rec, bdf) cluster file pairs -> Bee JSON, for any subset of the 4 anodes (`--pair ANODE REC BDF`, repeatable)
│   ├── wct-img-2-bee-hd.py             # Converts all 4 anodes' rec-only clusters -> Bee JSON
│   └── upload-to-bee.sh                # Uploads a Bee zip to the viewer and prints the resulting URL on stdout
│
├── pdvd/                            # Reserved for ProtoDUNE-VD configs (currently empty)
└── js.sh                            # Compiles a jsonnet config to JSON and/or renders its pipeline graph as a PDF, written next to the input file
```
