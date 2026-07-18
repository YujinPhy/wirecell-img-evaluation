# Constants, Known-Bug History, and Efficiency Notes

## Summary

`../wire-cell-toolkit/img/docs/examinations/hardcoded-constants.md`, `potential-bugs.md`, `efficiency-concerns.md`를 바탕으로, 코드를 읽거나 PDHD용으로 튜닝할 때 알아야 할 것들을 정리한다. 2026-07-15 기준 현재 체크아웃된 소스를 직접 대조해 본 결과, examinations 문서에서 "Status: FIXED"로 표기한 항목들은 실제로 소스에 반영되어 있음을 확인했다(`InSliceDeghosting.cxx`의 bit-clear, `CSGraph.cxx`의 Cholesky 직접 계산, `ChargeSolving.cxx`의 `good_blob_charge_th` 설정화 등). 즉 이 examinations 디렉터리는 "발견된 문제 목록"이 아니라 "이미 한 차례 리뷰-수정 사이클을 거친 현재 상태에 대한 기록"으로 읽는 것이 정확하다.

---

## 1. UBooNE에서 넘어온, 검출기별 재검토가 필요한 상수

### `MaskSlice` 기본 threshold (`img/inc/WireCellImg/MaskSlice.h:77-79`)

```cpp
m_nthreshold = {3.6, 3.6, 3.6};
m_default_threshold = {587.819*4.0, 836.644*4.0, 567.974*4.0};  // U/V/W, UBooNE RMS x4
```
`default_threshold`는 `summary`(RMS) 태그가 0일 때만 쓰이는 fallback이라 실제 영향은 적지만, `nthreshold`(RMS 곱셈 계수)는 항상 쓰인다. 이 저장소의 `img.jsonnet`은 `nthreshold: [3.6, 3.6, 3.6]`을 그대로 명시적으로 재설정해서 쓰고 있다(`01_slicing_and_tiling.md` §1) — UBooNE 값을 그대로 채택한 것인지, PDHD 노이즈 특성으로 별도 검증한 것인지는 이 프로젝트 차원에서 확인이 필요하다.

### `FrameQualityTagging` 상수 (`img/src/FrameQualityTagging.cxx:49-68`, `wire-cell-cfg/pdhd/img.jsonnet:59-82`)

| 상수 | 기본값(툴킷) | 이 저장소 설정값 |
|---|---|---|
| `m_min_time`/`m_max_time` | 3180 / 7870 | 동일하게 사용 (`min_time: 3180, max_time: 7870`) |
| `m_length_cut`/`m_time_cut` | 12 / 12 | `3 / 3`로 재설정 |
| `m_ch_threshold` | 100 | 100 (동일) |
| `m_n_cover_cut2`/`m_n_fire_cut2` | 6 / 14 | `6 / 6`로 재설정 |

`min_time`/`max_time`은 특정 run/dataset의 시간창을 하드코딩한 값으로 examinations 문서가 특히 우려하는 항목인데, 이 저장소도 그 값을 그대로 물려받아 쓰고 있다. PDHD 데이터의 실제 유효 시간창(tick range)과 일치하는지 별도 확인이 필요.

### 좋은 blob 전하 임계값 300

`InSliceDeghosting.h`의 `m_good_blob_charge_th{300.}`와 `ChargeSolving`의 `good_blob_charge_th`(과거엔 하드코딩, 현재는 설정 가능) 둘 다 같은 개념의 값 `300`을 쓴다. 두 컴포넌트에 **각각** 설정해줘야 하며 단일 소스가 아니므로, 하나만 바꾸고 다른 하나를 잊기 쉽다. 이 저장소 `img.jsonnet`은 `InSliceDeghosting`에 `good_blob_charge_th: 300`을 명시하지만 `ChargeSolving` 노드에는 명시하지 않아 컴포넌트 기본값(코드 상 기본값도 300으로 보임)에 의존하고 있다 — 값을 바꿀 계획이 있다면 두 곳 모두 갱신할 것.

---

## 2. LASSO/가중치 관련 하드코딩 (`img/src/CSGraph.cxx:144-148`, `img/src/ChargeSolving.cxx:122-129`)

```cpp
lambda    = 3. / total_wire_charge / 2. * scale;
tolerance = total_wire_charge / 3. / scale / R_mat.cols() * 0.005;
max_iter  = 100000;                       // 수렴 확인 없음
weight    = 9 / 3^(prev_con + next_con);  // 9, 3, 1
```
계수 `3, 2, 0.005`와 `9, 3`은 소스에 설명 없이 이식된 값(UBooNE `2dtoy` 유래, `ChargeSolving.cxx` 파일 상단 주석 참조)이며, `02_charge_solving.md` §5.4/§3에서 물리적 해석을 시도했지만 정확한 유래는 코드만으로는 알 수 없다. 정규화 강도 튜닝이 필요하면 이 계수들이 조정 대상이 된다.

---

## 3. Sentinel 값 패턴

| 상수 | 값 | 위치 | 용도 |
|---|---|---|---|
| `dead_default_charge` | `-1e12` | `Projection2D.h:61` | dead 채널 표식 전하 |
| `uncer_cut` | `1e11` | `Projection2D.h:60` | dead 판정 임계값 |
| `dummy_error`/`masked_error` | `1e12` | `MaskSlice.h:73,75` | dummy/masked 채널 오차 |

"사실상 무한대"를 나타내는 관행이며, whitening 시 해당 measure의 가중치를 0에 가깝게 만드는 효과를 낸다(`02_charge_solving.md` §5.5). 데이터 값이 실제로 이 크기에 근접할 일은 없지만, 부동소수점 리터럴을 `==`로 비교하는 코드는 과거 버그의 원인이었다(§5의 #10).

---

## 4. 기하 관련 하드코딩

- **3평면 가정**: `BlobGrouping.cxx:52`의 `bcs(3)` (소스에 `// fixme: hard-code 3 planes` 코멘트로 자기 인정된 제약), `GridTiling.cxx`의 `iplane >= 3` 체크, `MaskSlice.cxx`의 `active_planes[0..2]`, `Projection2D.cxx`의 `kUlayer/kVlayer/kWlayer` 등. 2평면 또는 4평면 이상 검출기로는 포팅 불가.
- **RayGrid 경계 layer 수 = 2**: `GridTiling.cxx:93`(`nbounds_layers = 2`), `BlobSetReframer.cxx:52,129`. RayGrid의 관례이나 API에서 조회하지 않고 하드코딩.
- **Dead-time 오프셋**: `GeomClusteringUtil.cxx:34`, `adjacent_dead(..., offset=4*500*us)` — 설정 불가, TODO 주석("confirm with Xin")이 남아있음.
- **Geometric clustering 정책 표**: `simple`/`uboone`/`uboone_local`의 `max_rel_diff`/`gap_tol` 값들(`01_slicing_and_tiling.md` §6)도 소스에 고정.

---

## 5. 과거 버그 이력 (현재 소스에서 수정 확인됨)

아래는 examinations의 `potential-bugs.md`에 기록된 항목 중, 실제 소스 대조로 "현재는 수정된 상태"임을 확인한 것들이다. 앞으로 이 파일들을 수정할 때 **회귀시키지 않도록** 주의할 지점이라는 의미로 남긴다.

| # | 위치 | 문제 | 수정된 현재 상태 |
|---|---|---|---|
| 1 | `InSliceDeghosting.cxx:66` | `pack &= (0 << p)`가 전체 비트를 지움 | `pack &= ~(1 << p)`로 특정 비트만 클리어 |
| 2 | `InSliceDeghosting.cxx` `calculate_wire_overlap` | `wires1` 비었을 때 0-나눗셈 | `if (wires1.empty()) return 0.0;` 조기 반환 |
| 3 | `CSGraph.cxx` whitening | `mcov.inverse()`가 특이행렬에서 조용히 NaN 전파 | `LLT` 직접 분해 + `llt.info() != Success` 체크 후 조기 반환 |
| 4 | `CSGraph.cxx` 단일-blob 케이스 | `params.scale` 누락으로 다중-blob과 스케일 불일치 | `val / nmeas * params.scale`로 통일 |
| 5 | `Projection2D.cxx:420` | `judge_coverage` 끝에 도달 불가능한 `return OTHER` | 제거됨 |
| 11 | `ChargeSolving.cxx:114-115` | `300` 하드코딩 + TODO | `good_blob_charge_th` 설정 파라미터로 노출 |
| 14 | `Projection2D.cxx` `pair_hash` | XOR만으로 해시 결합(대칭적 충돌) | boost `hash_combine` 스타일 믹싱으로 교체 |
| 17 | `FrameQualityTagging.cxx:83` | `n_fire_cut2` 기본값에 `n_cover_cut2`를 복사-붙여넣기 | 자기 자신의 기본값으로 수정 |

이 외에도 `potential-bugs.md`에 기록된 대부분의 MEDIUM/LOW 항목이 동일하게 수정 확인되었다. **의도적으로 수정하지 않은 것으로 명시된 항목**도 있다: `BlobGrouping.cxx`의 3평면 하드코딩(§4), `DeadLiveMerging.cxx`의 미완성 구현(더미 구현, "FIXME: which ident to use?"). 이들은 버그라기보다 알려진 미해결 제약으로 남겨둔 것이다.

---

## 6. 알고리즘 복잡도 / 효율성 노트

| 컴포넌트 | 복잡도 | 비고 |
|---|---|---|
| `InSliceDeghosting::local_deghosting1` | slice당 $O(n_{2\text{view}} \cdot n_{3\text{view}})$ (인접도) + $O(n_{2\text{view}} \cdot n_{\text{meas}} \cdot n_{\text{blobs/meas}})$ (점수) | 근본적으로 2-view/3-view 쌍별 비교가 필요; 공간 인덱싱 없이는 줄이기 어려움 |
| `ProjectionDeghosting` | 평면당 $O(n_{\text{clusters}}^2)$ | 클러스터 쌍별 커버리지 비교가 알고리즘 자체의 요구사항 |
| `CMMModifier` | $O(n^3)$ (채널 x 인접탐색 x 시간정렬) | 채널 수가 많은 검출기에서 누적 |
| `BlobDepoFill` | $O(n_{\text{slice}} \cdot n_{\text{depo}} \cdot n_{\text{wire}} \cdot n_{\text{blob}})$ | 공간 인덱싱(R-tree 등) 없이는 사실상 $O(n^4)$ — 이 저장소가 실제로 쓰는 컴포넌트이므로(`CLAUDE.md` Stage 1) depo/blob 수가 많아지면 체감 성능 이슈가 될 수 있음 |
| `CSGraph::solve` whitening | (수정 전) 명시적 역행렬 $O(n^3)$ + 별도 Cholesky $O(n^3)$ -> (수정 후) 직접 Cholesky + 삼각대입, 역행렬 계산 생략 | §5의 #3과 연결 |

대부분의 "NOT FIXED" 효율성 이슈는 알고리즘 자체의 본질적 요구사항(쌍별 비교)이거나, 이 프로젝트 규모에서는 영향이 미미한 사소한 할당 패턴(`reserve()` 누락 등)이다.

---

## Related Documents

- [00_pipeline_overview.md](./00_pipeline_overview.md): 전체 파이프라인 및 이 저장소의 실제 설정 예시.
- [01_slicing_and_tiling.md](./01_slicing_and_tiling.md): `nthreshold`/`nudge`/geometric clustering 정책 표가 실제로 쓰이는 맥락.
- [02_charge_solving.md](./02_charge_solving.md): LASSO lambda/tolerance/weight 상수의 수학적 의미.
- [03_deghosting.md](./03_deghosting.md): `m_deghost_th`, `uncer_cut` 등이 쓰이는 알고리즘 맥락.
