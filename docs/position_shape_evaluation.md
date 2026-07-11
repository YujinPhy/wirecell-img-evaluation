# Position/Shape Evaluation (true blob vs. reco blob)

## Summary

`scripts/utils/eval/position_shape.py`가 제공하는, depo 기반 true blob(`utils.true_blob.build_true_blob`)과 재구성된 reco blob 노드(`utils.load.load_graph_nodes(cgraph, 'b')`)를 IoU/중심거리/시간 겹침/전하 오차 네 지표로 비교하는 평가(evaluation) 코드를 정리한 문서다.
이 코드는 원래 `scripts/utils/true_blob.py`(`reco_blob_polygon`, `compare_true_to_reco`)에 있었는데, blob을 "만드는" 로직과 blob을 "평가하는" 로직이 성격이 다르다는 이유로 `scripts/utils/eval/position_shape.py`로 분리했다.
true blob 자체를 만드는 방법은 `docs/true_blob_prototype.md`를 참고한다.

## 1. 왜 분리했는가

`utils.true_blob`은 depo 하나로부터 true blob(폴리곤 + 시간 slice + 전하)을 만드는 것까지만 책임진다.
`reco_blob_polygon`/`compare_true_to_reco`는 그렇게 만들어진 true blob을 재구성된 blob과 견주어 정확도 지표를 계산하는, 성격이 다른 코드다.
전자는 "무엇이 참값인가"를 정의하는 코드이고, 후자는 "참값과 재구성 결과가 얼마나 다른가"를 재는 evaluation 코드이므로, `scripts/utils/eval/` 아래에 독립된 모듈로 둔다.

## 2. 코드 설명

### 2.1 `reco_blob_polygon(blob_node)`

reco blob 노드로부터 (y,z) 폴리곤을 만든다.

reco blob 노드의 `corners` 필드(`[x,y,z]` 리스트, x는 모든 corner에서 그 blob의 slice `start` 값으로 동일)에서 y,z만 뽑아 `shapely.geometry.MultiPoint(yz_points).convex_hull`로 볼록 껍질 폴리곤을 만든다.
`corners`가 이미 폴리곤 꼭짓점 순서로 정렬되어 있다는 보장이 없어도, convex hull을 쓰면 순서와 무관하게 올바른 폴리곤이 만들어진다.

### 2.2 `compare_true_to_reco(true_blob, reco_blob_node)`

true blob 하나와 reco blob 노드 하나를 네 가지 지표로 비교한다.

먼저 `true_blob["polygon"]`과 `reco_blob_polygon(reco_blob_node)`를 준비한다.
`true_poly`가 `None`이거나 두 폴리곤 중 하나라도 비어 있으면 `iou=0.0`, `centroid_distance=nan`으로 처리해 이후 계산에서 예외가 나지 않게 방어한다.
그렇지 않으면 `true_poly.intersection(reco_poly).area`/`true_poly.union(reco_poly).area`로 IoU(교집합 면적/합집합 면적)를 구하고, 두 폴리곤의 `centroid` 사이 유클리드 거리(`centroid_distance`)를 구한다.
시간축에서는 `true_blob`의 `(start, start+span)`과 `reco_blob_node`의 `(start, start+span)` 두 구간의 겹치는 길이를 전체 합집합 길이로 나눠 `time_overlap_frac`을 구하며, `max(0.0, ...)`로 겹치지 않는 경우(음수가 나오는 경우) 0으로 클램프한다.
전하는 `reco_blob_node["val"]`을 기준값으로 삼아 `(true_blob["charge"] - reco_charge) / reco_charge`로 상대 오차를 구하고, `reco_charge`가 0이면 0으로 나누는 대신 `nan`을 반환한다.
네 지표(`iou`, `centroid_distance`, `time_overlap_frac`, `charge_rel_error`)를 딕셔너리로 묶어 반환한다.

| 지표 | 의미 | 값의 범위/방어 처리 |
|---|---|---|
| `iou` | 두 폴리곤의 겹침 정도 (교집합 면적/합집합 면적) | `[0, 1]`, 폴리곤이 없거나 비어 있으면 `0.0` |
| `centroid_distance` | 두 폴리곤 중심 사이 유클리드 거리 (mm) | 폴리곤이 없거나 비어 있으면 `nan` |
| `time_overlap_frac` | 두 시간 slice가 겹치는 비율 | `[0, 1]`, 겹치지 않으면 `0.0` |
| `charge_rel_error` | `(true_charge - reco_charge) / reco_charge` | `reco_charge == 0`이면 `nan` |

## 3. 사용 예시

`scripts/pdhd_true_blob_check.py`가 실제 사용 예시다.

```python
from utils.true_blob import build_true_blobs
from utils.eval.position_shape import compare_true_to_reco
from utils.vis.true_blob_plots import nearest_reco_blob

true_blobs = build_true_blobs(plane_geoms, depos, speed=DRIFT_SPEED, nsigma=NSIGMA)
for tb in true_blobs:
    rb = nearest_reco_blob(tb, reco_blobs)   # utils.vis.true_blob_plots, 중심거리 기준 매칭
    if rb is None:
        continue
    metrics = compare_true_to_reco(tb, rb)
```

true blob과 비교할 reco blob을 먼저 짝지어야 하는데, 그 짝짓기(`nearest_reco_blob`)는 `scripts/utils/vis/true_blob_plots.py`에 있다(`docs/true_blob_prototype.md` §5 참고).
`compare_true_to_reco` 자체는 짝짓기를 하지 않고, 이미 짝지어진 true blob 하나와 reco blob 노드 하나를 받아 지표만 계산한다.

## 4. 알려진 한계

`time_overlap_frac`/`charge_rel_error`는 depo의 원본 시간과 reco blob의 `start` 시간 사이에 존재하는, 아직 보정되지 않은 오프셋 때문에 현재는 의미 있는 값이 아니다.
자세한 원인은 `docs/true_blob_prototype.md` §6.3을 참고한다.
이 오프셋이 보정되기 전까지는 `iou`/`centroid_distance`(위치·모양 지표)만 신뢰할 수 있다.
