# WCT `img` 3D Imaging Pipeline Overview

## Summary

`../wire-cell-toolkit/img/`은 2D 채널x시간 파형(`IFrame`)을 3D 공간 객체(`IBlob`)와 그 시공간 클러스터(`ICluster`)로 변환하고, 전하량을 풀고(charge solving), 유령(ghost) 아티팩트를 제거하는 파이프라인을 구현한다. 이 문서 시리즈는 `../wire-cell-toolkit/img/docs/examinations/*.md`(코드 리뷰 산출물)와 실제 소스(`img/src/`, `img/inc/WireCellImg/`, `util/src/RayTiling.cxx`)를 교차 확인하여 정리한 것이다. 확인 결과 examinations 문서에 "Status: FIXED"로 표기된 항목들은 현재 체크아웃된 소스에 실제로 반영되어 있다(`04_constants_and_caveats.md` 참조).

문서 구성:
- `00_pipeline_overview.md` (본 문서): 전체 파이프라인, 핵심 데이터 구조, 이 저장소(`wirecell-img-evaluation`)의 실제 설정 예시.
- `01_slicing_and_tiling.md`: `MaskSlice`/`SumSlice` -> `RayGrid`/`GridTiling` -> `BlobGrouping`/`BlobClustering`/`GeomClusteringUtil`.
- `02_charge_solving.md`: `ChargeSolving`/`CSGraph`의 LASSO 기반 전하 분배.
- `03_deghosting.md`: `InSliceDeghosting`/`Projection2D`/`ProjectionDeghosting`/`ShadowGhosting`.
- `04_constants_and_caveats.md`: 하드코딩 상수, 과거 버그(수정 확인됨), 효율성 이슈 — 코드를 읽거나 PDHD로 튜닝할 때 주의할 점 모음.

---

## 1. 파이프라인 데이터 흐름

```
IFrame (channel x time)
   |  MaskSlice / SumSlice   ->  tick_span개의 tick을 하나로 묶음
   v
ISlice (channel -> (charge, uncertainty))
   |  GridTiling (RayGrid::make_blobs)
   v
IBlob (평면별 활성 와이어 교차로 정의되는 3D 영역, per-slice per-face)
   |  BlobGrouping (측정 노드 추가) + BlobClustering (slice간 b-b 엣지)
   v
ICluster (cluster_graph_t: 's','b','m','w','c' 노드 그래프)
   |  ChargeSolving (LASSO, CSGraph::unpack/solve/prune/repack)
   v
ICluster (blob마다 풀린 전하값)
   |  InSliceDeghosting (per-slice) / ProjectionDeghosting (global, Projection2D 기반)
   v
ICluster (ghost 제거된 최종 클러스터) -> ClusterFileSink 등 출력
```

각 화살표는 별도의 `IConfigurable`/`INamed` 컴포넌트(jsonnet에서 `type` 필드로 지정)이며, 그래프 파이프라인(`pgraph.jsonnet`)으로 직렬 연결된다.

---

## 2. 핵심 데이터 구조

### `ISlice` (`iface/inc/WireCellIface/ISlice.h`)
- 하나의 시간창(time slice)에 대한 채널 활동 맵: `map_t = unordered_map<IChannel::pointer, value_t>`, `value_t = Measurement::float32` (값 + 불확실성).
- `start()`/`span()`: 프레임 시작 시각 기준 절대/상대 시간 폭. `span() = tick x tick_span` (`docs/img_time_slicing_reference.md` 참조).
- `MaskSlice`/`SumSlice`가 생성.

### `RayGrid` 프레임워크 (`util/inc/WireCellUtil/RayGrid.h`, `RayTiling.h`)
- 각 와이어 평면을 "층(layer)"으로, 평면 내 각 와이어를 그 층의 "격자 인덱스(grid index)"를 갖는 평행한 광선(ray)으로 모델링.
- `layer 0, 1`은 항상 애노드 면(face)의 가로/세로 경계(bounding box)를 나타내는 예약된 층이고, `layer 2..`부터가 실제 와이어 평면(U/V/W)이다 (`GridTiling.cxx:93-94`의 `nbounds_layers = 2`).
- `Strip{layer, bounds}`: 한 층 안에서 활성 상태인 격자 인덱스의 연속 구간(반열림 구간 `[first, second)`).
- `Blob`: 여러 층의 `Strip`들의 교집합. `corners()`는 모든 strip에 동시에 포함되는 층-쌍 교차점들.
- 자세한 blob 생성 알고리즘은 `01_slicing_and_tiling.md` §3 참조.

### `IBlob` (`iface/inc/WireCellIface/IBlob.h`)
- `value()`/`uncertainty()`: 전하값과 그 불확실성. `uncertainty()`는 초기에는 채워지지 않다가(`GridTiling`은 `blob_value = 0.0`으로 생성) `ChargeSolving`이 값을 채운다.
- `shape()`: `RayGrid::Blob` (strip 목록 + corner 목록).
- `slice()`/`face()`: 소속 시간창과 애노드 면.

### `ICluster` / `cluster_graph_t` (`iface/inc/WireCellIface/ICluster.h`)
- `boost::adjacency_list<setS, vecS, undirectedS, cluster_node_t>`. 노드는 `std::variant`로 5종류를 표현하고 문자 코드로 식별:

| 코드 | 타입 | 의미 |
|---|---|---|
| `c` | `IChannel::pointer` | 물리적 채널 |
| `w` | `IWire::pointer` | 와이어 |
| `b` | `IBlob::pointer` | blob |
| `s` | `ISlice::pointer` | 시간창 |
| `m` | `IMeasure::pointer` | 평면별로 묶인 "측정값" (전기적으로 연결된 blob-channel 그룹의 신호 합) |

- 엣지는 소속/연결 관계를 나타낸다: `b-s` (blob이 어느 slice에 속함), `b-w` (blob이 어느 와이어를 덮음), `w-c` (와이어가 어느 채널인지), `b-m` (blob이 어느 measure에 기여), `b-b` (인접 시간창 blob 사이의 기하학적 겹침, `BlobClustering`이 생성).
- 하나의 `ICluster`는 보통 한 프레임 전체에 걸친 그래프이며, 여러 프레임에 걸칠 수도 있다(주석: "may span less than, more than or exactly one IFrame").

### `CS::graph_t` (`img/inc/WireCellImg/CSGraph.h`)
- `ChargeSolving` 내부에서만 쓰이는 bipartite 그래프(blob, measure 노드만). `cluster_graph_t`를 slice 단위 + connected-component 단위로 쪼갠 것 (`CS::unpack`). 각 노드는 `value_t`(값+불확실성)와 `ordering`(원본 그래프로 되돌리기 위한 인덱스)을 가진다. 자세한 내용은 `02_charge_solving.md`.

### `Projection2D` (`img/inc/WireCellImg/Projection2D.h`)
- 한 클러스터(연결된 blob 그룹)를 하나의 평면 위 (channel x time-slice) Eigen 희소 행렬로 투영한 것. Deghosting에서 두 클러스터의 "덮음(coverage)" 관계를 판정하는 데 쓰인다. `03_deghosting.md` 참조.

---

## 3. 이 저장소의 실제 설정: `wire-cell-cfg/pdhd/img.jsonnet`

`img.jsonnet`은 위 파이프라인을 PDHD APA 하나에 대해 조립하는 jsonnet 함수들의 모음이다. 실제 컴포넌트 나열 순서를 보면 examinations 문서의 일반적 서술("InSliceDeghosting 먼저, ProjectionDeghosting 나중")과 이 저장소의 `"full"` 파이프라인 순서가 다르다는 점이 드러난다:

```jsonnet
// img.jsonnet: solving(anode, aname, solving_type="full")
g.pipeline([bc, gd1, cs1, ld1, gd2, cs2, ld2, cs3, ld3, gc], "uboone-solving")
```

여기서:
- `bc` = `BlobClustering` (slice간 b-b geometric edge 생성, tiling 직후 첫 클러스터 그래프 구성)
- `gd1`/`gd2` = `ProjectionDeghosting` ("global_deghosting")
- `cs1`/`cs2`/`cs3` = `solving()` 함수가 반환하는 `[BlobGrouping, ChargeSolving(uniform), LocalGeomClustering, ChargeSolving(uboone)]` 4단계 서브파이프라인 (이름은 하나지만 내부에 2번의 `ChargeSolving` 호출을 포함)
- `ld1`/`ld2`/`ld3` = `InSliceDeghosting` ("local_deghosting", `config_round`가 1/2/3으로 증가)
- `gc` = `GlobalGeomClustering`

**순서가 이렇게 되는 이유**: `ProjectionDeghosting`(`Projection2D::get_projection`)은 blob의 solved charge가 아니라 **slice의 raw 채널 활동값(activity)**을 투영에 사용한다(`03_deghosting.md` §2). 따라서 `ChargeSolving`이 아직 돌기 전에도 실행 가능하다. 반면 `InSliceDeghosting`은 `iblob->value()` (solved charge)로 "good blob" 여부를 판정하므로 반드시 `ChargeSolving` **뒤에** 와야 한다. 즉 실제 실행 순서는:

```
BlobClustering -> ProjectionDeghosting(raw activity 기반)
   -> ChargeSolving(uniform) -> LocalGeomClustering -> ChargeSolving(uboone)
   -> InSliceDeghosting(solved charge 기반)
   -> ProjectionDeghosting -> ChargeSolving x2 -> InSliceDeghosting   (config_round=2로 반복)
   -> ChargeSolving x2 -> InSliceDeghosting                          (config_round=3으로 반복)
   -> GlobalGeomClustering
```

세 라운드에 걸쳐 "global(투영 기반) 정리 -> 전하 재추정 -> local(slice 내) 정리"를 반복하며 `config_round`를 늘려가는 구조다. `ld1/ld2/ld3`가 서로 다른 `config_round`를 받는 것으로 보아 `InSliceDeghosting`이 라운드마다 다른 판정 로직/임계값을 쓸 가능성이 있으므로(`InSliceDeghosting.h`의 `m_config_round` 사용처), 실제 튜닝 시 `img/src/InSliceDeghosting.cxx`에서 `m_config_round` 분기를 직접 확인할 것.

또한 `tiling()` 함수는 face마다 `GridTiling`을 하나씩 돌리고(`face in [0,1]`) `SliceFanout`/`BlobSetSync`로 합치는 구조이며, PDHD APA는 face가 2개(하나는 냉동고 벽을 향한 비민감면일 수 있음 — `01_slicing_and_tiling.md` §4의 `sensitive().empty()` 분기 참조)이다.

---

## 4. 읽는 순서 제안

1. `01_slicing_and_tiling.md`로 RayGrid의 기하학적 blob 생성 알고리즘부터 이해한다 (가장 기초).
2. `02_charge_solving.md`로 넘어가 왜 LASSO가 필요한지(같은 와이어를 여러 blob이 공유하는 문제, 즉 그 자체가 ghost의 원인)를 이해한다.
3. `03_deghosting.md`에서 charge solving만으로 못 없애는 ghost를 어떻게 추가로 걸러내는지 본다.
4. `04_constants_and_caveats.md`는 참고용 레퍼런스로 두고, PDHD 설정 튜닝 시 필요할 때마다 찾아본다.

---

## Related Documents

- [01_slicing_and_tiling.md](./01_slicing_and_tiling.md): Frame -> Slice -> Blob 단계 상세.
- [02_charge_solving.md](./02_charge_solving.md): LASSO 기반 전하 분배 상세.
- [03_deghosting.md](./03_deghosting.md): Ghost 제거 알고리즘 상세.
- [04_constants_and_caveats.md](./04_constants_and_caveats.md): 하드코딩 상수/버그이력/효율성 노트.
- [../img_time_slicing_reference.md](../img_time_slicing_reference.md): `ISlice.span()`이 어떻게 결정되는지에 대한 이 저장소의 기존 분석 (본 시리즈와 상호보완적).
