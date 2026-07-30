# `sim` 파라미터 필드: 구조, 설명, PDHD 값

[wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md)의 3절에서 다룬 최상위 네임스페이스 중 `sim` 필드만 따로 떼어, 각 하위 요소의 의미와 계층별(override) 값, 그리고 이 프로젝트가 실제로 쓰는 PDHD 최종 값을 정리한 문서.

## 1. `sim` 필드가 정의/override되는 계층

```
pgrapher/common/params.jsonnet        sim 필드 최초 정의 (범용 기본값)
    -> pgrapher/dune/params.jsonnet       sim을 override하지 않음 (adc.resolution, elec.gain만 override)
        -> pgrapher/experiment/pdhd/params.jsonnet     sim 전체를 override (ductor/reframer 공식 자체를 교체)
            -> pgrapher/experiment/pdhd/simparams.jsonnet  sim.fixed/continuous/fluctuate만 추가 override
                                                            (ductor/reframer는 주석 처리되어 있어 그대로 상속)
```

이 프로젝트의 PDHD 작업 파일(`wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet` 등)이 실제로 보는 `sim` 값은 위 체인을 모두 거친 **`simparams.jsonnet` 최종 결과**이다. 아래 3절의 "PDHD 최종 값"은 이 최종 결과를 의미한다.

## 2. `sim` 구조

```jsonnet
sim: {
    nimpacts: <int>,
    fluctuate: <bool>,
    continuous: <bool>,
    fixed: <bool>,
    depo_toffset: <time>,
    ductor: {
        nticks: <int>,
        readout_time: <time>,
        start_time: <time>,
    },
    reframer: {
        tbin: <int>,
        nticks: <int>,
    },
}
```

`ductor`와 `reframer`는 각각 시뮬레이션 파이프라인의 서로 다른 단계에 대응하는 하위 객체다.
- **`ductor`** — drift/induction 시뮬레이션을 수행하는 컴포넌트(`Ductor`)의 프레임 파라미터. 최종 readout(`daq.nticks`)보다 앞선 시점부터 데이터를 만들어야 하므로, 실제 readout보다 더 넓은 시간창을 가진다.
- **`reframer`** — `Ductor`가 만든 넓은 시간창을 최종 `daq.nticks` 길이로 잘라내는 컴포넌트(`Reframer`)의 파라미터.

## 3. 필드별 설명 및 계층별 값

| 필드 | 설명 | 범용 base 값 (`common/params.jsonnet`) | PDHD 최종 값 (`simparams.jsonnet` 적용 후) |
|---|---|---|---|
| `nimpacts` | wire 영역 하나당 impact bin 개수. 횡방향(transverse) 시뮬레이션 convolution의 세밀도를 결정하며, field-response 파일이 정의된 세밀도와 일치해야 한다. | `10` | `10` (override 없음, base 그대로) |
| `fluctuate` | 통계적 요동(전하 fluctuation)을 적용할지 여부. | `true` | `true` (`simparams.jsonnet`이 동일 값으로 명시적으로 재지정) |
| `continuous` | 연속(continuous) 모드로 프레임을 생성할지 여부(불연속 모드와 대비). | `true` | `false` (`simparams.jsonnet`에서 override) |
| `fixed` | `true`이면 `continuous` 설정과 무관하게 고정된 시각에 프레임을 만든다. LArSoft에서 구동하려면 반드시 `true`여야 한다. | `false` | `true` (`pdhd/params.jsonnet`, `simparams.jsonnet` 양쪽에서 override) |
| `depo_toffset` | drift된 모든 depo 시각에 더해지는 고정 시간 오프셋. depo source가 올바른 절대 시각을 주지 못할 때 보정용으로 사용. | `0.0` | `0.0` (override 없음, 현재 미사용) |
| `ductor.nticks` | `Ductor`가 내부적으로 생성하는 총 tick 수. `daq.nticks`보다 `response_nticks`만큼 더 많다. | `$.daq.nticks + $.elec.fields.nticks` (공식) | `6128` (계산값, 4절 참고) |
| `ductor.readout_time` | 위 `nticks`에 대응하는 총 시간 길이. | `self.nticks * $.daq.tick` (공식) | `3064us` (`3064000ns`, 계산값) |
| `ductor.start_time` | `Ductor`가 데이터를 생성하기 시작하는 절대 시각. 최종 readout 시작 시각보다 앞서 열어 두어야 response plane에서 anode까지의 drift 시간을 놓치지 않는다. | `$.daq.start_time - $.elec.fields.drift_dt` (공식) | `-314.10us` (계산값) |
| `reframer.tbin` | `Ductor` 출력 앞부분에서 잘라낼 tick 수. `ductor`가 추가로 확보한 lead-time tick 수(`response_nticks`)와 같아야 한다. | `$.elec.fields.nticks` (공식) | `128` (계산값) |
| `reframer.nticks` | 잘라낸 뒤 최종 프레임의 tick 수. | `$.daq.nticks` (공식) | `6000` (`daq.nticks`와 동일) |

## 4. `ductor`/`reframer` PDHD 수치 유도 과정

PDHD는 `elec.fields.drift_dt`(범용 공식, `elec.fields.start_dx`와 `lar.drift_speed` 기반)를 그대로 쓰지 않고, `det.response_plane`과 `lar.drift_speed`로 직접 `response_time_offset`을 계산한다(`pgrapher/experiment/pdhd/params.jsonnet`).

```jsonnet
local tick0_time = -250*wc.us,
local response_time_offset = $.det.response_plane / $.lar.drift_speed,
local response_nticks = wc.roundToInt(response_time_offset / $.daq.tick),

ductor: {
    nticks: $.daq.nticks + response_nticks,
    readout_time: self.nticks * $.daq.tick,
    start_time: tick0_time - response_time_offset,
},
reframer: {
    tbin: response_nticks,
    nticks: $.daq.nticks,
}
```

입력값:
- `det.response_plane = 10*wc.cm = 100mm` (`pdhd/params.jsonnet`)
- `lar.drift_speed = 1.56*wc.mm/wc.us` (`pdhd/params.jsonnet`, 2026-07-23 수정. `np04hd-garfield-6paths-mcmc-bestfit.json.bz2`의 `drift_speed`와 일치시키기 위한 override)
- `daq.tick` — **`pdhd/params.jsonnet`은 `512*wc.ns`로 설정하지만, `pdhd/simparams.jsonnet`이 이를 다시 `0.5*wc.us`(`500ns`, 시뮬레이션 native tick, 별도 `Resampler` 불필요)로 override한다. 아래 `response_nticks`/`ductor`/`reframer` 계산에 쓰이는 `$.daq.tick`은 이 최종 override된 `500ns`로 평가된다** (4-1절 참고).
- `daq.nticks = 6000` (`pdhd/params.jsonnet`, `simparams.jsonnet` 양쪽에서 동일하게 설정)
- `tick0_time = -250*wc.us` (`pdhd/params.jsonnet`에 하드코딩된 로컬 앵커. 아래 5절 참고)

계산:
1. `response_time_offset = 100mm / 1.56mm/us = 64.10us` (`64102.56ns`)
2. `response_nticks = roundToInt(64102.56ns / 500ns) = roundToInt(128.21) = 128`
3. `ductor.nticks = 6000 + 128 = 6128`
4. `ductor.readout_time = 6128 * 500ns = 3064000ns = 3064us`
5. `ductor.start_time = -250us - 64.10us = -314.10us`
6. `reframer.tbin = 128`, `reframer.nticks = 6000` (`daq.nticks` 그대로)

위 값은 `_jsonnet` 파이썬 바인딩(`wire-cell-python/venv`)으로 `pdhd/simparams.jsonnet`을 실제로 평가해 `sim: {"ductor": {"nticks": 6128, "readout_time": 3064000, "start_time": -314102.564...}, "reframer": {"tbin": 128, "nticks": 6000}}`을 직접 확인한 결과이며, 손으로 계산한 위 6단계와 일치한다.

### 4-1. 주의: `$`는 어느 파일에서 쓰였는지가 아니라 최종 병합 결과를 가리킨다

`response_nticks`를 계산하는 `local` 식은 `pdhd/params.jsonnet` 안에 텍스트로 적혀 있지만, 그 안의 `$.daq.tick`은 **그 식이 적힌 파일의 값(512ns)이 아니라, import 체인 전체가 끝난 뒤 최종적으로 병합된 루트 객체의 `daq.tick`**을 가리킨다. `pdhd/simparams.jsonnet`이 `daq: super.daq { tick: 0.5*wc.us }`로 이를 다시 override하므로, `pdhd/params.jsonnet`에 적힌 수식이라도 최종 결과는 `500ns` 기준으로 계산된다(`super`/`self`처럼 override 체인을 그대로 따라간다는 뜻이며, 이는 [wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md) 1절에서 설명한 `$`의 동작과 일치한다 — `$`가 "어느 파일에 적혔는지"에 고정되지 않는다는 점은 착각하기 쉬우므로 별도로 강조해 둔다). `simparams.jsonnet`은 `ductor`/`reframer`의 override 자체는 주석 처리해 두었으므로(§5), `sim.ductor`/`sim.reframer`의 **공식과 구조**는 `pdhd/params.jsonnet` 것을 그대로 쓰지만, 그 공식이 참조하는 `$.daq.tick` 값은 `simparams.jsonnet`이 마지막에 덮어쓴 `500ns`라는 점에 유의해야 한다.

## 5. PDHD가 `ductor`/`reframer` 공식 자체를 교체하는 이유

범용 base(`pgrapher/common/params.jsonnet`)의 `ductor.start_time`은 `$.daq.start_time`(기본값 `0.0*wc.s`)을 기준으로 `$.elec.fields.drift_dt`만큼 앞당기는 식이다. 반면 PDHD의 `ductor.start_time`은 `$.daq.start_time`을 전혀 참조하지 않고, 별도의 로컬 상수 `tick0_time = -250*wc.us`를 새 기준점(앵커)으로 사용한다. 즉:

- 범용 base: `daq.start_time`을 기준점으로 삼고, `elec.fields`(범용 `start_dx=10cm`, 범용 `lar.drift_speed`)로 lead-time을 계산.
- PDHD: `tick0_time=-250us`라는 자체 기준점을 새로 도입하고, `det.response_plane`(PDHD 고유 값)과 PDHD의 `lar.drift_speed`로 lead-time(`response_time_offset`)을 계산.

이는 [wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md) 6절에서 설명한 일반 규칙의 구체적 사례다: 하위 공식이 그대로 유효하면 입력값만 override하면 되지만, 기준점/유도 로직 자체가 다르면 하위 객체 전체(`ductor`, `reframer`)를 통째로 교체해야 한다. `elec.fields.drift_dt`는 범용 `elec.fields.start_dx`(field-response 파일이 시작되는 지점) 기반이고, PDHD의 `response_time_offset`은 `det.response_plane`(PDHD가 정의한 response plane 위치) 기반이므로, 두 값이 개념적으로는 비슷하지만(둘 다 "response plane까지의 drift 시간") 서로 다른 입력을 참조하는 별개의 계산이다.

`simparams.jsonnet`에는 이 `ductor`/`reframer`를 다시 override하려던 주석 처리된 코드가 남아 있다:

```jsonnet
//ductor : super.ductor {
//    start_time: $.daq.start_time - $.elec.fields.drift_dt + $.trigger.time,
//},
//reframer: super.reframer{
//    tbin: if $.sys_status == true
//            then (81*wc.us-($.sys_resp.start))/($.daq.tick)
//            else (81*wc.us)/($.daq.tick),
//    nticks: $.daq.nticks,
//    toffset: if $.sys_status == true
//                then $.elec.fields.drift_dt - 81*wc.us + $.sys_resp.start
//                else $.elec.fields.drift_dt - 81*wc.us,
//},
```

두 블록 모두 현재 비활성 상태다. 위쪽은 MicroBooNE 전용의 `trigger` 블록(같은 파일에서 역시 주석 처리됨)을 참조하므로 PDHD에서는 애초에 평가될 수 없는 코드이고, 아래쪽은 `$.sys_status`(현재 `false`)가 켜졌을 때 `81us` 기준의 다른 `reframer.tbin` 공식을 쓰려던 것이다. 즉 현재 PDHD 설정에서는 4절의 계산값이 그대로 유효하며, `sys_status`를 켜는 시점에는 `reframer` 공식을 다시 검토해야 한다.

## 6. 관련 상수와의 관계 (주의: 동일한 값이 아님)

4절에서 계산한 `sim.ductor.start_time ≈ -314.10us`는 [time_offset_calibration.md](time_offset_calibration.md)에서 다루는 `wire-cell-cfg/pdhd/img.jsonnet`의 `BlobDepoFill.time_offset`(현재 경험적으로 설정된 값 `314.5us`)과 수치가 우연히 비슷하지만, **서로 다른 목적의 서로 다른 상수**다.

- `sim.ductor.start_time` — 시뮬레이션 단계에서 `Ductor`가 언제부터 데이터를 만들기 시작해야 하는지를 결정하는 프레임 타이밍 파라미터. `det.response_plane`과 `lar.drift_speed`로부터 **해석적으로 계산**된다.
- `BlobDepoFill.time_offset` — 평가(evaluation) 단계에서 depo 시각과 reco blob의 시간축을 맞추기 위해 `img.jsonnet`에 **경험적으로** 설정한 상수. `time_offset_calibration.md`에 따르면 이 값의 잔차 원인 중 상당 부분은 `intrinsic_time_offset`(field response 파일에 내장된 speed)과 `response_time_offset`(`lar.drift_speed`로 계산된 값)이 서로 다른 drift speed를 사용하기 때문임이 확인되었다.

두 값이 비슷한 크기인 것은 둘 다 "response plane까지의 drift 시간"이라는 같은 물리량에서 출발하기 때문이지만, 이 문서의 `-314.10us`를 `BlobDepoFill.time_offset`에 그대로 대입해도 되는지는 별도로 검증되지 않았다. 시간축 정합이 필요한 작업에서는 반드시 `time_offset_calibration.md`를 참고할 것.

## Related documents

- [wirecell_params_jsonnet_reference.md](wirecell_params_jsonnet_reference.md): Parent doc — Jsonnet 상속 메커니즘, 단위 체계, 전체 파라미터 네임스페이스 개요.
- [time_offset_calibration.md](time_offset_calibration.md): Sibling doc — `BlobDepoFill.time_offset`(`314.5us`)의 근본 원인 분석 및 보정. 본 문서 6절에서 `sim.ductor.start_time`과의 차이를 설명하는 데 참조.
