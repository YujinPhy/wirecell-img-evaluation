# position_eval_center_comparison_Report

## Document Metadata
* **Created Date:** 2026-07-14
* **Last Updated:** 2026-07-18

## Summary
* `scripts/position_center_comparison.py`를 통해 point depo의 중심과 reco blob 중심을 34개 위치, 118개 (depo, blob) 쌍에 대해 비교하였다.
* Success Criteria(축별 1시그마 이내 95% 이상)는 x축(59.3%)과 z축(66.1%)에서 미달했고, y축(97.5%)은 형식적으로는 통과했지만 이는 3개의 `val=0`(전하 0) degenerate blob이 표준편차를 비정상적으로 부풀린 착시 효과임을 시각적으로 확인했다.
* 이 degenerate blob들을 제외한 나머지 데이터는 x/y/z 모두 수 mm 스케일의 편차를 보이며, 이는 diffusion tail 가장자리의 저전하 slice에서 주로 발생한다.
* (2026-07-17) `scripts/position_center_comparison_grid.py`(단일 파일에 여러 depo가 packed된 경우)를 `scripts/position_center_comparison.py`에 `--mode {per_file,one}`로 통합하고, `depo_idx`를 전체 파이프라인(통계/outlier plot)에 걸쳐 일반화했다. `point_depos_Y300Z100_small`(`--mode per_file`, 34 위치/118쌍)와 `point_depos_Y300Z100_one`(`--mode one`, depo 60개/121쌍) 두 데이터셋으로 재실행한 결과, 두 모드 모두 median 기준 x~0.9-1.0mm, y~1.5mm, z~0.8-0.9mm로 서로 잘 일치했고, 최대 outlier의 원인도 동일한 `val=0` degenerate blob으로 재확인되어 `--mode one`의 시간 기반 매칭(`match_blobs_to_depos`)이 `--mode per_file`과 동등한 품질의 depo/blob 대응을 복원함을 검증했다.

---

## 사전 작업
- Reconstructed blob과 True Deposition 간의 Time offset 문제을 해결해야 함.
    - 현재 314.5us 값을 우선 사용하고, 추후에 analytic한 방법으로 찾거나, offset을 없애는 방법에 대한 study 진행 필요

## Code Implementation Steps(2026-7-14)
- Code: `scripts/position_center_comparison.py`

#### 1. 데이터 스캔






`scan_positions()`가 `base_dir` 하위 서브디렉터리를 스캔하여 나열 및 경로 리스트를 생성, 좌표는 항상 로드된 데이터에서 얻으며 디렉터리 이름은 순회용으로만 사용
- Data: `/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_small` 하위 좌표에 따른 (depo, blob) 쌍
    - 34개 `X*_Y300_Z100` 서브디렉터리를 나열하고, 각각에 `depos-drifted-1.zip`/`clusters-apa-1.tar.gz`(anode_index=1 고정)가 있는지만 확인. 디렉터리 이름은 순회용으로만 쓰고, 좌표는 항상 로드된 데이터에서 얻는다.
    - 위치정보만 비교하므로 `BlobDepoFill`파일은 불필요
> 해당 작업에서 파일 이름과 같이 하드코딩된 부분이 존재하여 다른 경우에 적용하기에 유연하지 않지만 초기 스터디의 히스토리를 위해 관련 파일은 계속 남겨둠

> **(2026-07-18)** 이 "depo 1개당 파일 1개" 가정은 원래 `--mode per_file`(기본값, 위 로직 그대로) 전용이었다. 이제 하나의 depo/reco 파일 쌍에 여러 point-depo 위치가 packed된 경우(`--mode one`)도 같은 파이프라인으로 처리한다: `match_blobs_to_depos()`가 각 depo의 예상 reco-clock 시각(`depo_reco_time_ns` = depo의 Gen0 `t` + `t_offset`)과 각 blob의 slice-window 중심 시각(`start + span/2`)을 비교해 최근접 시간의 depo에 blob을 배정한다. 두 모드 모두 최종적으로 `(label, depos, blobs, depo_idx)` 그룹 리스트로 수렴하고(`collect_groups_per_file`/`collect_groups_one`), 이후 2~5단계는 완전히 동일한 코드(`collect_records` 이하)를 공유한다. 인접 위치들의 depo 시간 분포가 크게 겹치지 않는다는 가정에 의존하는 휴리스틱이므로, depo가 매우 촘촘한 grid(예: `data/pdhd/point_depo_grid_v1`, depo 89776개)에서는 매칭이 깨질 수 있음을 확인했다(§Code Implementation Steps 2026-07-17 재실행 결과 참고).

#### 2. Blob 중심 계산
하나의 Blob을 구성하는 모든 corner 좌표의 산술평균을 통해 중심 좌표를 계산. 
- `blob_center()`: `corners` 필드가 `[t_ns, y_mm, z_mm]`임을 반영해, `x = ANODE1_X_POS - V_DRIFT * ((start+span/2)/1000 - T_OFFSET)`(T_OFFSET=314.5us), `y`/`z`는 `corners[:, 1:3]`의 단순 평균.

#### 3. Depo 중심 계산
Point Depo 1개는 확산에 의해 여러 time slice에 걸치개 되며, 여려 Blob으로 reconstruction된다. 따라서 Point Depo의 정중앙 좌표 1개와 여러 Blob의 중심 좌표를 계산하게 되면 x방향의 편향이 발생하게 된다. 이를 위해 Point Depo를 blob과 동일한 slice로 나누어서 해당 슬라이스에 포함된 Depo의 체적에 대해서만 중심 좌표를 계산한다. (y,z)는 전체 Depo의 중심좌표와 동일하므로 그래도 사용하고, x좌표는 **일반적인 산순 평균** 과 **Truncated-mean** 두가지를 고려하여 모두 구현하였다.

- `depo_center()`: Gen0(post-drift) depo의 중심(y,z)는 그대로 사용, x좌표는 `t`(ns)에 time offset을 더한 뒤, 변환한 값으로 사용
- `depo_slice_center()`: 특정 slice에 포함된 Depo의 체적에 대해서만 중심 좌표를 계산

#### 4. 중심 좌표 비교
- `collect_records()`: blob이 존재하는 slice 상에서의 depo의 중심과 blob의 중심을 비교

#### 5. Analysis / Statitics

Reconstruction Blob과 그 blob이 존재하는 slice의 depo의 중심간의 차이의 절댓값 분표를 이용.
- 분포의 median과 기준범위(`PERCENTILA`변수 또는 `--percentile`파싱인자, 기본 1시그마 68.27 사용) 지점을 지표로 사용
- outlier는 기준범위(`OUTLIER_PERCENTILE`변수 또는 `--outlier-percentile`파싱인자)보다 이후의 blob으로 분류




실행 커맨드:
```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"
python scripts/position_center_comparison.py
```

콘솔 출력(요약):
```
[INFO] Found 34 position directories
[INFO] Collected 118 (position, blob) records from 34 usable positions
[INFO] x-axis: mean=0.309mm std=3.127mm within_1sigma=59.3% [FAIL] (criterion: >=95%)
[INFO] y-axis: mean=-41.834mm std=272.933mm within_1sigma=97.5% [PASS] (criterion: >=95%)
[INFO] z-axis: mean=-0.282mm std=1.570mm within_1sigma=66.1% [FAIL] (criterion: >=95%)
[INFO] 66/118 records flagged as outliers (>1 sigma on any axis)
```

스킵된 위치나 로딩 에러는 없었다(34/34 위치 모두 사용 가능, 위치당 평균 3.47개 blob).

`center_diff_histograms.png`를 육안 확인한 결과, x/z축은 완만하게 퍼진 다봉형(multi-modal) 분포(±2~6mm 범위)인 반면, y축은 0 부근에 대부분(115/118)이 몰려 있고 극소수(3개)가 -1300~-2360mm 스케일로 멀리 떨어진 형태였다 — 즉 표준편차(272.9mm)가 이 3개 이상치에 의해 지배되고 있음을 그래프에서도 바로 확인할 수 있었다.

Outlier 시각화 중 `X220_Y300_Z100_blob0_overlay.png`를 직접 열어 확인한 결과, 이 blob(`val=0`)의 corner 6개가 (y≈3000mm 근처 3개) + (y≈650mm 근처 3개)로 완전히 분리된 두 군집을 이루고 있었다 — 정상적인 blob이라면 corner들이 depo 주변에 조밀하게 모여야 하는데, 이 경우는 전하가 0인 채로 기하학적으로 뒤틀린(degenerate) 폴리곤이 만들어진 것으로 보인다. x축(시간축)은 이 blob도 depo Gaussian의 피크와 잘 맞았다(dx=4.07mm) — 즉 시간축 매칭은 정상이지만 (y,z) corner 집합 자체가 비정상인 경우였다.

반면 정상 전하를 가진 outlier(`X70_Y300_Z100_blob3_overlay.png`, 이 blob도 `val`은 매우 작음)는 depo Gaussian의 꼬리(오른쪽 끝) 부근 time slice였고, corner들이 depo 주변에 조밀하게 모여 있되 중심이 수 mm(dy=3.11mm, dz=-1.91mm, dx=-6.34mm) 어긋난, 훨씬 "정상적인" 형태의 outlier였다.

---

## 5. Result Verification & Validation

### 5.1 Evaluation

| 축 | mean [mm] | std [mm] | 1σ 이내 비율 | 판정 |
|---|---|---|---|---|
| x | 0.31 | 3.13 | 59.3% | FAIL |
| y | -41.83 | 272.93 | 97.5% | **PASS이지만 착시** |
| z | -0.28 | 1.57 | 66.1% | FAIL |

Success Criteria(§3, "평균 기준 1시그마 내 개수가 95% 이상")를 문자 그대로 적용하면 x/z는 미달이고 y만 통과한다. 그러나 y축의 "통과"는 실제 정확도가 좋아서가 아니라, 3개의 `val=0` degenerate blob이 std를 정상 스케일(수 mm) 대비 약 100배 가까이 부풀려 1σ 밴드 자체가 극단적으로 넓어졌기 때문이다(±272.9mm이면 정상 데이터 115/118개가 전부 그 안에 들어가는 것이 당연하다). 이 3개를 제외하면 y축도 x/z와 비슷한 수 mm 스케일의 산포를 가질 것으로 보이며, std가 정상화되면 오히려 1σ 통과율이 낮아질 가능성이 크다(즉 현재 y축 수치는 신뢰할 수 없는 값이다).

x/z축의 미달 원인은 §4.2에서 확인한 대로, diffusion tail 가장자리의 저전하 time-slice blob들이 만드는 수 mm 수준의 체계적 편차로 보인다 — 이는 Plan 문서(§3 Objective 2)가 애초에 찾고자 했던 현상과 일치한다.

### 5.2 Conclusion

**[결과 미흡]** — 세 축 모두(y축은 통계적 착시를 제외하면 사실상 마찬가지로) 95% 기준을 충족하지 못했다. Plan 문서의 Task Planning 루프(§워크플로우)에 따라 다음 반복을 위한 개선 방향을 아래 "Next Action"에 정리한다. 코드 자체의 버그는 아님을 실측 시각화로 확인했다(§4.2) — 개선이 필요한 것은 저전하/degenerate blob을 어떻게 다룰지에 대한 분석 설계다.

### 5.3 (2026-07-17) `--mode {per_file,one}` 통합 이후 재실행

§Code Implementation Steps에 정리한 `--mode` 통합(및 `depo_idx` 일반화, `t_offset` docstring 정정) 이후, 회귀 여부를 확인하기 위해 두 데이터셋에 대해 재실행했다. 두 실행 모두 §5.1과 달리 이후 세션에서 도입된 percentile 기반 지표(median, 68.27th/90th percentile of `|diff|`, `t`축 포함)를 사용하므로 §5.1의 mean/std/PASS-FAIL 표와 절대 수치가 직접 비교되지는 않는다 — 다만 §5.1이 지목한 현상(수 mm 스케일의 x/y/z 산포, `val=0` degenerate blob에 의한 대형 y outlier)이 그대로 재현되는지를 교차검증하는 것이 이번 재실행의 목적이다.

실행 커맨드:
```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"

# --mode per_file (기존과 동일한 데이터셋/기본값)
python scripts/position_center_comparison.py --mode per_file

# --mode one (단일 파일에 여러 depo가 packed된 데이터셋)
python scripts/position_center_comparison.py --mode one \
    --depo-file data/pdhd/point_depos_Y300Z100_one/depos-drifted-1.zip \
    --reco-file data/pdhd/point_depos_Y300Z100_one/clusters-apa-1.tar.gz \
    --output-dir results/pdhd/position_center_comparison_one \
    --tag one_314p5
```

콘솔 출력(요약):
```
# --mode per_file : data/pdhd/point_depos_Y300Z100_small, 34 positions
[INFO] Found 34 position directories
[INFO] Collected 118 (position, blob) records from 34 usable groups
[ANALYSIS] t-axis: median=0.602us 68.27th percentile=0.725us
[ANALYSIS] x-axis: median=0.964mm 68.27th percentile=1.161mm
[ANALYSIS] y-axis: median=1.508mm 68.27th percentile=2.492mm
[ANALYSIS] z-axis: median=0.855mm 68.27th percentile=1.461mm
# outliers_314p5.csv: 25/118 (21.2%) flagged (>90th percentile on any axis)

# --mode one : data/pdhd/point_depos_Y300Z100_one, depo 60개 (전부 매칭됨, unmatched 없음)
[INFO] 60 depos, 121 reco blobs in clusters-apa-1.tar.gz
[INFO] Collected 121 (position, blob) records from 60 usable groups
[ANALYSIS] t-axis: median=0.542us 68.27th percentile=0.662us
[ANALYSIS] x-axis: median=0.867mm 68.27th percentile=1.058mm
[ANALYSIS] y-axis: median=1.508mm 68.27th percentile=1.508mm
[ANALYSIS] z-axis: median=0.764mm 68.27th percentile=1.095mm
# outliers_one_314p5.csv: 24/121 (19.8%) flagged (>90th percentile on any axis)
```

| 데이터셋 | 모드 | 레코드 수 | t median/68.27pct [us] | x median/68.27pct [mm] | y median/68.27pct [mm] | z median/68.27pct [mm] | outlier 비율 | outlier 중 `val=0` |
|---|---|---|---|---|---|---|---|---|
| `point_depos_Y300Z100_small` | `per_file` | 118 | 0.602 / 0.725 | 0.964 / 1.161 | 1.508 / 2.492 | 0.855 / 1.461 | 25/118 (21.2%) | 6/25 |
| `point_depos_Y300Z100_one` | `one` | 121 | 0.542 / 0.662 | 0.867 / 1.058 | 1.508 / 1.508 | 0.764 / 1.095 | 24/121 (19.8%) | 5/24 |

두 데이터셋(서로 다른 위치 개수/범위)임에도 median 기준 x~0.9-1.0mm, y~1.5mm, z~0.8-0.9mm로 잘 일치했다. `--mode one`의 `match_blobs_to_depos()`가 시간만으로 depo/blob 대응을 복원함에도 `--mode per_file`(대응이 파일 구조로 이미 주어짐)과 동등한 결과를 낸다는 것은, 이 데이터셋 규모(depo 60개)에서는 nearest-time 매칭 휴리스틱이 정상적으로 동작함을 뜻한다.

가장 큰 outlier도 두 모드에서 동일한 패턴이었다: `--mode per_file`의 `X220_Y300_Z100_blob0`(`val=0`, dy=-2361.45mm)와 `--mode one`의 `depo053_x-103mm_blob2`(`val=0`, dy=-929.48mm) 모두, corner가 depo와 동떨어진 (y,z) 위치에 조밀하게 몰려 있는 diamond형 degenerate 폴리곤이었다(§4.2에서 확인한 것과 동일한 형태). 즉 `--mode one`의 시간 기반 매칭이 실제로는 다른 depo의 blob을 잘못 끌어온 것이 아니라, `per_file`에서도 나타나는 동일한 `val=0` degenerate blob 현상을 시간축으로도 올바르게 원래 depo에 배정한 것임을 시각적으로 확인했다.

한편 `--mode one`을 depo 89776개짜리 밀집 grid(`data/pdhd/point_depo_grid_v1`)에 적용해보면 89706/89776 depo가 매칭되지 못하고(y/z median이 수백~수천 mm로 폭주) 사실상 무의미한 결과가 나온다 — 이는 코드 결함이 아니라 `match_blobs_to_depos()`의 문서화된 전제("인접 위치들의 depo 시간 분포가 크게 겹치지 않음")가 이 데이터셋 규모에서 깨지기 때문이다. `--mode one`은 `point_depos_Y300Z100_one` 정도의 성긴 grid에는 적합하지만, 조밀한 grid에는 `--mode per_file`(또는 시공간을 함께 쓰는 매칭으로의 개선)이 필요하다.

---

## 6. Task Termination (Task 종료 및 문서화)

### 6.1 Summary

- Point depo와 reco blob의 중심을 corner 평균 기반의 가벼운 방식으로 비교하는 파이프라인(`scripts/position_center_comparison.py`)을 구현하고 34개 위치에서 실행해, 3D imaging position 정확도를 정량화했다.
- x/z축은 수 mm 스케일의 산포(std 1.6~3.1mm)를 보였고, 이는 대체로 저전하 diffusion-tail slice에서 발생한다.
- 전하가 0인 blob 중 일부는 corner가 두 개의 분리된 군집으로 쪼개지는 기하학적으로 비정상인(degenerate) 형태를 보이며, 이것이 이번 측정에서 가장 큰 이상치(y 방향 최대 2.36m)의 원인이었다 — position 정확도 자체의 문제라기보다는 `val=0` blob을 통계에 포함할지에 대한 분석 설계 문제였다.
- 원안의 Success Criteria(95% within 1σ)는 이번 raw 실행에서는 충족하지 못했지만, 원인(저전하/degenerate blob의 영향)이 명확히 식별되어 다음 반복에서 개선 가능하다.

### 6.2 Next Action

- **`val=0`(또는 매우 낮은 전하) blob을 별도 카테고리로 분리**해 통계를 다시 계산 — 정상 전하를 가진 blob만으로 1σ 기준을 재평가하면 실제 position 정확도를 더 정확히 판단할 수 있을 것으로 보인다(이번 리포트에서 제안만 하고 구현하지 않음).
- Plan 문서 §1 Dependency대로, position 정확도가 확인되면 charge 평가와 분리해 진행하고, point depo를 검출기 전체 볼륨의 더 많은 지점에서 생성해 동일 분석을 반복.
- Blob (y,z) 중심을 corner 단순 평균이 아니라 `eval/position_shape.py`의 shapely 폴리곤 area centroid로 바꿨을 때 결과가 얼마나 달라지는지 비교(현재는 vertex 평균 근사의 영향이 정량화되지 않았다).

---

## Related Documents

* **Parent docs:**
  * [position_eval_center_comparison_Plan.md](./position_eval_center_comparison_Plan.md): 본 Report가 수행/검증한 계획 원문.
* **Child docs:** 없음.
* **Sibling docs:**
  * [time_offset_calibration.md](./time_offset_calibration.md): 이 Report가 그대로 채택한 `T_OFFSET=314.5us`의 origin과, 별도로 재검증된 313.9us 값의 근거.
  * [true_blob_prototype.md](./true_blob_prototype.md), [position_shape_evaluation.md](./position_shape_evaluation.md): 이 Report가 의도적으로 우회한, wire geometry 기반의 더 무거운 true-blob-vs-reco-blob 비교 파이프라인.
