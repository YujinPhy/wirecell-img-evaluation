# True Blob Prototype (depo 기반 ground-truth blob 생성)

## Summary
재구성된 blob(`utils.load.load_graph_nodes(cgraph, 'b')`)과 직접 비교할 수 있는 "true blob"을 depo 데이터만으로 독립적으로 만드는 1단계(Python 프로토타입) 작업의 기록이다.

`docs/true_blob_plan.md`에서의 Stage 1 계획의 구현을 정리한 문서로, position/shape 정확도까지 검증하기 위한 독립적인 true blob을 새로 만드는 실제 구현과 코드 설명, 구현 중 발견한 버그, 검증 결과를 정리한다.


## 1. 배경

WCT에서 blob은 세 평면(U/V/W)의 와이어 구간 교차로 정의되는 2D 폴리곤(y-z)과 시간 slice(드리프트 방향 두께)로 구성된 3D 영역이다.
depo는 이온화 전하 침착점 하나를 나타내는 점(위치 x,y,z)과 부가 정보(시간 t, 전하 q, 종/횡 확산 시그마 L/T)로 구성된다(`docs/wirecell_depo_reference.md` 참고).
depo는 원래 점이고 blob은 영역이기 때문에, depo를 blob과 같은 형태(폴리곤 + 시간 slice)로 변환해야 두 그레인 사이에서 직접 비교(IoU, 중심 거리, 전하 오차)를 할 수 있다.
이 변환을 담당하는 것이 이번에 만든 `true_blob` 모듈이다.


## 2. 파일 구성

| 파일 | 역할 |
|---|---|
| `scripts/utils/wires.py` | wire store JSON을 읽어 평면별 pitch 축과 "띠(strip)" 폴리곤을 만드는 `PlaneGeometry`/`build_plane_geometries`, 그리고 감지 영역 경계를 근사하는 `face_sensitive_bounds` (`docs/wires_geometry_walkthrough.md`, §5.4) |
| `scripts/utils/true_blob.py` | depo 하나로부터 true blob(폴리곤/시간 slice/전하)을 만드는 핵심 로직 |
| `scripts/utils/eval/position_shape.py` | true blob과 reco blob을 비교하는 평가 지표(IoU/중심거리/시간 겹침/전하 오차) 함수 (`docs/position_shape_evaluation.md`) |
| `scripts/utils/vis/true_blob_plots.py` | true blob과 reco blob을 겹쳐 그리는 시각화 함수, 두 blob을 짝짓는 `nearest_reco_blob` |
| `scripts/pdhd_true_blob_check.py` | `test_point_depo`, `test_single_trk` 샘플 데이터로 위 로직을 실행하고 통계/플롯을 출력하는 검증 드라이버 스크립트 |


> `scripts/utils/wires.py`(`PlaneGeometry`/`build_plane_geometries`)의 코드 설명은 `docs/wires_geometry_walkthrough.md`로 옮겼다.
> 단일 point depo 하나를 예시로 각 메서드의 실제 계산값을 따라가는 문서이며, 이 문서(§5.1, §5.2)가 다루는 두 가지 버그의 배경도 함께 정리돼 있다.

## 3. `scripts/utils/true_blob.py` 코드 설명

### 3.1 depo 하나 → true blob 변환 함수들

`plane_geoms`는 어느 함수에서건 `utils.wires.build_plane_geometries`가 만든 `PlaneGeometry` 리스트(평면 0, 1, 2 순서)를 그대로 받는다(`docs/wires_geometry_walkthrough.md` 참고).

**`true_blob_polygon(plane_geoms, y, z, extent_tran, nsigma=3.0, sensitive_bounds=None)`** — depo 하나의 (y,z) 폴리곤을 만든다.

`plane_geoms`를 순서대로(U, V, W) 순회하며, 각 평면에 대해 `pg.pitch_of(y, z)`로 depo의 pitch 중심을 구한 뒤, `pg.wire_index_range(center - nsigma*extent_tran, center + nsigma*extent_tran)`로 `center ± nsigma*extent_tran` 두 경계 지점 각각에 가장 가까운 wire index `(imin, imax)`를 구하고, `pg.strip_polygon(pg.pitch_vals[imin], pg.pitch_vals[imax])`처럼 그 wire들의 실제 pitch 좌표로 띠를 만든다(연속적인 nsigma 좌표를 실제 wire 위치에 스냅하는 이유는 §5.5 참고).
첫 번째 평면의 띠를 초기 `polygon`으로 삼고, 이후 평면의 띠와 `polygon.intersection(strip)`으로 누적 교차시킨다.
교차 도중 `polygon.is_empty`가 참이 되면(즉 지금까지 처리한 평면들의 띠가 이미 겹치지 않으면) 남은 평면을 처리하지 않고 즉시 `None`을 반환한다.
세 평면 모두 교차에 성공하면, `sensitive_bounds`가 주어진 경우 그 박스와 한 번 더 `polygon.intersection(sensitive_bounds)`으로 교차시킨 뒤(역시 비면 `None`) 최종 폴리곤을 반환한다.
`sensitive_bounds`는 기본값이 `None`이라 생략하면 기존과 동일하게 동작하며, 무엇을 클리핑하는 것이고 왜 필요한지는 §5.4에서 다룬다.

**`true_blob_time_slice(t, extent_long, speed, nsigma=3.0)`** — depo 하나의 시간 slice 구간을 만든다.

`extent_long`(거리 단위 확산 시그마)을 `speed`(드리프트 속도)로 나눠 시간 단위 시그마 `tsigma`로 바꾸고, `(t - nsigma*tsigma, t + nsigma*tsigma)`를 반환한다.
이 변환은 WCT의 `Gen::DepoFluxSplat`/`Img::BlobDepoFill`이 쓰는 것과 같은 관례(거리 시그마를 드리프트 속도로 나눠 시간 시그마로 바꾸는 것)를 따른다.

**`true_blob_charge(charge, t, extent_long, speed, tmin, tmax)`** — 시간 slice 안에 남는 전하량을 계산한다.

`true_blob_time_slice`와 동일한 공식으로 `tsigma`를 다시 계산한 뒤(이 함수 자체는 `true_blob_time_slice`를 호출하지 않고 별도로 계산한다), `scripts/utils/slicer.py`의 `gbounds(tmin, tmax, t, tsigma)`(가우시안 구간 적분, WCT `Binning.h`의 파이썬 포팅)로 `[tmin, tmax]` 구간 안에 남는 가우시안 질량의 비율을 구하고, 이를 `abs(charge)`에 곱한다.
`charge`에 절댓값을 취하는 이유는 depo 전하의 부호 관례(전자를 음수로 두는 경우 등)와 무관하게 항상 양의 전하량을 돌려주기 위해서다.
(y,z) 폴리곤 쪽에는 별도의 가우시안 가중치를 곱하지 않는다.
true blob은 정의상 depo 하나만 담당하므로(1 depo = 1 true blob 후보), `BlobDepoFill`처럼 여러 blob에 전하를 나눠 배분할 필요가 없고, nsigma 컷오프로 잘려나가는 꼬리만 시간축에서 `gbounds`로 보정하면 충분하다고 판단했다.

**`build_true_blob(plane_geoms, t, y, z, charge, extent_long, extent_tran, speed, nsigma=3.0, sensitive_bounds=None)`** — 위 세 함수를 묶어 depo 하나의 true blob을 완성한다.

`true_blob_polygon`으로 폴리곤을, `true_blob_time_slice`로 `(tmin, tmax)`를, `true_blob_charge`로 전하량을 각각 구한 뒤, `{"polygon": polygon, "start": tmin, "span": tmax - tmin, "charge": charge_val}` 딕셔너리로 묶어 반환한다.
`start`/`span`/`charge` 키 이름은 reco blob 노드의 `start`/`span`/`val` 필드와 나란히 비교할 수 있도록 맞춘 것이다.
`sensitive_bounds`는 그대로 `true_blob_polygon`에 전달된다.

**`build_true_blobs(plane_geoms, depos, speed, nsigma=3.0, sensitive_bounds=None)`** — depo 여러 개에 대해 `build_true_blob`를 반복 호출한다.

`depos`는 `utils.load.load_generation_data`가 반환하는, 키(`t`,`q`,`x`,`y`,`z`,`L`,`T`)별로 값이 배열로 들어 있는 딕셔너리다.
`depos["t"]`의 길이만큼 인덱스를 순회하며 매 인덱스에서 `t`,`y`,`z`,`q`,`L`,`T` 값을 뽑아 `build_true_blob`를 호출하고, 결과 딕셔너리를 리스트에 모아 반환한다.
`sensitive_bounds`가 주어지면 모든 depo에 동일하게 적용된다(같은 anode face의 depo라면 face마다 한 번만 계산하면 되므로).


> true blob과 reco blob을 비교하는 `reco_blob_polygon`/`compare_true_to_reco`는 blob을 만드는 로직이 아니라 평가 지표를 계산하는 로직이라, `scripts/utils/eval/position_shape.py`로 분리했다.
> 자세한 코드 설명은 `docs/position_shape_evaluation.md`를 참고한다.

## 4. `scripts/utils/vis/true_blob_plots.py` 코드 설명

`nearest_reco_blob(true_blob, reco_blobs)`는 하나의 true blob과 가장 가까운 reco blob을 찾는다.
처음에는 시간 slice가 가장 많이 겹치는 blob을 찾도록 만들었지만, 실제로 실행해 보니 이 저장소에서는 depo의 원본 시간(`t`)과 reco blob의 `start` 시간 사이에 알려진(그러나 아직 보정되지 않은) 오프셋이 있어서 이 방식이 항상 실패했다(§5.3).
그래서 현재 구현은 두 폴리곤의 중심(centroid) 사이 거리로 가장 가까운 reco blob을 찾는, 시간축과 무관한 방식으로 바꿨다.

**`plot_depo_heatmap_tran_ax(ax, y, z, extent_tran, nsigma=3.0)`** — depo의 진짜(스냅 전) nsigma 경계를 검정 배경 위에 (Z, Y) 윤곽선으로 그린다.

처음에는 등방(isotropic) 2D 가우시안 밀도 $\rho(y,z) = \frac{|charge|}{2\pi\sigma_T^2}\exp\left(-\frac{(y-y_0)^2+(z-z_0)^2}{2\sigma_T^2}\right)$를 `pcolormesh`로 채워 그리는 연속 히트맵이었지만, 이제는 `ax.set_facecolor("black")`으로 axes 전체 배경을 검정으로 칠하고, `true_blob_polygon`이 실제로 자르는 원래(스냅 전) nsigma 경계를 `fill=False`인 흰색 점선 원으로만 그린다.
내부를 채우지 않기 때문에, 그 위에 겹쳐 그려지는 true blob/reco blob 폴리곤과 뒤섞이지 않고 depo의 "진짜" 경계가 실루엣처럼 또렷하게 보인다.
depo 중심에는 빨간 `+` 마커를 찍는다.

`plot_true_vs_reco_tran_ax(ax, true_polygon, reco_blob_node, depo=None, margin=5.0)`는 `utils.vis.transverse_plots`와 같은 (Z, Y) 축 관례로 true/reco 두 폴리곤을 한 axes에 겹쳐 그린다.
`depo`(`{"y", "z", "extent_tran"}` 딕셔너리)가 주어지면, 폴리곤을 그리기 전에 `plot_depo_heatmap_tran_ax`로 그 depo의 검정 배경 + 경계선을 먼저 그린다.
일반 `Polygon` patch는 matplotlib이 자동으로 축 범위를 맞춰주지 않는 경우가 있어서, 그려질 점들의 bounding box를 직접 계산해 `set_xlim`/`set_ylim`으로 명시적으로 맞춘다.

`plot_true_vs_reco_check(true_blobs, reco_blobs, depo_indices, output_dir, filename, depos=None)`는 지정한 depo 인덱스들에 대해 위 함수를 반복 호출해 한 장의 그림(서브플롯 여러 개)으로 저장한다.
`depos`(`utils.load.load_generation_data`가 반환하는 것과 같은 배열 딕셔너리, `true_blobs`를 만들 때 쓴 것)가 주어지면, 각 서브플롯의 `idx`에 해당하는 `y`/`z`/`T` 값을 뽑아 `depo` 딕셔너리로 만들어 `plot_true_vs_reco_tran_ax`에 전달한다 — 생략하면(기본값 `None`) 검정 배경/경계선 없이 기존과 동일하게 동작한다.
저장은 프로젝트 공용 헬퍼 `utils.vis.plot_utils.save_and_show`(output_dir/filename 분리)를 그대로 재사용한다.

## 5. 구현 중 발견한 문제와 수정

### 5.1 cluster graph의 wire 노드는 너무 희소하다

`utils.load.load_graph_nodes(cgraph, 'w')`로 얻은 wire 노드는 이미 실제 (x,y,z) 좌표(`tail`/`head`)를 담고 있어서, 별도의 wire store 파일 없이도 기하 정보를 얻을 수 있어 보였다.
하지만 실제로 확인해 보니 cluster graph는 그 이벤트에서 재구성된 blob 경계에 실제로 쓰인 와이어만 담고 있어(전체 평면 와이어 수의 일부, 예: plane2는 480개 중 극히 일부), depo의 nsigma 구간(수 mm)에 맞는 세밀한 인접 와이어 조회에 쓰기엔 간격이 너무 불규칙했다.
이 때문에 처음 버전은 5000개 depo 중 4423개(약 88%)에서 세 평면 띠의 교집합이 비어버리는 문제가 있었다.
해결: 전체 wire store JSON(`wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2`)에서 `wirecell.util.wires.persist`/`schema`로 평면의 모든 와이어를 읽어오도록 `build_plane_geometries`를 다시 작성했다.

### 5.2 와이어 끝점으로 만든 "띠"가 실제로는 점을 포함하지 못했다

전체 wire store로 바꾼 뒤에도 여전히 5000개 중 4414개(약 88%)가 빈 폴리곤이었다.
원인은 두 가지가 겹쳐 있었다.
첫째, pitch 축을 "첫 와이어 중점 → 마지막 와이어 중점"으로 구했는데, 평면 가장자리의 짧은 와이어는 중점이 와이어 방향으로도 밀려 있어 이 축이 실제 pitch 방향과 어긋났다.
둘째, 각 평면의 "띠" 폴리곤을 경계 와이어 두 개의 실제 tail/head 끝점 4개의 convex hull로 만들었는데, 와이어 자체가 검출기 전체 길이에 걸친 대각선이어서 이 convex hull이 depo 주변의 좁은 국소 영역이 아니라 평면 전체 크기의 거대한 대각 띠가 되었고, 두 평면(U,V)을 교차시킨 결과가 depo의 실제 z 위치(약 1353mm)와 전혀 다른 곳(약 1202~1214mm)에 생겨, 세 번째 평면(W)의 띠와 교집합이 없어져 버렸다.
해결: pitch 축을 모든 와이어 중점에 대한 PCA(주성분 방향)로 구하도록 바꾸고, "띠" 폴리곤은 실제 와이어 끝점을 쓰지 않고 pitch 축/wire 축과 pitch 구간값만으로 아주 긴(±100km) 사각 밴드를 직접 만들도록 바꿨다.
수정 후에는 5000개 depo 전부에서 폴리곤이 성공적으로 만들어졌고, 폴리곤 중심이 depo의 실제 (y,z)와 소수점 이하 오차로 일치했다.

### 5.3 depo 시간과 reco blob 시간 사이의 오프셋 (해결됨)

true blob의 시간 slice를 reco blob의 `start`/`span`과 직접 겹침 비교했더니, 모든 depo-blob 쌍에서 겹침이 없었다(항상 초기값 -1.0보다 작은 음수).
원인은 depo의 원본 시간과, `DepoTransform`의 `start_time` 설정 등으로 프레임 시간축에 흡수되는 reco blob의 `start` 시간 사이에 상수 오프셋이 존재하기 때문이다.
이 저장소의 git 이력(`Add point depo time offset fine tuning`, `need to check time offset or difference b/w depos and blobs`)에서 이미 이 문제가 별도로 다뤄지고 있는 것을 확인했다.
이 작업 당시에는 이 오프셋을 보정하지 않고, true blob과 reco blob을 짝짓는 기준을 시간 겹침 대신 폴리곤 중심 거리로 바꿔 이 문제를 우회했다.

이 오프셋은 이후 `[[time_offset_calibration|docs/time_offset_calibration.md]]`에서 원인 분석과 calibration을 거쳐 해결됐다.
`tick0_time`(DAQ/G4-clock 관례)과 `response_plane/drift_speed`(response plane 도달 시간)로부터 계산되는 analytic baseline($312.5us$, PDHD 기준)에, signal processing 단계(`OmnibusSigProc`의 `ctoffset`/`intrinsic_time_offset` 재인덱싱)에서 오는 작은 residual($+1.4us$)을 더한 값이 실제 필요한 offset과 $0.6us$ 이내로 일치함을 확인했다(`docs/time_offset_calibration.md` §6).
`scripts/pdhd_true_blob_check.py`는 이제 이 calibrated offset(`TIME_OFFSET`)을 depo 시간에 적용한 뒤 true blob을 생성하며, `time_overlap_frac`이 더 이상 항상 음수가 아니라 의미 있는 양의 값(평균 $0.405$)을 낸다.
`charge_rel_error`는 여전히 §7의 "그레인 차이"/"전하 가중치 단순화" 한계와 얽혀 있어 별도 개선이 필요하다.

### 5.4 세 평면 교차만으로는 부족했다 — 감지 영역 경계 누락 (해결됨)

`true_blob_polygon`은 U/V/W 세 평면의 띠(strip)만 교차시켜 폴리곤을 만든다.
그런데 `PlaneGeometry.strip_polygon`(`docs/wires_geometry_walkthrough.md` §6) 자체는 pitch 방향으로만 잘리고 wire 축 방향으로는 $\pm100km$인, 사실상 무한한 밴드다.
따라서 depo가 감지 영역(sensitive volume) 경계 근처에 있으면, 세 평면 교차만으로 만든 폴리곤이 검출기 물리적 범위 바깥까지 확장될 수 있다.
이는 실제 reco blob은 절대 가질 수 없는 형태라, 경계 근처 depo에서는 true blob과 reco blob의 모양 비교가 체계적으로 왜곡될 수 있다.

이 누락을 확인하기 위해 `wire-cell-toolkit/img/`, `wire-cell-toolkit/util/`, `wire-cell-toolkit/gen/`의 실제 blob 타일링 코드를 분석했다.
실제 WCT blob은 3개 wire-plane 레이어뿐 아니라, anode face의 물리적 감지 영역을 나타내는 2개의 합성("bounds") ray-grid 레이어와도 반드시 교차한다.

* `wire-cell-toolkit/gen/src/AnodeFace.cxx`의 `get_raypairs(const BoundingBox& bb, const IWirePlane::vector& planes)`가 face의 `BoundingBox`로부터 수평($Y$-extent)/수직($Z$-extent) ray-pair 2개를 만들어, wire-plane들의 ray-pair보다 앞자리(레이어 0, 1)에 놓는다.
* `wire-cell-toolkit/img/src/GridTiling.cxx`는 `nbounds_layers=2`로 이 두 레이어를 항상 "활성" 상태(전체 박스 하나짜리 strip, `measures[0].push_back(1); measures[1].push_back(1)`)로 취급하고, 실제 wire-plane 레이어는 인덱스 `nbounds_layers + planeid.index()`로 그 뒤에 이어붙인다.
* `wire-cell-toolkit/util/src/RayTiling.cxx`의 `make_blobs()`는 이 5개(bounds 2개 + wire-plane 3개) 레이어의 activity를 `Tiling::operator()`로 순차 교차시켜 최종 blob을 만든다.
  부동소수점 오차 보정용 `nudge` 톨러런스는 실제 wire-plane 레이어(`layer >= 2`)에만 적용되고, 두 bounds 레이어는 별도 톨러런스 없이 정확한 기하 클리핑만 받는다.

즉 실제 WCT blob은 수학적으로 $(y\text{-bound}) \cap (z\text{-bound}) \cap U \cap V \cap W$이며, 항상 anode face의 물리적 감지 영역 안으로 클리핑된다.

**해결**: 이 클리핑을 재현하기 위해 `scripts/utils/wires.py`에 새 함수를 추가했다.

**`face_sensitive_bounds(wire_store_path, anode_index, face_index)`** — anode face의 감지 영역 $(y, z)$ 바운딩 박스를 근사한다.

face에 속한 3개 평면 모든 와이어의 tail/head 끝점 $(y, z)$ 좌표 전체의 합집합으로 axis-aligned bounding box(`shapely.geometry.box`)를 만들어 반환한다.
C++가 쓰는 진짜 `BoundingBox`는 wire store JSON이 아니라 검출기 Jsonnet geometry 설정에서 anode face 생성자에 별도로 주입되므로, 이 wire store 파일만으로는 얻을 수 없다.
와이어가 감지 영역 가장자리까지 촘촘히 채워져 있다는 사실에 기대어 근사한 값이며, 정확한 재현은 아니지만 가까운 근사치다.

`true_blob_polygon`(및 이를 감싸는 `build_true_blob`/`build_true_blobs`)은 새 인자 `sensitive_bounds`(기본값 `None`)를 받아, 세 평면 교차 결과를 이 박스와 한 번 더 교차시킨다(§3.1).
교집합은 교환·결합법칙이 성립하므로, bounds 레이어를 먼저 교차시키는 C++ 순서와 나중에 교차시키는 이 구현의 순서는 최종 폴리곤에 차이를 만들지 않는다.
`scripts/pdhd_true_blob_check.py`는 이제 `face_sensitive_bounds`로 계산한 박스를 `build_true_blobs`에 전달한다.

**결과**: PDHD anode 1/face 1에 대해 `face_sensitive_bounds`가 계산한 박스는 $y \in [76.10, 6066.70]mm$, $z \in [-1.00, 2305.73]mm$이다.
`test_single_trk` 샘플(depo 5000개, 모두 감지 영역 안쪽에 위치)은 이 클리핑을 적용해도 폴리곤이 하나도 바뀌지 않았다 — 즉 §6의 검증 결과(IoU/중심거리 등)에는 영향이 없다.
경계 근처 효과를 직접 확인하기 위해 $(y, z) = (6061.7, 1152.4)mm$($y$ 최대 경계 $6066.70mm$ 바로 안쪽), $extent\_tran = 5mm$인 합성 depo로 테스트한 결과, 클리핑 없이는 폴리곤이 $y = 6076.67mm$까지 확장돼 면적이 $878.8mm^2$였지만, `sensitive_bounds`를 적용하면 실제 경계인 $y = 6066.70mm$에서 정확히 잘려 면적이 $625.6mm^2$(약 29% 감소)로 나왔다.
감지 영역 경계 밖으로 확장되지 않도록 정확히 클리핑되는 것을 확인했다.
(§5.5/§5.6에서 strip 경계를 wire 위치에 스냅하는 로직을 추가한 뒤에는, pitch축 방향으로는 wire 자체가 이미 감지 영역을 벗어나지 않으므로 이 클리핑의 영향이 다소 줄었지만, 위 예시처럼 pitch 축이 $y$/$z$ 축과 정렬돼 있지 않은 평면에서는 여전히 유효하게 작동한다.)

### 5.5 strip 경계가 실제 wire 위치에 스냅되지 않았다 (해결됨)

`true_blob_polygon`은 각 평면의 strip 경계로 depo의 연속적인 pitch 좌표(`center ± nsigma*extent_tran`)를 그대로 썼다.
이 값은 wire 간격과 무관한 임의의 실수이므로, 어떤 depo의 nsigma 경계는 예를 들어 "270번과 271번 wire 사이"처럼 두 wire의 정중앙에 놓일 수도 있었다.

실제 WCT의 RayGrid 타일링에서는 blob의 각 평면 방향 경계가 항상 특정 wire의 물리적 선(ray)이다.
`Strip`(`wire-cell-toolkit/util/inc/WireCellUtil/RayGrid.h`)의 경계는 두 개의 wire-ray 인덱스 쌍으로 정의되고, 폴리곤의 꼭짓점은 이 인덱스에 대응하는 실제 wire 선과 다른 평면의 wire 선이 교차하는 점이다.
wire(채널)는 그 위치를 지나는 전하를 하나의 값으로 집적해서 읽는 이산적인 검출 단위이므로, 물리적으로 "wire 270.3에서 시작하는 blob" 같은 결과는 애초에 나올 수 없다 — reco blob의 경계는 항상 wire 270 아니면 271, 둘 중 하나다.
`scripts/utils/wires.py`의 `PlaneGeometry.wire_index_range(pitch_min, pitch_max)`가 이미 정확히 이 변환(연속 pitch 구간 → 경계 wire index)을 계산해 주는데도, `true_blob_polygon`은 이 함수를 쓰지 않고 연속 좌표를 그대로 strip 경계로 넘기고 있었다.

**해결**: `true_blob_polygon`이 각 평면에서 `pg.wire_index_range(center - nsigma*extent_tran, center + nsigma*extent_tran)`로 경계 wire index `(imin, imax)`를 구한 뒤, `pg.strip_polygon(pg.pitch_vals[imin], pg.pitch_vals[imax])`처럼 그 wire들의 실제 pitch 좌표를 strip 경계로 쓰도록 바꿨다(§3.1).
처음 버전의 `wire_index_range`는 항상 바깥쪽으로만 반올림했는데(nsigma 구간을 포함하는 가장 가까운 wire까지 무조건 확장), 이 방식 자체에 문제가 있다는 것을 나중에 알게 됐다 — 자세한 내용과 수정은 §5.6 참고.

이 효과를 시각적으로 직접 확인할 수 있도록, `scripts/utils/vis/true_blob_plots.py`에 depo의 진짜(스냅 전) nsigma 경계를 그려 보여주는 `plot_depo_heatmap_tran_ax`를 추가하고 `plot_true_vs_reco_tran_ax`/`plot_true_vs_reco_check`에 연결했다(§4).

### 5.6 wire 스냅이 항상 바깥쪽으로만 반올림됐다 (해결됨)

§5.5에서 처음 구현한 `wire_index_range`는 `pitch_min`보다 낮은 쪽 wire, `pitch_max`보다 높은 쪽 wire로 항상 "바깥쪽"만 골랐다(`np.searchsorted`의 `side="left"`/`side="right"`와 -1/+1 오프셋 조합).
하지만 이건 실제로 경계 지점에 더 가까운 wire가 안쪽에 있는 경우에도 무조건 바깥쪽 wire를 선택하게 만든다.
예를 들어 `center + nsigma*extent_tran` 지점이 두 wire 사이에서 안쪽 wire 쪽에 훨씬 더 가깝더라도, 항상 바깥쪽 wire까지 확장해버린다.

3-sigma 경계 지점 하나에는 항상 그 지점을 감싸는 2개의 후보 wire(안쪽 하나, 바깥쪽 하나)가 있는데, 이 중 pitch 거리상 실제로 더 가까운 쪽을 선택해야 물리적으로 더 타당하다(경계 지점이 안쪽 wire 쪽에 더 가까우면 그 wire가, 바깥쪽 wire 쪽에 더 가까우면 그쪽이 실제 경계를 더 잘 대표한다).

**해결**: `PlaneGeometry`에 `nearest_wire_index(pitch)`를 추가했다.
`np.searchsorted(self.pitch_vals, pitch)`로 두 후보 wire 인덱스(`idx - 1`, `idx`)를 구한 뒤, `abs(pitch_vals[i] - pitch)`가 더 작은 쪽을 반환한다(평면 양 끝에서 후보가 하나뿐인 경우는 그 하나를 그대로 반환).
`wire_index_range(pitch_min, pitch_max)`는 이제 `pitch_min`/`pitch_max` 각각에 대해 독립적으로 `nearest_wire_index`를 호출한다 — 두 경계가 항상 바깥쪽으로만 확장되는 대신, 각자 실제로 더 가까운 wire를 고르므로 결과 폴리곤이 이전보다 커질 수도 작아질 수도 있다.

**결과**: `docs/wires_geometry_walkthrough.md`의 point depo 예시($y=3000$, $z=1000$, $extent\_tran=1.7017mm$)에서 U평면의 `imax`가 $589 \to 588$로 바뀌었다(경계 지점이 588번 wire에 더 가까웠기 때문).
그 결과 최종 폴리곤 면적이 $198.74mm^2 \to 76.66mm^2$로 줄었고, 중심(centroid)도 $(2998.54, 998.76) \to (3001.22, 1001.49)$로 이동했다 — depo 실제 위치 $(3000.00, 1000.00)$과의 편차가 오히려 약간 커졌는데, 이는 wire 격자가 3개 평면에서 딱 맞아떨어지지 않는 한 자연스럽게 생기는 수 mm 수준의 편차이지 버그가 아니다(§7 "그레인 차이"와는 별개의, wire 해상도 자체에서 오는 한계).
`test_point_depo` 샘플의 IoU는 $0.469 \to 0.388$, 중심 거리는 $1.91mm \to 2.18mm$로, `test_single_trk` 샘플의 IoU는 $0.576 \to 0.258$, 중심 거리는 $1.88mm \to 1.60mm$로 바뀌었다(§6에 최신 수치 반영).
IoU가 전반적으로 낮아진 것은 예상된 결과다: "바깥쪽으로만" 반올림하던 이전 버전은 항상 원래 nsigma 영역을 완전히 포함하는 더 큰 폴리곤을 만들었는데, 그레인 차이(depo 1개 대 reco blob, §7)로 인해 true blob이 원래 reco blob보다 작은 상황에서는 "더 크게" 반올림하는 쪽이 우연히 IoU를 부풀리는 효과가 있었다.
`nearest_wire_index`로 바꾼 지금은 이런 인위적인 확대 없이, 실제 wire 위치를 있는 그대로 반영한 형태가 된다.

## 6. 검증 결과

`scripts/pdhd_true_blob_check.py`를 `data/pdhd/test_single_trk`(단일 트랙, depo 5000개, reco blob 113개)와 `data/pdhd/test_point_depo`(depo 1개) 샘플에 대해 실행한 결과다.
nearest-wire 스냅(§5.6) 적용 이후의 수치다.

| 지표 | test_single_trk (5000 depo) | test_point_depo (1 depo) |
|---|---|---|
| 빈 폴리곤 개수 | 0 / 5000 | 0 / 1 |
| IoU 평균 | 0.258 | 0.388 |
| 폴리곤 중심 거리 평균 | 1.60 mm | 2.18 mm |
| 시간 slice 겹침 비율 평균 | 0.379 | 0.405 |

depo 5000개가 reco blob 113개로 묶이는(약 44:1) 그레인 차이를 고려하면, true blob 하나가 reco blob 안에 대체로 겹쳐 들어가면서도 면적 비율 때문에 IoU가 1보다 작게 나오는 것은 예상된 결과다.
`results/pdhd/true_blob_check/single_trk_overlay.png`와 `point_depo_overlay.png`에 저장된 오버레이 그림에서, true blob(마젠타 폴리곤, 세 평면 교차로 생긴 모양)이 reco blob(청록색 외곽선) 안에 기하학적으로 합리적인 위치에 겹쳐 그려지고, 그 아래로 검정 배경과 depo의 진짜(스냅 전) nsigma 경계(흰색 점선 원)가 함께 표시되는 것을 육안으로 확인했다.

## 7. 알려진 한계와 다음 단계

- **시간 오프셋**: §5.3 참고. `docs/time_offset_calibration.md`에서 해결됐다.
- **감지 영역 경계 근사**: §5.4 참고.
  `face_sensitive_bounds`가 계산하는 박스는 wire store의 와이어 끝점 범위로 근사한 값이라, 검출기 Jsonnet geometry 설정이 정의하는 진짜 `BoundingBox`와 정확히 일치한다는 보장은 없다.
  두 값의 차이를 정량적으로 확인하려면 실제 Jsonnet geometry 설정값과 직접 대조하거나, §7의 "다음 단계"에 있는 옵션 C(WCT job graph 재실행)로 교차검증해야 한다.
- **그레인 차이**: 현재는 depo 1개 = true blob 후보 1개로 가장 단순하게 구현했다.
  reco blob과 더 정확히 비교하려면 인접 depo를 하나의 time-slice(예: reco의 `tick_span`)로 묶는 로직이 필요할 수 있다.
- **전하 가중치 단순화**: §3.1에서 설명한 대로, true blob의 전하는 시간축 `gbounds` 보정만 적용하고 pitch축 가우시안 가중은 적용하지 않는다.
  단일 depo-단일 blob 가정 하에서는 타당하지만, 여러 depo를 하나의 true blob으로 묶는 방향으로 발전시키면 `Img::BlobDepoFill`(`wire-cell-toolkit/img/src/BlobDepoFill.cxx`)처럼 더 정교한 가우시안 가중 배분이 필요해질 수 있다.
- **다음 단계(2단계, 아직 미착수)**: 이 Python 근사가 얼마나 정확한지 교차검증하기 위해, `DepoFluxSplat`이 만드는 true frame을 reco blob과 동일한 tiling 엔진(`img.slicing`/`img.tiling`, `GridTiling`/`RayGrid::make_blobs`)에 통과시켜 기하학적으로 완전히 동일한 방식의 true blob을 만드는 방안이 있다.
  이 방안은 WCT job graph(Jsonnet) 확장과 재실행이 필요하며, 이번 세션에서는 설계만 검토했고 아직 착수하지 않았다.



Version:          2.1.204
Session name:     true-blob-depo-design
Session ID:       35a7e4ac-64c4-4839-904b-3c950eb79616
cwd:              /nfs/data/1/yujin/img_evaluation
Login method:     Claude Pro account
Model:            Default (Sonnet 5 · Efficient for routine tasks)