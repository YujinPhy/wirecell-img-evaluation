# Time Offset Calibration (`Img::BlobDepoFill`)

## 1. Summary

`Img::BlobDepoFill`이 depo truth time과 reconstructed blob time을 짝짓는 데 쓰는 상수 `time_offset`의 origin을 분석하고, 이전 `scripts/timeoffset/` 스터디의 방법론과 한계를 정리하고, 이를 대체하는 새 calibration 방법론(`scripts/utils/time_offset.py`, `scripts/pdhd_time_offset_check.py`)과 검증 결과를 기록한 문서다.
핵심 결론은 `time_offset`이 임의의 자유 매개변수가 아니라, PDHD 시뮬레이션에 이미 쓰이는 다른 jsonnet 파라미터로부터 정확히 계산 가능한 baseline과, 그 위에 얹히는 작은 residual의 합으로 분해된다는 것이다.

## 2. 배경

`Img::BlobDepoFill::slice_and_dice_depos()`(`wire-cell-toolkit/img/src/BlobDepoFill.cxx:114-136`)는 `tmean = idepo->time() + time_offset`을 계산해 blob의 `ISlice` bin과 비교한다.
이 클래스는 drift 물리량에 대한 내부 지식이 전혀 없고, `time_offset`을 그대로 caller가 넘겨받은 값으로 사용한다.
`img/docs/BlobDepoFill.org`는 이 값을 caller가 직접 맞춰야 한다고 명시하며, ParaView에서 depo와 blob의 X축 정렬을 눈으로 확인하는 방법까지 제안한다.
`wire-cell-cfg/pdhd/img.jsonnet:357`의 현재 값은 `time_offset: 314.5*wc.us`이며, 이 값은 순수하게 경험적으로(`scripts/timeoffset/`의 스캔으로) 도출된 것이었다.

이 상수가 정확하지 않으면 `docs/true_blob_prototype.md`의 §6.3에서 다룬 것처럼, depo 기반 true blob과 reco blob 사이의 시간축 비교(`time_overlap_frac`, `charge_rel_error`)가 항상 의미 없는 값(겹침 없음)을 낸다.
`docs/true_blob_prototype.md`는 이 문제를 우회하기 위해 시간 겹침 대신 폴리곤 중심 거리로 blob을 짝지었으나, 시간축 지표 자체는 이 offset이 calibrate되기 전까지 신뢰할 수 없다고 명시했다([[true_blob_prototype#6.3|§6.3]] 참고).

## 3. 원인 분석: `time_offset`은 어디서 오는가

`wire-cell-toolkit`의 C++ 소스와 PDHD jsonnet 파라미터(`cfg/pgrapher/common/params.jsonnet`, `cfg/pgrapher/experiment/pdhd/{params,simparams,sim,sp}.jsonnet`)를 끝까지 추적한 결과다.

### 3.1 depo 시간의 기준: `Gen::Drifter`

이 저장소의 study 데이터가 쓰는 depo 파일(`depos-drifted-N.zip`)은 `Gen::Drifter` 직후에서 탭된, drift 후(post-drift) truth time이다(`wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet:239-263`, `dsf` edge 2 -> `drifted_depos`).
`Gen::Drifter`는 원본 depo 시간에 response plane까지의 drift transit time(`(respx - pos.x())/speed`)만 더하며, epoch 자체를 바꾸지는 않는다(`gen/src/Drifter.cxx:154,182`).
즉 이 depo 시간은 여전히 원본 G4 clock 위에 있는, response plane 도달 시각이다.

### 3.2 reco frame 시간의 기준: `tick0_time`과 `ductor`/`reframer`의 자기상쇄 설계

PDHD의 frame 시간축 원점은 다음과 같이 구성된다.

- `tick0_time = -250*wc.us`(`cfg/pgrapher/experiment/pdhd/params.jsonnet:147`): output tick 0이 어떤 절대(G4) 시각에 대응하는지를 정하는, 순수한 DAQ/G4-clock 관례다.
  물리량이 아니라 detector/production마다 고정하는 convention이다.
- `response_time_offset = det.response_plane / lar.drift_speed = 100mm / 1.6mm/us = 62.5us`(`params.jsonnet:151`).
- `ductor.start_time = tick0_time - response_time_offset = -312.5us`(`params.jsonnet:157`): induction 신호가 완전히 빌드업되도록 ductor의 gate를 그만큼 미리 연다.
- `reframer.tbin = response_nticks`(그 62.5us에 해당하는 tick 수), `toffset: 0`(`cfg/pgrapher/experiment/pdhd/sim.jsonnet:28-40`): 앞서 미리 열어둔 만큼을 다시 잘라내, Reframer 이후 `frame->time()`을 정확히 `tick0_time = -250us`로 복원한다.

이 부분은 설계상 완전히 자기상쇄(self-canceling)된다.
`img/src/SumSlice.cxx:90`와 `MaskSlice.cxx:347`을 확인한 결과, blob의 `ISlice` `start`는 `inframe->time() + slicebin * span`으로 실제 `frame->time()`을 포함해 계산되므로, 이 자기상쇄가 blob 쪽에도 그대로 반영된다.

### 3.3 SP residual: `OmnibusSigProc`의 `ctoffset`/`intrinsic_time_offset`

`sigproc/src/OmnibusSigProc.cxx`는 deconvolution 후 samples를 `time_shift = (ctoffset + intrinsic_time_offset)/tick`만큼 내부적으로 재인덱싱한다(`OmnibusSigProc.cxx:1297`, `intrinsic_time_offset = fr.origin/fr.speed`는 `:919`).
PDHD의 `sp.jsonnet`은 `ctoffset: 1.0*wc.microsecond`로 override한다(기본값은 다른 detector에서 `-8.0us`).
문제는, 이 재인덱싱이 `frame->time()`을 갱신하지 않는다는 점이다(`OmnibusSigProc.cxx:2102`에서 출력 frame이 `in->time()`을 그대로 유지하는 것을 확인했다).
즉 §3.2의 자기상쇄 설계가 정확히 성립하려면 SP 단계가 tick-index와 절대시간의 대응을 보존해야 하는데, 이 재인덱싱이 그 대응을 조용히 어긋나게 만든다.
이것이 config만으로는 문서화되지 않는, chain에서 유일하게 "self-documenting"하지 않은 연결고리다.

### 3.4 종합: `312.5us`라는 우연의 일치

`abs(tick0_time) + response_time_offset = 250 + 62.5 = 312.5us`는, 이전 스터디의 git 이력에서 실제로 시도됐던 값 중 하나(`git show 8d0255f`의 초기 `img.jsonnet`, `time_offset: 312.5*wc.us`)이자, 경험적으로 수렴한 값들의 최저점(`312.5` -> `314.667` -> 현재 `314.5`)과 정확히 일치한다.
이는 우연이 아니라, 이전 스터디의 blind scan이 실제로는 이 analytic quantity 주변으로 수렴하고 있었다는 강한 증거다.
남은 잔차(수 us)는 §3.3의 `ctoffset`/`intrinsic_time_offset` 재인덱싱, 혹은 field response의 실제 peak time이 `response_plane/drift_speed`로 단순 계산한 값과 정확히 일치하지 않는 효과(다른 detector에서 실제로 문서화된 사례가 `simparams.jsonnet:182-197`의 MicroBooNE 관련 주석에 있다: "Garfield field response에서 collection plane peak가 `response_plane/drift_speed`가 아니라 약 $81us$ 근방에서 생긴다")로 설명 가능하다.

## 4. 이전 스터디(`scripts/timeoffset/`) 리뷰

### 4.1 방법론

두 가지 metric이 쓰였다: depo의 Gaussian arrival-time 모델과 reco blob의 binned charge fraction 사이의 RSS(residual sum of squares) shape-fit, 그리고 Gaussian/reco 사이의 overlap coefficient(histogram intersection, `[0,1]`로 bound됨).
스캔은 전체 데이터셋에 대한 단일 global offset과, `center_X_Y_Z` 공간 그룹별 localized offset 두 방식으로 조직됐다.

### 4.2 잘된 점

Overlap coefficient는 RSS보다 원칙적인 metric이다: RSS는 slice 경계를 악용하는 것을 막기 위해 별도의 "peak-centering position penalty"를 추가해야 했지만, overlap coefficient는 그런 hack 없이 bound된 값을 낸다.
Localized(공간별) 스캔으로 최적값이 위치에 따라 달라지는지 확인하려던 시도도 좋은 방향이었다.
이 프로젝트는 그 metric을 계승해 `scripts/utils/time_offset.py`의 `overlap_coefficient`로 재구현했다.

### 4.3 한계

이전 스터디는 다음 문제들로 결론에 도달하지 못했다.

- Import 경로가 깨져 있었다: `scripts.utils.load_data`를 참조했으나 실제 모듈은 `scripts/utils/load.py`였다(`img_BlobDepoFill` 시절 이름 변경의 잔재).
- Loader 헬퍼가 스크립트마다 중복 복사돼 있었다(공유 모듈로 통합되지 않음).
- `314.0us`와 `314.5us` 사이에서 "marginal difference"라며 결론을 내지 못하고 멈췄다.
- Global-vs-local aggregation을 마무리짓지 않은 채 코드가 주석 처리된 채로 남아 있었다.
- 근본적으로, §3의 analytic decomposition을 시도하지 않고 순수 blind curve-fit에만 의존했다: baseline을 계산할 수 있다는 것을 몰랐기 때문에, 수십 us 범위의 넓은 스캔이 필요했고 노이즈에 취약했다.
- 스터디에 쓰인 원본 데이터 파일이 모두 삭제돼 재현이 불가능한 상태였다.

## 5. 새 방법론

### 5.1 `scripts/utils/time_offset.py`

`analytic_time_offset(tick0_time, response_plane, drift_speed)`는 §3.2-3.4의 baseline(`abs(tick0_time) + response_plane/drift_speed`)을 계산하는 순수 함수다.
Detector-specific 상수를 하드코딩하지 않고 인자로 받으므로, 다른 detector/anode 설정에도 재사용 가능하다.

`overlap_coefficient(depo_t, depo_tsigma, reco_blobs, offset)`는 이전 스터디의 overlap coefficient를 계승하되, 두 가지를 개선했다.
첫째, reco 쪽 시간축을 임의의 고정폭(이전 스터디는 $2us$)으로 재구간화하지 않고, 각 reco blob 자신의 `[start, start+span)`을 그대로 하나의 bin으로 쓴다.
둘째, 두 연속 곡선의 point-wise minimum을 수치적분하는 대신, `scripts/utils/slicer.py`의 `gbounds`(이미 `scripts/utils/true_blob.py`에서 검증된 Gaussian 구간적분)로 각 bin의 true fraction을 정확히 계산한다.

`scan_residual(depo_t, depo_tsigma, reco_blobs, baseline_offset, window, step)`는 baseline 주변의 좁은 창(기본 `±10us`, step `0.05us`)만 스캔한다.
Baseline의 analytic한 부분은 이미 알고 있으므로, 넓은 blind sweep 대신 residual만 좁게 재확인하면 충분하다는 것이 이전 스터디와의 핵심 차이다.

### 5.2 `scripts/pdhd_time_offset_check.py`

PDHD 상수(`tick0_time=-250*wc.us`, `response_plane=100*wc.mm`, `drift_speed=1.6*wc.mm/wc.us`)로 baseline을 계산하고, `data/pdhd/test_point_depo` 샘플(depo 1개, reco blob 3개)에 대해 `scan_residual`을 실행하고, 현재 `wire-cell-cfg/pdhd/img.jsonnet`에 설정된 값과 비교하고, offset-vs-overlap 곡선을 플롯으로 저장한다.
`test_point_depo`를 선택한 이유는, depo가 하나뿐이라 spatial blob matching 없이 그 위치의 모든 reco blob(서로 다른 time slice들)을 그대로 "total"로 삼을 수 있어 시간축 calibration을 공간축 문제와 분리해서 볼 수 있기 때문이다.

## 6. 검증 결과

`python scripts/pdhd_time_offset_check.py` 실행 결과다.

| 항목 | 값 |
|---|---|
| Analytic baseline | $312.500us$ |
| 좁은 스캔으로 찾은 최적 offset | $313.900us$ |
| Baseline 대비 residual | $+1.400us$ |
| `wire-cell-cfg/pdhd/img.jsonnet`의 현재 설정값 | $314.500us$ |
| 스캔 결과와 현재 설정값의 차이 | $0.600us$ |

Analytic baseline($312.5us$)이 이전 스터디가 실제로 시도했던 값(§3.4)과 정확히 일치하고, 좁은 스캔으로 찾은 최적값($313.9us$)이 현재 설정값($314.5us$)과 $0.6us$ 이내로 일치한다.
이는 §3의 분해(analytic baseline + SP residual)가 우연이 아니라 실제로 이 offset의 구조를 설명한다는 것을 뒷받침한다.

계산된 offset($313.9us$)을 `scripts/pdhd_true_blob_check.py`(depo time에 이 offset을 더한 뒤 true blob을 생성하도록 수정)에 적용해 재실행한 결과, `time_overlap_frac`이 이전의 항상 음수(겹침 없음, `-1.0` placeholder)였던 것과 달리 평균 $0.405$로 나와, 시간축 지표가 처음으로 의미 있는 값을 내기 시작했다.

## 7. 알려진 한계와 다음 단계

- 이번 검증은 `test_point_depo` 샘플 하나에만 의존했다.
  `scripts/timeoffset/`이 시도했던 것처럼 residual이 anode/위치에 따라 달라지는지는 확인되지 않았다.
  다음 단계로 `wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet`으로 여러 위치의 point-depo를 새로 생성해, residual이 정말 상수인지 검증해야 한다.
- §3.3의 `ctoffset`/`intrinsic_time_offset` 재인덱싱이 정확히 얼마의 residual을 만드는지는 이번 분석에서 analytic하게 유도하지 않고 경험적으로만 측정했다.
  Field response 파일의 실제 파형을 직접 들여다보면 이 residual도 analytic하게 설명될 가능성이 있다.
- `charge_rel_error`(§6 검증에서 측정하지 않았으나 `pdhd_true_blob_check.py`가 함께 출력하는 지표)는 여전히 크게 벗어난다(`docs/true_blob_prototype.md` §8의 "그레인 차이"/"전하 가중치 단순화" 한계와 별개의 문제이며, 이번 작업의 범위 밖이다).


Version:          2.1.204
Session name:     time-offset-calibration-redesign
Session ID:       7304b528-2720-4dc3-8c0e-e2327a1c07b7
cwd:              /nfs/data/1/yujin/img_evaluation
Login method:     Claude Pro account