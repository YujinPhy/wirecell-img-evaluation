# `OmnibusSigProc` Pipeline Reference

## Summary

`wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx`에 정의된 `WireCell::SigProc::OmnibusSigProc` 클래스는 raw ADC 프레임을 받아 field response + electronics response로 2D(wire × time) deconvolution을 수행하고, ROI(Region of Interest) 탐색/정제를 거쳐 `"wiener"`(hit 진폭용)와 `"gauss"`(전하 적분용) 두 종류의 deconvolved 프레임을 만드는 signal processing(SP) 컴포넌트다. 이 문서는 그 안에 정의된 각 단계 함수의 역할을 요약한다.

## 파이프라인 흐름 (`opepad_datarator()` 기준)

`operator()`(`:1804`)가 평면(U/V/W)별로 아래 순서를 호출한다.

```
load_data()                       raw ADC -> Eigen 행렬(m_r_data)
  -> decon_2D_init()               1차 2D deconvolution (raw / (field*electronics response))
    -> decon_2D_tighterROI() / decon_2D_tightROI()   ROI 탐색용 좁은 필터 파형 (roi_form.find_ROI_by_decon_itself)
    -> decon_2D_looseROI()         ROI 탐색용 넓은 필터 파형 (roi_form.find_ROI_loose)
    -> decon_2D_ROI_refine()       loose ROI 정제 입력용 재필터링
  -> roi_refine.{BreakROIs,CheckROIs,CleanUpROIs,ShrinkROIs,ExtendROIs,...}   ROI 형태 정제 (ROI_refinement.cxx, 이 파일 밖)
  -> decon_2D_hits()                최종 "wiener" 출력용 넓은 HF 필터만 적용
  -> decon_2D_charge()              최종 "gauss" 출력용 Gaussian HF 필터 적용
-> save_data() / save_roi() / save_ext_roi() / save_mproi()   결과를 ITrace로 변환해 출력 프레임에 태깅
```

`init_overall_response()`는 평면별 루프 진입 전 한 번(그리고 `m_filter_resps_tn`가 설정된 경우 wiener 저장 후 한 번 더) 호출되어 response 배열과 FFT 크기를 준비한다.

## 함수 역할 요약

### 설정/초기화

| 함수 | 위치 | 역할 |
|---|---|---|
| `OspChan::str()` | `:52` | 디버그 로그용 `OspChan`(channel/wire/plane/ident) 문자열 표현. |
| `configure(config)` | `:59` | jsonnet cfg에서 필터 이름, ROI 임계값/패딩, 출력 태그(`wiener_tag`/`gauss_tag`/디버그 태그들), `ctoffset`/`ftoffset`, 평면별 wire 수 등 수십 개 파라미터를 멤버 변수로 읽어들인다. |
| `default_configuration()` | `:309` | `configure()`가 읽는 키들의 기본값 템플릿을 반환한다. |
| `init_overall_response(frame)` | `:817` | field response(`IFieldResponse`) × electronics response를 wire-averaging해 평면별 `overall_resp[plane]`(wire당 응답 파형)을 만들고, FFT 크기(`m_fft_nticks`/`m_fft_nwires`/패딩 폭)와 `m_wire_shift`를 계산한다. |

### 데이터 입출력 (raw ↔ Eigen 행렬 ↔ `ITrace`)

| 함수 | 위치 | 역할 |
|---|---|---|
| `load_data(in, plane)` | `:403` | 입력 프레임의 raw ADC 파형을 채널→wire 매핑에 따라 `m_r_data[plane]` 2D 행렬에 채운다. `"bad"` 채널 마스크 구간은 0으로 지운다. 설정된 평면이면 `rebase_waveform()`으로 기울어진 베이스라인도 보정한다. |
| `check_data(iplane, loglabel)` | `:464` | (`m_verbose`일 때만) `m_r_data[plane]`의 sum/mean/min/max를 디버그 로그로 남기는 진단 훅. |
| `save_data(...)` | `:477` | `m_r_data[plane]`을 채널별 `ITrace`로 변환해 출력 프레임에 넣는다. 기본은 음수 전하를 0으로 자르고(`save_negative_charge=false`), `"bad"` 구간을 0으로 지운다. `m_sparse`면 연속 양수 구간만 sparse하게 저장한다. |
| `save_roi(...)` | `:582` | `SignalROI`의 실제 전하 내용(`get_contents()`)을 `[start,end]` bin에 채워 디버그용 ROI 트레이스로 저장한다. |
| `save_ext_roi(...)` | `:666` | `SignalROI`의 "extended" bin 범위를 고정값(`10.`)으로 채워 디버그 시각화용으로 저장한다. |
| `save_mproi(...)` | `:751` | multi-plane protection(MP2/MP3) ROI 맵을 고정값(`4000.`)으로 채워 디버그 트레이스로 저장한다. |
| `pad_data(plane)` | `:1361` | 한 평면 내에 물리적으로 분리된 wire 구간(`m_nwires_separate_planes`)이 있을 때, 구간 사이에 베이스라인 값으로 채운 padding 블록을 끼워 넣는다(FFT deconvolution이 서로 다른 물리 구간을 섞지 않도록). |
| `unpad_data(plane)` | `:1415` | `pad_data()`가 끼워 넣은 padding을 제거해 원래 wire 인덱싱으로 되돌린다. |

### Deconvolution 단계

| 함수 | 위치 | 역할 |
|---|---|---|
| `decon_2D_init(plane)` | `:1157` | raw 데이터를 2D(wire,time) FFT하고, 채널별 electronics response 보정(선택)과 response(field×electronics)로 나눠 1차 deconvolution을 수행한 뒤, wire 방향 소프트 필터·역FFT·wire/time shift 복원까지 마친 결과를 `m_r_data`/`m_c_data`에 남긴다. 자세한 단계별 설명은 이전 대화(2026-07-14) 참고. |
| `decon_2D_tighterROI(plane)` | `:1519` | `Wiener_tight` HF × `ROI_tighter` LF 필터(가장 좁은 통과대역)를 적용해 ROI 탐색의 첫 후보(가장 보수적인 신호 영역)를 만든다. |
| `decon_2D_tightROI(plane)` | `:1473` | `Wiener_tight` HF × `ROI_tight` LF 필터를 적용한 "tight" ROI 파형. Collection 평면(`plane==2`)은 LF 필터 없이 HF만 적용. |
| `decon_2D_ROI_refine(plane)` | `:1449` | `Wiener_tight` HF 필터만(LF 없이) 다시 적용해, loose ROI 정제(`roi_form.find_ROI_loose` 이후) 단계에서 쓸 입력을 만든다. |
| `decon_2D_looseROI(plane)` | `:1564` | `Wiener_tight` HF × `ROI_loose` LF(넓은 통과대역)를 기본으로 적용하되, `masked_neighbors()`로 확인한 `"bad"`/`"lf_noisy"` 인접 채널에는 `ROI_tight` LF 조합을 대신 적용해 노이즈 채널 주변에서 ROI가 과도하게 넓어지는 것을 막는다. Collection 평면은 건너뛴다. |
| `decon_2D_looseROI_debug_mode(plane)` | `:1657` | `decon_2D_looseROI()`의 단순화 버전(`masked_neighbors` 오버라이드 없음). `m_use_roi_debug_mode`일 때만 `"loose_lf"` 디버그 태그 저장용으로 호출된다. |
| `decon_2D_hits(plane)` | `:1735` | `Wiener_wide` HF 필터(LF 없음, 가장 넓은 통과대역)만 적용한 최종 deconvolution. `"wiener"` 태그로 출력되는 hit 진폭 추정용 파형이다. |
| `decon_2D_charge(plane)` | `:1771` | `Gaus_wide` HF(Gaussian) 필터를 적용한 최종 deconvolution. `"gauss"` 태그로 출력되는, 전하 적분(charge-preserving)에 적합한 더 매끄러운 파형이다. |

### 베이스라인/마스킹 헬퍼

| 함수 | 위치 | 역할 |
|---|---|---|
| `restore_baseline(arr)` | `:1012` | 행(wire)별로 0이 아닌 샘플의 median을 구해 빼는 2-pass 베이스라인 제거(1차 median 근방 ±500 밖 샘플 제외 후 재계산). `decon_2D_*ROI` 계열 함수들이 역FFT 직후 호출한다. |
| `rebase_waveform(arr, n_bins)` | `:1059` | 파형 앞/뒤 `n_bins` 윈도우에서 앵커(median 또는 16/50/84 percentile 기반 sigma-masked robust 추정)를 구해 선형 기울기(tilt)를 빼는 베이스라인 보정. `load_data()`에서 `m_rebase_planes`에 포함된 평면에만 적용된다. |
| `masked_neighbors(cmname, ochan, nnn)` | `:1706` | 주어진 채널 기준 ±`nnn` 범위 안에 이름이 `cmname`인 채널 마스크(예: `"bad"`, `"lf_noisy"`)가 하나라도 있는지 확인한다. `decon_2D_looseROI()`에서 사용. |

### 메인 진입점

| 함수 | 위치 | 역할 |
|---|---|---|
| `operator()(in, out)` | `:1804` | `IFrameFilter`의 실제 진입점. 평면별로 `load_data → decon_2D_init → {tighter/tight/loose ROI 탐색} → ROI_formation/ROI_refinement로 ROI 정제(Break/Check/CleanUp/Shrink/Extend, 선택적으로 multi-plane protection MP2/MP3) → decon_2D_hits(wiener)/decon_2D_charge(gauss)` 순서로 처리한 뒤, 각 단계 결과를 `save_data`/`save_roi`/`save_ext_roi`/`save_mproi`로 태깅해 하나의 출력 `IFrame`으로 합친다. `m_use_roi_refinement=false`면 ROI 정제를 건너뛰고 (디버그 모드일 때만) `decon_2D_charge` 결과를 그대로 저장한다. |

## 참고

- ROI 탐색 로직 자체(`find_ROI_by_decon_itself`, `find_ROI_loose`)는 이 파일이 아니라 `ROI_formation.cxx`에, ROI 정제 로직(`BreakROIs`/`ShrinkROIs`/`ExtendROIs`/`MP2ROI`/`MP3ROI` 등)은 `ROI_refinement.cxx`에 있다.
- `m_coarse_time_offset`(`ctoffset`)와 `m_intrinsic_time_offset`(field response origin/speed)이 `decon_2D_init()`의 time-shift 계산(`:1297`)에 쓰이는 부분은 [`time_offset_calibration.md`](./time_offset_calibration.md) §3.3에서 다룬다.
