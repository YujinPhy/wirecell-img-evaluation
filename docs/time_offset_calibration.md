# `Img::BlobDepoFill` Time Offset Calibration 

## 1. Summary

`Img::BlobDepoFill` 컴포넌트의 인자 `time_offset`은 true depo와 reconstructed blob의 drift time의 offset을 설정하는 역활을 한다. 본 문서에서는 `time_offset`의 origin을 분석하고, 이전 스터디의 방법론과 한계를 정리하고, 이를 대체하는 새 calibration 방법론(`scripts/utils/time_offset.py`, `scripts/pdhd_time_offset_check.py`)과 검증 결과를 기록한 문서다.

핵심 결론은 `time_offset`이 임의의 자유 매개변수가 아니라, PDHD 시뮬레이션에 이미 쓰이는 다른 jsonnet 파라미터로부터 정확히 계산 가능한 baseline과, 그 위에 얹히는 작은 residual의 합으로 분해된다는 것이다.

## 2. 배경

`Img::BlobDepoFill::slice_and_dice_depos()`(`wire-cell-toolkit/img/src/BlobDepoFill.cxx:114-136`)는 `tmean = idepo->time() + time_offset`을 계산해 blob의 `ISlice` bin과 비교한다. 이 클래스는 drift 물리량에 대한 내부 지식이 전혀 없고, `time_offset`을 그대로 jsonnegt cfg에서 넘겨받은 값으로 사용한다. `img/docs/BlobDepoFill.org`는 이 값을 직접 맞춰야 한다고 명시하며, ParaView에서 depo와 blob의 X축 정렬을 눈으로 확인하는 방법까지 제안한다. `wire-cell-cfg/pdhd/img.jsonnet:357`의 현재 값은 `time_offset: 314.5*wc.us`이며, 이 값은 순수하게 경험적으로 도출된 것이었다. (2026-02 study 진행)

이 상수가 정확하지 않으면 performance evaluation에서 `BlobDepoFill`을  통한 charge 정보 및 시간축(x축) 비교를 정확하게 진행할 수 없다. `314.5`라는 수치는 정보를 어느정도 근사하게 주는 것 같지만, 현재 정확한 time offset의 원인과 영향에 대한 스터디는 이루어지지 않았다.

## 3. 원인 분석: `time_offset`은 어디서 오는가

`wire-cell-toolkit`의 C++ 소스와 PDHD jsonnet 파라미터(`cfg/pgrapher/common/params.jsonnet`, `cfg/pgrapher/experiment/pdhd/{params,simparams,sim,sp}.jsonnet`)를 끝까지 추적한 결과다.

### 3.1 depo 시간의 기준: `Gen::Drifter`

`Gen::Drifter`는 depo의 initial time에 response plane까지의 drift time`dt`만 더한다(`gen/src/Drifter.cxx:154,182`). 즉 이 depo 시간은 response plane 도달 시각이다.

```cpp
double respx = 0, direction = 0.0;
auto xrit = std::find_if(m_xregions.begin(), m_xregions.end(), Gen::Drifter::IsInsideResp(depo));

(...)

respx = xrit->response->location();
direction = -1.0;

const double dt = std::abs((respx - pos.x()) / m_speed);
```

> 예시 - Anode1 (`data/pdhd/test_point_depo/depos-drifted-1.zip`)
> - response plane 위치: 3430.465mm (face1)
> - depo intial x poistion: 1500mm
> - depo intial time: 0ns 
> - m_speed = 1.6 mm/us
>  
> -> dt = 1206.540625us , depo파일에 저장된 값: 1206540.6ns = 1206.540625us (match!)

### 3.2 reco frame 시간의 기준: `tick0_time`과 `ductor`/`reframer`의 자기상쇄 설계

PDHD의 frame 시간축 원점은 다음과 같이 구성된다.

```
tick0_time = -250*wc.us # params.jsonnet:147

response_time_offset = det.response_plane / lar.drift_speed # 100mm / 1.6mm/us = 62.5us, params.jsonnet:151

ductor.start_time = tick0_time - response_time_offset # -312.5us, params.jsonnet:157
```

- `tick0_time`: output tick 0이 어떤 절대(G4) 시각에 대응하는지를 정하는, 순수한 DAQ/G4-clock 관례다. 물리량이 아니라 detector/production마다 고정하는 convention이다.
- `ductor.start_time`: induction 신호가 완전히 빌드업되도록 ductor의 gate를 그만큼 미리 연다.
- `reframer.tbin = response_nticks(pdhd/params.jsonnet:179-182)`: `response_time`에 해당하는 tick 수
    - `tick: 0.5*wc.us`
    - 


, `toffset: 0`(`cfg/pgrapher/experiment/pdhd/sim.jsonnet:28-40`): 앞서 미리 열어둔 만큼을 다시 잘라내, Reframer 이후 `frame->time()`을 정확히 `tick0_time = -250us`로 복원한다.


```


# pdhd/params.jsonnet:179-182
reframer: {
    tbin: response_nticks, # wc.roundToInt(response_time_offset / $.daq.tick), tick: 0.5*wc.us
    nticks: $.daq.nticks, # 10000
}

# pdhd/sim.jsonnet:28-40
local reframers = [
        g.pnode({
            type: 'Reframer',
            name: 'reframer-'+tools.anodes[n].name,
            data: {
                anode: wc.tn(tools.anodes[n]),
                tags: [],           // ?? what do?
                fill: 0.0,
                tbin: params.sim.reframer.tbin,
                toffset: 0,
                nticks: params.sim.reframer.nticks,
            },
        }, nin=1, nout=1) for n in std.range(0, nanodes-1)],
```

이 부분은 설계상 완전히 자기상쇄(self-canceling)된다.
`img/src/SumSlice.cxx:90`와 `MaskSlice.cxx:347`을 확인한 결과, blob의 `ISlice` `start`는 `inframe->time() + slicebin * span`으로 실제 `frame->time()`을 포함해 계산되므로, 이 자기상쇄가 blob 쪽에도 그대로 반영된다.

### 3.3 SP residual: `OmnibusSigProc`의 `ctoffset`/`intrinsic_time_offset`

`wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx`는 deconvolution 후 samples를 내부적으로 재인텍싱한다. 

```cpp
cfg["ctoffset"] = m_coarse_time_offset; #L316

m_period = frame->tick(); #L828
m_intrinsic_time_offset = fr.origin / fr.speed; #L919

int time_shift = (m_coarse_time_offset + m_intrinsic_time_offset) / m_period; #L1303


    -> `time_shift` = (ctoffset + intrinsic_time_offset)/tick`
```

PDHD의 경우, `ctoffeset`은 `sp.jsonnet`에서 `ctoffset: 1.0*wc.microsecond`로 override한다

PDHD의 `sp.jsonnet`은 `ctoffset: 1.0*wc.microsecond`로 override한다(기본값은 다른 detector에서 `-8.0us`).


문제는, 이 재인덱싱이 `frame->time()`을 갱신하지 않는다는 점이다(`OmnibusSigProc.cxx:2102`에서 출력 frame이 `in->time()`을 그대로 유지하는 것을 확인했다).

즉 §3.2의 자기상쇄 설계가 정확히 성립하려면 SP 단계가 tick-index와 절대시간의 대응을 보존해야 하는데, 이 재인덱싱이 그 대응을 조용히 어긋나게 만든다.
이것이 config만으로는 문서화되지 않는, chain에서 유일하게 "self-documenting"하지 않은 연결고리다.

`OmnibusSigProc.cxx` 안에는 이 `time_shift` 외에도 시간축을 만지는 지점이 더 있다.

- **`init_overall_response()`의 `ftoffset`(`m_fine_time_offset`) shift (`:947-961`)**: `decon_2D_init`의 `time_shift`(`ctoffset + intrinsic_time_offset`)와는 별개의 파라미터다. Raw 데이터가 아니라 field×electronics response 파형 자체를, SP tick 그리드로 리샘플링하기 전에 fine-grid(response 고유 grid) 단위로 순환 이동시킨다.
  ```cpp
  int fine_time_shift = m_fine_time_offset / fravg.period;   // ftoffset, cfg: `:63,315`
  ```
- **`init_overall_response()`의 fine→coarse 리샘플링 time-origin (`:964-1001`)**: response를 `fravg.period`(fine grid)에서 `m_period`(SP tick)로 linear interpolation redigitize하는 부분이다. 명시적 offset 파라미터는 아니지만, 코드 주석(`:980-988`)에 예전 boxcar 방식 대비 이 리샘플링이 `-200ns`만큼 time origin을 이동시켰다는 경고가 남아 있어, 사실상 시간 정렬을 결정하는 지점 중 하나다.
- **`init_overall_response()`의 시간축 pad 폭 설정 (`:840-853`)**: `m_pad_nticks = m_fft_nticks - m_nticks`로 `decon_2D_init`이 쓸 시간축 padding 폭을 결정한다. 다만 `m_pad_nticks` 변수 자체는 이 파일 안에서 다시 읽히는 곳이 없다.
- **`load_data()`의 입력 trace `tbin` 소비 (`:424-430`)**: `OmnibusSigProc`이 계산하는 offset이 아니라, 입력 프레임 각 trace가 이미 갖고 있는 `tbin`을 그대로 배치 위치로 쓴다. `// fixme: this code uses tbin() but other places in this file will barf if tbin!=0`(`:424`) 주석대로, 이후 단계는 전부 `tbin==0`을 암묵적으로 가정한다.
- **7개 `decon_2D_*` 함수의 시간축 crop (`decon_2D_ROI_refine`/`decon_2D_tightROI`/`decon_2D_tighterROI`/`decon_2D_looseROI`/`decon_2D_looseROI_debug_mode`/`decon_2D_hits`/`decon_2D_charge`, `:1469,1514,1560,1652,1701,1765,1798`)**: 전부 `m_r_data[plane] = tm_r_data.block(m_pad_nwires[plane], 0, m_nwires[plane], m_nticks)` 패턴을 반복한다. `decon_2D_init` 안의 `unpad_data()`는 wire 방향 padding만 제거하고 시간축은 `m_fft_nticks` 길이로 그대로 남기므로, FFT용으로 늘렸던 시간축 padding이 실제로 제거되는 지점은 `decon_2D_init`이 아니라 이 7개 하위 함수 각각이다.

(`pad_data()`/`unpad_data()`는 wire(공간) 방향 padding만 다루고 시간축과는 무관하다.)

### 3.4 종합: `312.5us`라는 우연의 일치

`abs(tick0_time) + response_time_offset = 250 + 62.5 = 312.5us`는, 이전 스터디의 git 이력에서 실제로 시도됐던 값 중 하나(`git show 8d0255f`의 초기 `img.jsonnet`, `time_offset: 312.5*wc.us`)이자, 경험적으로 수렴한 값들의 최저점(`312.5` -> `314.667` -> 현재 `314.5`)과 정확히 일치한다.
이는 우연이 아니라, 이전 스터디의 blind scan이 실제로는 이 analytic quantity 주변으로 수렴하고 있었다는 강한 증거다.
남은 잔차(수 us)는 §3.3의 `ctoffset`/`intrinsic_time_offset` 재인덱싱, 혹은 field response의 실제 peak time이 `response_plane/drift_speed`로 단순 계산한 값과 정확히 일치하지 않는 효과(다른 detector에서 실제로 문서화된 사례가 `simparams.jsonnet:182-197`의 MicroBooNE 관련 주석에 있다: "Garfield field response에서 collection plane peak가 `response_plane/drift_speed`가 아니라 약 $81us$ 근방에서 생긴다")로 설명 가능하다.

### 3.5 검증: `intrinsic_time_offset`을 실제 PDHD field response 파일에서 계산

§3.3의 `intrinsic_time_offset = fr.origin / fr.speed`(`OmnibusSigProc.cxx:919`)를 PDHD가 실제로 쓰는 field response 파일로 직접 계산해, §3.4에서 추측만 하고 있던 잔차 원인을 구체적인 수치로 확인했다.

`wire-cell-toolkit/cfg/pgrapher/experiment/pdhd/params.jsonnet:172`에서 anode 0(face 0)이 참조하는 파일은 `np04hd-garfield-6paths-mcmc-bestfit.json.bz2`다. 이 파일의 `FieldResponse`를 직접 읽으면:

```
fr.origin = 100.0        (mm)
fr.speed  = 0.001565      (mm/ns) = 1.565 mm/us
```

```
intrinsic_time_offset = fr.origin / fr.speed = 100.0 / 0.001565 = 63.898us
```

반면 §3.2의 `response_time_offset`(ductor/reframer 자기상쇄 설계에 쓰이는 값)은 detector params의 `lar.drift_speed`(1.6mm/us)로 계산된다:

```
response_time_offset = det.response_plane / lar.drift_speed = 100mm / 1.6mm/us = 62.5us
```

`fr.origin`(100mm)과 `det.response_plane`(100mm)은 같은 값을 가리키지만, **`intrinsic_time_offset`은 field response 파일에 내장된 speed(1.565mm/us, Garfield 계산 시 가정한 값)로, `response_time_offset`은 detector params가 정의한 `lar.drift_speed`(1.6mm/us)로 계산되어 서로 다르다.** 그 차이는:

```
63.898us - 62.5us = 1.398us
```

이 값은 §6에서 측정한 residual(analytic baseline 312.5us -> 좁은 스캔 최적값 313.9us, `+1.400us`)과 거의 정확히 일치한다. 즉 이전까지 "SP residual"이라고만 불렀던 것의 상당 부분은, `intrinsic_time_offset`과 `response_time_offset`이 같은 물리량(response plane까지의 drift time)임에도 서로 다른 drift speed 값으로 계산되기 때문에 생기는 구체적이고 재현 가능한 어긋남이다.

나머지 후보였던 `ftoffset`(`m_fine_time_offset`, §3.3)은 PDHD `sp.jsonnet:107`에서 `ftoffset: 0.0`으로 명시적으로 꺼져 있음을 확인했다 — 이 프로젝트에서는 기여분이 0이므로 후보에서 제외할 수 있다. `ctoffset`(1.0us, §3.3)과 §3.3의 보간(`-200ns`) time-origin 항은 여전히 남은 잔차(스캔 최적값 313.9us와 현재 설정값 314.5us 사이의 `0.6us`)의 후보로 남아 있다.









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