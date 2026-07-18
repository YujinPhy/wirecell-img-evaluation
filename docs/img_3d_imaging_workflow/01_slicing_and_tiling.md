# Slicing, RayGrid Tiling, and Blob Clustering

## Summary

`IFrame`(channel x time 파형)을 `ISlice`(시간창별 채널 활동)로 나누고, 그 활동을 `RayGrid` 프레임워크로 기하학적으로 교차시켜 `IBlob`(3D 영역)을 만든 뒤, blob들을 전기적으로(`BlobGrouping`) 또는 시간적으로(`BlobClustering`) 서로 이어 `cluster_graph_t`를 구성하는 단계를 다룬다. 소스: `img/src/MaskSlice.cxx`, `img/src/SumSlice.cxx`, `img/src/GridTiling.cxx`, `util/src/RayTiling.cxx`, `img/src/BlobGrouping.cxx`, `img/src/BlobClustering.cxx`, `img/src/GeomClusteringUtil.cxx`.

---

## 1. `MaskSlice` — 활동 기반 thresholding slicer

**파일**: `img/src/MaskSlice.cxx`, `img/inc/WireCellImg/MaskSlice.h`

`slice()` (`MaskSlice.cxx:218`)는 입력 `IFrame`에서 3종류 태그된 trace를 가져온다: `charge_tag`(전하값), `wiener_tag`(신호 검출용 wiener-필터 트레이스), `error_tag`(불확실성). 채널은 세 그룹으로 나뉜다.

### Active planes (전하 기반)

각 tick에 대해 `thresholding()` (`MaskSlice.cxx:173-216`)가 활성 여부를 판정한다:

```cpp
bool thresholding(wiener_charge, gauss_charge, qind, threshold, tick_span, ...) {
    if (q_wiener[qind] > threshold) return true;          // 1차: wiener 신호가 임계값 초과
    // 2차: 인접 slice(이전/다음)의 평균 wiener 신호가 임계값을 넘고,
    //      현재 tick의 gauss(=charge) 신호가 그 인접 신호의 1/3을 넘으면 활성으로 인정
    if ((q_gauss > q_next/3. && q_next > threshold) ||
        (q_gauss > q_prev/3. && q_prev > threshold)) return true;
    return false;
}
```

임계값 자체는 `threshold = nthreshold[plane] * summary[idx]` (RMS 기반, `summary`는 `summary_tag`로 태깅된 trace의 RMS 요약값)이고, `summary`가 0이면 `default_threshold[plane]`로 대체한다. 즉 신호 대 잡음비가 좋으면 RMS 적응형, 아니면 고정값 fallback. `nthreshold`/`default_threshold`의 기본값은 UBooNE에서 튜닝된 것으로, PDHD에서는 이 저장소의 `img.jsonnet`처럼 `nthreshold: [3.6, 3.6, 3.6]`을 명시적으로 재설정해 쓴다(`default_threshold`는 대부분 안 쓰이는데, RMS `summary`가 통상 0이 아니기 때문).

이 2단계 로직의 의도는 "본 slice에서는 threshold를 살짝 못 넘었지만, 실제로는 인접 slice와 이어지는 진짜 신호의 tail"인 경우를 살려주는 것으로 보인다.

활성으로 판정된 `(charge, error)`는 `s->sum(ich, {q, e})`로 slice에 누적된다.

### Dummy planes

`m_dummy_planes`에 속한 평면은 모든 채널/모든 slice에 대해 고정값 `(dummy_charge=0, dummy_error=1e12)`를 채운다. `1e12`라는 거대한 오차는 "이 평면은 실제 데이터가 없으니 charge solving에서 사실상 무시하라"는 신호(측정 공분산 대각항이 매우 커짐 -> LASSO whitening에서 가중치가 0에 가까워짐).

### Masked planes

채널 마스크 맵(channel mask map, `"bad"` 태그)에 등록된 시간 구간에 대해 `(masked_charge=0, masked_error=1e12)`를 채운다. 죽은/veto 채널을 표현하는 방식.

### 두 종류의 fanout: `active`/`masked`

이 저장소의 `img.jsonnet`은 실제로 **하나의 anode에 대해 두 가지 슬라이싱을 병렬로 돌린다** (`multi_active_slicing_tiling` + `multi_masked_2view_slicing_tiling`, `FrameFanout`으로 분기). "active" 포크는 3평면 모두 살아있는 조합(및 2평면 조합)으로 실제 신호를 태깅하고, "masked" 포크는 죽은 채널이 있는 영역을 2-view blob으로 채워 넣는 용도로 보인다. `GeomClusteringUtil`의 `dead_clus` 정책(§6)이 이 dead 채널 blob들을 다루기 위한 것.

---

## 2. `SumSlice` — 단순 누적 slicer

**파일**: `img/src/SumSlice.cxx`

Thresholding이나 평면 분류 없이, `tick_span` 폭의 시간창에 non-zero trace 샘플을 그대로 누적한다. Noise-aware 필터링이 없는 대신 훨씬 단순하며, 노이즈 없는 truth-level 프레임(예: `DepoFluxSplat`로 만든 noise-free 프레임)을 다룰 때 적합하다 — 이 저장소의 Stage 2 계획(`CLAUDE.md` 2.2절, `DepoFluxSplat` + tiling cross-validation)과 직접 관련된 컴포넌트다.

---

## 3. `RayGrid` 프레임워크와 `GridTiling` — 기하학적 blob 생성

**파일**: `util/inc/WireCellUtil/RayGrid.h`, `util/inc/WireCellUtil/RayTiling.h`, `util/src/RayTiling.cxx`, `img/src/GridTiling.cxx`

### 3.1 기본 개념

- **Layer**: 한 그룹의 평행한 광선(ray)들의 집합. Layer 0, 1은 항상 애노드 면의 가로/세로 경계(bounding box, `nbounds_layers = 2`)이고 layer 2부터가 실제 와이어 평면(U, V, W)이다.
- **Grid index**: 한 layer 안에서 광선(=와이어)의 순번.
- **`Activity`**: 한 layer에 대해 격자 인덱스별 활동값(전하)을 저장한 벡터. `active_ranges()`가 `threshold`를 초과하는 연속 구간들을 찾아낸다 (`RayTiling.cxx:115-166`).
- **`Strip`**: 한 layer 안에서 연속 활성 구간의 경계 `[bounds.first, bounds.second)`. `Activity::make_strips()`가 `active_ranges()`의 각 구간을 `Strip`으로 변환한다.
- **`Blob`**: 여러 layer의 `Strip`들이 만드는 교집합. 내부에 `corners()` (모든 strip에 동시에 속하는 층-쌍 교차점 목록)를 캐시해 둔다.

### 3.2 `Blob::add()` — strip을 하나씩 추가하며 교집합을 갱신 (`RayTiling.cxx:216-289`)

`make_blobs`는 layer를 하나씩 추가해가며 기존 blob 후보 집합을 계속 좁혀나가는 **점진적 정제(incremental refinement)** 방식이다:

1. **첫 strip**: 그냥 저장. corner 없음 (조건이 하나뿐이라 아직 "영역"이 아님).
2. **두번째 strip**: 두 strip의 4개 조합 `(first,first),(first,second),(second,first),(second,second)`가 모두 corner가 된다 (`find_corners`, `RayTiling.cxx:170-181`) — 사각형의 네 꼭짓점.
3. **세번째 strip부터**: 새 strip을 추가할 때
   - 기존 corner들 중 새 strip 범위 안에 들어오는 것만 살아남고(`in_strip`),
   - 새 strip과 기존의 각 strip 쌍이 만드는 새로운 corner 후보들 중, **다른 모든 기존 strip 안에도 들어있는 것**만 채택한다 (이중 for문, `si1`/`si2`).
   - `in_strip()`은 부동소수점 오차를 보정하기 위해 `nudge` 파라미터로 판정 경계를 살짝 안쪽/바깥쪽으로 밀어준다(교차점이 이상적으로는 정수 격자 위에 있어야 하는데 실제로는 미세하게 어긋나는 경우를 흡수).

이 알고리즘은 본질적으로 **볼록 다각형의 half-plane 교집합을 순차적으로 갱신**하는 것과 동일한 아이디어이며, `RayGrid`에서는 half-plane 대신 "strip(두 평행선 사이의 띠)"의 교집합이라는 점이 다르다.

### 3.3 `make_blobs()` 전체 흐름 (`RayTiling.cxx:497-539`)

```cpp
blobs_t make_blobs(coords, activities, nudge) {
    for (activity : activities) {           // layer 순서대로
        blobs = (blobs.empty()) ? tiling(activity)         // 첫 layer: strip마다 1-strip blob
                                 : tiling(blobs, activity); // 이후: 기존 blob에 strip 추가 시도
        drop_invalid(blobs);                // valid()==false (폭 0, corner<3 등) 인 blob 버림
        if (blobs.empty()) return {};        // 한 layer라도 완전히 씨가 마르면 즉시 포기
    }
    prune(coords, blobs, nudge);            // 각 blob의 strip 경계를 corner 투영 범위로 재조정
    drop_invalid(blobs);
    // 모든 layer의 strip을 갖지 않은(중간에 유실된) blob은 제거
    return blobs;
}
```

`Tiling::operator()(prior_blobs, activity)`는 기존 blob마다 새 layer activity를 **그 blob의 corner 투영 범위로 미리 잘라낸(`projection()`) 뒤** 그 안에서 새 strip을 찾아 추가한다 — 전체 activity가 아니라 blob 주변만 보는 최적화. 단일-strip blob(첫 layer만 있는 경우)은 사실상 무한히 뻗어있다고 보고 activity 전체를 그대로 쓴다 (`RayTiling.cxx:343-345`).

`prune()` (`RayTiling.cxx:442-495`)은 마지막에 각 blob의 각 평면 층에 대해, 실제 corner들이 차지하는 pitch 범위로 strip 경계를 다시 잘라준다 — 다른 layer의 corner 때문에 생긴 "쓸모없는 여분의 strip 영역"을 제거하는 것.

### 3.4 `GridTiling` — slice activity를 RayGrid activity로 변환 (`img/src/GridTiling.cxx`)

`operator()(slice, out)`:
1. `slice->activity()`를 순회하며 채널의 각 와이어에 대해 `measures[layer][pitch_index] += 1.0`을 누적 (여러 채널이 같은 pitch에 매핑될 수 있으므로 개수 누적; 실제 전하값이 아니라 "활동 있음" 카운트라는 점에 주의 — 실제 charge 값은 나중에 `ChargeSolving`이 채운다).
2. 평면 수(`nplanes`)보다 활성 layer 수가 적으면 즉시 포기 (`nactive_layers != measures.size()`).
3. `make_blobs(m_face->raygrid(), activities, m_nudge)` 호출로 3D 영역 후보를 얻는다.
4. 각 결과 `RayGrid::Blob`을 `SimpleBlob`으로 감싸 `IBlob`을 만든다. `Aux::BlobCategory`로 형태가 정상인지(`bcat.ok()`) 검사 후 `sbs->m_blobs`에 추가.

**비민감면(non-sensitive face) 처리** (`GridTiling.cxx:65-77`, 코드 주석 참조): PDHD APA의 한 면은 냉동고 벽을 향해 있어 드리프트 볼륨이 없는 "비민감 면"일 수 있다 (`m_face->sensitive().empty()`). 이 경우 활성 채널로는 애초에 blob이 안 생기지만, masked/dead 포크는 순수 기하학적으로 타일링하기 때문에 그대로 두면 **가짜(phantom) dead blob**이 생겨 이후 clustering을 오염시킨다. 그래서 비민감 면에서는 활동 유무와 무관하게 즉시 빈 blob set을 반환한다. 이는 PDHD처럼 face가 비대칭인 검출기에 특화된 방어 코드이므로, PDVD 등 다른 지오메트리로 포팅할 때도 `sensitive()` 판정이 올바른지 확인할 필요가 있다.

`m_nudge`(기본 `1e-3`, 이 저장소는 `1e-2`로 재설정)는 `RayGrid`의 부동소수점 강건성 파라미터를 그대로 전달한다.

---

## 4. `BlobGrouping` — 전기적으로 연결된 blob 묶어 `IMeasure` 생성 (`img/src/BlobGrouping.cxx`)

한 slice 안에서, 같은 채널(또는 같은 채널에 연결된 서로 다른 blob들)을 통해 **전기적으로 이어진 blob들의 연결 성분(connected component)**을 찾아 각 성분을 하나의 `SimpleMeasure`로 만든다:

1. 평면마다(하드코딩 3개, `bcs(3)` — `04_constants_and_caveats.md`의 알려진 제약사항) blob-channel subgraph를 만든다.
2. `boost::connected_components`로 연결 성분을 찾는다.
3. 성분마다 `IMeasure`: signal = 성분 내 채널 활동값 합, planeid는 해당 평면.
4. `cluster_graph_t`에 `m` 노드와 이를 구성하는 blob들로의 `b-m` 엣지를 추가한다.

이 `b-m` 이분 구조가 바로 `ChargeSolving`이 LASSO로 풀어야 할 대상(§`02_charge_solving.md`)이다. 여러 blob이 같은 measure를 공유한다는 것은, 그 채널의 신호를 여러 blob이 나눠 가져야 함(전하가 어떻게 분배되는지 모호함)을 의미하며 이것이 바로 "ghost blob" 문제의 근원이다.

---

## 5. `BlobClustering` — 프레임 단위로 시간축 clustering 수행 (`img/src/BlobClustering.cxx`)

1. Frame ident가 바뀔 때까지 들어오는 `IBlobSet`들을 버퍼링.
2. Frame 완료 시 slice 시간 순으로 정렬.
3. slice/blob/channel/wire 노드와 엣지로 `cluster_graph_t` 구성.
4. `geom_clustering()` (`GeomClusteringUtil`)을 호출해 인접 시간창 blob 사이에 `b-b` 엣지를 생성.

---

## 6. `GeomClusteringUtil` — blob-blob 시간축 연결 정책 (`img/src/GeomClusteringUtil.cxx`)

블록 집합 A(시간 t)의 각 blob에 대해, 블록 집합 B(시간 t+n)의 blob들 중 `RayGrid::overlap()` (기하학적 strip 겹침)으로 겹치는 것을 찾아 `b-b` 엣지를 만든다. 몇 개 slice까지(`max_rel_diff`) 확인할지, 겹침 판정 시 몇 wire의 간격(gap)까지 허용할지(`gap_tol`)가 정책별로 다르다:

| 정책 | `max_rel_diff` | `gap_tol` | 용도 |
|---|---|---|---|
| `simple` | 1 | `{1: 0}` | 인접 slice만, 정확히 겹칠 때만 |
| `uboone` | 2 | `{1: 2, 2: 1}` | 2-slice까지, wire 2개/1개 간격 허용 |
| `uboone_local` | 2 | `{1: 2, 2: 2}` | 재-clustering용(더 관대) |
| `dead_clus` | 특수 | `adjacent_dead()` 사용 | dead 영역 병합 |

`dead_clus` 정책은 `adjacent_dead()` (`GeomClusteringUtil.cxx:34`)에서 `offset = 4*500*us`(4 tick x 500us/tick = 2ms) 라는 하드코딩된 시간 허용치로 dead 채널 영역의 blob들을 더 관대하게 이어붙인다. 이 하드코딩값은 detector-specific이며 설정 불가능하다는 점에 주의 (`04_constants_and_caveats.md` 참조).

`grouped_geom_clustering()`은 동일 알고리즘을 미리 정의된 blob 그룹(순차적 slice 쌍이 아니라 임의 그룹)에 적용하는 변형으로, `GlobalGeomClustering`/`LocalGeomClustering`에서 재-clustering 시 사용된다 — `00_pipeline_overview.md` §3에서 본 `LocalGeomClustering`이 두 번의 `ChargeSolving` 사이에 끼어드는 이유가 바로 이것: 전하 재추정 전후로 blob 그룹 자체를 다시 묶어야 할 수 있기 때문이다.

---

## Related Documents

- [00_pipeline_overview.md](./00_pipeline_overview.md): 전체 파이프라인과 데이터 구조 개요, 이 저장소의 실제 파이프라인 순서.
- [02_charge_solving.md](./02_charge_solving.md): 여기서 만든 `b-m` bipartite 그래프를 LASSO로 푸는 다음 단계.
- [03_deghosting.md](./03_deghosting.md): geometric clustering만으로 남는 ghost를 추가로 제거.
- [../img_time_slicing_reference.md](../img_time_slicing_reference.md): `tick`/`tick_span`이 slice 폭을 어떻게 결정하는지에 대한 상세 분석.
