# PlaneGeometry Walkthrough (`scripts/utils/wires.py`)

## Summary

`scripts/utils/wires.py`의 `PlaneGeometry`/`build_plane_geometries`/`face_sensitive_bounds`가 실제로 어떻게 동작하는지, 단일 point depo 하나를 예시로 삼아 각 단계의 실제 숫자를 따라가며 설명하는 문서다.
원래 `docs/true_blob_prototype.md` §3에 있던 코드 설명을 여기로 옮기고, 예시를 덧붙였다.
이 문서에 나오는 모든 숫자는 `data/pdhd/test_point_depo/depos-drifted-1.zip`과 `wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2`를 실제로 로드해서 계산한 값이며, `scripts/depo_wire_validation.py`를 실행하면 동일한 계산을 직접 재현할 수 있다.

## 1. 예시로 쓸 depo

`data/pdhd/test_point_depo/depos-drifted-1.zip`에는 depo가 딱 1개 들어 있다.

```python
from utils.load import load_generation_data
depos = load_generation_data("data/pdhd/test_point_depo/depos-drifted-1.zip", 0)
y, z, T = depos["y"][0], depos["z"][0], depos["T"][0]
# y=3000.000mm z=1000.000mm T(extent_tran)=1.7017mm
```

이 문서 전체에서 이 depo의 $y=3000.00$mm, $z=1000.00$mm, `extent_tran`(횡방향 확산 시그마) $T=1.7017$mm 값을 그대로 사용한다.
`anode_index=1`, `face_index=1`(PDHD, 이 저장소가 기본으로 쓰는 anode/face)을 기준으로 한다.

## 2. `build_plane_geometries(wire_store_path, anode_index, face_index)`

지정한 anode/face에 속한 3개 평면(U, V, W) 각각에 대해 `PlaneGeometry`를 만들어 반환한다.
와이어 좌표는 `wirecell.util.wires.persist`/`schema`로 로드한 전체 wire store JSON(`wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2`)에서 가져온다(`docs/wirecell_wires_reference.md` 참고).

```python
from utils.wires import build_plane_geometries
plane_geoms = build_plane_geometries(
    "wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2",
    anode_index=1, face_index=1,
)
# plane_geoms[0] = U평면 (nwires=1148)
# plane_geoms[1] = V평면 (nwires=1148)
# plane_geoms[2] = W평면 (nwires=480)
```

처음에는 재구성 cluster graph 자체에 들어있는 `'w'`(wire) 노드를 재사용하려 했지만, cluster graph는 실제로 blob 경계에 쓰인 와이어만 희소하게(sparse) 담고 있어서 depo의 미세한 nsigma 구간 계산에 쓰기에는 와이어 간격이 너무 불규칙했다(자세한 경위는 `[[true_blob_prototype#5.1|docs/true_blob_prototype.md §5.1]]` 참고).
전체 wire store는 평면의 모든 와이어를 pitch 순서대로 담고 있어 이 문제가 없다.

## 3. `PlaneGeometry.__init__` — pitch 축 계산

가장 이해하기 쉬운 W평면(`plane_geoms[2]`)부터 본다.
W평면의 와이어들은 거의 수직(z축과 반대 방향)으로 뻗어 있어서, 계산 결과가 직관적으로 딱 맞아떨어진다.

```python
pg = plane_geoms[2]
# pg.nwires      = 480
# pg.origin      = [3068.05, 1152.44]        # 모든 와이어 중점의 평균, (y,z)
# pg.pitch_axis  = [-1.2e-29, -1.0]          # 사실상 (0, -1): -z 방향
# pg.wire_axis   = [1.0, -1.2e-29]           # 사실상 (1, 0): +y 방향
# pg.pitch_vals  = [-1147.68, ..., 1147.68]  # 오름차순, 480개
```

내부 계산은 다음과 같다.

1. 모든 와이어의 tail/head 끝점 평균(중점)을 구하고, 그 중점들 전체의 평균을 `origin`으로 잡는다.
2. 중심화된 중점 좌표(`origin` 기준)에 PCA(특이값분해, `np.linalg.svd`)를 적용해, 분산이 가장 큰 방향을 `pitch_axis`로 삼는다.
   W평면은 와이어가 거의 수평(y축 방향)으로 나란히 늘어서 있으므로, 그 중점들이 흩어지는(분산이 큰) 방향은 수직(z축) 방향이고, 그래서 `pitch_axis`가 거의 정확히 $(0, -1)$이 된다.
3. `pitch_axis`를 90도 회전시킨 벡터를 `wire_axis`(와이어가 뻗어나가는 방향)로 저장한다.
4. 각 와이어 중점을 `pitch_axis`에 투영한 값을 `pitch_vals`(오름차순 배열)로, 와이어 개수를 `nwires`로 저장한다.

> 초기 구현은 "첫 와이어 중점 → 마지막 와이어 중점" 벡터를 pitch 축으로 썼는데, 평면 가장자리의 와이어는 사다리꼴 모양의 평면 경계 때문에 중앙부 와이어보다 짧아서 중점이 와이어 방향으로도 밀려나 있고, 이 때문에 두 점만으로 구한 축이 실제 pitch 방향과 어긋나는 문제가 있었다.
> PCA는 모든 와이어의 중점을 종합해서 방향을 추정하므로 이 왜곡에 훨씬 덜 민감하다.
> 자세한 경위는 `[[true_blob_prototype#5.2|docs/true_blob_prototype.md §5.2]]` 참고.

U평면(`plane_geoms[0]`)과 V평면(`plane_geoms[1]`)도 원리는 같지만, 와이어가 비스듬히 뻗어 있어서 축이 기울어져 있다.

```python
# plane_geoms[0] (U): origin=[3072.10, 1152.63] pitch_axis=[-0.965, -0.261] wire_axis=[0.261, -0.965]
# plane_geoms[1] (V): origin=[3068.94, 1152.66] pitch_axis=[ 0.966, -0.260] wire_axis=[0.260,  0.966]
```

세 평면의 `pitch_axis`가 서로 다른 각도를 가리키기 때문에, 뒤에서 세 평면의 "띠"를 교차시키면 삼각형에 가까운 폴리곤이 만들어진다.

## 4. `pitch_of(y, z)` — depo 위치를 pitch 좌표로

depo의 $(y, z) = (3000.00, 1000.00)$을 W평면 좌표로 옮기면 다음과 같다.

```python
pg.pitch_of(3000.0, 1000.0)
# (y,z) - origin = [3000.0, 1000.0] - [3068.05, 1152.44] = [-68.05, -152.44]
# dot([-68.05, -152.44], [0, -1]) = 152.44
# -> 152.4378
```

`pitch_axis`가 정확히 $(0,-1)$이라면 내적은 그냥 $z$ 성분의 부호를 뒤집은 값과 같아지므로, `origin`의 $z$($1152.44$)에서 depo의 $z$($1000.00$)를 뺀 $152.44$가 그대로 나온다.
U/V평면은 축이 기울어져 있어 이렇게 단순하지 않지만, 계산 방식(내적)은 동일하다(U평면은 $109.40$, V평면은 $-26.84$가 나온다).

## 5. `wire_index_range(pitch_min, pitch_max)` — pitch 경계를 가장 가까운 와이어로

true blob을 만들 때는 depo의 pitch 중심에 `extent_tran`을 `nsigma`(기본 $3.0$)배 곱한 구간의 두 끝점(`pitch_min`, `pitch_max`)을 쓴다.
각 끝점은 독립적으로, 그 지점을 사이에 둔 두 후보 와이어 중 실제 pitch 거리가 더 가까운 쪽으로 스냅된다.

```python
center = pg.pitch_of(3000.0, 1000.0)     # 152.4378 (W plane)
pitch_max = center + 3.0 * T             # 152.4378 + 3.0*1.7017 = 157.5429
pg.nearest_wire_index(pitch_max)
# 후보: wire 272 (pitch_vals[272]=155.7403, 거리=1.8026), wire 273 (pitch_vals[273]=160.5318, 거리=2.9889)
# -> 272 (더 가까운 쪽)
```

`nearest_wire_index(pitch)`는 `np.searchsorted(pitch_vals, pitch)`로 두 후보 인덱스(`idx - 1`, `idx`)를 찾은 뒤, `abs(pitch_vals[i] - pitch)`가 더 작은 쪽을 반환한다(평면 양 끝이라 후보가 하나뿐이면 그 하나를 그대로 반환).
`wire_index_range(pitch_min, pitch_max)`는 `pitch_min`/`pitch_max` 각각에 대해 이 함수를 독립적으로 호출한 `(imin, imax)`를 돌려준다.

```python
pg.wire_index_range(147.3327, 157.5429)
# -> (270, 272)
# pg.pitch_vals[270] = 146.1578, pg.pitch_vals[272] = 155.7403
```

이전 버전은 `pitch_min`보다 항상 낮은 쪽, `pitch_max`보다 항상 높은 쪽으로만 반올림해 `(270, 273)`을 반환했다(요청 구간을 항상 완전히 포함하도록 바깥쪽으로만 확장).
하지만 이 방식은 위 예시의 `pitch_max`처럼 실제로는 안쪽 후보(272)가 더 가까운 경우에도 무조건 바깥쪽(273)을 선택해 버리는 문제가 있어, 지금의 최근접 방식으로 바꿨다(자세한 배경은 `docs/true_blob_prototype.md` §5.6).
`utils.true_blob.true_blob_polygon`은 바로 이 `imin`/`imax`에 대응하는 `pitch_vals[imin]`/`pitch_vals[imax]`를 다음 §6의 `strip_polygon` 경계로 넘긴다 — depo의 연속적인 nsigma 좌표를 그대로 쓰지 않고 실제 wire 위치에 스냅하기 위해서다.
실제 blob의 경계가 항상 wire ray 선 위에 있다는 사실(WCT RayGrid 타일링의 `Strip.bounds`가 wire-ray 인덱스 쌍인 것)을 반영한 것이다.

## 6. `strip_polygon(pitch_min, pitch_max)` — pitch 구간을 폴리곤 띠로

실제 와이어의 tail/head 끝점을 폴리곤 경계로 쓰지 않고, `pitch_axis`와 `wire_axis`만으로 아주 긴(`_STRIP_HALF_LENGTH = 1.0e5`, 즉 ±100km) 사각형 밴드를 직접 만든다.
와이어 길이에 의존하지 않기 때문에, 가장자리의 짧은 와이어가 띠를 원래보다 좁게 잘라내는 문제가 생기지 않는다.

W평면에서 위 pitch 구간 $[147.33, 157.54]$으로 만든 띠의 실제 꼭짓점은 다음과 같다.

```python
pg.strip_polygon(147.3328, 157.5428).exterior.coords[:4]
# (-96931.95, 1005.11), (103068.05, 1005.11), (103068.05, 994.89), (-96931.95, 994.89)
```

W평면은 `pitch_axis`가 $(0,-1)$이라서, 이 띠는 그냥 $z \in [994.89, 1005.11]$인 수평 밴드다($y$는 $-96932$부터 $103068$까지, 사실상 무한히 넓다).
$1005.11 - 994.89 = 10.21$mm인데, 이는 정확히 `pitch_max - pitch_min`($157.54-147.33=10.21$)과 같다 — pitch 구간의 폭이 그대로 띠의 폭이 된다.
U/V평면은 `pitch_axis`가 기울어져 있으므로 같은 논리로 만들어진 띠가 수평이 아니라 대각선 방향의 좁은 밴드가 된다.

## 7. 세 평면의 교차 — 최종 폴리곤

세 평면 각각의 띠를 순서대로 교차시키면(`strips[0].intersection(strips[1]).intersection(strips[2])`), 세 방향에서 서로 다른 각도로 잘라낸 좁은 다각형이 남는다.
실제 `true_blob_polygon()`이 만드는 띠는 §5/§6에서처럼 각 평면의 wire-스냅된 pitch 경계(`pitch_vals[imin]`/`pitch_vals[imax]`)로 만든 것이므로, 아래는 그 값을 그대로 쓴 세 개의 띠(U: $[103.97, 111.70]$, V: $[-35.09, -19.64]$, W: $[146.16, 155.74]$)를 교차시킨 결과다.

```python
inter_uv = strips[0].intersection(strips[1])          # area=237.23mm^2
inter_uvw = inter_uv.intersection(strips[2])           # area=76.66mm^2, centroid=(3001.22, 1001.49)
```

U/V 두 평면만 교차했을 때는 아직 폭이 넓은 평행사변형($237.23$mm²)이고, 여기에 W평면의 수평 밴드까지 교차시키면 depo 주변의 좁은 다각형(약 $76.66$mm²)으로 좁혀진다.
이 최종 폴리곤의 중심(centroid)은 $(3001.22, 1001.49)$로, 원래 depo 위치 $(3000.00, 1000.00)$과 완전히 일치하지는 않는다 — wire 위치로 스냅하는 과정에서 세 평면의 격자가 딱 맞아떨어지지 않는 한 몇 mm 수준의 편차가 자연스럽게 생기기 때문이다(§5.6).

참고로 wire 스냅을 하지 않고 §6처럼 depo의 연속 nsigma 경계($[147.33, 157.54]$ 등)를 그대로 썼다면 면적 $93.91$mm², 중심 $(3000.00, 1000.00)$(depo 위치와 소수점 이하로 정확히 일치)이 나온다 — wire 스냅은 폴리곤을 depo의 연속 nsigma 영역보다 작게(이 예시에서는 약 82%로) 만들 수도, 크게 만들 수도 있고, 중심을 depo 위치에서 살짝 벗어나게 만드는 트레이드오프를 갖는다는 뜻이다.
`utils.true_blob.true_blob_polygon()`이 바로 이 단계들(각 평면의 `pitch_of`→`wire_index_range`→`strip_polygon`, 그리고 순차 교차)을 depo 하나에 대해 수행하는 함수이며, `depo 여러 개 → true blob 여러 개`로 확장한 전체 그림과 wire 스냅의 배경/효과는 `docs/true_blob_prototype.md`(§3.1, §5.5, §5.6)를 참고한다.

## 8. `face_sensitive_bounds(wire_store_path, anode_index, face_index)` — 감지 영역 경계 근사

`strip_polygon`(§6)이 만드는 띠는 wire 축 방향으로 $\pm100km$인 사실상 무한한 밴드라, 세 평면을 교차시킨 최종 폴리곤(§7)도 depo가 감지 영역(sensitive volume) 경계 근처에 있으면 검출기 물리적 범위 바깥까지 확장될 수 있다.
`face_sensitive_bounds`는 face에 속한 3개 평면 모든 와이어의 tail/head 끝점 $(y, z)$ 좌표 전체의 합집합으로 axis-aligned bounding box(`shapely.geometry.box`)를 만들어 이 경계를 근사한다.
`build_plane_geometries`와 동일한 인자를 받아 같은 wire store에서 계산하지만, 별도 함수로 분리되어 있어 필요할 때만 호출하면 된다.

이 함수를 만들게 된 배경(실제 WCT blob이 3개 wire-plane 레이어 외에 2개의 합성 "bounds" ray-grid 레이어와도 교차한다는 사실)과, `utils.true_blob.true_blob_polygon`의 `sensitive_bounds` 인자로 이 박스를 실제로 적용하는 과정, PDHD anode 1/face 1에서 계산된 실제 박스값과 경계 근처 depo에서의 클리핑 효과는 `docs/true_blob_prototype.md` §5.4에 정리했다.

## 9. 실행해서 직접 확인하기

이 문서의 모든 계산은 `scripts/depo_wire_validation.py`(`test_point_depo` 샘플 사용)와 `scripts/geometry_validation.py`(합성 예시 사용)로 직접 재현할 수 있다.

```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"
python scripts/depo_wire_validation.py
```

관련 문서: `docs/wirecell_wires_reference.md`(이 코드가 의존하는 `wirecell.util.wires.schema`/`persist`의 데이터 모델 자체), `docs/true_blob_prototype.md`(이 `PlaneGeometry`를 depo 여러 개의 true blob으로 조립하는 전체 파이프라인).
