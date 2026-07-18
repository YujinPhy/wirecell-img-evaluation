# WCT Imaging Time-Slice Determination

## Summary

`../wire-cell-toolkit/img/` 내에서 blob의 두께(시간축 방향 두께, `span`)를 결정하는 time-slice 메커니즘을 코드 레벨에서 추적한 문서다. 결론부터 요약하면, 하나의 time slice(`ISlice`)의 폭은 두 값의 곱으로 정해진다.

```
slice.span() = tick x tick_span
```

- `tick` : 프레임(`IFrame`)의 디지타이징 샘플링 주기. 이 저장소(PDHD)에서는 `0.5us`로 고정.
- `tick_span` : slicer 컴포넌트(`MaskSlices`/`SumSlices`)의 설정 파라미터로, 몇 개의 raw tick을 하나의 slice로 묶을지 정하는 정수. 이 저장소의 `img.jsonnet`에서는 기본값 `4`.

이 `span`은 이후 `GridTiling`이 slice로부터 blob을 만들 때 그대로 blob에 전달되고(`islice->span()`), 클러스터 파일로 직렬화될 때(`blob_jsoner`) blob 노드의 `"span"` 필드가 된다. 즉 **slice의 시간 폭 = blob의 시간 폭(두께)**이며, drift speed를 곱해 실제 $x$ 방향 공간 두께로 변환된다.

관련 코드 경로는 `../wire-cell-toolkit/`을 기준으로 표기한다.

---

## 1. `tick` — 프레임의 샘플링 주기

`ISlice`/`IFrame`은 자체적으로 tick 값을 정하지 않는다. 프레임을 만드는 시뮬레이션/디지타이징 단계에서 결정된 값이 `IFrame::tick()`을 통해 그대로 파이프라인 끝까지 전달된다.

- 정의 위치: `cfg/pgrapher/experiment/pdhd/simparams.jsonnet:111`
  ```jsonnet
  // Data path uses params.daq.tick=512 ns and runs the Resampler (512->500 ns).
  tick: 0.5*wc.us,
  ```
- 이 값은 `nf-sp` 체인(노이즈 필터링/시그널 프로세싱)을 거쳐 `wiener`/`gauss` 등으로 태깅된 trace를 담은 `IFrame`에 그대로 실려서 `Img::MaskSliceBase::slice()`에 도달한다.
- `MaskSlice.cxx:225`
  ```cpp
  const double tick = in->tick();
  const double span = tick * m_tick_span;
  ```
  즉 slicer는 자신이 tick 값을 만들지 않고, 입력 `IFrame`이 들고 있는 `tick()`을 그대로 읽어 쓴다.

## 2. `tick_span` — slice에 묶이는 raw tick 개수

`tick_span`은 `MaskSlices`(및 단순 버전인 `SumSlices`)의 configuration parameter다.

- 클래스/인터페이스: `img/inc/WireCellImg/MaskSlice.h:64` (`int m_tick_span{4};`), 팩토리 이름은 `MaskSlices` / `MaskSlicer` (`img/src/MaskSlice.cxx:13-19`, `WIRECELL_FACTORY` 매크로).
  - 파일명은 `MaskSlice.h/.cxx`이지만 등록된 컴포넌트 이름은 `MaskSlicer`(단일 `IFrame` 반환)와 `MaskSlices`(개별 `ISlice`를 큐로 반환) 두 가지다. 이 저장소는 `MaskSlices`를 쓴다.
- 이 저장소에서의 설정 위치: `wire-cell-cfg/pdhd/img.jsonnet:98-118`의 `img.slicing` 함수.
  ```jsonnet
  slicing :: function(anode, aname, span=4, active_planes=[0,1,2], masked_planes=[], dummy_planes=[]) {
      ret: g.pnode({
          type: "MaskSlices",
          data: {
              tick_span: span,
              ...
          },
      ...
  ```
  그리고 실제 파이프라인 구성에서 `img.slicing(anode, anode.name, 4, ...)`처럼 `span=4`가 `tick_span`으로 전달된다(`img.jsonnet:305` 등).
- 컴포넌트 기본값(`img/src/MaskSlice.cxx:70`)도 `4`. 즉 jsonnet에서 명시적으로 값을 안 주면 코드 기본값도 4로 일치한다.

`Not yet ported...` 절에서 언급했듯, 대안으로 `SumSlice`(`img/src/SumSlice.cxx`)도 동일한 `tick_span` 파라미터를 가진 훨씬 단순한 슬라이서다(임계값 없이 0이 아닌 샘플을 모두 합산). 현재 이 저장소의 `img.jsonnet`은 `MaskSlices`만 사용한다.

## 3. Slice 생성 알고리즘 — `MaskSlice.cxx`의 `slice()`

`Img::MaskSliceBase::slice()` (`img/src/MaskSlice.cxx:218`)가 실제로 raw tick들을 `tick_span` 단위로 묶어 `ISlice` 객체들을 만드는 곳이다.

1. **slice bin 범위 결정** (`:243-258`)
   - `min_tbin`/`max_tbin`이 설정으로 주어지지 않으면(둘 다 0), 입력 charge trace들의 `tbin()`과 길이로부터 자동 계산한다.
   - 이 저장소는 명시적으로 `min_tbin: 0, max_tbin: 8500`을 준다(`img.jsonnet:109-110`).
   - `min_slicebin = floor(min_tbin / tick_span)`, `max_slicebin = ceil(max_tbin / tick_span)` — 이 범위의 모든 slicebin에 대해 빈 슬라이스를 미리 만들어 둔다(다운스트림 `BlobSetMerge`의 동기화를 위해).

2. **활성(active) plane 채널 순회 및 thresholding** (`:293-359`)
   - `active_planes`에 속한 채널의 각 raw tick(`qind`)에 대해 `slicebin = (tbin + qind) / tick_span`(정수 나눗셈)으로 어느 slice에 속하는지 결정한다. 이 나눗셈이 곧 "몇 개의 raw tick이 한 slice로 묶이는가"를 결정하는 지점이다.
   - `thresholding()`(`:173-216`)이 해당 tick/채널을 "활성"으로 볼지 판단한다:
     - `wiener` 태그 trace의 값이 `threshold = nthreshold[plane] * RMS(summary_tag)`를 넘으면 active. (`nthreshold`가 0이면 `default_threshold[plane]`를 대신 사용.)
     - 넘지 않아도, 이웃한 slice(`sbin-1`/`sbin+1`)의 평균 `wiener` 신호가 threshold를 넘고 현재 tick의 `gauss`(charge) 값이 그 이웃 slice 평균의 1/3을 넘으면 active로 인정(경계에 걸친 신호를 살리기 위한 보정).
   - active로 판정된 tick만 `s->sum(ich, {q, e})`로 슬라이스의 채널 활동(activity)에 charge/error를 누적한다.
   - 여기서 **`tick_span`은 두 가지 역할을 동시에 한다**: (a) 몇 개의 raw tick을 하나의 slice로 합산할지, (b) thresholding에서 이웃 slice의 평균을 계산할 때의 그룹 크기.

3. **dummy / masked plane 채우기** (`:361-438`)
   - `dummy_planes`에 속한 채널은 모든 slicebin에 대해 무조건 `dummy_charge`/`dummy_error`(기본 0 / 1e12, "신뢰 불가"를 의미)를 채운다.
   - `masked_planes`는 프레임의 `"bad"` channel-mask 범위(`cmm`)와 겹치는 slicebin에 `masked_charge`/`masked_error`(기본 0 / 1e12)를 채운다.
   - 두 경우 모두 실제 charge 판단이 아니라 "이 plane은 여기서 신뢰할 수 없다"는 표식이며, `tick_span`으로 정해진 동일한 slicebin 경계를 그대로 따른다.

4. **`start`/`span` 계산** (`:264-266`, `:346-349` 등)
   ```cpp
   const double start = in->time() + slicebin * m_tick_span * tick;
   const double span  = m_tick_span * tick;
   auto s = new Img::Data::Slice(tlframe_ptr, slicebin, start, span);
   ```
   - `span`은 앞서 언급한 `tick x tick_span`.
   - `start`는 프레임의 절대 시간(`in->time()`)에 `slicebin x span`을 더한 절대 시각(`SLICE_START_TIME_IS_RELATIVE`가 `#undef` 되어 있어 상대 모드는 현재 비활성).

`ISlice` 인터페이스 자체(`iface/inc/WireCellIface/ISlice.h:64-68`)도 `start()`/`span()`을 "WCT 단위계의 시간 폭"으로 문서화하고 있으며, "보통 sampling tick의 배수이지만 반드시 그럴 필요는 없다"고 명시한다 — `MaskSlices`가 그 "보통의 경우"를 구현한 것이다.

## 4. Slice 두께가 Blob 두께로 전파되는 경로

### 4.1 `GridTiling` — slice 하나당 blob 두께는 slice의 `span`을 그대로 물려받음

`img/src/GridTiling.cxx:53-` (`Img::GridTiling::operator()`)는 `ISlice`를 입력받아 `RayGrid::make_blobs()`로 2D 다각형(3-plane wire 교차)들을 만들고 `IBlobSet`으로 패킹한다. 이 단계에서 blob 자체는 "몇 시(when)"의 정보를 별도로 갖지 않고, `IBlob::slice()`로 자신을 만든 slice를 다시 가리키기만 한다(`Aux::SimpleBlobSet(sbs_ident, slice)`). 즉 blob의 시간 폭은 slice로부터 lazy하게 참조된다 — GridTiling 자체가 두께를 계산하지 않는다.

### 4.2 클러스터 파일로 직렬화될 때 blob의 `"span"`이 확정됨

`aux/src/ClusterHelpersJsonify.cxx:59-112`의 `blob_jsoner()`가 blob 노드를 JSON으로 만들 때:

```cpp
auto islice = iblob->slice();
double t0 = islice->start();
...
ret["span"] = islice->span();   // line 79
ret["start"] = islice->start(); // line 80
...
for (const auto& c : blob.corners()) {
    Json::Value j = jpoint(coords.ray_crossing(c.first, c.second));
    j[0] = t0;              // corner의 X(=시간축) 좌표는 slice 시작 시각으로 통일
    jcorners.append(j);
}
```

즉 클러스터 파일에 저장되는 blob 노드의 `"span"`은 **정확히 `islice->span()`**, 그러니까 §1-3에서 유도한 `tick x tick_span`과 동일하다. `blob.corners()`의 각 코너는 2D(pitch-pitch) 교차점이며, 그 앞에 시간축 좌표(`t0`, 곧 slice의 `start`)를 붙여 반쪽짜리 3D 좌표를 만드는데, 이때 실제 두께 정보는 코너가 아니라 별도 필드인 `"span"`에만 담긴다. `wirecell_img_reference.md` §1에 정리된 `b` 노드의 `span` (thickness) 필드가 바로 이것이다.

### 4.3 시간 두께 -> 공간 두께 변환

`wirecell.img.converter.undrift_blobs(cgraph, speed, time, x0=0, drift_index=0)` (`../wire-cell-python/wirecell/img/converter.py`, `wirecell_img_reference.md` §4)가 이 `span`(시간 단위)에 `abs(speed)`(drift speed)를 곱해 blob의 실제 공간( $x$ 방향) 두께로 환산한다. 즉:

```
dx (mm) = span (us) x drift_speed (mm/us)
```

이 저장소에서 쓰는 기본 drift speed는 `cfg/pgrapher/common/params.jsonnet:29`의 `drift_speed: 1.6*wc.mm/wc.us` (500V/cm 기준).

## 5. 이 저장소(PDHD)에서 실제로 쓰이는 값

| 파라미터 | 값 | 출처 |
|---|---|---|
| `tick` | `0.5us` | `cfg/.../pdhd/simparams.jsonnet:111` |
| `tick_span` | `4` | `wire-cell-cfg/pdhd/img.jsonnet:98,305` (`img.slicing` 호출 시 `span=4`) |
| `drift_speed` | `1.6mm/us` | `cfg/pgrapher/common/params.jsonnet:29` |
| `min_tbin`/`max_tbin` | `0`/`8500` | `wire-cell-cfg/pdhd/img.jsonnet:109-110` |
| `nthreshold` | `[3.6, 3.6, 3.6]` | `wire-cell-cfg/pdhd/img.jsonnet:115` |

따라서:

```
slice.span() = 0.5us x 4 = 2us
blob dx      = 2us x 1.6mm/us = 3.2mm
```

즉 현재 파이프라인에서 만들어지는 모든 blob의 시간축(=drift 방향) 두께는 `2us`(공간으로는 약 `3.2mm`)로 고정되어 있으며, 이는 오직 `img.jsonnet`의 `img.slicing(..., span=4, ...)` 호출 인자 하나를 바꾸면 조정된다. `nthreshold`/`default_threshold`는 두께 자체가 아니라 "어떤 tick/채널을 active로 볼지"만 결정하므로 두께와는 독립적이다 (`CLAUDE.md`의 로드맵 2.2 Stage 2에서 언급된 "noise-free true frame에 대해 `nthreshold`를 0에 가깝게 낮춘다"는 이 판정 임계값을 낮추는 것이지, slice 두께를 바꾸는 것이 아니다).

## 6. 관련 파일 요약

| 파일 | 역할 |
|---|---|
| `cfg/pgrapher/experiment/pdhd/simparams.jsonnet` | `tick`(샘플링 주기) 정의 |
| `cfg/pgrapher/common/params.jsonnet` | `drift_speed` 기본값 정의 |
| `wire-cell-cfg/pdhd/img.jsonnet` (`img.slicing`) | `tick_span`, threshold, plane 분류(active/dummy/masked) 설정 |
| `img/inc/WireCellImg/MaskSlice.h`, `img/src/MaskSlice.cxx` | `MaskSlicer`/`MaskSlices` 구현: tick 그룹핑, thresholding, slice `start`/`span` 계산 |
| `iface/inc/WireCellIface/ISlice.h` | `ISlice` 인터페이스(`start()`/`span()`/`activity()`) 정의 |
| `img/src/GridTiling.cxx` | slice -> blob 변환(`RayGrid::make_blobs`); blob은 slice를 참조만 함 |
| `aux/src/ClusterHelpersJsonify.cxx` (`blob_jsoner`) | 클러스터 파일 직렬화 시 blob의 `"span"`/`"start"`를 `islice->span()`/`start()`로 확정 |
| `../wire-cell-python/wirecell/img/converter.py` (`undrift_blobs`) | `span`(시간) x `drift_speed` -> 공간 두께 변환 |

---

## Related Documents

- [wirecell_img_reference.md](./wirecell_img_reference.md): `wirecell.img` 파이썬 패키지 전체 인벤토리. `b`(blob) 노드의 `span` 필드가 본 문서에서 다룬 값임을 정의.
- [pdhd_sensitive_volume_geometry.md](./pdhd_sensitive_volume_geometry.md): 본 문서의 drift_speed/geometry와 함께 blob의 실제 3D 공간 범위를 이해하는 데 참고.
