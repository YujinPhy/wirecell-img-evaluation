# Project Structure  

This document serves as a map of the current project structure, written to orient anyone (including future-me) landing in this directory. It is descriptive, not aspirational.

This repository is structured to benchmark the charge and position reconstruction accuracy, as well as the overall performance of the Wire-Cell 3D imaging algorithm. The directory tree reflects the workflow of this evaluation: generate a Wire-Cell simulation config (`wire-cell-cfg/`), run it (`sh_scripts/`), then inspect/plot the resulting depos and clusters (`scripts/`).

## Environment
The evaluation workflow is built on **Python**. To ensure all dependencies and workspace paths are correctly resolved, the environment must be configured as follows before running any scripts:
```bash
source ../wire-cell-python/venv/bin/activate    # placed at workspace root, not wirecell-img-evaluation/ itself
```

## Top-level layout

```
wirecell-img-evaluation/
├── .git/               # Git repository metadata
├── .gitignore          # Specifies intentionally untracked files to ignore
├── CLAUDE.md            # Project guide, build/test commands, and code style rules
├── README.md            # This file
│
├── docs/                # Reference documentation for external dependencies, plus write-ups of work done in this repo
│   ├── wirecell_img_reference.md   # Inventory of ../wire-cell-python's wirecell.img package (functions, classes, wirecell-img CLI)
│   ├── wirecell_gen_reference.md   # Inventory of ../wire-cell-python's wirecell.gen package (functions, classes, wirecell-gen CLI)
│   ├── wirecell_depo_reference.md  # Depo data model, .npz file format, and C++ pipeline (../wire-cell-toolkit/gen, iface, aux, sio)
│   ├── wirecell_sigproc_reference.md # OmnibusSigProc (deconvolution/ROI) pipeline reference (../wire-cell-toolkit/sigproc)
│   ├── wires_geometry_walkthrough.md # PlaneGeometry/build_plane_geometries/face_sensitive_bounds walked through with a single point-depo example (utils/wires.py)
│   ├── img_time_slicing_reference.md # How img's ISlice time-bin width (tick x tick_span) is determined
│   ├── time_offset_calibration.md  # Root-cause analysis + calibration of BlobDepoFill's time_offset (scripts/time_offset.py, pdhd_time_offset_check.py)
│   ├── geometry/          # Sensitive-volume and wire-geometry reference docs
│   │   ├── wirecell_sensitive_volume.md # Full 3D (x,y,z) sensitive-volume bounds: wire store JSON vs. simparams.jsonnet det.volumes vs. AnodePlane.cxx
│   │   └── wirecell_wires_reference.md  # wirecell.util.wires schema/persist: wire-geometry data model and file I/O
│   ├── img_3d_imaging_workflow/ # WCT img 3D pipeline walkthrough, split by stage (00 overview, 01 slicing/tiling, 02 charge solving, 03 deghosting, 04 constants/caveats)
│   ├── evaluation/        # Plan/Report docs for the depo-vs-reco-blob position evaluation task (see Task_Plan_and_Report_Workflow policy)
│   │   ├── position_center_comparison_plan.md   # Plan (steps 1-3): objective, success criteria, action items
│   │   └── position_center_center_comparison_report.md # Report (steps 4-6): per_file/one-mode runs, results, next actions
│   └── axive/             # Archived: superseded true-blob/position-shape prototype (docs + scripts), kept for history only
│
├── blob_viewer/         # trame-based live 3D web viewer for any clusters-apa/depos-drifted file pair (PDHD, PDVD, or otherwise)
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

`from_jay/` still exists on disk but is gitignored and superseded by `wire-cell-cfg/` + `sh_scripts/` + `scripts/`; it's kept around only as historical reference and is not part of the current workflow. The old top-level `pdhd-wct-sim/`/`pdvd-wct-sim/` directories are gone: `pdhd-wct-sim/`'s files were folded into `wire-cell-cfg/pdhd/` (documented below), and `pdvd-wct-sim/`'s files were relocated to `wire-cell-cfg/pdvd/pdvd-wct-sim/` (still gitignored, still historical-reference-only).

## Sub-level layouts
### `wirecell-img-evaluation/scripts`
This directory centralizes all analysis, inspection, and visualization code for the performance evaluation.

```
wirecell-img-evaluation/scripts/
├── pdhd_single_point_analysis.py   # CLI entry point: inspects + plots one anode's depo/cluster/BDF run
│                                    #   usage: python pdhd_single_point_analysis.py <data_dir under data/pdhd, or full path>
├── pdhd_time_offset_check.py       # Computes + validates BlobDepoFill's calibrated time_offset for PDHD (see docs/time_offset_calibration.md)
├── pdhd_generate_point_grid.py     # Generates a 3D grid of point-depo positions for wct-sim-nf-sp-img-bdf-grid.jsonnet (one WCT job for many points)
├── position_center_comparison.py   # Compares point-depo vs. reco-blob centers; `--mode {per_file,one}` selects the depo/blob correspondence source (see docs/evaluation/)
├── time_offset.py                  # Analytic baseline + narrow residual scan for BlobDepoFill's time_offset (docs/time_offset_calibration.md)
├── point_depo_anlaysis.ipynb       # Ad-hoc notebook exploration of point-depo data (scratch, not a maintained entry point)
├── geometry_validation.py          # Educational walkthrough of wire-store schema + PlaneGeometry mechanics (synthetic example, no depo data)
├── depo_wire_validation.py         # Validates that PlaneGeometry/true_blob_polygon select the correct wires for real depo positions
└── utils/
    ├── load.py                     # Depo / cluster-graph / wire-geometry loading (wraps wirecell.gen.depos, wirecell.img.tap)
    ├── slicer.py                   # Binning class + Gaussian PDF/CDF/interval-integration utilities
    ├── wires.py                    # Wire-store loading + PlaneGeometry (pitch axis, strip polygons) + face_sensitive_bounds (sensitive-volume clip) (docs/wires_geometry_walkthrough.md)
    ├── true_blob.py                # Depo -> independent ground-truth blob polygon/time-slice/charge (see docs/axive/true_blob_prototype.md)
    ├── depo_inspect.py             # Console reports for depo (Gen0 post-drift / Gen1 pre-drift) data
    ├── blob_inspect.py             # Console reports for cluster-graph nodes (graph/slices/blobs/wires)
    ├── report_format.py            # Shared banner/rule formatting (WIDTH, print_banner, print_rule) used by the *_inspect modules
    └── vis/
        ├── plot_utils.py           # Shared save_and_show() helper (output_dir + filename, makedirs, optional plt.show())
        ├── longitudinal_plots.py   # Drift-time charge density plots: depo (Gaussian) vs. reco blobs vs. true BDF blobs
        ├── transverse_plots.py     # Y-Z plane charge distribution plots for one slice (depo Gaussian, wires, blob outlines)
        ├── true_blob_plots.py      # Overlay plots of true blob vs. reco blob polygons over the depo's true (unsnapped) nsigma boundary on a black background, plus nearest_reco_blob matching
        └── depo_3d.py              # 3D Gaussian ellipsoid plots of a single depo (spatial, and drift-time-converted)
```

`pdhd_true_blob_check.py` and `utils/eval/position_shape.py` (true-blob-vs-reco-blob IoU/centroid/charge comparison) were superseded by the depo-center-vs-blob-center approach in `position_center_comparison.py` and moved to `docs/axive/` for historical reference; `utils/eval/` is now an empty leftover directory.

Not yet ported/implemented: the per-slice charge accounting used by `plot_longitudinal_charge_distribution` / `plot_transverse_charge_distribution` (`summrize_slice_charges`, `print_slice_charge_summary`, expected at `utils/evaluation/charge_analysis.py`) does not exist yet, so those two composite plot calls in `pdhd_single_point_analysis.py` are currently non-functional until that module is written.

### `wirecell-img-evaluation/sh_scripts`
Shell entry points that drive one evaluation run end-to-end: compile+run a Wire-Cell Jsonnet config (`wire-cell-cfg/pdhd/...`), convert the resulting cluster files to Bee format, upload to the Bee viewer, and (for the single-run scripts) record the run's parameters + viewer URL as a `run-<timestamp>.json` file alongside the data.

```
wirecell-img-evaluation/sh_scripts/
├── run_single_trk.sh             # Single parameterized track (angle/length/position/charge/anodes set via shell vars at the top)
├── run_single_point.sh           # Same as above, tuned for a single point deposition (tiny track length, large charge)
├── run_grid_points.sh            # Runs wct-sim-nf-sp-img-bdf-grid.jsonnet: many point-depo positions (via pdhd_generate_point_grid.py) in one WCT job
├── run_img_points.sh             # Scans a grid of point-depo (X,Y,Z) positions
├── run_img_localized_points.sh   # Scans a localized spherical cluster of point-depo positions around several centers
└── run_img_track_angles.sh       # Scans track angle (theta_xz) at a fixed track length
```

`run_single_trk.sh`, `run_single_point.sh`, and `run_grid_points.sh` point at the current `wire-cell-cfg/pdhd/` layout and are kept working. `run_img_points.sh`, `run_img_localized_points.sh`, and `run_img_track_angles.sh` still reference the older `img_BlobDepoFill` output paths and jsonnet filenames (`wct-sim-nf-sp-img-bdf-points.jsonnet`, `wct-sim-nf-sp-img-bdf-tracks.jsonnet`) and have not been updated to the current layout yet.

### `wirecell-img-evaluation/wire-cell-cfg/`
This directory manages the configuration files and detector geometry assets required by the Wire-Cell Toolkit (WCT) to execute or validate the 3D imaging environment.

```
wirecell-img-evaluation/wire-cell-cfg/
├── det_geo/                        # Detector wire geometry files
│   ├── protodunehd-wires-larsoft-v1.json.bz2   # Wire geometry for ProtoDUNE-HD
│   └── protodunevd-wires-larsoft-v3.json.bz2   # Wire geometry for ProtoDUNE-VD
│
├── pdhd/                            # WCT Jsonnet + Bee-conversion tooling for ProtoDUNE-HD
│   ├── wct-sim-nf-sp-img-bdf.jsonnet   # Sim -> NF/SP -> Img -> BlobDepoFill pipeline; track/anode geometry via jsonnet TLAs
│   ├── wct-sim-nf-sp-img-bdf-grid.jsonnet # Same pipeline, but takes a grid of point-depo positions (sim.tracks()) in one job instead of one job per position
│   ├── img.jsonnet                     # Customized imaging pipeline (adds cluster_fanout/blob_depo_fill/sink helpers over the stock WCT img.jsonnet)
│   ├── wct-img-2-bee-hd-bdf.py         # Converts (rec, bdf) cluster file pairs -> Bee JSON, for any subset of the 4 anodes (`--pair ANODE REC BDF`, repeatable)
│   ├── wct-img-2-bee-hd.py             # Converts all 4 anodes' rec-only clusters -> Bee JSON
│   └── upload-to-bee.sh                # Uploads a Bee zip to the viewer and prints the resulting URL on stdout
│
├── pdvd/                            # ProtoDUNE-VD configs; currently just a gitignored `pdvd-wct-sim/` (historical reference, see Top-level layout)
└── js.sh                            # Compiles a jsonnet config to JSON and/or renders its pipeline graph as a PDF, written next to the input file
```

### `wirecell-img-evaluation/blob_viewer`
A `trame`-based live 3D web viewer, independent of the rest of the evaluation pipeline: it renders any `clusters-apa-<N>.tar.gz`/`depos-drifted-<N>.zip` pair (not detector-specific) and streams the scene to a browser over the server's port.

```
wirecell-img-evaluation/blob_viewer/
├── blob_web_server.py                          # Entry point: starts the trame server for a given --blob-file/--depo-file pair
├── blob_web_server_reference.md                 # Reference notes on the server's structure/usage
├── blob_web_server_generalization_plan.md       # Plan for generalizing the viewer beyond its original PDHD-only prototype
├── blob_web_server_generalization_report.md     # Report on the generalization work
└── wirecell_bee_reference.md                    # Reference notes on the Bee 3D event-display format/conventions
```
