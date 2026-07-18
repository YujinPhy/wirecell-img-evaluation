# Deghosting

## Summary

3평면 와이어 TPC에서 각 평면은 전하 분포의 1D 투영만 준다. `IBlob`은 세 평면 모두에서 활성인 와이어들의 3D 교차 영역이므로, 서로 무관한 실제 궤적들의 와이어가 우연히 교차하면 **존재하지 않는 3D 위치에 가짜 blob("ghost")**이 생긴다. `ChargeSolving`의 LASSO 정규화(`02_charge_solving.md`)가 증거가 부족한 blob의 전하를 0으로 미는 방식으로 어느 정도 ghost를 억제하지만, 이것만으로 부족한 나머지를 두 단계(local/global)로 추가 제거한다. 소스: `img/src/InSliceDeghosting.cxx`, `img/src/Projection2D.cxx`, `img/inc/WireCellImg/Projection2D.h`, `img/src/ProjectionDeghosting.cxx`, `img/src/ShadowGhosting.cxx`.

---

## 1. `InSliceDeghosting` — slice 내부 국소 정리 (`img/src/InSliceDeghosting.cxx`)

`ChargeSolving` 직후 실행되며, **solved charge**(`iblob->value()`)를 사용해 slice 하나 안에서 신뢰도 낮은 blob을 제거한다.

### 1.1 Bit-tag 시스템

```cpp
namespace {
    template <class Map, class Key, class Pos>
    void tag(Map& m, const Key& k, const Pos& p, const bool tag) {
        if (m.find(k)==m.end()) m[k]=0;
        int& pack = m[k];
        if (tag) pack |= (1 << p);
        else     pack &= ~(1 << p);   // 특정 비트만 클리어
    }
}
```
blob마다 정수 하나에 여러 플래그(bit position enum: `GOOD`, `BAD`, `POTENTIAL_GOOD`, `POTENTIAL_BAD`, `TO_BE_REMOVED`)를 패킹한다. (과거 이 클리어 로직이 `pack &= (0 << p)`로 잘못 구현되어 있어 특정 비트 하나만 지우려 해도 전체 태그가 날아가는 버그가 있었으나, 현재는 `~(1 << p)`로 수정되어 있다.)

### 1.2 Phase 1: `blob_quality_ident` — GOOD/POTENTIAL_GOOD 태깅 (`InSliceDeghosting.cxx:274-313`)

```cpp
if (iblob->value() > m_good_blob_charge_th)          tag(GOOD); tag(POTENTIAL_GOOD);
for (b-b로 연결된 이웃 blob ib)
    if (ib->value() > m_good_blob_charge_th)         tag(POTENTIAL_GOOD);
```
자신의 전하가 크거나, 시간축으로 연결된 이웃 중 전하가 큰 blob이 있으면 "잠재적으로 진짜"로 표시한다. `m_good_blob_charge_th` 기본값 `300`(`02_charge_solving.md`의 `ChargeSolving::good_blob_charge_th`와 개념적으로 같은 값이며, 두 컴포넌트에 각각 설정해줘야 한다 — 단일 소스가 아니라는 점에 유의).

### 1.3 Phase 2: `local_deghosting1` — 와이어 점수 기반 판정 (`InSliceDeghosting.cxx:314-`)

각 slice(`s` 노드) 안에서:

1. **View-count로 그룹화**: 연결된 `meas` 노드 개수 = 살아있는 평면 개수라는 가정 하에, blob을 `view_groups[3]`(3-view, 고신뢰) / `view_groups[2]`(2-view, ghost 가능성 높음)로 분류.
2. **와이어 점수 맵 구축**: 3-view blob이 쓰는 각 채널에 대해 "몇 개의 blob이 이 채널을 쓰는가"를 누적(`wire_score_map`). 2-view blob도 자신의 두 살아있는 평면에 대해 같은 방식으로 누적. 점수가 높을수록(=여러 blob이 공유) 그 채널은 애매(ambiguous), 낮을수록 특정 blob에 고유함.
3. **`cannot_remove` 집합**: 2-view blob이 `POTENTIAL_GOOD` 3-view blob **2개 이상과** `adjacent()`하면 보호 대상으로 지정.
4. **`blob_high_score_map`**: 각 blob에 대해, 살아있는 각 평면의 `mean(1/wire_score)`(그 blob의 채널들이 얼마나 "고유"한지 평균) 중 최댓값. 단, `POTENTIAL_GOOD`으로 태그된 3-view blob은 무조건 1(최댓값)로 강제.
5. **제거 판정**: 2-view blob마다, 자신이 공유하는 measure를 통해 연결된 다른(더 높은 점수의) blob과 비교하여
   - `overlap_ratio = calculate_wire_overlap(wires1, wires2) >= m_deghost_th`(기본 `0.75`), 그리고
   - `current_q2 > current_q1 * m_deghost_th` (상대방 전하가 자신보다 threshold 비율 이상 큼)
   조건을 만족하는 상대가 **2개 이상** 있고, `cannot_remove`에 속하지 않으면 `TO_BE_REMOVED` 태그.

### `adjacent()` — 평면별 인접도 스코어 (`InSliceDeghosting.cxx:145-198`)

```cpp
for (평면 p in cid1) {
    if (p not in cid2) continue;
    overlap  = 채널 교집합 존재?
    is_adj   = 채널 값이 +-1 차이로 인접?
    score = overlap ? 2 : (is_adj ? 1 : 0);
    if (score == 0) return false;      // 공통 평면에서 완전 무관하면 즉시 실패
    sum_score += score;
    if (sum_score >= 5) return true;   // 조기 종료
}
return sum_score >= 5;
```
3평면 모두 겹치면(`2*3=6 >= 5`), 2평면 겹치고 1평면 인접이면(`2+2+1=5`) 등 — "대부분의 평면에서 실질적으로 겹친다"는 것을 하나의 정수 점수로 판정하는 휴리스틱. `calculate_wire_overlap`(§1.4)은 정렬된 두 `set<int>`를 병합하며 공통 원소 개수를 세는 $O(n+m)$ 카운팅 루프(과거 `std::set_intersection` + 임시 벡터 할당 방식에서 할당 없는 방식으로 개선됨).

### 1.4 Phase 3: 그래프 필터링

`TO_BE_REMOVED` blob을 그래프에서 제거하고, 설정에 따라 남은 blob들을 `geom_clustering()`으로 재-clustering한다.

---

## 2. `Projection2D` — 클러스터의 2D 투영 (`img/src/Projection2D.cxx`, `img/inc/WireCellImg/Projection2D.h`)

### `get_projection()` (`Projection2D.cxx:136-266`)

blob 그룹(연결 성분) 하나를 평면별 (channel x time-slice) Eigen 희소 행렬로 만든다:

1. slice->blob, blob->channel 맵 구성.
2. `(slice, blob, channel)` 조합마다 slice의 채널 활동값을 조회 — **여기서 쓰는 값은 blob의 solved charge가 아니라 slice의 raw 채널 활동값**이다. 즉 `Projection2D`는 `ChargeSolving` 이전에도 계산 가능하며, 이것이 `00_pipeline_overview.md` §3에서 본 것처럼 이 저장소의 파이프라인이 `ProjectionDeghosting`을 첫 `ChargeSolving`보다 먼저 배치할 수 있는 이유다.
3. 불확실성이 `uncer_cut`(기본 `1e11`)을 넘으면 "dead" 취급, `dead_default_charge = -1e12`로 마킹.
4. 평면별 Eigen 희소 행렬(triplet -> CSC)로 조립. 추가로 blob별 최소/총 추정 전하, blob 개수, slice 개수 등도 함께 계산.

### `get_geom_clusters()` (`Projection2D.cxx:55-123`)
`cluster_graph_t`에서 blob만 남긴 서브그래프에 `connected_components`를 돌려 (기하학적으로 이어진) 그룹을 만든다.

### `judge_coverage()` (`Projection2D.cxx:365-448`)
두 투영(ref/tar)의 이진 마스크(`charge > -uncer_cut`이면 "살아있음")를 비교해 `REF_COVERS_TAR`/`TAR_COVERS_REF`/`REF_EQ_TAR`/`BOTH_EMPTY`/`OTHER` 중 하나를 판정한다. 부동소수점 비교 threshold `0.01`이 하드코딩되어 있다.

### `judge_coverage_alt()` (`Projection2D.cxx:454-527`)
전하량/픽셀개수 비율까지 고려한 더 정교한 버전:
```
(1 - common_charge/small_charge) < min(cut[0]*(small+dead)/small, cut[1])
AND
(1 - common_counts/small_counts) < min(cut[2]*(small+dead)/small, cut[3])
```
`judge_coverage()`가 "살아있음"을 `> -uncer_cut`(0 전하도 포함)으로 보는 반면, `judge_coverage_alt()`는 `x > 0`만 살아있음으로 세는 등 두 함수의 "live" 정의가 미묘하게 다르다 — 의도된 차이(더 엄격한 대안 모드)로 보이나 문서화되어 있지는 않다.

---

## 3. `ProjectionDeghosting` — 전역 클러스터 비교 (`img/src/ProjectionDeghosting.cxx`)

1. `get_geom_clusters()`로 클러스터(기하학적 blob 그룹) 목록을 얻는다.
2. 각 클러스터에 대해 3평면 각각의 `Projection2D`를 계산.
3. 평면마다, 모든 클러스터 쌍에 대해 `judge_coverage()`/`judge_coverage_alt()`로 "한쪽이 다른 쪽의 부분집합인가"를 비교.
4. 충분히 많은 평면에서 다른(더 우량한) 클러스터에 덮이는 클러스터는 제거 대상으로 표시.
5. 시간창 수 x blob당 전하를 결합한 카이제곱형 전역 컷(`global_deghosting_cut_values`)으로 추가 필터링.

`InSliceDeghosting`이 **slice 내부, 국소적, 와이어 점수 기반**인 반면 `ProjectionDeghosting`은 **클러스터 전체, 전역적, 2D 투영 커버리지 기반**이라는 점이 핵심 차이다. 두 접근이 상호보완적으로 여러 라운드에 걸쳐 반복 적용된다(`00_pipeline_overview.md` §3의 `gd1/cs1/ld1/gd2/cs2/ld2/cs3/ld3` 순서).

---

## 4. `ShadowGhosting` — 미완성 (`img/src/ShadowGhosting.cxx`)

`BlobShadow::shadow()`/`ClusterShadow::shadow()`로 shadow 그래프를 계산은 하지만, 실제로 그 결과를 쓰지 않고 입력 클러스터를 그대로 통과시킨다(pass-through). 향후 구현을 위한 뼈대만 존재하는 상태이므로, 이 컴포넌트에 의존한 설정은 아직 실질적 효과가 없다는 점에 유의.

---

## 5. 요약 비교

| 컴포넌트 | 범위 | 방법 | 입력으로 쓰는 전하 | 실행 시점(이 저장소 기준) |
|---|---|---|---|---|
| `InSliceDeghosting` | slice 내부(local) | 와이어 점수 + 평면별 인접도 | solved charge (`ChargeSolving` 이후) | 각 `ChargeSolving` 라운드 직후 |
| `ProjectionDeghosting` | 클러스터 전체(global) | 2D 투영 커버리지(`Projection2D`) | slice의 raw 채널 활동값 | `ChargeSolving` 이전에도 실행 가능 |
| `ShadowGhosting` | 전역(계획) | cross-view shadow (미구현) | - | 사용 시 사실상 no-op |

---

## Related Documents

- [00_pipeline_overview.md](./00_pipeline_overview.md): 이 세 컴포넌트가 실제로 어떤 순서로 반복되는지(`gd1/cs1/ld1/...`).
- [02_charge_solving.md](./02_charge_solving.md): `InSliceDeghosting`이 사용하는 solved charge를 만드는 단계, `good_blob_charge_th`가 두 컴포넌트에 공유되는 개념임.
- [04_constants_and_caveats.md](./04_constants_and_caveats.md): `m_deghost_th`, `uncer_cut`, `dead_default_charge` 등 하드코딩값과 알고리즘 복잡도(`InSliceDeghosting`은 slice당 $O(n_{2\text{view}} \cdot n_{3\text{view}})$, `ProjectionDeghosting`은 평면당 $O(n_{\text{clusters}}^2)$).
