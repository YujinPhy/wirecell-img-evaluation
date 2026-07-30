# Wire-Cell Jsonnet 파라미터 파일: 구조화 규칙 및 개념 정리

`../wire-cell-toolkit/cfg/`의 Jsonnet 파라미터 파일들이 어떻게 구조화되어 있는지 정리한 문서. 이 프로젝트가 실제로 import하는 PDHD 체인을 예시로 사용한다.

```
wirecell.jsonnet                                    (단위 체계 + 헬퍼 함수)
    -> pgrapher/common/params.jsonnet                (범용 base 구조체)
        -> pgrapher/dune/params.jsonnet              (DUNE 계열 공통 override)
            -> pgrapher/experiment/pdhd/params.jsonnet     (PDHD 검출기 실측 파라미터)
                -> pgrapher/experiment/pdhd/simparams.jsonnet  (PDHD 시뮬레이션 전용 override)
                    -> wire-cell-cfg/pdhd/{wct-sim-nf-sp-img-bdf.jsonnet, wct-sim-nf-sp-img-bdf-grid.jsonnet, img.jsonnet}
```

화살표 하나하나가 Jsonnet의 `import` 다음에 오는 객체 상속(`base { ... overrides ... }`)이다. 이 프로젝트의 PDHD 작업 파일들(`wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet:12`, `wct-sim-nf-sp-img-bdf-grid.jsonnet:21`, `img.jsonnet:4`)은 모두 체인의 가장 마지막 단계인 `pgrapher/experiment/pdhd/simparams.jsonnet`을 `params`라는 이름으로 import한다. 즉, 이 프로젝트의 설정 파일이 보는 시점에는 그 위 단계의 내용이 이미 전부 반영되어 있다.

## 1. Jsonnet 상속 메커니즘

전체 체계는 다음 세 가지 구성 요소로 만들어지며, 모든 `params.jsonnet`에서 일관되게 사용된다.

- **`local x = import "path.jsonnet"; x { ... }`** — 파일(그 파일의 최상위 객체)을 import한 뒤 곧바로 `{ ... }`로 확장/override한다. 위 체인의 모든 화살표가 이 상속 단계에 해당한다.
- **`super.foo { ... }`** — override 블록 안에서 `super`는 *부모*가 갖고 있던 현재 객체를 가리킨다. `daq: super.daq { tick: 512*wc.ns }`는 "부모의 `daq` 객체 전체를 가져오고 `tick`만 교체한다"는 뜻이다. 반면 `daq: { tick: 512*wc.ns }`라고 쓰면 부모의 다른 필드(`nticks`, `readout_time` 등)가 전부 조용히 사라진다. `pdhd/params.jsonnet`과 `pdhd/simparams.jsonnet`의 모든 override가 바로 이 이유 때문에 `super.X { ... }` 형태를 사용한다.
- **`self` vs `$`** — `self`는 현재 객체 레벨을 가리키며 모든 override가 적용된 *이후*에 값이 결정된다(자식이 형제 필드를 override하면 그 값을 반영한다). `$`는 중첩 깊이와 무관하게 항상 전체 평가 대상 객체의 루트를 가리킨다. `pgrapher/common/params.jsonnet`의 예:
  ```jsonnet
  daq: {
      tick: 0.5*wc.us,
      nticks: 10000,
      readout_time: self.tick*self.nticks,   // 같은 객체 내부 참조, override 반영됨
  },
  elec: {
      fields: {
          drift_dt: self.start_dx / $.lar.drift_speed,  // 루트를 가리키는 다른 섹션 참조
      },
  },
  ```
  자식이 `daq.tick`을 override해도 `readout_time`은 캡처된 값이 아니라 `self.tick`을 읽기 때문에 올바르게 재계산된다.
- **객체 내부의 `local` 바인딩** — 최종 출력 필드로 나타나지 않고 실제 필드를 계산하기 위한 중간값/파생값으로만 쓰인다. PDHD의 `params.jsonnet`은 `det.volumes`를 조립하기 전에 `apa_cpa`, `apa_w2w`, `plane_gap`, `apa_plane`, `res_plane`, `cpa_plane`을 이런 방식으로 계산하며, 이 값들은 최종 렌더링된 JSON에는 전혀 나타나지 않는다.

## 2. 단위 체계 (`wirecell.jsonnet`)

모든 params 파일의 물리량은 내부적으로 단순한 float이며, `WireCellUtil/Units.h`를 그대로 옮긴 고정된 자기참조형 base-unit 체계로 표현된다.

| 물리량 | Base unit = 1.0 |
|---|---|
| 길이 | `millimeter` |
| 시간 | `nanosecond` |
| 전하 | `eplus` (양전자 전하) |
| 에너지 | `megaelectronvolt` |
| 온도 | `kelvin` |
| 물질량 | `mole` |
| 광도 | `candela` |

다른 모든 단위(`wc.cm`, `wc.m`, `wc.us`, `wc.ms`, `wc.fC`, `wc.mV`, `wc.volt`, `wc.Bq` 등)는 위 base 단위들의 배수로 정의되며 `self.*` 참조로 서로 연결된다(예: `centimeter: 10.0*self.millimeter`, `microsecond: 1.0e-6*self.second`). params 파일을 읽거나 작성할 때의 실전 규칙: **숫자 하나만 있으면 의미가 없고, `숫자 * wc.단위` 형태만 유효한 값**이다. 예: `3.5734*wc.m`, `2.2*wc.us`, `7.8*wc.mV/wc.fC`. 모든 단위가 동일한 base 단위로 환원되므로, 서로 다른 물리량(예: `response_plane / drift_speed`처럼 길이를 속도로 나누는 경우) 간의 연산도 별도의 단위 변환 없이 그대로 성립한다.

`wirecell.jsonnet`은 params 파일 전반에서 쓰이는 헬퍼 함수도 정의한다.
- `wc.point(x,y,z,u)` / `wc.ray(p1,p2)` — 점/선분 구조체를 만든다. `u`는 각 좌표에 곱할 단위이다(`pdhd/params.jsonnet:103-104`의 `det.bounds` 참고).
- `wc.roundToInt(x)` — format/parse 트릭으로 가장 가까운 정수로 반올림한다. 시간을 `nticks`로 변환할 때 쓰인다(예: `sim.response.nticks`, PDHD의 `response_nticks`).
- `wc.tn(obj)` — configurable 컴포넌트의 정규화된 `"type:name"` 문자열을 만든다(params 파일에서 직접 쓰이기보다는 `pgrapher/`의 그래프 구성 코드에서 사용).
- `freqbinner`, `freqmasks_phys` — 노이즈 필터(`nf`) chndb 설정을 위한 주파수 bin 헬퍼.

## 3. 최상위 파라미터 네임스페이스

`pgrapher/common/params.jsonnet`은 아래의 최상위 키들로 범용 base 객체를 정의한다. 각 experiment의 `params.jsonnet`/`simparams.jsonnet`은 이 키들의 하위 필드만 override할 뿐, 새로운 최상위 네임스페이스를 도입하는 경우는 거의 없다(PDHD의 `sys_status`/`sys_resp`/`rc_resp`가 범용 키와 나란히 존재하는 experiment 전용 확장의 유일한 예외다).

| 네임스페이스 | 목적 | 대표 소비 주체 |
|---|---|---|
| `lar` | 벌크 액체 아르곤 물리량: 확산(`DL`,`DT`), `lifetime`, `drift_speed`, `density`, `ar39activity` | `Drifter`, diffusion/lifetime 시뮬레이션 |
| `det` | 검출기 volume: `{wires, name, faces:[...]}`로 구성된 `volumes[]`, 대략적인 `bounds` 박스 | `AnodePlane`, `Drifter` |
| `daq` | 리드아웃 타이밍: `tick`, `nticks`, `readout_time`, `start_time`/`stop_time`, `first_frame_number` | 프레임 소스/싱크 컴포넌트, `Resampler` |
| `adc` | 디지타이제이션: 상대 `gain`, `baselines`(U/V/W별), `resolution`(비트 수), `fullscale` 범위 | ADC/디지타이저 컴포넌트 |
| `elec` | 프론트엔드 전자장비: 증폭기 `gain`, `shaping` 시간, `postgain`, `fields.{start_dx,drift_dt,nticks}`(field-response 타이밍) | shaper/response 시뮬레이션 |
| `sim` | 다른 곳에 없는 시뮬레이션 전용 옵션: `nimpacts`, `fluctuate`, `continuous`/`fixed`, `depo_toffset`, `ductor.{nticks,readout_time,start_time}`, `reframer.{tbin,nticks}` | `Ductor`, `Reframer` |
| `nf` | 노이즈 필터링: `nsamples`(주파수 bin 개수) | `OmniChannelNoiseDB` 및 NF 체인 |
| `files` | 외부 데이터 파일 참조: `wires`, `fields[]`(field response, 첫 번째가 nominal), `noise`, `chresp` | 그래프 구성 시점의 파일 로딩 컴포넌트 |

`pgrapher/common/params.jsonnet` 상단 주석에 이 의도가 직접 명시되어 있다: 파라미터를 하위 객체로 나눈 것은 "C++ 컴포넌트가 구조화되고 자신의 설정 파라미터 이름을 짓는 방식에 부합하도록" 하기 위함이다. 즉 네임스페이스 이름은 임의의 분류가 아니라 C++ 컴포넌트 설정을 그대로 반영하도록 선택된 것이다.

## 4. `det.volumes` / `faces` 구조

`det.volumes`의 각 항목은 하나의 anode plane(즉, `AnodePlane` 컴포넌트 인스턴스 하나)을 기술한다.

```jsonnet
{
    wires: n,          // anode 번호. AnodePlane.ident로 쓰이고 WireSchema에서 wire를 조회하는 데 사용됨
    name: "apa%d" % n,
    faces: [ front_face_or_null, back_face_or_null ],
}
```

null이 아닌 각 face는 `{ anode, response, cathode }`로, drift 축을 따라 놓인 세 개의 평면 위치를 나타낸다.
- **`anode`** — cutoff 평면. wire보다 이 평면에 더 가까운 depo는 그대로 버려진다.
- **`response`** — field-response 함수가 시작되는 지점(Garfield 기반 field-response 파일이 가정하는 값과 반드시 일치해야 한다. PDHD의 `response_plane: 10*wc.cm`은 collection wire 기준 상대값이다).
- **`cathode`** — 반대쪽 cutoff 평면. `[anode, cathode]` 범위 밖의 depo는 drift 계산 전에 제거된다.

순서 규칙(`pdhd/params.jsonnet:63-67`에 명시): **face는 "front"가 먼저 나열된다.** 여기서 "front"는 $x$ 좌표가 더 양(+)의 값을 갖는 쪽을 의미한다. 어떤 volume에서 한쪽 면이 존재하지 않거나 무시되는 경우(예: cryostat 벽 쪽을 향한 one-sided anode) 해당 face는 `null`이다. `pdhd/params.jsonnet`은 벽을 향한 쪽을 `null`로 두지만, `pdhd/simparams.jsonnet`은 동일한 `det.volumes` 블록을 재정의하면서 각 anode의 양쪽 face를 모두 채운다(시뮬레이션에서는 실제로 계측된 쪽뿐 아니라 cryostat 전체 volume도 고려해야 하기 때문).

## 5. `params.jsonnet` vs `simparams.jsonnet`: 저장소 전반의 관례

시뮬레이션을 지원하는 `pgrapher/experiment/` 하위의 모든 experiment 디렉터리(`pdsp`, `dune-vd`, `dunevd-crp2`, `dune10kt-1x2x6`, `iceberg`, `dune-vd-coldbox`, `pdhd`, `icarus`, `protodunevd`, `sbnd`, `uboone`, `pcbro-50liter`)가 이 두 파일을 동일한 방식으로 짝지어 놓는다 — 이는 PDHD만의 특이 사항이 아니라 저장소 전반의 관례다.

- **`params.jsonnet`** — 검출기 실측/운영 파라미터: 실제 기하 구조(GDML/측량 값에서 유도되며 주석에 출처가 남아 있음), nominal `daq`/`adc`/`elec` 설정, 실제 wire-geometry 및 field-response 데이터를 가리키는 `files`. 원칙적으로 실제 데이터 처리와 시뮬레이션 양쪽 모두의 출발점으로 쓰일 수 있다.
- **`simparams.jsonnet`** — `local base = import ".../params.jsonnet"; base { ... }` 형태로, 실제로 시뮬레이션 작업을 *실행*하는 데 필요한 것만 추가한다: `sim.fixed = true`(LArSoft 스타일의 fixed-time 모드) 강제, cryostat 쪽 volume까지 포함하도록 `det.volumes` 재정의(계측된 anode face가 없는 영역에서도 depo를 올바르게 추적/제거하기 위함), `sim.continuous`/`sim.fluctuate` 플래그, detector-response 변화를 다루는 블록들(PDHD의 `sys_status`, `sys_resp`, `rc_resp` — RC/short-recovery response 형태 조정. 기본값은 `sys_status: false`로 꺼져 있음).

이렇게 분리해 두면 하나의 `params.jsonnet`을 여러 하위 목적(실데이터 reco 파라미터 vs. 시뮬레이션 파라미터)의 base로 재사용할 수 있어, 공유되는 기하/전자장비 수치를 중복 기술할 필요가 없다. `simparams.jsonnet`은 시뮬레이션에 특별히 필요한 부분만 추가로 감당하면 된다.

## 6. 파생/계산 필드와 override 전파

뒤에 나오는 필드가 앞의 필드를 `self`/`$`로 참조하는 경우가 많기 때문에, 자식 파일에서의 override 하나가 해당 파생 필드를 직접 건드리지 않아도 자동으로 그 값에 전파될 수 있다.

- 범용 base: `elec.fields.drift_dt = self.start_dx / $.lar.drift_speed`, `elec.fields.nticks = wc.roundToInt(self.drift_dt / $.daq.tick)`. 상위 어디에서든 `lar.drift_speed`를 override하면 `drift_dt`와 `nticks` 둘 다 재계산된다.
- 범용 base: `sim.ductor.nticks = $.daq.nticks + $.elec.fields.nticks`, `sim.ductor.start_time = $.daq.start_time - $.elec.fields.drift_dt`.
- PDHD의 `params.jsonnet`은 `sim.ductor`/`sim.reframer`를 범용 공식에 의존하지 않고 *통째로 교체*한다. 서로 다른 유도 방식이 필요하기 때문이다(`response_time_offset = $.det.response_plane / $.lar.drift_speed`로 먼저 계산한 뒤 `response_nticks = wc.roundToInt(response_time_offset / $.daq.tick)`). 이는 자식이 값이 아니라 *공식 자체*를 override하는 경우로, 범용 버전이 "field-response drift 시간"(`elec.fields.drift_dt`, `start_dx` 기반)과 PDHD 고유의 `det.response_plane` 기반 타이밍을 혼동하고 있었기 때문이다.

여기서 알 수 있는 일반 규칙: 하위 공식이 여전히 유효하다면 상위 *입력값*(예: `lar.drift_speed`)만 override하는 것으로 충분하다. 하지만 자식의 유도 로직 자체가 다르다면 *하위 객체 전체*(`sim: super.sim { ductor: {...} }`)를 override해야 한다.

## 7. 이 프로젝트가 실제로 사용하는 override 예시

- `elecGain` ext-var: `pdhd/params.jsonnet`의 `elecs[n].gain`은 `std.extVar("elecGain")`을 읽으며, 숫자형 ext-code 값과 JSON 문자열 값을 모두 받아들인다(`std.parseJson` 폴백). 덕분에 동일한 설정 파일을 `wire-cell -V elecGain=7.8`(문자열)로도, `--ext-code elecGain=7.8`(숫자, 예: `dunesw`에서 전달)로도 구동할 수 있다.
- `files.noise`는 하드코딩이 아니라 계산된 값이다: `params.jsonnet` 상단에 정의된 `local` 함수 `pdhd_noise($.elec.gain)`이 설정된 FE gain을 두 가지 알려진 noise-spectra 파일(7.8 또는 14 mV/fC) 중 하나로 매핑하며, 그 외의 gain 값에는 `error(...)`를 호출한다. 잘못 매칭된 spectrum을 조용히 불러오는 대신 의도적으로 즉시 실패시키는 방식이다.
- `lar.drift_speed`는 `pdhd/params.jsonnet:117`에서 `1.56*wc.mm/wc.us`로 override되어 있으며, *왜* 그렇게 했는지(`np04hd-garfield-6paths-mcmc-bestfit.json.bz2`에 내장된 `drift_speed`와 일치시키기 위함)를 인라인 주석으로 남겨 두었다. 이는 이 파일들 전반에서 "값만이 아니라 이유를 기록하는" 스타일의 한 예다.

## 관련 문서

- [wirecell_sim_field_reference.md](wirecell_sim_field_reference.md) — 이 문서 3/6절에서 다룬 `sim` 네임스페이스만 따로 떼어, 필드별 설명과 PDHD 최종 계산값을 상세히 정리한 하위 문서.
- [wires_geometry_walkthrough.md](wires_geometry_walkthrough.md) — 이 문서에서 다룬 params/simparams 체인과는 별개로, 이 프로젝트의 `utils/wires.py`가 `files.wires`가 가리키는 wire-geometry 파일을 어떻게 소비하는지 다룬다.
- [geometry/wirecell_sensitive_volume.md](geometry/wirecell_sensitive_volume.md) — 이 문서의 4절에서 설명한 `det.volumes`/`faces`의 sensitive-volume 경계를 wire store JSON 및 `AnodePlane.cxx`와 교차 검증한다.
