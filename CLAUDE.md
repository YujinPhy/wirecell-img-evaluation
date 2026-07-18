# CLAUDE.md

This file provides project-level guidance, current status, and development rules for Claude Code (claude.ai/code) when operating within this repository.


## 1. Project Overview & Context
* **Purpose**: `wirecell-img-evaluation` evaluates the 3D imaging reconstruction performance (specifically charge and spatial accuracy, algorithms) of the Wire-Cell Toolkit (WCT).
* **Project Nature**: This is a research-notebook style directory containing analysis/plotting driver scripts and large, dated result artifacts rather than a shipped application.
* **Core Goal**: Validate a robust framework by quantitatively analyzing the 3D imaging performance of WCT in ProtoDUNE-HD and ProtoDUNE-VD.
* **Context**: Read @./README.md in this directory first. It is a maintained, factual map of the exact on-disk layout
and a "Known issues" section.This file complements it with run commands and the code architecture; don't duplicate README's directory-by-directory inventory here.


## 2. Project Roadmap & Current Status

### 2.1 WireCell Implementation Part

#### 2.1.1 Write WireCell Configurations with required components

프로젝트에 필요한 데이터 파일을 실질적으로 만드는데 필요한 구성 파일을 만드는 작업.
서버에 `dune_sl7` apptainer 내에서 


### 2.2 Extract Physical Quantities & Visualization

### Stage 1: Python-Based True Blob Prototype 
* **Status**: Successfully implemented a lightweight, pure Python prototype to construct independent true polygons from depo data without re-running WCT jobs.
* **Key Components**:
  * `scripts/utils/true_blob.py`: Core logic mapping depo $t, q, x, y, z, L, T$ fields to 2D polygons using PCA-driven pitch axes and `shapely` intersections.
  * `scripts/utils/vis/true_blob_plots.py`: Spatial overlay and nearest-reco blob matching utilities.
  * `scripts/pdhd_true_blob_check.py`: Validation driver script tested against `test_single_trk` and `test_point_depo` datasets.
* **Known Limitations**:
  * **Time Offset Miscalibration**: A constant offset exists between raw depo time ($t$) and reco blob `start` time, forcing nearest-blob matching to rely purely on spatial centroids for now.
  * **Granularity Differences**: Currently maps `1 depo = 1 true blob candidate`. Future iterations may merge adjacent depos matching the reco `tick_span`.

### Stage 2: WCT Job Graph Tiling Cross-Validation (Next Steps)
* **Objective**: Cross-validate the Stage 1 Python approximations by passing a noise-free true frame generated via `Gen::DepoFluxSplat` through the actual WCT tiling engine (`img.slicing` + `img.tiling`).
* **Tasks**:
  * Integrate `DepoFluxSplat` into `wct-sim-nf-sp-img-bdf.jsonnet`.
  * Tune `MaskSlices` parameters (e.g., lower `nthreshold` close to 0 for noise-free true frames).
  * Export independent `clusters-apa-true-tiled-.tar.gz` and compute IoU against Stage 1 true polygons to quantify geometric approximation errors.

### 2.3 Performance Evaluation




## 3. Strict Development Rules & Constraints

### Wire Geometry API Usage
* **Indirect Reference Model**: Always respect the `Store` flat repository pattern. `Wire.tail` and `Wire.head` are integer indices pointing to `store.points`, not direct `Point` objects. Retrieve actual 3D endpoints via `store.points[wire.tail]`.
* **Ordering Guarantees**: Rely on `face.planes` for sequential U/V/W drift ordering and `plane.wires` for increasing pitch ordering.
* **PCA for Pitch Axes**: Do not calculate pitch orientation using only the first and last wire midpoints (due to trapezoidal boundary biases). Always apply PCA to all wire midpoints within the plane.

### Testing & Validation Framework
* **No Automated Test Runner**: There is no installed test runner (`pytest`) or CI pipeline configured for this directory.
* **Manual Verification Requirement**: Validate any code change by re-running the relevant numbered study or check script (e.g., `scripts/pdhd_true_blob_check.py`) against sample data.
* **Output Inspection**: Explicitly inspect the resulting visual plots, ROOT histograms, or HDF5 output structures to confirm that the geometry and charge variables are mathematically sound and uncorrupted.