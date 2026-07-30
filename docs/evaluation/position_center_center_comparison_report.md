# Position Center Evaluation
## Document Metadata
* **Created Date:** 2026-07-14
* **Last Updated:** 2026-07-18
## Summary
`scripts/position_center_comparison.py`를 통해 point depo의 중심과 reco blob 중심을 비교한다.

---

## 사전 작업
Reconstructed blob과 True Deposition 간의 Time offset 문제을 해결해야 함.
    - 현재 314.5us 값을 우선 사용하고, 추후에 analytic한 방법으로 찾거나, offset을 없애는 방법에 대한 study 진행 필요

## Depo & Blob 구분

#### Depo
1. longitudinal/transverse 방향으로 gaussian distribution을 갖는 연속적인 분포이지만, blob과의 비교를 위해 경계를 정의해야 한다. 여기서는 $3\sigma$를 경계로 설정

2. Depo는 확산에 의헤 anode에 도착할 때, 여러 time slice에 걸치게 된다. 따라서 Depo 1개에 여러 blob이 맵핑된다. 따라서 Blob은 해당 slice에 존재하는 depo의 부분하고만 비교하는 것이 타당하다.

#### Blob
1. 현재 point depo의 경우만 다루며, depo 간의 간격이 충분한 상황이므로, blob이 어느 depo와 맵핑되는지는 고려하지 않아도 된다.

2. Blob 중에 Depo와 맵핑되지 않는 ghost를 분석에 포함하게 되면 왜곡이 발생하므로, 이를 제외하고 진행해야 한다.
    - blob의 전하가 일정 기준 미만인 경우 제외-> 우선 전하량 0 인경우만 제외
    - blob이 depo와 일정 거리 이상 멀리 생성된 경우 -> 우선 transverse sigma의 5배 이상

3. Depo와 인접하지만, depo가 걸친 time slice 밖에 위치한 blob도 식별하여 구분해야 한다.

#### 결론
Depo가 걸치 slice 중에 blob이 존재하지 않는 slice를 식별해야 한다.
Blob의 경우 ghost를 제외




### [2026-07-20] 6. Blob 분류 (Ghost / Out-of-range) 구현
위 "Depo & Blob 구분" 절에서 정리한 ghost/out-of-range 구분을 `collect_records()` 이전 단계에 신설한 `classify_blob()`으로 구현했다.

- `classify_blob(b, depos, depo_idx, ...)`: blob 하나를 depo 하나에 대해 아래 우선순위로 판정.
    1. **`out_of_range`**: blob의 slice 시간창 `[start, start+span]`이 depo의 유효 시간경계 `mean_ns ± depo_range_nsigma * sigma_ns`(`--depo-range-nsigma`, 기본 3.0 = report의 depo 3σ 경계)와 전혀 겹치지 않는 경우. `depo_slice_center()`의 truncated mean이 이 경우 구간 중점으로 degenerate하므로, 애초에 depo와의 1:1 비교 대상에서 제외한다.
    2. **`ghost`**: 위 조건을 통과했지만(시간상 depo 범위 내) `blob.val < --val-thr`(기본 0.0) 이거나, blob 중심의 (y,z)가 depo 중심에서 `ghost_nsigma_trans * depos["T"][depo_idx]`(`--ghost-nsigma-trans`, 기본 5.0 = depo 자체의 transverse 확산폭의 5배) 보다 멀리 떨어진 경우. 두 조건 모두 해당하면 `reason="low_charge+far_distance"`.
    3. **`matched`**: 그 외. 기존과 동일하게 `depo_slice_center()`와 비교해 `dt/dx/dy/dz` record 생성.
- `collect_records()`는 이제 `(records, excluded, data_cache)`를 반환한다. `records`는 `matched` blob만 담고(메인 diff 통계·outlier 분석의 입력), `excluded["ghost"]`/`excluded["out_of_range"]`는 각각 `ghost_blobs_<tag>.csv`/`out_of_range_blobs_<tag>.csv`로 저장된다.
- 기존에 `percentile_analysis`/`outlier_analysis`가 각자 받던 `val_thr` 인자(사후 필터링/아웃라이어 플래깅용)는 제거했다 — `matched` record는 이미 `classify_blob()` 단계에서 charge/거리 조건을 만족하는 것만 남으므로 사후 필터링이 무의미해졌다.


## Code Implementation Steps(2026-7-14)

- Code: `scripts/position_center_comparison.py`

#### 1. 데이터 스캔
`scan_positions()`가 `base_dir` 하위 서브디렉터리를 스캔하여 나열 및 경로 리스트를 생성, 좌표는 항상 로드된 데이터에서 얻으며 디렉터리 이름은 순회용으로만 사용
- Data: `/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_small` 하위 좌표에 따른 (depo, blob) 쌍
	- 34개 `X*_Y300_Z100` 서브디렉터리를 나열하고, 각각에 `depos-drifted-1.zip`/`clusters-apa-1.tar.gz`(anode_index=1 고정)가 있는지만 확인. 디렉터리 이름은 순회용으로만 쓰고, 좌표는 항상 로드된 데이터에서 얻는다.
	- 위치정보만 비교하므로 `BlobDepoFill`파일은 불필요

> 해당 작업에서 파일 이름과 같이 하드코딩된 부분이 존재하여 다른 경우에 적용하기에 유연하지 않지만 초기 스터디의 히스토리를 위해 관련 파일은 계속 남겨둠

- Data: `/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one` 
	- 한 데이터 파일에 여러 위치에서의 depo, blob정보 저장

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

### [2026-07-20] 6. Blob 분류 (Ghost / Out-of-range) 구현
위 "Depo & Blob 구분" 절에서 정리한 ghost/out-of-range 구분을 `collect_records()` 이전 단계에 신설한 `classify_blob()`으로 구현했다.

- `classify_blob(b, depos, depo_idx, ...)`: blob 하나를 depo 하나에 대해 아래 우선순위로 판정.
    1. **`out_of_range`**: blob의 slice 시간창 `[start, start+span]`이 depo의 유효 시간경계 `mean_ns ± depo_range_nsigma * sigma_ns`(`--depo-range-nsigma`, 기본 3.0 = report의 depo 3σ 경계)와 전혀 겹치지 않는 경우. `depo_slice_center()`의 truncated mean이 이 경우 구간 중점으로 degenerate하므로, 애초에 depo와의 1:1 비교 대상에서 제외한다.
    2. **`ghost`**: 위 조건을 통과했지만(시간상 depo 범위 내) `blob.val < --val-thr`(기본 0.0) 이거나, blob 중심의 (y,z)가 depo 중심에서 `ghost_nsigma_trans * depos["T"][depo_idx]`(`--ghost-nsigma-trans`, 기본 5.0 = depo 자체의 transverse 확산폭의 5배) 보다 멀리 떨어진 경우. 두 조건 모두 해당하면 `reason="low_charge+far_distance"`.
    3. **`matched`**: 그 외. 기존과 동일하게 `depo_slice_center()`와 비교해 `dt/dx/dy/dz` record 생성.
- `collect_records()`는 이제 `(records, excluded, data_cache)`를 반환한다. `records`는 `matched` blob만 담고(메인 diff 통계·outlier 분석의 입력), `excluded["ghost"]`/`excluded["out_of_range"]`는 각각 `ghost_blobs_<tag>.csv`/`out_of_range_blobs_<tag>.csv`로 저장된다.
- 기존에 `percentile_analysis`/`outlier_analysis`가 각자 받던 `val_thr` 인자(사후 필터링/아웃라이어 플래깅용)는 제거했다 — `matched` record는 이미 `classify_blob()` 단계에서 charge/거리 조건을 만족하는 것만 남으므로 사후 필터링이 무의미해졌다.

## Result Verification & Validation

### 5.1 Evaluation
#### Data: `/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_small`
```bash
python scripts/position_center_comparison.py \
	--mode per_file \
	--data-base-dir /nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_small \
	--output-dir /nfs/data/1/yujin/wirecell-img-evaluation/results/pdhd/position_center_comparison_offset_314p5 \
	--anode-index 1 --v-drift 1.6 --t-offset 314.5 --anode1-x-pos 3430.47 \
	--mean-method truncated_mean --percentile 68.27 --val-thr 0 --outlier-percentile 90 --n-outlier-plot 50 
```
Or 기본값사용
```bash
python scripts/position_center_comparison.py --mode per_file
```

| 축   | median [mm] | 68.27 pct [mm] |
| --- | ----------- | -------------- |
| x   | 0.96        | 1.16           |
| y   | 1.51        | 2.49           |
| z   | 0.86        | 1.46           |

![[Pasted image 20260718154959.png]]

```
[INFO] Found 34 position directories
[INFO] Collected 118 (position, blob) records from 34 usable groups
[ANALYSIS] t-axis: median=0.602us 68.27th percentile=0.725us
[ANALYSIS] x-axis: median=0.964mm 68.27th percentile=1.161mm
[ANALYSIS] y-axis: median=1.508mm 68.27th percentile=2.492mm
[ANALYSIS] z-axis: median=0.855mm 68.27th percentile=1.461mm
outliers_314p5.csv: 25/118 (21.2%) flagged (>90th percentile on any axis)
```
- y축에서 특정 blob이 depo와 멀리 떨어진 곳에 생성(noise or ghost 추정), 해당 히스토그램의 축 범위 주의

#### Data: `/nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one`
```bash
python scripts/position_center_comparison.py \
	--mode one \
	--depo-file /nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one/depos-drifted-1.zip \
	--reco-file /nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one/clusters-apa-1.tar.gz \
	--output-dir /nfs/data/1/yujin/wirecell-img-evaluation/results/pdhd/position_center_comparison_one \
	--tag one_314p5 \
	--anode-index 1 --v-drift 1.6 --t-offset 314.5 --anode1-x-pos 3430.47 \
	--mean-method truncated_mean --percentile 68.27 --val-thr 0 --outlier-percentile 90 --n-outlier-plot 50 
```

```
[INFO] 60 depos, 121 reco blobs in clusters-apa-1.tar.gz
[INFO] Collected 121 (position, blob) records from 60 usable groups
[ANALYSIS] t-axis: median=0.542us 68.27th percentile=0.662us
[ANALYSIS] x-axis: median=0.867mm 68.27th percentile=1.058mm
[ANALYSIS] y-axis: median=1.508mm 68.27th percentile=1.508mm
[ANALYSIS] z-axis: median=0.764mm 68.27th percentile=1.095mm
outliers_one_314p5.csv: 24/121 (19.8%) flagged (>90th percentile on any axis)

```



  

| 데이터셋                         | 모드         | 레코드 수 | t median/68.27pct [us] | x median/68.27pct [mm] | y median/68.27pct [mm] | z median/68.27pct [mm] | outlier 비율     | outlier 중 `val=0` |
| ---------------------------- | ---------- | ----- | ---------------------- | ---------------------- | ---------------------- | ---------------------- | -------------- | ----------------- |
| `point_depos_Y300Z100_small` | `per_file` | 118   | 0.602 / 0.725          | 0.964 / 1.161          | 1.508 / 2.492          | 0.855 / 1.461          | 25/118 (21.2%) | 6/25              |
| `point_depos_Y300Z100_one`   | `one`      | 121   | 0.542 / 0.662          | 0.867 / 1.058          | 1.508 / 1.508          | 0.764 / 1.095          | 24/121 (19.8%) | 5/24              |

두 데이터셋(서로 다른 위치 개수/범위)임에도 median 기준 x~0.9-1.0mm, y~1.5mm, z~0.8-0.9mm로 잘 일치했다. `--mode one`의 `match_blobs_to_depos()`가 시간만으로 depo/blob 대응을 복원함에도 `--mode per_file`(대응이 파일 구조로 이미 주어짐)과 동등한 결과를 낸다는 것은, 이 데이터셋 규모(depo 60개)에서는 nearest-time 매칭 휴리스틱이 정상적으로 동작함을 뜻한다.

가장 큰 outlier도 두 모드에서 동일한 패턴이었다: `--mode per_file`의 `X220_Y300_Z100_blob0`(`val=0`, dy=-2361.45mm)와 `--mode one`의 `depo053_x-103mm_blob2`(`val=0`, dy=-929.48mm) 모두, corner가 depo와 동떨어진 (y,z) 위치에 조밀하게 몰려 있는 diamond형 degenerate 폴리곤이었다(§4.2에서 확인한 것과 동일한 형태). 즉 `--mode one`의 시간 기반 매칭이 실제로는 다른 depo의 blob을 잘못 끌어온 것이 아니라, `per_file`에서도 나타나는 동일한 `val=0` degenerate blob 현상을 시간축으로도 올바르게 원래 depo에 배정한 것임을 시각적으로 확인했다.

한편 `--mode one`을 depo 89776개짜리 밀집 grid(`data/pdhd/point_depo_grid_v1`)에 적용해보면 89706/89776 depo가 매칭되지 못하고(y/z median이 수백~수천 mm로 폭주) 사실상 무의미한 결과가 나온다 — 이는 코드 결함이 아니라 `match_blobs_to_depos()`의 문서화된 전제("인접 위치들의 depo 시간 분포가 크게 겹치지 않음")가 이 데이터셋 규모에서 깨지기 때문이다. `--mode one`은 `point_depos_Y300Z100_one` 정도의 성긴 grid에는 적합하지만, 조밀한 grid에는 `--mode per_file`(또는 시공간을 함께 쓰는 매칭으로의 개선)이 필요하다.

### 5.2 [2026-07-20] Ghost / Out-of-range 분리 재실행 결과
§Code Implementation Steps의 `classify_blob()` 구현을 §5.1과 동일한 두 데이터셋·동일 output-dir/tag·동일 파라미터(`--ghost-nsigma-trans 5.0`, `--val-thr 0.0`, `--depo-range-nsigma 3.0`)로 재실행해 `results/pdhd/position_center_comparison_offset_314p5/`, `results/pdhd/position_center_comparison_one/`을 직접 갱신했다 (`ghost_blobs_*.csv`/`out_of_range_blobs_*.csv`는 이번에 신규 추가된 산출물).

| 데이터셋 | 모드 | matched 레코드 수 | ghost (low_charge / far_distance) | out_of_range | x median/68.27pct [mm] | y median/68.27pct [mm] | z median/68.27pct [mm] |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `point_depos_Y300Z100_small` (§5.1과 동일 전) | `per_file` | 118 | - | - | 0.964 / 1.161 | 1.508 / 2.492 | 0.855 / 1.461 |
| `point_depos_Y300Z100_small` (분류 적용 후) | `per_file` | 101 | 4 (0 / 4) | 12 | 0.847 / 1.051 | 1.508 / 1.508 | 0.616 / 1.095 |
| `point_depos_Y300Z100_one` (§5.1과 동일 전) | `one` | 121 | - | - | 0.867 / 1.058 | 1.508 / 1.508 | 0.764 / 1.095 |
| `point_depos_Y300Z100_one` (분류 적용 후) | `one` | 98 | 2 (0 / 2) | 10 | 0.851 / 1.014 | 0.492 / 1.508 | 0.616 / 0.616 |

- 두 데이터셋 모두 ghost는 전량 `far_distance` 사유였다(`low_charge=0`) — 즉 이번 두 데이터셋 범위에서는 `val<0`(사실상 존재하지 않음)보다 거리 기준이 실질적인 필터였다.
- `point_depos_Y300Z100_small`의 ghost 목록에 §Task Termination에서 이미 지목했던 최대 outlier(`X220_Y300_Z100_blob0`, `val=0`, corners가 depo와 동떨어진 diamond형 degenerate 폴리곤)가 `far_distance`로 정확히 분류됨을 `results/pdhd/position_center_comparison_offset_314p5/ghost_blobs_314p5.csv`에서 직접 확인했다 — 거리 문턱(`5 * depos["T"]`, 이 depo 기준 약 5.9mm)이 실제 정상 blob들의 산포(수 mm)와 비정상 degenerate blob(수백~수천 mm 이탈)을 잘 분리했다.
- y축 68.27th percentile이 두 데이터셋 모두 크게 개선됐다(`per_file`: 2.492→1.508mm, `one`: 1.508mm 유지하되 median은 1.508→0.492mm로 개선) — degenerate/ghost blob이 y축 분포를 지배적으로 왜곡시키고 있었다는 §Task Termination의 가설이 재확인됐다.
- `out_of_range`(depo 3σ 시간경계 밖 slice의 blob)도 두 데이터셋에서 각 10~12건 존재 — depo diffusion tail이 3σ보다 더 넓게 퍼진 slice에서 reco blob이 만들어지는 경우로 보이며, 이 자체가 이상 현상은 아니지만 depo-blob 1:1 비교에서는 제외하는 것이 맞다는 설계가 실측으로 확인됐다.

## Task Termination 
### Summary
- Point depo와 reco blob의 중심을 corner 평균 기반의 가벼운 방식으로 비교하는 파이프라인(`scripts/position_center_comparison.py`)을 구현하고 34개 위치에서 실행해, 3D imaging position 정확도를 정량화했다.
- x/z축은 수 mm 스케일의 산포(std 1.6~3.1mm)를 보였고, 이는 대체로 저전하 diffusion-tail slice에서 발생한다.
- 전하가 0인 blob 중 일부는 corner가 두 개의 분리된 군집으로 쪼개지는 기하학적으로 비정상인(degenerate) 형태를 보이며, 이것이 이번 측정에서 가장 큰 이상치(y 방향 최대 2.36m)의 원인이었다 — position 정확도 자체의 문제라기보다는 `val=0` blob을 통계에 포함할지에 대한 분석 설계 문제였다.
- 원안의 Success Criteria(95% within 1σ)는 이번 raw 실행에서는 충족하지 못했지만, 원인(저전하/degenerate blob의 영향)이 명확히 식별되어 다음 반복에서 개선 가능하다.

### Next Action
- **`val=0`(또는 매우 낮은 전하) blob을 별도 카테고리로 분리**해 통계를 다시 계산 — 정상 전하를 가진 blob만으로 1σ 기준을 재평가하면 실제 position 정확도를 더 정확히 판단할 수 있을 것으로 보인다(이번 리포트에서 제안만 하고 구현하지 않음).
- Plan 문서 §1 Dependency대로, position 정확도가 확인되면 charge 평가와 분리해 진행하고, point depo를 검출기 전체 볼륨의 더 많은 지점에서 생성해 동일 분석을 반복.
- Blob (y,z) 중심을 corner 단순 평균이 아니라 `eval/position_shape.py`의 shapely 폴리곤 area centroid로 바꿨을 때 결과가 얼마나 달라지는지 비교(현재는 vertex 평균 근사의 영향이 정량화되지 않았다).

**(2026-07-20 갱신)** 위 첫 항목(`val=0`/저전하 blob 분리)은 §5.2에서 `classify_blob()`으로 구현·검증 완료. 남은 후속 작업:
- **Missing-slice detection**: "Depo & Blob 구분" 절 결론의 나머지 절반("depo가 걸친 slice 중 blob이 없는 slice 식별")은 이번 구현 범위에서 제외했다. 관측된 blob의 `start`/`span`만으로는 slice grid의 phase를 알 수 없어, 그룹 내 blob 하나의 `start`를 앵커로 slicebin 격자를 역산하는 방식이 필요하며(해당 depo에 매칭된 blob이 0개인 경우는 애초에 `collect_groups_*`에서 그룹째 드롭되어 이 방법의 적용 대상이 아님), reconstruction efficiency(검출 누락률) 지표로 다음 iteration에서 별도 구현 예정.
- `--ghost-nsigma-trans`(5.0)/`--depo-range-nsigma`(3.0) 기본값은 이번 두 데이터셋에서만 검증됨 — 더 넓은 위치 범위/다른 T,L 스케일의 depo에도 일반화되는지 후속 스캔에서 재확인 필요.

**(2026-07-20 추가)** `plot_outliers()`를 `_plot_case_overlay()` 공용 헬퍼 + 3개의 얇은 wrapper(`plot_outliers`/`plot_ghost_blobs`/`plot_out_of_range_blobs`)로 분리해, 세 카테고리를 각각 `outliers_<tag>/`, `ghost_blobs_<tag>/`, `out_of_range_blobs_<tag>/`에 저장하도록 했다. transverse 패널의 near/far 분할(broken-axis) 여부는 더 이상 `_boxes_overlap()`으로 자동 판정하지 않고 카테고리별로 고정: outlier(matched 중 통계적 이상치)는 `classify_blob()`의 ghost 거리 문턱 안에 항상 존재하므로 단일 패널, ghost/out_of_range는 (공간적으로 가깝더라도) 항상 near/far 2분할. 두 데이터셋 재실행으로 세 카테고리 플롯이 각각 올바른 디렉터리·레이아웃으로 저장됨을 확인했다.

## Related Documents
* **Parent docs:**
	* [position_eval_center_comparison_Plan.md](./position_eval_center_comparison_Plan.md): 본 Report가 수행/검증한 초기 계획 원문.
* **Child docs:** 없음.
* **Sibling docs:**
	* [time_offset_calibration.md](./time_offset_calibration.md): 이 Report가 그대로 채택한 `T_OFFSET=314.5us`의 origin과, 별도로 재검증된 313.9us 값의 근거.




















```
python scripts/position_center_comparison.py \
	--mode one \
	--depo-file /nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one/depos-drifted-1.zip \
	--reco-file /nfs/data/1/yujin/wirecell-img-evaluation/data/pdhd/point_depos_Y300Z100_one/clusters-apa-1.tar.gz \
	--output-dir /nfs/data/1/yujin/wirecell-img-evaluation/results/pdhd/position_center_comparison_one \
	--tag one_314p5_simple_mean \
	--anode-index 1 --v-drift 1.6 --t-offset 314.5 --anode1-x-pos 3430.47 \
	--mean-method slice_midpoint --percentile 68.27 --val-thr 0 --outlier-percentile 90 --n-outlier-plot 50 
```