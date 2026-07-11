# True Blob 설계 계획 (session plan record)

## Summary

depo 기반 "true blob" 생성 아이디어를 검토하고 실행 계획을 세운 세션의 plan-mode 기록이다.
실제 구현 결과와 코드 설명은 `docs/true_blob_prototype.md`를 참고한다.

## 1. Context & 목적
* **프로젝트 개요**: `wirecell-img-evaluation`은 WCT(Wire-Cell Toolkit) 3D imaging 재구성 결과(blob)의 전하량(charge) 및 위치(position) 정확도를 depo(실제 물리량, ground-truth)와 직접 비교하여 평가하는 프로젝트다.
* **현재 목표**: 재구성된 reco blob과 직접 기하학적으로 비교할 수 있는 "독립적인 true blob"을 depo로부터 생성하는 아이디어를 정립하고 실행 계획을 수립한다.

## 2. 핵심 발견 및 기존 메커니즘 분석

### 2.1 기존 툴킷 내 메커니즘: `BlobDepoFill`
* **위치**: `wire-cell-toolkit/img/src/BlobDepoFill.cxx` (factory명: `BlobDepoFill`)
* **현황**: 이미 `wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet` 파이프라인에 배선되어 `clusters-apa-bdf-<ident>.tar.gz` 형태로 산출물이 존재한다.
  Python 측에서도 `load_graph_nodes(graph, 'b')`를 통해 로드되어 `True Charge` 시각화에 활용 중이다.
* **알고리즘적 제약 (중요)**:
    > `BlobDepoFill`은 새로운 blob을 생성하는 것이 아니라, reco blob의 위치 정보(corner, sliceid 등)를 그대로 재사용한다.
    > 그 내부 공간에 들어오는 depo 전하를 가우시안 적분(시간축은 `extent_long/speed`, yz평면의 pitch축은 `extent_tran`, 나머지 두 평면은 실제 폴리곤 경계와 `RayGrid::Coordinates::ray_crossing` 교차 검증)으로 채워 넣어 전하 필드만 업데이트하는 방식이다 (`slice_and_dice_depos()` 및 메인 `operator()` 로직 기반).
* **결론**: "이 reco blob 자리에 진짜로 있어야 할 전하량"은 검증할 수 있으나(charge 정확도 평가), 모양을 그대로 빌려 쓰기 때문에 **"이 자리에 blob이 실제로 존재하는가" 및 "블롭의 모양·위치(position/size)가 맞는가"는 검증할 수 없다.**

### 2.2 재구성(reco) blob 쪽에서 가용한 데이터
`wirecell-img-evaluation/scripts/utils/load.py`의 `load_graph_nodes(cgraph, 'b')`가 반환하는 blob 노드 딕셔너리는 이미 형상 비교에 필요한 충분한 필드를 들고 있다.
* `corners`: 실제 $y, z$ 좌표로 변환된 폴리곤 꼭짓점 리스트 (`[x_ns, y_mm, z_mm]`)
* `bounds`: 평면별 wire-index 범위
* `start` / `span`: 시간 slice 정보
* `val` / `unc`: 전하량 및 불확정도

> **핵심 과제**: reco blob 쪽 형상 데이터는 준비되어 있으므로, 이에 대응할 수 있는 **depo 기반의 독립적인 true blob(polygon) 생성이 필요**하다.

## 3. 접근 옵션 최종 비교
검증 목표인 **charge**와 **position/shape** 중에서, 현재 단원에서는 **position/shape 검증의 우선순위가 더 높다.** 이를 바탕으로 도출된 3가지 옵션의 특징은 다음과 같다.

| 비교 항목 | 옵션 A (현재 상태 유지) | 옵션 B (Python 기반 독립 폴리곤) | 옵션 C (C++ Tiling 파이프라인 통과) |
| :--- | :--- | :--- | :--- |
| **개요** | 기존 `BlobDepoFill` 산출물 사용 | Python에서 가벼운 기하학적 근사 구현 | `DepoFluxSplat` 생성을 tiling에 주입 |
| **구현 난이도** | 없음 (이미 존재) | 보통 (기하학적 포팅 및 shapely 활용) | 높음 (WCT job graph 확장 및 튜닝 필요) |
| **기하학적 신호도** | 없음 (reco 형상 재사용) | 보통 (RayGrid의 미세 예외 누락으로 근사치) | **최고** (reco와 동일한 기하 엔진/RayGrid 사용) |
| **운영 비용** | 없음 | **낮음** (WCT 재실행 불필요, 순수 분석 코드) | 높음 (WCT job graph 재실행 필요) |
| **검증 가능 범위** | Charge 정확도만 가능 | **Charge + Position/Shape 가능** | **Charge + Position/Shape 가능** |

## 4. 2단계 실행 계획 (최종 방향)

> **전략**: **옵션 B**를 통해 가볍고 빠른 프로토타입을 먼저 구축하여 신속하게 피드백을 얻은 후, **옵션 C**를 구현하여 기하학적 완성도를 높이고 두 결과를 교차 검증한다.

### [Stage1] 옵션 B: depo 기반 true blob 폴리곤 Python 프로토타입 (즉시 착수)
WCT을 재실행할 필요 없이, 이미 만들어진 depo/cluster 데이터 파일만으로 순수 분석 코드를 작성하는 단계다.

#### 활용 가능한 기존 재료
* **가우시안 적분**: `scripts/utils/slicer.py` 내 `Binning`, `gcumulative`, `gbounds`, `gaussian_bins`가 WCT `Binning.h` 로직을 포팅해 둔 상태이므로 이를 그대로 재사용한다.
* **와이어 실제 좌표**: `wirecell.util.wires.schema` 및 `persist` 모듈을 통해 `wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2` 스토어를 로드한다.
  `Store.points[wire.tail]` / `head` 조합으로 3D 끝점 좌표를 즉시 획득할 수 있다.
* **샘플 데이터 & 로더**: `data/pdhd/test_single_trk/`에 `depos-drifted-1.zip`(depo), `clusters-apa-1.tar.gz`(reco), `clusters-apa-bdf-1.tar.gz`(기존 bdf true charge)가 이미 준비되어 있다.
  `scripts/utils/load.py` 함수군으로 로드한다.
* **폴리곤 연산**: `shapely` 라이브러리를 활용한다.

#### 새로 작성할 컴포넌트 (`scripts/utils/true_blob.py` 가칭)
1. **`wire_pitch_index(store, plane, y, z) -> (wire_index, pitch_value)`**
   * 임의의 $(y,z)$ 위치가 어느 wire index와 pitch값에 대응하는지 계산하는 저수준 기하 함수 (`Pimpos` 매핑 로직의 파이썬 대응).
2. **`depo_wire_range(store, plane, depo, nsigma) -> (wire_min, wire_max)`**
   * depo의 pitch 중심과 `extent_tran * nsigma` 연산을 통해 wire-index 구간 도출 (`BlobDepoFill` dice 공식 재사용).
3. **`wire_index_to_line(store, plane, wire_index) -> ((y1,z1),(y2,z2))`**
   * 경계 와이어의 실제 $y-z$ 선분 좌표 반환.
4. **`true_polygon(store, depo, nsigma) -> shapely.Polygon`**
   * 3개 평면의 wire-index 구간을 띠(strip) 폴리곤으로 변환한 뒤, `shapely.intersection()`으로 교차시켜 독립적인 true 폴리곤 생성.
5. **`depo_time_slice(depo, speed, nsigma) -> (t_min, t_max)`**
   * `extent_long/speed`를 이용하여 drift 방향 slice 구간을 계산하고, reco blob의 시간 단위와 동기화.
6. **`true_blob_charge(depo, polygon, slice_range, nsigma) -> float`**
   * `gbounds` 기반 가우시안 가중 전하 적분 수행.
7. **`depo 묶음 전략`**: 초기에는 `depo 1개 = true blob 후보 1개` 성격의 단순 매핑으로 시작하며, 이후 필요에 따라 인접 depo들을 동일 타임 슬라이스(reco의 tick_span 윈도우 등) 기준으로 병합하는 로직을 고도화한다.

#### 비교 지표 및 검증 방법
* **지표**: `shapely`를 활용한 reco 폴리곤과 true 폴리곤 간의 IoU(Intersection over Union), 중심(centroid) 간의 거리, 시간 축 slice 겹침 비율, 전하 상대 오차(기존 bdf 산출물과 비교).
* **방법**: 
  * `test_single_trk`(단일 트랙) 데이터로 2D 폴리곤들을 `matplotlib`로 겹쳐 그려 형상이 깨지거나 무너지지 않고 reco 주변에 올바르게 감싸지는지 육안 검증한다.
    (※ 컨벤션에 따라 `output_dir/filename` 인자 분리 적용)
  * `test_point_depo`(점 depo) 데이터로 확산 시그마만 존재하는 극단적인 점근적 케이스에서의 동작을 최종 확인한다.


### [Stage2] 옵션 C: WCT job graph를 통한 true-tiled blob 직접 생성 (교차검증)

1단계 프로토타입의 기하학적 근사가 실제 RayGrid 엔진 결과와 얼마나 유격이 있는지 검증하고, 향후 가장 정확도가 높은 완성형 Ground Truth 라인을 구축하기 위함이다.

#### 재사용할 기존 컴포넌트
* **Jsonnet 구조**: `wire-cell-cfg/pdhd/img.jsonnet` 내에 선언된 `img.slicing(anode, ...)` 및 `img.tiling(anode, ...)` 캡슐화 함수를 그대로 재사용한다.
  내부적으로 `MaskSlices`와 `GridTiling`(`RayGrid::make_blobs` 기반)을 조합하여 활용한다.
* **true 프레임 생성**: `Gen::DepoFluxSplat` 컴포넌트를 활용하여 노이즈가 없는 깨끗한 물리적 진실(true signal) 프레임을 생성한다.

#### 필요한 새 작업
1. `wct-sim-nf-sp-img-bdf.jsonnet` 내부에 `DepoFluxSplat` 노드를 추가 배치하여 true frame 파이프라인을 형성한다.
2. `MaskSlices`가 요구하는 태그(`wiener_tag`, `charge_tag` 등)를 true frame에 맞춰 매핑한다.
3. **시행착오 및 튜닝**: 기존 슬라이싱 임계값(`nthreshold=3.6`)은 노이즈가 존재하는 실제 신호 기준이므로, 노이즈가 전무한 true frame 가동 시에는 이 임계값을 0에 가깝거나 매우 작은 값으로 조정해야 하므로 데이터 매칭 후 최적화를 진행한다.
4. 기존 reco용 경로와 병렬로 `img.slicing` + `img.tiling`을 연결하여, 완전히 독립적인 true-tiled cluster 파일(`clusters-apa-true-tiled-<ident>.tar.gz`)을 빌드 및 덤프한다.
5. Python 측 로더(`load.py`)는 기존의 `load_cluster_data` 인터페이스를 그대로 활용하여 로드하므로 추가 작업이 없다.

#### 검증 방법
* 1단계에서 구현한 **Python 기반 true 폴리곤**과 2단계에서 추출된 **true-tiled blob의 corners 폴리곤**을 동일 depo 세트상에 오버랩하여 플롯한다.
* 두 폴리곤 간의 IoU 스코어를 기반으로 1단계 근사 알고리즘의 오차 규모(Fake bounds layer 효과, 픽셀 격자화에 따른 수치 편차 등)를 정량화한다.
* 검증이 완료된 이후부터는 이 true-tiled blob을 최상위 ground truth의 기준으로 삼아 reco blob 성능 평가의 벤치마크 지표를 산출한다.