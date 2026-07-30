# `time_offset` 근본 원인 분석 (PDHD 기준)

## Summary

Wire-Cell Toolkit의 Signal Processing 입력(depo)과 출력(reco blob) 사이에 시간축이 어긋나는 현상이 있고, 현재는 `wire-cell-cfg/pdhd/img.jsonnet`의 `BlobDepoFill.time_offset` 상수(`314.5us`, 경험적으로 결정됨)로 보정하고 있다. 이 문서는 이 어긋남이 실제로 파이프라인의 어느 단계에서, 어떤 파라미터로부터 발생하는지 구조적으로 분해한다.

이 분석은 depo와 reco blob의 정확한 시간축 비교(3D Imaging Performance evaluation)에 필요한 배경 지식이다. 이 분해를 바탕으로 실제 `time_offset` 값을 찾기 위해 수행한 스캔/검증 작업은 [time_offset_calibration_report.md](time_offset_calibration_report.md)에 별도로 정리했다.

## 관련 문서

- [wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md) — Jsonnet 파라미터 파일 전반의 구조화 규칙 (import 체인, 단위 체계, `params`/`simparams` 분리 관례).
- [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md) — `sim.ductor`/`sim.reframer` 등 `sim` 필드 전체의 설명과 PDHD 최종 계산값. 이 문서의 §1은 그 결과값만 요약해서 쓴다.
- [time_offset_calibration_report.md](time_offset_calibration_report.md) — 실제 `time_offset` 값을 찾기 위한 이전 스터디 리뷰, 새 방법론, 검증 결과, 다음 단계.

## Updates

(2026-07-23) `pgrapher/experiment/pdhd/params.jsonnet`의 `lar.drift_speed`를 base 기본값 `1.6mm/us`에서 `1.56mm/us`로 override 추가.
> 해당 값은 현재 FR 파일(`np04hd-garfield-6paths-mcmc-bestfit.json.bz2`)에 저장된 speed와 맞춘 값이며, 정확한 값은 계속 확인 필요.

(2026-07-25) 문서를 mechanism 전용 참고 문서로 재구성함: 이전 스터디 리뷰/새 방법론/검증 결과는 [time_offset_calibration_report.md](time_offset_calibration_report.md)로 분리하고, `sim` 파라미터 유도 과정 중 [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md)와 중복되던 부분을 제거해 그 문서를 가리키도록 정리함. §4의 `intrinsic_time_offset`/`response_time_offset` 비교를 현재 `lar.drift_speed=1.56mm/us` 기준으로 재계산함(과거 `1.6mm/us` 기준 계산은 report 문서에 이력으로 남겨둠).

(2026-07-26) §3에 `Reframer`가 `tick0_time`을 기준으로 자르는 이유(`params.jsonnet` 주석 인용)와, `Reframer.cxx:190`의 실제 `outframe->time()` 계산식·정수-tick 반올림 잔차(`≈0.1026us`)를 추가함. §4에 SP의 `time_shift`가 `int` 절삭이라 `129.796`이 아니라 `129`ticks(`64.5us`)로 적용된다는 점, 그리고 이 `ctoffset+intrinsic_time_offset` 보정이 forward(`DepoTransform`)와 reverse(SP)가 동일한 field response 파일을 쓰는 자기완결적 시뮬레이션에서는 이론적으로 불필요할 수 있다는 가설을 추가함. 새 §5를 추가해 `MaskSlice.cxx`의 slice-start 공식이 코드 경로에 따라 다르다는 점(`-64165` 하드코딩이 pre-population 루프에만 있음)과, `Reframer`/SP 잔차가 그 패치와 누적되어 만들어지는 구체적 수치(`-314.2675641025641us`)를 유도 과정과 함께 정리함.

같은 날, §4에 `OmnibusSigProc::operator()`의 실행 순서(`load_data` → `decon_2D_init`의 나눗셈/롤 → `save_data` → 최종 frame 생성)를 코드 줄 단위로 추가함: `load_data`가 `tbin=0`을 전제로 열 인덱스를 절대시간에 대응시키는 지점(`:425-430`), `time_shift` 롤이 실제로 배열 내용을 옮기는 방식(작은 예시 포함, `:1297-1305`), `save_data`가 롤 이후 배열을 `[0,m_nticks)`·`tbin=0`으로 그대로 읽어 최종 trace로 굳히는 지점(`:498,:558`), `operator()`가 `in->time()`을 그대로 재사용하는 지점(`:2102`)까지 추적해, `64.5us` 지연이 정확히 어느 줄에서 데이터에 새겨지는지 확인함.

## 1. 시뮬레이션 단계가 만드는 시간 구조

PDHD sim 체인이 최종적으로 만들어내는 값이다(`_jsonnet`으로 직접 평가해 확인, 유도 과정은 [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md) §4 참고):

| 값 | 계산식 | 결과 |
|---|---|---|
| `response_time_offset` | `det.response_plane / lar.drift_speed = 100mm / 1.56mm/us` | `64.1026us` |
| `sim.ductor.start_time` | `tick0_time - response_time_offset = -250us - 64.1026us` | `-314.1026us` |
| `sim.reframer.tbin` | `roundToInt(response_time_offset / daq.tick) = roundToInt(64102.56ns / 500ns)` | `128` ticks |
| `daq.tick` (최종) | `pdhd/params.jsonnet`의 `512ns`를 `pdhd/simparams.jsonnet`이 `500ns`로 재override | `500ns` |

`wirecell-sigproc response-info`로 FR 파일 자체의 파라미터를 직접 확인할 수 있다:
```
wirecell-sigproc response-info /cvmfs/dune.opensciencegrid.org/products/dune/dunereco/v10_21_00d00/wire-cell-cfg/np04hd-garfield-6paths-mcmc-bestfit.json.bz2

// Output
origin:10.00 cm, period:0.10 us, tstart:0.00 us, speed:1.56 mm/us, axis:(1.00,0.00,0.00)
        plane:0, location:9.4200mm, pitch:4.7100mm
        plane:1, location:4.7100mm, pitch:4.7100mm
        plane:2, location:0.0000mm, pitch:4.7100mm
```

이 값들이 왜 그렇게 유도되는지, `daq.tick`이 왜 파일 경계를 넘어 `500ns`로 최종 평가되는지 등 Jsonnet 구조 자체는 [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md)에서 이미 다뤘으므로 여기서는 반복하지 않는다.

## 2. Depo 시간의 기준: `Gen::Drifter`

Depo의 시간은 **G4의 절대 시간을 기준**으로 하며, post-drift depo의 시간은 **response plane 도착 시간**을 사용한다.
- `Gen::Drifter`가 pre-drift(initial) depo를 response plane까지 이동시키며, 이때 `params.jsonnet`에 설정된 `drift_speed`를 사용한다.

$t_\text{post} = t_\text{pre} + \dfrac{|x_\text{response plane} - x_\text{pre}|}{v_\text{drift}}$

```cpp
// wire-cell-toolkit/gen/src/drifter.cxx
double respx = 0, direction = 0.0;
auto xrit = std::find_if(m_xregions.begin(), m_xregions.end(), Gen::Drifter::IsInsideResp(depo));
(...)
respx = xrit->response->location();
direction = -1.0;
const double dt = std::abs((respx - pos.x()) / m_speed);
```

#### Depo Check (`data/pdhd/test_point_depo/depos-drifted-1.zip`)
- response plane 위치: $3430.465mm$ (face1)
- depo initial x position: $1500mm$, depo initial time: $0ns$
- `m_speed = 1.56mm/us`
- → `dt = 1237.47756410us`
- → depo 파일에 저장된 Gen1의 `t` 값: `1237477.6ns = 1237.4776540625us` (match!)

## 3. Data Readout Mechanism: `DepoBagger` → `DepoTransform` → `Reframer`

#### Collection (`DepoBagger`)
`wire-cell-toolkit/gen/src/DepoBagger.cxx`는 지정된 시간 구간(`gate: [start, end)`) 내에 들어온 depo들을 모아 `IDepoSet`으로 넘기는 필터 역할이다. 시간을 변화시키지는 않는다.

```jsonnet
// cfg/pgrapher/experiment/pdhd/funcs.jsonnet
local bg = g.pnode({
        type:'DepoBagger',
        name: sufix,
        data: {
            gate: [params.sim.ductor.start_time,
                   params.sim.ductor.start_time+params.sim.ductor.readout_time],
        },
    }, nin=1, nout=1),
```

`tick0_time = -250*wc.us`(`params.jsonnet:147`)는 wirecell 내부의 어떤 시간이 절대(G4) 시각에 대응하는지를 정의한다. G4의 절대 시간(`-250us`)에서, 가장 먼저 들어오는 depo의 field response 정보까지 모두 기록하도록 앞당긴 시간(`64.1026us`, §1)만큼을 뺀 `start_time`(`-314.1026us`)을 설정하며, 이 시점부터 `DepoBagger`가 depo를 모은다.

#### Transform (`DepoTransform`)
`DepoBagger`가 모은 depo(`IDepoSet`)는 `DepoTransform`을 통해 convolution으로 simulated readout frame(`IFrame`)이 된다.

```jsonnet
// wire-cell-toolkit/cfg/pgrapher/common/sim/nodes.jsonnet
make_depotransform :: function(name, anode, pirs) g.pnode({
	type:'DepoTransform',
	name:name,
	data: {
		rng: wc.tn(tools.random),
		dft: wc.tn(tools.dft),
		anode: wc.tn(anode),
		pirs: std.map(function(pir) wc.tn(pir), pirs),
		fluctuate: params.sim.fluctuate,
		drift_speed: params.lar.drift_speed,
		first_frame_number: params.daq.first_frame_number,
		readout_time: params.sim.ductor.readout_time,
		start_time: params.sim.ductor.start_time,
		tick: params.daq.tick,
		nsigma: 3,
	},
}, nin=1, nout=1, uses=[anode, tools.random, tools.dft] + pirs),
```
- `[start_time, start_time+readout_time)` 동안 들어온 depo를 tick 단위로 처리한다.
- 이때 모든 시간은 response plane에 도달한("readin") 시간 기준이다.
- 개별 depo에 대해 $\pm nsigma$(기본 3) 시간 범위(longitudinal)만 frame으로 변환한다.

#### Reframe (`Reframer`)
`wire-cell-toolkit/gen/src/Reframer.cxx`가 frame 배열 크기를 최종 크기로 잘라낸다.

```jsonnet
// wire-cell-toolkit/cfg/pgrapher/experiment/pdhd/sim.jsonnet:28-40
local reframers = [
        g.pnode({
            type: 'Reframer',
            name: 'reframer-'+tools.anodes[n].name,
            data: {
                anode: wc.tn(tools.anodes[n]),
                tags: [],
                fill: 0.0,
                tbin: params.sim.reframer.tbin,
                toffset: 0,
                nticks: params.sim.reframer.nticks,
            },
        }, nin=1, nout=1) for n in std.range(0, nanodes-1)],
```

`tbin`번째 tick(현재 `128`)부터 output frame의 시작 tick으로 설정한다.
- `128 * 500ns = 64us` → `DepoTransform`의 `start_time(-314.1026us)`에서 이 `64us`만큼 앞부분을 잘라낸다.
- 이후 `nticks`(`6000`)만큼 output frame을 만든다 → `6000 * 500ns = 3000us` 저장.
- `toffset`(현재 `0`)으로 참조 시각에 추가 오프셋을 더 줄 수 있고, `fill`(현재 `0.0`)로 pad되는 부분을 채운다.

**왜 `response_time_offset`이 아니라 `tick0_time`을 기준으로 자르는가.** `pdhd/params.jsonnet`의 두 `local` 선언 바로 위 주석이 이 설계 의도를 그대로 말해준다:
```jsonnet
// The "absolute" time (ie, in G4 time) that the lower edge of
// of final readout tick #0 should correspond to.  This is a
// "fixed" notion.
local tick0_time = -250*wc.us,

// Open the ductor's gate a bit early.
local response_time_offset = $.det.response_plane / $.lar.drift_speed,
```
`tick0_time`은 "**최종 readout tick #0**이 대응해야 하는 절대(G4) 시각"으로 애초에 고정 정의된 값이다. 반면 `response_time_offset`은 그 주석대로 `Ductor`의 gate를 "조금 일찍" 여는 용도일 뿐이다 — field response는 depo가 `response_plane`에 도달한 시점부터 유도전류를 만들기 시작하므로(collection wire 도달 *이전*부터), `tick0_time`에 정확히 도착하는 depo의 전류 파형을 놓치지 않으려면 `Ductor`가 `response_time_offset`만큼 일찍 gate를 열어야 한다(`sim.ductor.start_time = tick0_time - response_time_offset`). 즉 `response_time_offset`은 convolution을 정확히 하기 위한 **내부 버퍼**일 뿐 시간 원점이 아니고, `Reframer`는 이 버퍼를 잘라내 frame을 원래 정의된 원점인 `tick0_time`으로 되돌리는 역할을 한다.

**이 보정이 실제로 `frame->time()`에 반영되는가.** `Gen::Reframer::operator()`(`wire-cell-toolkit/gen/src/Reframer.cxx:190`)가 출력 frame의 시각을 직접 계산한다:
```cpp
auto sframe = make_shared<SimpleFrame>(inframe->ident(), inframe->time() + m_toffset + m_tbin * inframe->tick(),
                                       out_traces, inframe->tick(), ...);
```
즉 `outframe->time() = inframe->time() + toffset + tbin*tick`이다. `SP`의 `OmnibusSigProc::decon_2D_init`(§4)와 달리, `Reframer`는 자신이 잘라낸 만큼을 **`frame->time()`에 명시적으로 더해서 갱신**한다 — 이 보정은 실제로 반영되고 있다.

다만 정확히 상쇄되지는 않는다. `tbin`(`=response_nticks=128`)은 `response_time_offset`(`64.1026us`)을 `daq.tick`(`500ns`)으로 나눈 뒤 **정수 tick으로 반올림**한 값이므로, `128 * 500ns = 64.0000us`이지 `64.1026us`가 아니다. 따라서:
```
outframe->time() = ductor.start_time + tbin*tick + toffset
                 = (tick0_time - response_time_offset) + response_nticks*tick + 0
                 = -314.1026us + 64.0000us
                 = -250.1026us   (tick0_time = -250us이 아니다!)
```
정수 tick 반올림 때문에 `response_nticks*tick`(`64.0000us`)이 `response_time_offset`(`64.1026us`)을 완전히 상쇄하지 못하고 `0.1026us`만큼 남으며, 이 잔차는 `outframe->time()`에 그대로 담겨 하위 `ISlice`(`inframe->time() + slicebin*span`, §4 이전 서술 참고)에도 그대로 전파된다. 즉 최종 frame(그리고 그로부터 만들어지는 slice)의 실제 원점은 `tick0_time=-250us`가 아니라 `-250.1026us`이다.

Reframer.cxx에는 이 값을 직접 확인하기 위한 디버그 로그가 이미 추가되어 있다(`Reframer.cxx:203-204`, 2026-07-23):
```cpp
// YuJin, 2026-07-23: debug log to confirm frame->time()
log->debug("[YuJin 2026-07-23] Reframer outframe time check: {} us", outframe->time()/units::us);
```
디버그 로그 레벨로 실행해 이 값이 실제로 `-250.1026us`로 찍히는지 확인하면, 위 계산을 경험적으로 검증할 수 있다.

## 4. SP 단계의 시간 조작: `OmnibusSigProc`

`wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx`의 `decon_2D_init(int plane)`은 평면 단위 deconvolution을 수행하며, 내부적으로 frame에 대한 time shift를 한 번 더 적용한다.

```jsonnet
// wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx:316
cfg["ctoffset"] = m_coarse_time_offset;

// pdhd/sp.jsonnet
ctoffset: 1.0*wc.microsecond, // default -8.0
```

FR 파일에는 자체 speed가 내장되어 있으며(`lar.drift_speed`와는 별개 값), 이로부터 `intrinsic_time_offset`이 계산된다:
```
// wire-cell-python으로 확인, 또는 디버깅 라인 추가
fr.origin = 100.0        (mm)
fr.speed  = 0.001565      (mm/ns) = 1.565 mm/us

// wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx:919
intrinsic_time_offset = fr.origin / fr.speed = 100.0 / 0.001565 = 63.898us
```

```cpp
// wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx:828
m_period = frame->tick(); // 0.5us (500ns, §1의 daq.tick 최종값과 일치)

// wire-cell-toolkit/sigproc/src/OmnibusSigProc.cxx:1303
int time_shift = (m_coarse_time_offset + m_intrinsic_time_offset) / m_period;
// = (1.0us + 63.898us) / 0.5us = 129.796 -> int 대입이라 소수부 버림 -> 129 ticks = 64.5us
```
`time_shift`는 `int`로 선언되어 있어, `double` 나눗셈 결과(`129.796`)가 **반올림이 아니라 절삭(truncate)**되어 `129`가 된다(`Reframer`의 `wc.roundToInt`와 달리 여기는 그냥 C++ `int` 대입).

### 이 shift가 최종 데이터에 정확히 어떻게 새겨지는가 (`operator()` 실행 순서대로)

**1) `load_data()`(`:403-431`) — 배열의 열(column) 인덱스가 곧 절대시간이다.**
```cpp
m_r_data[plane] = Array::array_xxf::Zero(m_fft_nwires[plane], m_fft_nticks);   // :405
...
int tbin = trace->tbin();   // :425 — fixme 주석: 다른 곳은 전부 tbin==0을 가정
for (int qind = 0; qind < ntbins; ++qind) {
    m_r_data[plane](och.wire + m_pad_nwires[plane], tbin + qind) = q;   // :430
}
```
`tbin=0`이 전제이므로, 열 `j`는 `in->time() + j*period`(절대시간)에 대응한다. **열 0 = `frame->time()`**이라는 이 대응이 여기서 정해진다. `m_fft_nticks`는 실제 프레임 길이(`m_nticks`, Reframer 이후 `6000`)보다 FFT 최적화를 위해 넓게 잡힌 버퍼다(`:840-853`).

**2) `decon_2D_init()`의 나눗셈(`:1236`) — 이 시점까지는 순수 deconvolution.** `m_c_data[plane] = m_c_data[plane] / c_resp;`로 $X(f)/R(f)$를 계산해 시간영역으로 역변환하면(`:1282`), 열 `j`는 여전히 `in->time()+j*period`에 정확히 대응하는, 이미 복원이 끝난 depo 신호다.

**3) 그 다음 `time_shift`만큼 순환 이동(`:1297-1305`).**
```cpp
Array::array_xxf arr1(nrows, ncols - time_shift);
arr1 = m_r_data[plane].block(0, 0, nrows, ncols - time_shift);          // :1300, [0, ncols-129) 앞부분
Array::array_xxf arr2(nrows, time_shift);
arr2 = m_r_data[plane].block(0, ncols - time_shift, nrows, time_shift); // :1302, [ncols-129, ncols) 끝부분
m_r_data[plane].block(0, 0, nrows, time_shift) = arr2;                  // :1303, 끝부분을 맨 앞으로
m_r_data[plane].block(0, time_shift, nrows, ncols - time_shift) = arr1; // :1304, 원래 앞부분을 129칸 뒤로
```
`ncols=6, time_shift=2`, 원본 `[A,B,C,D,E,F]`로 예를 들면: `arr1=[A,B,C,D]`, `arr2=[E,F]` → 결과 `[E,F,A,B,C,D]`. 즉 **원래 열 `i`의 값이 열 `i+time_shift`로 옮겨간다**(오른쪽 순환 이동). 열 0(=`in->time()`)에 있던 진짜 신호가 열 129(=`in->time()+64.5us`)로 밀려난다.

**4) `save_data()`(`:489-563`) — 밀려난 위치를 그대로 최종 trace로 굳힌다.**
```cpp
for (int itick = 0; itick != m_nticks; itick++) {
    const float q = m_r_data[plane](och.wire, itick);   // :498, 롤 이후 배열에서 [0, m_nticks) 그대로 읽음
}
...
auto trace = new Aux::SimpleTrace(och.ident, 0, charge);   // :558, 출력 trace의 tbin은 항상 0
```
롤이 끝난 배열의 **처음부터** `m_nticks`개를 그대로 잘라 읽고 `tbin=0`으로 못박는다. 129칸 밀려난 진짜 신호가 그대로 최종 데이터가 되고, 원래 그 자리(버퍼 맨 끝, 거의 비어있는 FFT padding)가 wrap되어 trace 맨 앞 `64.5us`를 채운다. `decon_2D_tightROI`/`decon_2D_hits` 등 실제 프로덕션 경로가 쓰는 `.block(m_pad_nwires[plane], 0, m_nwires[plane], m_nticks)` 크롭들도 전부 시간축 오프셋 없이(`0`부터) 자르므로 동일하게 적용된다.

**5) `operator()`의 최종 frame 생성(`:2102`) — 메타데이터는 그대로.**
```cpp
auto sframe = new Aux::SimpleFrame(in->ident(), in->time(), ITrace::shared_vector(itraces), in->tick(), in->masks());
```
롤이 있기 전 입력 frame의 시각(`in->time()`)을 그대로 새 frame에 넣는다. `time_shift`만큼 데이터가 뒤로 밀렸다는 사실은 이 메타데이터 어디에도 반영되지 않는다.

**결과**: `frame->time() + itick*period`로 절대시간을 복원하는 모든 하위 코드(`MaskSlice.cxx` 등, §5)는, 실제로 `itick`에 있는 신호가 진짜로 발생한 시각보다 `time_shift*period = 129*500ns = 64.5us` **더 늦은** 시각으로 잘못 해석하게 된다.

**`intrinsic_time_offset`(`63.898us`, FR 파일에 내장된 speed `1.565mm/us` 기준)과 `response_time_offset`(§1, `lar.drift_speed` 기준)은 같은 물리량("response plane까지의 drift 시간")을 서로 다른 speed로 계산한 것이라 값이 다르다.**
- 과거(`lar.drift_speed=1.6mm/us` 시절): `response_time_offset=62.5us` → 차이 `63.898-62.5=+1.398us`. 이 차이가, 당시 `BlobDepoFill.time_offset`에 analytic baseline `312.5us`를 그대로 썼을 때 정보를 주지 못했던 이유였고, 그래서 `314.5us`로 경험적 보정을 했던 것으로 추정된다([time_offset_calibration_report.md](time_offset_calibration_report.md) §3 참고).
- 현재(`lar.drift_speed=1.56mm/us`, 2026-07-23 override 이후): `response_time_offset=64.1026us` → 차이 `63.898-64.1026=-0.2046us`로 줄어들고 부호도 바뀐다. 즉 `drift_speed`를 FR 파일 speed(`1.565mm/us`)에 더 가깝게 맞춘 결과 두 값의 괴리는 거의 사라졌다. 다만 이것이 실제 `BlobDepoFill.time_offset`의 최적값에 어떻게 반영되는지는 재검증이 필요하다.

**이 보정이 이 파이프라인에서는 애초에 불필요할 가능성.** `ctoffset`/`intrinsic_time_offset`은 원래 "response 함수의 자체 시간 기준"과 "실제 ADC tick 0" 사이의 관계를 전혀 모르는 **실데이터**를 위해 설계된 보정이다. 하지만 위 2)에서 보였듯, 이 프로젝트의 `m_r_data[plane]`(= $X(f)$)는 `DepoTransform`이 **SP와 완전히 동일한 field response 파일**(`files.fields`)로 depo를 convolution해서 만든 것이다. Forward를 $X(f)=H(f)\cdot R(f)$($H$=depo 시각의 델타함수, $R$=field response)라 하면, `decon_2D_init`의 나눗셈은 $\hat H(f)=X(f)/R(f)=H(f)$로 **이론적으로 완전히 원복되며, response 함수 자체의 "느린 시작"(intrinsic_time_offset)은 이 나눗셈에서 자동으로 상쇄된다.** 즉 forward와 reverse가 같은 $R(f)$를 쓰는 **자기완결적 시뮬레이션**에서는 3)의 `time_shift` 롤이 원래 필요 없다 — 그런데도 적용되면서, 이미 정확했던 결과에 인위적인 `64.5us` 지연을 한 번 더 얹는 것으로 보인다. (검증 방법: `ctoffset`을 바꾸거나 이 롤을 건너뛰게 해서 재실행 — [time_offset_calibration_report.md](time_offset_calibration_report.md) §4 참고.)

§3의 자기상쇄 설계(Ductor를 일찍 열고 Reframer가 되돌리는 것)가 성립하려면 SP 단계가 tick-index와 절대시간의 대응을 보존해야 하는데, 위 3)-5)의 재인덱싱이 그 대응을 조용히 어긋나게 만든다 — config만 봐서는 알 수 없는, chain에서 유일하게 self-documenting하지 않은 연결고리다.

### 그 밖에 시간축을 만지는 지점들 (`OmnibusSigProc.cxx`)

MicroBooNE `simparams.jsonnet:182-197`의 주석에는 다른 detector에서 실제로 문서화된 사례가 있다: "Garfield field response에서 collection plane peak가 `response_plane/drift_speed`가 아니라 약 $81us$ 근방에서 생긴다." 즉 단순 `response_plane/drift_speed` 계산이 애초에 FR 파형의 실제 peak와 정확히 일치한다는 보장은 없다.

- **`init_overall_response()`의 `ftoffset`(`m_fine_time_offset`) shift (`:947-961`)**: `decon_2D_init`의 `time_shift`와는 별개의 파라미터다. Raw 데이터가 아니라 field×electronics response 파형 자체를, SP tick 그리드로 리샘플링하기 전에 fine-grid(response 고유 grid) 단위로 순환 이동시킨다.
  ```cpp
  int fine_time_shift = m_fine_time_offset / fravg.period;   // ftoffset, cfg: `:63,315`
  ```
- **`init_overall_response()`의 fine→coarse 리샘플링 time-origin (`:964-1001`)**: response를 `fravg.period`(fine grid)에서 `m_period`(SP tick)로 linear interpolation redigitize한다. 명시적 offset 파라미터는 아니지만, 코드 주석(`:980-988`)에 예전 boxcar 방식 대비 이 리샘플링이 `-200ns`만큼 time origin을 이동시켰다는 경고가 남아 있다.
- **`init_overall_response()`의 시간축 pad 폭 설정 (`:840-853`)**: `m_pad_nticks = m_fft_nticks - m_nticks`로 `decon_2D_init`이 쓸 시간축 padding 폭을 결정한다. 다만 이 변수 자체는 파일 내에서 다시 읽히는 곳이 없다.
- **`load_data()`의 입력 trace `tbin` 소비 (`:424-430`)**: `OmnibusSigProc`이 계산하는 offset이 아니라, 입력 프레임 각 trace가 이미 갖고 있는 `tbin`을 그대로 배치 위치로 쓴다. `// fixme: this code uses tbin() but other places in this file will barf if tbin!=0`(`:424`) 주석대로, 이후 단계는 전부 `tbin==0`을 암묵적으로 가정한다.
- **7개 `decon_2D_*` 함수의 시간축 crop** (`decon_2D_ROI_refine`/`decon_2D_tightROI`/`decon_2D_tighterROI`/`decon_2D_looseROI`/`decon_2D_looseROI_debug_mode`/`decon_2D_hits`/`decon_2D_charge`, `:1469,1514,1560,1652,1701,1765,1798`): 전부 `m_r_data[plane] = tm_r_data.block(m_pad_nwires[plane], 0, m_nwires[plane], m_nticks)` 패턴을 반복한다. `decon_2D_init`의 `unpad_data()`는 wire 방향 padding만 제거하고 시간축은 `m_fft_nticks` 길이로 남기므로, FFT용 시간축 padding이 실제로 제거되는 지점은 이 7개 함수 각각이다. (`pad_data()`/`unpad_data()` 자체는 wire(공간) 방향 padding만 다루고 시간축과는 무관하다.)

이 후보들이 실제 잔차에 얼마나 기여하는지는 analytic하게 유도되지 않았다 — 실제 검증 스캔 결과와 남은 한계는 [time_offset_calibration_report.md](time_offset_calibration_report.md)를 참고.

## 5. Slicing 단계의 시간 처리: `MaskSlice`와 하드코딩된 `-64165`

PDHD는 `img.jsonnet:100`에서 `MaskSlices`(`img/src/MaskSlice.cxx`)를 슬라이서로 쓴다. 이 파일에는 slice의 `start` 시각을 계산하는 코드가 **두 군데** 있고, 서로 다른 공식을 쓴다.

- **Pre-population 루프** — 미리 모든 slicebin에 대해 slice 객체를 만들어두는 곳(`:263-270`):
  ```cpp
  // const double start = slicebin * m_tick_span * tick;   // 원래 주석 처리된 stock 코드: in->time() 자체가 없었다
  const double start = in->time() - 64165 + slicebin * m_tick_span * tick;   // :265
  ```
- **나머지(wiener/threshold/masked-charge) 루프** — 필요할 때 on-demand로 slice를 만드는 곳(`:359, :385, :424`, 전부 동일):
  ```cpp
  const double start = in->time() + slicebin * span;   // -64165 없음
  ```

`-64165`(단위 없는 리터럴이므로 `ns`, 즉 `-64.165us`)는 stock WCT 코드가 아니다: 원래 주석 처리된 줄은 `in->time()`조차 없는 순수 상대값(`slicebin*span`)이었다. 누군가 여기에 `in->time()`을 추가해 절대값으로 바꾸면서, 동시에 `-64165`라는 보정을 끼워 넣은 것으로 보인다. 바로 옆에 `2026-07-23` 날짜의 디버그 로그(`:271-276`, "pre-populated slice start가 relative인지 absolute인지 확인")가 있는 걸 보면 최근에 직접 조사된 흔적이다.

**문제 1 — 같은 파일 안에서 slice 생성 경로에 따라 `start`가 `64.165us`만큼 달라진다.** 어떤 slicebin의 slice 객체가 pre-population 루프에서 먼저 만들어지는지, on-demand 루프에서 만들어지는지에 따라 `-64165` 보정이 있거나 없다(`svcmap[slicebin]`이 이미 있으면 두 번째 루프는 건너뛴다).

**문제 2 — 이 값의 정체.** 크기가 §4의 SP `time_shift`(`(1.0+63.898)/0.5 → int 절삭 → 129 ticks = 64.5us`)와 비슷하다(`0.335us` 차이). §4에서 지적한 "SP가 `frame->time()`을 안 갱신하는 문제"를 이 slicing 단계에서 수동으로 되돌리려 한 패치로 추정된다 — 그런데 정작 SP 쪽(진짜 원인)은 그대로 두고, 훨씬 아래 slicing 단계에서 코드 경로 절반에만 임시로 끼워 넣은 상태다.

### 실제로 계산해보면: 앞선 모든 잔차가 겹쳐서 나오는 숫자

지금까지 나온 조각들을 그대로 이어 붙이면, `slicebin=0`의 `start`(pre-population 공식 기준)가 정확히 얼마가 되는지 계산할 수 있다.

1. `response_time_offset = 100mm / 1.56mm/us = 64.1025641025641us` (§1)
2. `ductor.start_time = tick0_time - response_time_offset = -250 - 64.1025641025641 = -314.1025641025641us` (§1)
3. `Reframer` 출력(§3, 정수 tick 반올림 잔차 포함): `outframe->time() = ductor.start_time + 128*500ns = -314.1025641025641 + 64.0 = -250.1025641025641us`
4. SP는 `frame->time()`을 그대로 유지하므로(§4), `MaskSlice`가 받는 `in->time()`도 동일하게 `-250.1025641025641us`
5. `MaskSlice`의 pre-population 공식(`slicebin=0`):
   ```
   start(0) = in->time() - 64165ns
            = -250.1025641025641 - 64.165
            = -314.2675641025641us
   ```

즉 `314.2675641025641`(절댓값)은 하나의 원인이 아니라, **Reframer의 정수-tick 반올림 잔차(`≈0.1026us`, §3)**와 **`MaskSlice.cxx`의 `-64165` 하드코딩 패치(`64.165us`)**가 그대로 누적된 값이다. `analytic baseline`(`|tick0_time|+response_time_offset=314.1026us`, §4)과 비교하면 `0.165us`만큼 더 크다 — 이 `0.165us`는 `MaskSlice`의 `64.165us`와 `Reframer`가 정확히 상쇄했어야 할 `64.000us`(`=128*500ns`)의 차이(`64.165-64.000=0.165`)와 정확히 같다.

## Related documents

- [wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md): Jsonnet 파라미터 파일 구조 전반.
- [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md): `sim` 필드 상세 + PDHD 계산값 (§1의 근거).
- [time_offset_calibration_report.md](time_offset_calibration_report.md): 이 문서의 분해를 바탕으로 실제 `time_offset` 값을 찾은 스터디 리뷰/방법론/검증 결과/다음 단계.
