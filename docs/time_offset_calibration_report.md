# `time_offset` 보정 스터디 리포트 (PDHD, `test_point_depo`)

## Summary

[time_offset_calibration.md](time_offset_calibration.md)에서 분해한 `time_offset`의 구성 요소(analytic baseline + SP 잔차)를 바탕으로, `wire-cell-cfg/pdhd/img.jsonnet`의 `BlobDepoFill.time_offset` 값을 실제로 검증한 스터디 기록이다. 이전(2026-02) 스터디를 리뷰하고, 그 한계를 보완한 새 방법론(`scripts/utils/time_offset.py`, `scripts/pdhd_time_offset_check.py`)으로 재검증했다.

## 관련 문서

- [time_offset_calibration.md](time_offset_calibration.md) — `time_offset`이 시뮬레이션(`sim.ductor`/`sim.reframer`)과 SP(`OmnibusSigProc`) 단계에서 어떻게 구성되는지에 대한 root-cause 분석. 이 리포트의 baseline 계산은 그 문서 §1/§4를 전제로 한다.

## 1. 이전 스터디 리뷰

### 1.1 방법론
두 가지 metric이 쓰였다: depo의 Gaussian arrival-time 모델과 reco blob의 binned charge fraction 사이의 RSS(residual sum of squares) shape-fit, 그리고 Gaussian/reco 사이의 overlap coefficient(histogram intersection, `[0,1]`로 bound됨).

스캔은 전체 데이터셋에 대한 단일 global offset과, `center_X_Y_Z` 공간 그룹별 localized offset 두 방식으로 조직됐다.

### 1.2 잘된 점
Overlap coefficient는 RSS보다 원칙적인 metric이다: RSS는 slice 경계를 악용하는 것을 막기 위해 별도의 "peak-centering position penalty"를 추가해야 했지만, overlap coefficient는 그런 hack 없이 bound된 값을 낸다.

Localized(공간별) 스캔으로 최적값이 위치에 따라 달라지는지 확인하려던 시도도 좋은 방향이었다. 이 프로젝트는 그 metric을 계승해 `scripts/utils/time_offset.py`의 `overlap_coefficient`로 재구현했다.

### 1.3 한계
이전 스터디는 다음 문제들로 결론에 도달하지 못했다.
- Import 경로가 깨져 있었다: `scripts.utils.load_data`를 참조했으나 실제 모듈은 `scripts/utils/load.py`였다(`img_BlobDepoFill` 시절 이름 변경의 잔재).
- Loader 헬퍼가 스크립트마다 중복 복사돼 있었다(공유 모듈로 통합되지 않음).
- `314.0us`와 `314.5us` 사이에서 "marginal difference"라며 결론을 내지 못하고 멈췄다.
- Global-vs-local aggregation을 마무리짓지 않은 채 코드가 주석 처리된 채로 남아 있었다.
- 근본적으로, [time_offset_calibration.md](time_offset_calibration.md)의 analytic decomposition을 시도하지 않고 순수 blind curve-fit에만 의존했다: baseline을 계산할 수 있다는 것을 몰랐기 때문에, 수십 us 범위의 넓은 스캔이 필요했고 노이즈에 취약했다.
- 스터디에 쓰인 원본 데이터 파일이 모두 삭제돼 재현이 불가능한 상태였다.

## 2. 새 방법론

### 2.1 `scripts/utils/time_offset.py`
`analytic_time_offset(tick0_time, response_plane, drift_speed)`는 [time_offset_calibration.md](time_offset_calibration.md) §1-§3의 baseline(`abs(tick0_time) + response_plane/drift_speed`)을 계산하는 순수 함수다. Detector-specific 상수를 하드코딩하지 않고 인자로 받으므로, 다른 detector/anode 설정에도 재사용 가능하다.

`overlap_coefficient(depo_t, depo_tsigma, reco_blobs, offset)`는 이전 스터디의 overlap coefficient를 계승하되, 두 가지를 개선했다.
- reco 쪽 시간축을 임의의 고정폭(이전 스터디는 $2us$)으로 재구간화하지 않고, 각 reco blob 자신의 `[start, start+span)`을 그대로 하나의 bin으로 쓴다.
- 두 연속 곡선의 point-wise minimum을 수치적분하는 대신, `scripts/utils/slicer.py`의 `gbounds`(이미 `scripts/utils/true_blob.py`에서 검증된 Gaussian 구간적분)로 각 bin의 true fraction을 정확히 계산한다.

`scan_residual(depo_t, depo_tsigma, reco_blobs, baseline_offset, window, step)`는 baseline 주변의 좁은 창(기본 `±10us`, step `0.05us`)만 스캔한다. Baseline의 analytic한 부분은 이미 알고 있으므로, 넓은 blind sweep 대신 residual만 좁게 재확인하면 충분하다는 것이 이전 스터디와의 핵심 차이다.

### 2.2 `scripts/pdhd_time_offset_check.py`
PDHD 상수(`tick0_time=-250*wc.us`, `response_plane=100*wc.mm`, `drift_speed=1.6*wc.mm/wc.us`)로 baseline을 계산하고, `data/pdhd/test_point_depo` 샘플(depo 1개, reco blob 3개)에 대해 `scan_residual`을 실행하고, 현재 `wire-cell-cfg/pdhd/img.jsonnet`에 설정된 값과 비교하고, offset-vs-overlap 곡선을 플롯으로 저장한다.

`test_point_depo`를 선택한 이유는, depo가 하나뿐이라 spatial blob matching 없이 그 위치의 모든 reco blob(서로 다른 time slice들)을 그대로 "total"로 삼을 수 있어 시간축 calibration을 공간축 문제와 분리해서 볼 수 있기 때문이다.

## 3. 검증 결과
`python scripts/pdhd_time_offset_check.py` 실행 결과다.

| 항목 | 값 |
|---|---|
| Analytic baseline | $312.500us$ |
| 좁은 스캔으로 찾은 최적 offset | $313.900us$ |
| Baseline 대비 residual | $+1.400us$ |
| `wire-cell-cfg/pdhd/img.jsonnet`의 현재 설정값 | $314.500us$ |
| 스캔 결과와 현재 설정값의 차이 | $0.600us$ |

Analytic baseline($312.5us$)이 이전 스터디가 실제로 시도했던 값(§1.3, git 이력의 `time_offset: 312.5*wc.us`)과 정확히 일치하고, 좁은 스캔으로 찾은 최적값($313.9us$)이 현재 설정값($314.5us$)과 $0.6us$ 이내로 일치한다. 이는 [time_offset_calibration.md](time_offset_calibration.md)의 분해(analytic baseline + SP residual)가 우연이 아니라 실제로 이 offset의 구조를 설명한다는 것을 뒷받침한다.

계산된 offset($313.9us$)을 `scripts/pdhd_true_blob_check.py`(depo time에 이 offset을 더한 뒤 true blob을 생성하도록 수정)에 적용해 재실행한 결과, `time_overlap_frac`이 이전의 항상 음수(겹침 없음, `-1.0` placeholder)였던 것과 달리 평균 $0.405$로 나와, 시간축 지표가 처음으로 의미 있는 값을 내기 시작했다.

> **주의(2026-07-25 재확인)**: 위 표는 `lar.drift_speed=1.6mm/us`(2026-07-23 이전 기본값) 기준으로 계산된 것이다. 이후 PDHD의 `drift_speed`가 `1.56mm/us`로 override되면서 analytic baseline은 `abs(-250us) + 100mm/1.56mm/us ≈ 314.10us`로 이동한다([time_offset_calibration.md](time_offset_calibration.md) §1). 이는 현재 `img.jsonnet`의 경험적 설정값(`314.5us`)과 `0.4us` 이내로 더 가까워지는 방향이지만, 이 표의 "좁은 스캔 최적값"/"residual" 항목은 아직 새 `drift_speed`로 재실행되지 않았다 — §4의 다음 단계 참고.

## 4. 알려진 한계와 다음 단계

- 이번 검증은 `test_point_depo` 샘플 하나에만 의존했다. `scripts/timeoffset/`이 시도했던 것처럼 residual이 anode/위치에 따라 달라지는지는 확인되지 않았다. 다음 단계로 `wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet`으로 여러 위치의 point-depo를 새로 생성해, residual이 정말 상수인지 검증해야 한다.
- [time_offset_calibration.md](time_offset_calibration.md) §4의 `ctoffset`/`intrinsic_time_offset` 재인덱싱이 정확히 얼마의 residual을 만드는지는 이번 분석에서 analytic하게 유도하지 않고 경험적으로만 측정했다. Field response 파일의 실제 파형을 직접 들여다보면 이 residual도 analytic하게 설명될 가능성이 있다.
- **(신규)** `lar.drift_speed=1.56mm/us`로 바뀐 현재 설정 기준으로 `scripts/pdhd_time_offset_check.py`를 재실행해 위 §3 표를 갱신해야 한다. 특히 [time_offset_calibration.md](time_offset_calibration.md) §4에서 재계산한 `intrinsic_time_offset` vs `response_time_offset` 차이(`+1.398us` → `-0.2046us`)가 스캔 최적값에도 그대로 반영되는지 확인이 필요하다.
- **(신규)** [time_offset_calibration.md](time_offset_calibration.md) §3(Reframe)에서, `sim.reframer.tbin`이 `response_time_offset`(`64.1026us`)을 정수 tick(`128`)으로 반올림한 값이라 `Reframer`가 실제로 보정하는 양(`128*500ns=64.0000us`)이 `response_time_offset`을 정확히 상쇄하지 못하고 `~0.1026us`가 남는다는 것을 확인했다(`Reframer.cxx:190`의 `outframe->time()` 계산으로 검증). `scripts/utils/time_offset.py`의 `analytic_time_offset`은 현재 이 tick-반올림 잔차를 반영하지 않고 연속값(`response_plane/drift_speed`)만 쓰므로, 실제 시뮬레이션 frame의 원점(`tick0_time - 0.1026us`)과 `~0.1us` 차이가 있다. 다음 재검증에서 이 반올림 잔차를 `analytic_time_offset`에 반영할지(또는 residual로 남겨둘지) 결정해야 한다. `Reframer.cxx:203-204`에 이미 추가된 디버그 로그로 실제 `outframe->time()` 값을 실행 로그에서 직접 확인할 수 있다.
- `charge_rel_error`(§3 검증에서 측정하지 않았으나 `pdhd_true_blob_check.py`가 함께 출력하는 지표)는 여전히 크게 벗어난다(`docs/axive/true_blob_prototype.md`의 "그레인 차이"/"전하 가중치 단순화" 한계와 별개의 문제이며, 이번 작업의 범위 밖이다).
- **(신규, 2026-07-26)** [time_offset_calibration.md](time_offset_calibration.md) §4에서, SP(`OmnibusSigProc::decon_2D_init`)의 `ctoffset+intrinsic_time_offset` 기반 `time_shift`가 forward(`DepoTransform`)와 동일한 field response 파일을 쓰는 이 시뮬레이션 체인에서는 이론적으로 불필요할 수 있다는 가설을 세웠다. `pdhd/sp.jsonnet`의 `ctoffset`을 `0`으로(또는 이 roll 자체를 우회하도록) 바꿔 재실행해서, 이 가설이 맞다면 `MaskSlice.cxx`의 하드코딩 없이도 depo-blob 시간이 맞아떨어지는지 검증해야 한다.
- **(신규, 2026-07-26)** §5에서 발견한 `MaskSlice.cxx`의 slice-start 공식 불일치(pre-population 루프만 `-64165` 보정을 갖고, 나머지 on-demand 루프는 없음)를 수정해야 한다. 이 값 자체가 SP의 `time_shift`를 대신 보정하려던 임시 패치로 추정되므로, 위 SP 쪽 근본 수정이 확인되면 이 하드코딩은 (모든 코드 경로에 동일하게 적용하는 방식이 아니라) 제거하는 방향이 맞다.

## Related documents

- [time_offset_calibration.md](time_offset_calibration.md): 이 리포트가 전제로 하는 `time_offset` 구성 요소 분해(root-cause 분석).
