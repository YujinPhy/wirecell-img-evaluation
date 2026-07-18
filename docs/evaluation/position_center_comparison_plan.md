# Plan: Position Evaluation - Blob Center

## Document Metadata
* **Created Date:** 2026-07-14
* **Last Updated:** 2026-07-14

## Summary
* Point depo의 참값 중심과 reco blob의 중심을 (x, y, z) 축별로 비교해 3D imaging position 정확도를 정량화하는 Task의 계획 문서.

## 1. Task/Component Identification 
- **Context:** 3D Imaging의 performance evaluation에서 depo와 reco blob의 중심 위차가 어느정도로 비슷한지 비교해보고, 향후 evaluation 방향성을 구체화한다.
    -> 중앙 좌표가 비슷하면 Blob에 대한 위치와 전햐에 대한 evaluation을 독립적으로 수행 가능
    -> 그렇지 않다면 추가적인 방안 탐구 필요
- **Target Component:** 분석, 수정, 또는 구현하고자 하는 구체적인 대상 (코드, 모델, 데이터셋 등)
    - 데이터: `/nfs/data/1/yujin/wirecell-img-evaluation/pdhd-wct-sim/05132026_point_depo_multi_scan_modified_subset`에 x좌표가 서로 다른 위치에서의 point depo의 데이터가 존재한다. 해당 데이터의 파일 이름을 통해 위치를 파악할 수 있다.
    - `scripts/position_center_comparison.py`를 생성하여 모든 분석과 관련된 코드를 작성한다.
    - 결과는 `results/position_center_comparison/`를 생성하여 하위에 저장한다.
- **Dependency:** 사전 task는 없으며 해당 작업 이후, position의 정확도가 어느정도 좋다고 판단되면, position과 charge에 대한 평가를 어느정도 분리하여 진행가능. 또한 현재 데이터는 적기에, 추후 point depo를 검출기 내 많은 지점에서 생성하도 동일한 작업을 할 계획.

## 2. Background Knowledge & Information Gathering 
- **Reference Materials:**
    - `docs/time_offset_calibration.md`: depo 시간과 reco blob 시간 사이의 `time_offset`(`314.5us` 현재 설정값, `313.9us` 재보정값)의 원인 분석 및 검증. 이 Task는 `T_OFFSET=314.5us`(계획 문서/기존 스크립트 명시값)를 그대로 쓰기로 확정(2026-07-13, 아래 §3 참고).
    - `docs/true_blob_prototype.md`, `docs/position_shape_evaluation.md`: 기존 depo-vs-reco-blob 비교 파이프라인(`true_blob.py`/`wires.py`/`eval/position_shape.py`)의 설계. 이 Task는 이 무거운(wire geometry, shapely 폴리곤 교차) 파이프라인을 쓰지 않고, corner 평균 기반의 훨씬 가벼운 방식을 쓴다 — 이유는 §3 참고.
    - `scripts/pdhd_single_point_analysis.py`: `V_DRIFT=1.6`, `T_SPAN=2`, `T_OFFSET=314.5`, `ANODE1_X_POS=3430.47`(모두 이 Task의 계획에 그대로 명시된 값과 동일)가 이미 정의되어 있고, `plot_depo_gaussian_long_ax`에서 `depo_t_us = depo['t']/1000.0 + T_OFFSET` 형태로 쓰인 전례가 있다.
    - `scripts/pdhd_true_blob_check.py`: `ANODE_INDEX=1, FACE_INDEX=1` 고정 전례, `load_generation_data(..., gen_index=0)`(post-drift)를 depo 참값으로 쓰는 전례.
- **Claude Command for Gathering:**
    - `scripts/utils/load.py` — `load_generation_data(depo_file, gen_index)`, `load_cluster_data(cluster_file)`, `load_graph_nodes(cgraph, 'b')`만 재사용(depo/reco blob 로딩에 필요한 전부).
    - `scripts/utils/blob_inspect.py` — reco blob 노드의 `corners` 필드가 `[t_ns, y_mm, z_mm]`이며 (x가 아니라 시간!) 모든 corner에서 첫 값이 그 blob의 slice `start`와 동일함을 확인한 근거.
    - `wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet:16` — `anodes=[1]`만 시뮬레이션 대상이라, `pdhd-wct-sim/.../X*_Y300_Z100/clusters-apa-0.tar.gz`가 항상 거의 비어 있음(anode_index=1 고정 근거).

## 3. Task Planning (실험 및 개발 계획 수립)
- **Objective:** 
    1. point depo와 reco blob의 중심 위치를 비교하여 중심이 잘 일치하는지 확인한다.
    2. 일치하지 않는 경우를 파악하여, 어떻게 y-z상에서 위치하는지 확인한다.
    3. 이후 point depo의 개수를 늘려, detector volmume 내 전체적으로 확인한다.
    - 중심사이의 거리 차이를 를 각 축에 대해서 히스토그램으로 그린다. -> 히스토그램 평균값에 대하여 많이 벗어난 데이터를 분류한다.
    - 해당 데이터들의 depo와 blob을 시각화하여 어떻게 차이가 나는지 비교한다.  
- **Success Criteria:** depo와 blob의 중심 차이 분포의 평균 기준 1시가마 내의 개수가 95%이상
- **Action Items:** 목표 달성을 위해 순차적으로 수행할 구체적인 구현 및 실험 단계 (Step-by-step)
    1. 데이터가 존재하는 디렉터리를 스캔하여, 좌표를 파악한다.
    2. 좌표별로 for문을 돌면서 처리한다.
        - 한 좌표에 대해서 필요한 데이터 세트를 로드한다. (`scripts/utils` 내의 로디 함수를 활용)
        - depo 데이터(zip파일)과 reco blob 데이터(tar.gz)파일만 필요(bdf는 필요 없음. 전하 정보는 관련없음)
        - reco blob 데이터에서 존재하는 slice와 blob를 모두 스캔한다.
        - slice 순서대로, blob 단위로 처리한다.
        - blob 하나의 corner의 정보를 활용하여 이들의 (x, y, z)평균값을 blob의 중심으로 간주한다.
    4. depo의 경우 drift된 gen의 데이터를 활용한다. 
        - x축(시간축)의 경우,  `V_DRIFT = 1.6 # [us], T_SPAN = 2 # [us], T_OFFSET = 314.5 # [us], ANODE1_X_POS = 3430.47 # [mm]`값을 활용하여 drifte하기 이전의 위치를 계산한다. 이를 통해 depo의 중심의 x좌표를 얻는다.
        - (y, z) 좌표의 경우에는, 데이터 상에 명시되어 있으므로 그대로 사용가능(시간 또는 slice와 무관하므로)
    5. depo와 blob의 중심 좌표를 비교한다.
        - `blob 중심 - depo 중심` 으로 중심 차이를 부호 고려하여 계산한다.
        - 모든 blob에 대해 계산하여 x, y, z 축에 대해 3개의 히스토그램을 그린다.(가로축을 중심 차이로 한다.)
        - 각 히스토 그램의 평균과 분산을 계산한다. 
        - 중심 기준 좌우로 1시그마 이상 벗어난 데이터들의 리스트를 확인한다. 

### [2026-07-13] 업데이트 내용 — 실측 검증 및 세부 공식 확정

실제 데이터(`pdhd-wct-sim/05132026_point_depo_multi_scan_modified_subset`)를 직접 로드해 위 §3의 항목들을 다음과 같이 구체화/검증했다. 아직 코드는 작성하지 않았고, 아래는 구현 시 그대로 따를 확정된 설계다.

**데이터 레이아웃 확인**
- 서브디렉터리는 `X<n>_Y300_Z100` 형태로 34개(X=10..340, step 10) 존재. 각 디렉터리에 `depos-drifted-{0,1}.zip`, `clusters-apa-{0,1}.tar.gz`, `clusters-apa-bdf-{0,1}.tar.gz`, `.root`, `.log`가 있다.
- `anode_index=1, face_index=1`만 쓴다. `clusters-apa-0.tar.gz`는 항상 거의 빈 파일(~154bytes)이다 — 시뮬레이션 설정(`wct-sim-nf-sp-img-bdf.jsonnet:16`)이 `anodes=[1]`만 대상으로 하기 때문.
- **디렉터리 이름은 좌표 파싱에 쓰지 않는다.** `X100_Y300_Z100`의 실제 depo pre-drift x가 1000mm가 아니라 3300mm임을 실측으로 확인했다("modified_subset"이라는 이름대로 일부 항목이 원 스캔에서 변형된 것으로 보인다). 디렉터리 이름은 순회(iteration)용으로만 쓰고, 실제 depo/blob 좌표는 항상 로드한 데이터에서 얻는다.

**Depo 중심 x좌표 복원 공식 (실측 검증 완료, 오차 <0.01mm)**
```
depo_x_mm = ANODE1_X_POS - V_DRIFT * (depo['t'][idx] / 1000.0)   # depo['t']는 ns 단위, gen_index=0(post-drift)
```
Gen0(`load_generation_data(depo_file, 0)`)의 `t`는 `Gen::Drifter`가 원본 시간에 순수 drift transit time만 더한 값이라 그 자체로 anode까지의 거리를 인코딩하며, **`T_OFFSET`을 더할 필요가 없다** (처음엔 4개 상수를 depo 쪽에도 모두 적용해야 하는 줄 알았으나, X10/X100/X200/X300 4개 지점에서 실측한 결과 offset 없이도 Gen1(pre-drift 참값)의 실제 x와 소수점 이하로 일치함을 확인했다). `depo_y_mm = depo['y'][idx]`, `depo_z_mm = depo['z'][idx]`는 그대로 사용(§3 Action Item 4 원안과 동일).

**Blob 중심 x좌표 변환 공식 — corners 필드가 시간(ns)이라는 점 확인**

reco blob 노드의 `corners` 필드는 `[x, y, z]`가 아니라 **`[t_ns, y_mm, z_mm]`**이다(`scripts/utils/blob_inspect.py`, `docs/position_shape_evaluation.md` §2.1). 한 blob 내 모든 corner의 첫 값은 동일하며 그 blob의 slice `start`(즉 span의 시작 시각)와 같다. 이 점이 원안(§3 Action Item 3, "corner의 (x,y,z) 평균")에서 암묵적으로 가정하지 않았던 부분이라 명시적으로 확정한다.

```
blob_t_us  = (blob['start'] + blob['span'] / 2.0) / 1000.0   # slice 중간 시점을 시간 중심으로 사용
blob_x_mm  = ANODE1_X_POS - V_DRIFT * (blob_t_us - T_OFFSET)
blob_y_mm  = corners[:, 1].mean()
blob_z_mm  = corners[:, 2].mean()
```
- `start`(slice 시작, 즉 corner의 원값 그대로)가 아니라 `start + span/2`(slice 중간 시점)을 쓰기로 확정했다: 실측 결과 `start`만 쓰면 depo 참값보다 항상 앞선 시점이 되어 x 오차 히스토그램에 slice 폭(2us=3.2mm)만큼의 체계적 바이어스가 낀다. `start+span/2`를 쓰면 이 바이어스가 절반으로 줄어든다(실측: X10/X100/X200/X300에서 `start` 사용 시 오차 +5.7~+6.5mm, `start+span/2` 사용 시 +2.4~+4.9mm).
- `T_OFFSET=314.5us`(계획 문서 명시값 = `pdhd_single_point_analysis.py`의 기존 상수 = `wire-cell-cfg/pdhd/img.jsonnet`에 실제 설정된 값)를 그대로 쓰기로 확정했다. `docs/time_offset_calibration.md`가 별도로 재검증한 `313.9us`(analytic baseline 312.5us + 실측 residual 1.4us)와 0.6us 차이가 나지만, 이 Task의 mm 단위 분석에 미치는 영향(<1mm)은 무시할 수 있다고 판단해 기존 스크립트와의 일관성을 우선했다.
- `blob_y_mm`/`blob_z_mm`은 `corners[:, 1:3]`의 단순 산술 평균이다(원안 §3 그대로) — `eval/position_shape.py`의 shapely 폴리곤 area centroid가 아닌 vertex 평균이라는 근사이며, 소수 mm 수준의 차이가 날 수 있다(§ 알려진 한계 참고).

**한 위치에 blob이 여러 개 존재할 때의 처리**

Point depo 하나의 longitudinal diffusion이 여러 2us time-slice에 걸쳐 퍼지기 때문에, 한 위치(depo 1개)에 보통 3~4개의 reco blob이 생긴다. 실측 예(X100, 4개 blob): `val`(전하)이 372 / 21320 / 21793 / 724로, 중앙 슬라이스에 전하가 집중되고 가장자리 슬라이스는 전하가 매우 작다.

원안(§3 Action Item 2, "slice 순서대로, blob 단위로 처리한다")을 문자 그대로 따라 **모든 blob을 개별적으로 depo 중심과 비교하며, 하나로 합치거나 가중평균하지 않는다.** 가장자리(저전하) 슬라이스가 더 큰 편차를 보이는 것 자체가 §3 Objective 2("일치하지 않는 경우를 파악하여 어떻게 y-z상에서 위치하는지 확인")가 찾고자 하는 대상이라고 판단했기 때문이다. 각 diff 레코드에 그 blob의 `val`(전하)을 함께 기록해, outlier가 저전하 가장자리 슬라이스인지 나중에 바로 구분할 수 있게 한다.

**파이프라인 재사용 범위**

`true_blob.py`/`wires.py`/`eval/position_shape.py`(wire geometry PCA, shapely 폴리곤 교차)는 이 Task에 쓰지 않는다. 이 Task는 그보다 훨씬 가벼운, corner 평균 대 depo 점 비교이며 `scripts/utils/load.py`의 로더(`load_generation_data`, `load_cluster_data`, `load_graph_nodes`)만 재사용한다.

**아직 미착수**: `scripts/position_center_comparison.py` 코드 작성은 이번 세션에서 하지 않았다. 위 확정된 설계대로 구현 착수 여부는 별도로 다시 확인 후 진행한다.

---

## Related Documents
문서 맨 하단에 불릿(`-`) 리스트로 작성하며, 링크와 함께 해당 문서와의 연관성을 간략히 기술한다. 관계는 오직 다음 3가지로만 분류한다.

* **Parent docs:** 해당 문서의 상위 문서 (예: Report 입장에서의 Plan 문서, 또는 상위 대규모 Task 문서)
  * `- [Upper_Project_Plan.md](../Upper_Project_Plan.md): 본 Task가 속한 상위 프로젝트의 메인 계획서`
* **Child docs:** 해당 문서의 하위 문서 (예: Plan 입장에서의 Report 문서, 또는 세부 서브 Task 문서)
  * `- [Task-01_Feature-A_Report.md](./Task-01_Feature-A_Report.md): 본 계획에 따른 수행 결과 및 검증 리포트`
* **Sibling docs:** 본 Task와 밀접한 연관이 있거나 참고한 문서 (예: 유사한 이전 Task, 참고 문서 등)
  * `- [Task-00_Baseline_Report.md](../Task-00/Task-00_Baseline_Report.md): 본 실험의 대조군으로 참