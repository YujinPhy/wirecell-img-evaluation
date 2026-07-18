# Charge Solving (LASSO)

## Summary

`GridTiling`이 만든 blob들은 형태(어떤 와이어를 덮는지)만 알 뿐, 실제 전하값(`value()`)은 아직 0이다. 같은 채널을 여러 blob이 공유하기 때문에(`01_slicing_and_tiling.md` §4), "이 채널의 전하를 어느 blob에 얼마나 배분할 것인가"는 대수적으로 미결정(under/over-determined mixed) 문제이며, `ChargeSolving`은 이를 **LASSO(L1-정규화 최소제곱) 회귀**로 푼다. 소스: `img/src/ChargeSolving.cxx`, `img/src/CSGraph.cxx`, `img/inc/WireCellImg/CSGraph.h`, `img/src/BlobSolving.cxx`, `img/src/ChargeErrorFrameEstimator.cxx`.

---

## 1. 문제 설정

한 시간창(slice) 안에서:
- $n$개의 blob(미지수) $x \in \mathbb{R}^n$ — 각 blob의 전하량.
- $m$개의 measure(관측값) $\text{meas} \in \mathbb{R}^m$ — `BlobGrouping`이 만든, 전기적으로 연결된 채널 그룹의 신호 합.
- 결합 행렬 $A \in \{0,1\}^{m \times n}$: $A_{ij}=1$이면 blob $j$가 measure $i$에 기여.
- 측정 공분산 $\Sigma$ (대각, $\Sigma_{ii} = \sigma_i^2$ = 그 measure의 불확실성 제곱).
- blob별 정규화 가중치 $w_j$.

$m < n$인 경우가 흔하다 — 여러 blob이 같은 와이어를 겹쳐 덮으므로, 미지수(blob)가 관측값(measure)보다 많을 수 있다. 이때 순수 최소제곱은 해가 유일하지 않으며, LASSO의 L1 정규화가 "증거가 부족한 blob의 전하를 0으로 밀어내는" 방식으로 모델 선택(model selection) 역할을 한다 — **이것이 charge solving 자체가 일종의 deghosting이기도 한 이유**다. `Ax=m`을 풀되:

$$\min_x \; \| U(Ax - \text{meas}) \|_2^2 + \lambda \sum_j w_j |x_j|$$

여기서 $U$는 $\Sigma^{-1} = U^T U$를 만족하는 whitening 변환(Cholesky factor).

---

## 2. `ChargeSolving::operator()` — 오케스트레이션 (`ChargeSolving.cxx:249-323`)

```
Input ICluster
  -> unpack(in_graph, meas_thresh)            // slice별 + connected-component별 b-m 서브그래프로 분해
  -> for strategy in weighting_strategies:    // 기본: ["uboone"], 이 저장소는 uniform 이후 uboone 2단계
       for sg in subgraphs:
         blob_weighter(in_graph, sg, good_blob_charge_th)  // vtx.value.uncertainty()에 가중치 기록
         sg = solve(sg, sparams)                            // LASSO
         sg = prune(sg, blob_threshold)                      // 임계값 이하 blob 제거
  -> repack(in_graph, subgraphs)              // 원본 cluster graph에 풀린 값 반영
Output ICluster
```

가중치 전략을 여러 개(`weighting_strategies` 리스트) 순서대로 적용할 수 있다. 이 저장소의 `img.jsonnet`(`solving()` 함수)은 `["uniform"]`로 한 번 풀고 나서(`cs1`) `LocalGeomClustering`으로 blob 그룹을 다시 묶고, 다시 `["uboone"]`로 한 번 더 푼다(`cs2`) — "일단 균등 가중치로 대충 풀어 어떤 blob이 살아남는지 본 뒤, 연결성 정보로 재-clustering하고 세밀한 가중치로 다시 푼다"는 2단계 전략으로 읽힌다.

---

## 3. Blob 가중치 전략 (`ChargeSolving.cxx:54-131`)

가중치는 `vtx.value.uncertainty()` 필드를 재활용해서 저장한다(주석: "weight"는 실제로는 LASSO의 정규화 강도이며, `value_t`의 uncertainty 슬롯을 빌려쓰는 것뿐, 물리적 불확실성이 아니다).

### `uniform`
모든 blob에 가중치 `9.0`. 위상 정보 없음.

### `simple`
```cpp
slice_idents.insert(현재 slice ident);
for (neighbor : b-b edges) slice_idents.insert(neighbor.slice().ident());
weight = slice_idents.size();
```
연결된 고유 slice 개수(현재 slice 포함, 최소 1) — 더 많은 시간창에 걸쳐 연결된 blob일수록 가중치(=정규화 강도)가 커진다. `distance` 기반 확장은 TODO로 남아있다(`ChargeSolving.cxx:88`).

### `uboone`
```cpp
double weight = 9.;
if (다음 slice에 charge > charge_th인 연결 blob 있음) weight /= 3.;
if (이전 slice에 charge > charge_th인 연결 blob 있음) weight /= 3.;
```

| 연결성 | 가중치 |
|---|---|
| 양쪽 다 없음 (고립) | 9.0 |
| 한쪽만 | 3.0 |
| 양쪽 다 | 1.0 |

$9=3^2, 3=3^1, 1=3^0$의 등비수열. `charge_th`는 과거 `ChargeSolving.cxx`에 `300`으로 하드코딩되어 있었으나(examinations 문서 기록), 현재 소스는 `good_blob_charge_th` 설정 파라미터로 노출되어 있고 `InSliceDeghosting`의 동명 파라미터와 같은 개념이다(`04_constants_and_caveats.md` 참조). **고립된 blob일수록 강하게 정규화(=0으로 밀림)되고, 앞뒤로 모두 이어진 blob은 거의 정규화되지 않는다** — 시간적으로 연속된 궤적일수록 신뢰한다는 물리적 직관을 인코딩한 것.

---

## 4. `CS::unpack` — 클러스터 그래프를 slice별 서브그래프로 분해 (`CSGraph.cxx`, 헤더는 `CSGraph.h`)

1. 모든 `b`(blob) 노드를 찾고, 각각의 소속 `s`(slice)와 연결된 `m`(measure)들을 찾는다.
2. slice별로 그룹화해 blob/measure 노드만 있는 그래프를 만든다.
3. `meas_thresh` 적용: 값이 threshold 미만이거나 불확실성이 threshold 초과인 measure는 skip.
4. `msum.uncertainty() > 0`이 아닌 measure는 skip(경고 로그, 예외 아님) — 불확실성이 0 이하인 measure를 그대로 두면 뒤의 whitening에서 division-by-zero/특이 행렬 문제가 생기므로 사전에 걸러내는 방어 코드.
5. slice별 그래프를 다시 `connected_subgraphs()`로 쪼갠다 — 서로 완전히 분리된 blob-measure 성분은 독립적으로 풀어도 되므로, LASSO를 더 작은 문제들로 분할해 효율을 높인다.

---

## 5. `CS::solve` — LASSO 본체 (`CSGraph.cxx:33-215`)

### 5.1 준비
```cpp
source(bind) = blob_in.value.value();        // 초기 추정값
weight(bind) = blob_in.value.uncertainty();  // §3의 가중치
measure(mind) = meas_in.value.value();
mcov(mind, mind) = uncertainty^2;             // 대각 공분산
```
`params.whiten && mcov.sum() == 0.0`이면 즉시 빈 그래프 반환(측정값이 전부 무의미).

### 5.2 단일-blob 특수 케이스 (`config == simple && nblob == 1`)
LASSO를 아예 돌리지 않고, 연결된 모든 measure 값의 평균을 그대로 그 blob의 전하로 쓴다:
```cpp
csg_out[nbdesc].value = val / nmeas * params.scale;
```
(과거에는 `params.scale` 곱셈이 누락되어 다중-blob 경로와 스케일이 어긋나는 버그가 있었으나 현재는 수정되어 있다 — `04_constants_and_caveats.md`.)

### 5.3 결합 행렬 $A$ 구성
`csg`의 모든 엣지를 순회하며 `A(mind, bind) = 1`을 채운다(이진 행렬).

### 5.4 `uboone` 설정의 LASSO 파라미터 (`CSGraph.cxx:144-148`)
```cpp
double total_wire_charge = m_vec.sum();               // whitening 전, 스케일링 전
double lambda    = 3. / total_wire_charge / 2. * params.scale;
double tolerance = total_wire_charge / 3. / params.scale / R_mat.cols() * 0.005;
rparams = Ress::Params{Ress::lasso, lambda, /*max_iter=*/100000, tolerance, true, false};
```
- $\lambda = 1.5 \cdot \text{scale} / Q_{\text{tot}}$: 총 wire 전하가 클수록(신호가 강할수록) 정규화를 상대적으로 약하게, 전하가 작을수록(노이즈 대비 신호가 약할수록) 강하게 — L1 항이 데이터 항과 비슷한 스케일을 유지하도록 하는 정규화(normalization)로 해석된다.
- `tolerance`도 같은 방식으로 총 전하에 반비례, blob 개수(`R_mat.cols()`)에도 반비례.
- 계수 `3, 2, 0.005`는 소스에 설명 없이 하드코딩되어 있다(UBooNE 2dtoy 코드에서 이식된 값으로 추정 — 파일 상단 주석 "reimplements ... BNLIF/wire-cell-2dtoy" 참조).
- `max_iter = 100000`은 하드코딩이며, 수렴 여부를 별도로 확인하는 코드는 없다.

### 5.5 Whitening (Cholesky) — 현재 구현 (`CSGraph.cxx:159-178`)
```cpp
Eigen::LLT<double_matrix_t> llt(mcov);         // mcov = L L^T  (직접 Cholesky, 역행렬 계산 없음)
if (llt.info() != Eigen::Success) { 경고 후 조기 반환; }
auto L = llt.matrixL();
m_vec = L.solve(measure);            // U*measure,  U = L^{-1}
R_mat = params.scale * L.solve(A);   // U*A
```
$\Sigma^{-1} = L^{-T}L^{-1}$이므로 $U=L^{-1}$이 whitening 변환이 되고, `L.solve(x)`는 $L^{-1}x$를 삼각행렬 전진대입으로 계산한다 — 명시적 역행렬(`mcov.inverse()`, $O(n^3)$)과 그 뒤의 별도 Cholesky를 모두 생략하는 효율적 구현이다. 과거 버전은 `mcov.inverse()`를 먼저 계산했었고, 그 결과가 특이/근사-특이일 때 NaN이 조용히 전파되는 버그가 있었다(`04_constants_and_caveats.md` #3, #10). 현재는 `llt.info()` 체크로 방어한다.

### 5.6 Solve & 후처리
```cpp
auto solution = Ress::solve(R_mat, m_vec, rparams, source, weight);  // 외부 Ress 라이브러리의 LASSO
auto predicted = Ress::chi2 등 diagnostic 계산
bvalue.value = solution[ind] * params.scale;   // 주의: weight는 결과에 반영되지 않음("drops weight")
```
`Ress::solve`가 실제 좌표하강(coordinate descent) 등 LASSO 최적화를 수행하는 부분으로, `source`(초기값)와 `weight`(정규화 강도, per-blob)를 받는다. 결과 `uncertainty`는 갱신되지 않는다는 점(코멘트 "drops weight")에 유의 — 즉 solved blob의 `uncertainty()`는 물리적 의미의 오차가 아니라 §3에서 마지막으로 기록된 가중치 값이 남아있을 수 있다.

### `CS::prune` / `CS::repack`
- `prune`: `value >= threshold`인 blob/그와 연결된 measure만 복사.
- `repack`: 여러 slice의 solved 서브그래프들을 원본 `cluster_graph_t` 크기로 되돌리며, 생존한 blob은 solved value로 교체하고 pruned된 blob/measure는 제거.

---

## 6. `BlobSolving` — 더 단순한 독립 LASSO 변형 (`img/src/BlobSolving.cxx`)

`CSGraph` 파이프라인을 쓰지 않는 standalone 컴포넌트. 가중치 스킴은 동일(`base=9`, 연결마다 `/3`, 최대 2개 slice까지 확인 — 변수명 `homer`가 "Max Power"라는 농담성 이름으로 남아있다). 매 slice마다 직접 `Ress::solve`를 호출하며, `uncertainty`는 항상 `0.0`으로 고정(코드 내 FIXME로 명시).

---

## 7. `ChargeErrorFrameEstimator` — 채널별 전하 불확실성 추정 (`img/src/ChargeErrorFrameEstimator.cxx`)

`CSGraph`가 쓰는 `mcov`(measure의 불확실성)는 여기서 미리 계산된다. ROI(Region Of Interest) 길이로 인덱싱된 사전 계산 오차 파형을 룩업하고, 평면별 fudge factor를 곱한다. 시간 구간별로 다른 모델(`time_limits.first`/`.second` 앞/사이/뒤)을 쓴다. 이 저장소의 `img.jsonnet`(`pre_proc` 함수)에서 `fudge_factors: [2.31, 2.31, 1.1]`, `time_limits: [12, 800]`(단위: tick), `rebin: 4`로 설정되어 있으며 `microboone-charge-error.json.bz2` 파형을 사용한다 — 이름 그대로 UBooNE에서 만든 오차 모델을 그대로 재사용하고 있음을 뜻하므로, PDHD 전용 오차 모델이 따로 검증되기 전까지는 정성적 참고치로만 취급하는 것이 안전하다.

---

## Related Documents

- [00_pipeline_overview.md](./00_pipeline_overview.md): 전체 파이프라인, 이 저장소의 `solving()` 파이프라인이 `ChargeSolving`을 두 번(uniform -> uboone) 호출하는 구조.
- [01_slicing_and_tiling.md](./01_slicing_and_tiling.md): `BlobGrouping`이 만드는 `b-m` bipartite 구조(§4) — 여기서 푸는 대상.
- [03_deghosting.md](./03_deghosting.md): LASSO의 정규화만으로 못 없애는 ghost blob을 추가로 처리하는 단계. `InSliceDeghosting`은 여기서 나온 solved charge(`iblob->value()`)를 직접 사용한다.
- [04_constants_and_caveats.md](./04_constants_and_caveats.md): `good_blob_charge_th`, lambda/tolerance 계수 등 하드코딩값 정리.
