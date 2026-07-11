# Depo(Deposition) in Wire-Cell Context
## 요약
Wire-Cell Toolkit(WCT)에서 "depo"(deposition, 에너지/전하 침착점)가 무엇인지, C++ 코드에서 어떤 데이터로 표현되는지, `.npz` 파일에 어떤 형식으로 저장되는지, 그리고 WCT job graph 안에서 생성부터 소비까지 어떻게 흘러가는지를 정리한 참고 문서다.

`wire-cell-python`의 파이썬 패키지 `wirecell.gen`은 이 문서가 다루는 C++ depo 파이프라인의 입출력(`.npz`) 형식을 그대로 읽고 쓰는 소비자/생산자다.
depo를 생성하거나 검사하려면 `wirecell-gen` CLI를 사용하거나, WCT job graph(Jsonnet)에서 아래 표에 나온 컴포넌트 이름을 노드로 배치한다.

Source root:
- 인터페이스 정의: `wire-cell-toolkit/iface/inc/WireCellIface/IDepo*.h`
- 공용 구현체: `wire-cell-toolkit/aux/{inc/WireCellAux,src}/*Depo*`
- depo를 다루는 컴포넌트 본체: `wire-cell-toolkit/gen/{inc/WireCellGen,src}/*Depo*`
- 파일 입출력(`.npz`) 컴포넌트: `wire-cell-toolkit/sio/{inc/WireCellSio,src}/*Depo*`

## 1. depo란 무엇인가
depo는 매질(액체 아르곤) 안의 한 지점에서 순간적으로 발생한 이온화 전하 침착(charge deposition)을 나타내는 최소 단위 데이터다.
물리적으로는 하전 입자가 검출기 내부를 지나가며 남긴 궤적을, 아주 짧은 길이의 스텝으로 잘게 나눈 각 조각에 대응한다.
WCT 자신은 depo를 생성하는 입자 수송 시뮬레이션(Geant4, LArSoft 등)을 포함하지 않으며, depo는 보통 그 상류 시뮬레이션의 산출물이거나 이 문서에서 다루는 `TrackDepos` 같은 테스트용 생성기의 산출물이다.
WCT 안에서 depo는 검출기 반응 시뮬레이션(전자 표류/확산, 전기장 응답 컨볼루션)의 입력이 되어 최종적으로 전자공학 신호(ADC 파형, `IFrame`)로 변환되거나, 평가 목적으로 신호와 비교 가능한 "참값(true signal)" 파형으로 직접 변환된다.
즉 depo는 "진짜 물리량"이고, `IFrame`은 그 물리량이 검출기를 거쳐 관측된 결과다.

## 2. C++ 데이터 모델

### 2.1 `IDepo` — depo 하나를 표현하는 인터페이스
정의 위치는 `iface/inc/WireCellIface/IDepo.h`다.
`IDepo`는 순수 가상 인터페이스이며 다음 정보를 노출한다.

| 접근자             | 의미                                       |
| --------------- | ---------------------------------------- |
| `pos()`         | 침착 위치 (`Point`, x/y/z)                   |
| `time()`        | 절대 기준 시각 대비 침착 시각 (초 단위 WCT 내부 단위계)      |
| `charge()`      | 침착된 전하량 (전자 개수 단위)                       |
| `energy()`      | 침착된 에너지 (MeV 단위)                         |
| `id()`          | Geant4 트랙 ID                             |
| `pdg()`         | Geant4 PDG 코드                            |
| `prior()`       | 이 depo의 "이전 단계" depo에 대한 포인터(있다면)        |
| `extent_long()` | 표류(drift) 방향의 반치폭(주로 가우시안 시그마), 확산 전에는 0 |
| `extent_tran()` | 표류에 수직인(pitch) 방향의 반치폭, 확산 전에는 0         |
`prior()`가 핵심이다.

depo는 파이프라인을 지나며 값이 바뀌는 것이 아니라, 매 단계마다 새 `IDepo` 객체가 만들어지고 그 객체가 `prior()`로 이전 단계 depo를 가리키는 체인을 형성한다.
예를 들어 표류(drift) 전 원본 depo가 있고, `Drifter`가 그 depo를 확산·흡수 처리해 새 depo를 만들면, 새 depo의 `prior()`는 원본 depo를 가리킨다.
`IDepo.h`가 제공하는 `depo_chain(IDepo::pointer)` 헬퍼는 이 `prior()` 체인을 따라가며 depo 벡터(최신 것이 맨 앞)로 풀어준다.
`IDepoDriftCompare`/`ascending_time`/`descending_time`은 depo를 시간(및 표류 방향 위치) 기준으로 정렬하기 위한 비교자다.

### 2.2 `SimpleDepo` — 실제로 쓰이는 구현체
정의 위치는 `aux/inc/WireCellAux/SimpleDepo.h`, `aux/src/SimpleDepo.cxx`다.
`SimpleDepo`는 `IDepo`가 요구하는 모든 필드를 생성자 인자로 받아 그대로 저장하는 "자료 뭉치" 클래스다.
사실상 이 저장소에서 다루는 모든 depo 생성/변환 컴포넌트(`TrackDepos`, `Drifter`, `NumpyDepoTools` 등)가 새 depo를 만들 때 이 클래스를 사용한다.
`set_prior()`는 `IDepo` 공개 인터페이스에는 없는, `SimpleDepo`에만 있는 메서드로, 파일에서 depo를 복원할 때 나중에 prior 관계를 채워 넣는 데 쓰인다([[wirecell_depo_reference#3.2 `gen`/`child` — prior 체인을 평면화하는 방법|§3.2]] 참고).

### 2.3 `IDepoSet` — depo 여러 개를 묶은 집합
정의 위치는 `iface/inc/WireCellIface/IDepoSet.h`다.
`IDepoSet`은 `ident()`(집합 식별자)와 `depos()`(`IDepo::shared_vector`, depo 벡터에 대한 공유 포인터)만 노출하는 얇은 인터페이스다.
개별 `IDepo` 스트림을 다루는 컴포넌트와, `IDepoSet`(depo 묶음) 단위로 다루는 컴포넌트가 WCT 안에 공존한다.
전자는 depo 하나하나가 job graph의 그래프 엣지를 타고 흐르고, 후자는 한 이벤트(또는 한 시간 구간)에 속하는 depo 전체가 한 번에 흐른다.
구현체는 `aux/inc/WireCellAux/SimpleDepoSet.h`의 `SimpleDepoSet`이며, `IDepoSet`과 마찬가지로 단순히 `ident`와 `IDepo::vector`를 감싸는 값 객체다.

## 3. 파일 저장 포맷 (`.npz`)
depo 스트림을 디스크에 저장하고 다시 읽어들이는 실제 구현은 `sio/` 모듈에 있다.
- 저장: `Sio::NumpyDepoSaver`(`sio/src/NumpyDepoSaver.cxx`, 인터페이스 `IDepoFilter`) 담당
- 로드: `Sio::NumpyDepoTools::load`(`sio/src/NumpyDepoTools.cxx`, `NumpyDepoLoader`/`NumpyDepoSetLoader`/`DepoFileSource`가 사용)가 담당

### 3.1 배열 두 개의 쌍
한 depo 집합(예: 한 이벤트, 또는 `NumpyDepoSaver`가 EOS를 볼 때까지 모은 한 묶음)은 numpy 배열 두 개의 쌍으로 저장된다.

- `depo_data_<N>` — `(n, 7)` float 배열.
	- 열 순서는 `t, q, x, y, z, L, T`이며 각각 시각, 전하(전자 개수), 위치 x/y/z, `extent_long`, `extent_tran`에 대응한다.
- `depo_info_<N>` — `(n, 4)` int 배열.
	- 열 순서는 `id, pdg, gen, child`다.
	-   `id`/`pdg`는 `IDepo::id()`/`IDepo::pdg()`를 그대로 옮긴 값이다.

`<N>`은 저장 호출 횟수(=depo 집합 인덱스)이며, `wirecell.gen.depos.load(depofile, index=N, ...)`의 `index` 인자가 이 값을 가리킨다.

### 3.2 `gen`/`child` — prior 체인을 평면화하는 방법
`IDepo`의 `prior()` 체인은 포인터 기반 트리 구조라 그대로는 배열에 담을 수 없기에 `Aux::DepoTools::fill`(`aux/src/DepoTools.cxx`)를 통해 평면화한다.

저장 대상 depo 각각에 대해 `prior()`를 재귀적으로 따라가며, depo 자신은 `gen=0`으로, 그 prior는 `gen=1`로, prior의 prior는 `gen=2`로 매겨 하나의 긴 배열에 순서대로 이어붙인다.
이때 `child`는 "자신이 prior인 그 자식 depo가 배열에서 몇 번째 행인지"를 가리키는 역참조 인덱스다.
로드 시(`NumpyDepoTools::load`)에는 이 과정이 반대로 실행된다.

각 행을 depo 객체로 복원하면서, `gen > 0`인 행(=누군가의 prior)은 최종 반환 목록에 넣지 않고 보류해 두었다가, `info(ind, 3)`(=child 인덱스)이 가리키는 자식 depo의 `set_prior()`를 호출해 연결한다.
결과적으로 파일에서 다시 읽은 depo 목록은 `gen=0`인(=가장 나중 단계, "가장 젊은") depo들만 최상위로 노출되고, 그 이전 단계 depo들은 `prior()` 체인을 통해서만 접근 가능하다.

`wire-cell-python`의 `wirecell.gen.depos.load(..., generation=g)`는 `info`의 `gen` 컬럼이 `g`와 일치하는 행만 골라내는 방식으로 이 평면화된 배열에서 원하는 세대를 되찾는다.

### 3.3 `wire-cell-python` 에서의 사용
이 `.npz` 포맷은 C++과 파이썬 양쪽에서 공통으로 읽고 쓰는 유일한 depo 교환 형식이다.

반대로 depo를 새로 만들어 이 포맷으로 저장하는 것은([[wirecell_depo_reference#4|§4]] 참고) WCT job graph 안의 `NumpyDepoSaver`/`DepoFileSink` 컴포넌트, 또는 오프라인으로 `wirecell-gen depo-lines` 등 CLI 명령을 실행해 만드는 두 가지 경로가 있다.

  
## 4. WCT 파이프라인 안에서 depo의 생애주기
depo는 WCT job graph 안에서 대체로 다음 순서로 흘러며 각 단계는 실제로 하나의 고정된 파이프라인이 아니라, job graph 구성에 따라 선택적으로 조합되는 컴포넌트들의 모음이다.
```

[생성]  ->  [표류/드리프트]  ->  [묶기·필터링·팬아웃]  ->  [소비: 신호화 / 저장 / 검사]

```

### 4.1 생성 (depo source)
`Gen::TrackDepos` (`gen/src/TrackDepos.cxx`, 인터페이스 `IDepoSource`) 
- 설정에 주어진 직선 트랙(`Ray`, 시작 시각, 전하)을 따라 `step_size` 간격으로 점을 찍어 depo를 생성하는 테스트용 소스다.
-   전하가 양수로 주어지면 트랙 길이에 걸쳐 균등 분배하고, 음수면 그 값을 스텝당 전하로 그대로 쓴다. 
- `group_time`이 양수면 생성된 depo 스트림을 그 시간 간격으로 잘라 EOS(`nullptr`)를 끼워 넣어 청크로 나눈다.

`Sio::DepoFileSource`/`NumpyDepoLoader`/`NumpyDepoSetLoader`(`sio/`) 
- 이미 [[wirecell_depo_reference#3|§3]]의 `.npz` 포맷으로 저장된 depo를 다시 읽어 job graph의 소스로 삼는다.
- Geant4/LArSoft 등 WCT 밖에서 만들어진 depo를 WCT 파이프라인에 주입할 때도 이 경로를 쓴다.

`wirecell-gen` CLI (파이썬, `depo-lines`/`depo-line`/`depo-point`/`depo-sphere`/`linegen`/`detlinegen`/`depo-morse`) 
- job graph 밖에서 오프라인으로 `.npz`/JSON depo 파일을 만드는 방법이다.
- 자세한 내용은 `wire-cell-python`의 해당 패키지 참고

### 4.2 표류/드리프트 (drift)
`IDrifter` (`iface/inc/WireCellIface/IDrifter.h`)
- depo 하나를 입력받아 0개 이상의 depo를 출력하는(`ISourceNode`/`IQueuedoutNode` 계열) 인터페이스다.

`Gen::Drifter` (`gen/src/Drifter.cxx`)
- 실제 표류 물리를 구현하는 핵심 컴포넌트다.
- depo가 설정된 X축 구간(`xregions`: anode/response/cathode 경계) 중 어디에 속하는지 판정하고, 표류 거리(depo 위치와 response plane 사이 거리)만큼 걸리는 시간 `dt`를 계산한다.
- 종방향/횡방향 확산 `extent_long`/`extent_tran`에 제곱합으로 더해 키운다.
- 전자 수명(`lifetime`)에 따른 흡수로 전하를 줄이고, `fluctuate=true`면 이항분포로 흡수량을 요동시킨다.
- 결과로 새 `SimpleDepo`를 만들어(원본을 `prior()`로 연결) response plane 위치로 이동시키고, 시간순으로 정렬해 출력 큐에 채운다(`flush`/`flush_ripe`).
- `Drifter`를 거친 depo는 실좌표가 아니라 "표류가 끝나 response plane 위에 투영된" 위치와 시각을 갖는다.

`Gen::DepoSetDrifter` (`gen/src/DepoSetDrifter.cxx`)
- `IDrifter`를 `IDepoSetFilter` 인터페이스로 감싸는 어댑터다.
- `IDepoSet` 하나(=depo 벡터)를 받아 그 안의 depo를 하나씩 내부 `m_drifter`(예: `Gen::Drifter`)에 흘려보내고, 끝에 EOS를 추가로 흘려보내 내부에 남은 depo까지 모두 비운(flush) 뒤, 그 결과를 다시 `IDepoSet`으로 묶어 반환한다.
- 주석에 명시된 대로 정렬 유지를 위해 다소 비효율적인 구현이며, Pgrapher 실행 시 순수 per-depo drifter를 직접 쓰는 것보다 빠르다는 실용적 이유로 존재한다.

`Gen::WireBoundedDepos`/`Gen::TimeGatedDepos`(`gen/inc/WireCellGen/`)
- `IDrifter`와 같은 인터페이스 형태를 재사용하지만 실제로는 표류를 하지 않고 depo를 선택(select)만 하는 컴포넌트다.
- 전자는 depo가 표류 방향(음의 X축)으로 "착지"하는 와이어 번호 구간으로, 후자는 시간 구간으로 accept/reject 모드를 걸러낸다.

### 4.3 묶기 · 필터링 · 팬아웃 (개별 depo ↔ depo 집합)
`Gen::DepoBagger` (`gen/src/DepoBagger.cxx`, 인터페이스 `IDepoCollector`)
- 개별 `IDepo` 스트림을 받아 EOS가 올 때까지 모은 뒤 하나의 `IDepoSet`(`SimpleDepoSet`)으로 묶어 출력한다.
- `gate`가 설정되면 그 시간 구간 안의 depo만 담는다.

 `Gen::DepoChunker` (`gen/inc/WireCellGen/DepoChunker.h`, 인터페이스 `IDepoCollector`) 
 - depo가 시간창(윈도) 밖으로 벗어날 때마다 그 시점까지 모인 depo로 하나의 집합을 만들고 창을 앞으로 전진시키는, "연속 시뮬레이션"을 위한 슬라이딩 윈도 방식 수집기다.
- `Gen::DepoFanout`/`Gen::DepoSetFanout` (인터페이스 `IDepoFanout`/`IDepoSetFanout`) 
- depo(집합) 하나를 설정된 배수(multiplicity)만큼 그대로 복제해 여러 출력 포트로 내보낸다.
- 여러 anode(APA)에 같은 depo를 동시에 공급해야 할 때 쓰인다.

`Gen::DepoMerger` (`gen/src/DepoMerger.cxx`, 인터페이스 `IDepoMerger`) 
- 개별 depo 스트림 두 개를 시각 순으로 병합해 하나의 스트림으로 합친다.

`Gen::DepoSetFilter`/`Gen::DepoSetFilterYZ` (인터페이스 `IDepoSetFilter`) 
- 설정된 바운딩 박스(`BoundingBox`) 안에 있는 depo만 통과시킨다.
- 주로 `DepoFanout`으로 복제된 depo 집합을 각 APA의 감지 영역(sensitive volume)에 맞게 잘라낼 때 쓰인다.

`Gen::DepoSetRotate`/`Gen::DepoSetScaler` (인터페이스 `IDepoSetFilter`)
- 좌표계 변환 어댑터다.
- 전자는 LArSoft 등 상류 시뮬레이션이 X축이 아닌 방향을 표류 방향으로 쓸 때 축 전치/부호 반전으로 WCT 내부 관례(X축 표류)에 맞추고, 후자는 `IScaler`를 depo 집합 단위로 적용하는 `DepoSetDrifter`와 동일한 패턴의 어댑터다.

`Gen::DeposOrBust` (인터페이스 `IDepos2DeposOrFrame`)
- depo 집합이 비어 있지 않으면 그대로 통과시키고, 비어 있으면 대신 완전히 빈 `IFrame`을 만들어 다른 포트로 내보내는 분기(branch) 컴포넌트다.
- depo가 없는 이벤트에 대해 신호 시뮬레이션 전체를 실행하는 대신 빈 프레임으로 우회하는 용도다.

### 4.4 소비 (depo → frame / 저장 / 검사)
depo 파이프라인의 최종 출력은 대체로 세 갈래 중 하나다.

1. **검출기 반응 시뮬레이션(전체 시뮬레이션 경로)**

`Gen::DepoTransform` (`gen/src/DepoTransform.cxx`, 인터페이스 `IDepoFramer`, `IDepoSet -> IFrame`)이 이 경로를 담당한다.
anode의 각 face·plane에 대해 그 면의 감지 영역에 속하는 depo만 골라내고(`Aux::sensitive`), `Gen::BinnedDiffusion_transform`으로 각 depo의 전하를 시간(tick)×pitch(wire) 평면 위 가우시안 분포로 표현한 뒤, `Gen::ImpactTransform`이 `IPlaneImpactResponse`(전기장+전자공학 응답)와 컨볼루션해 와이어별 파형을 만든다.
이 파형이 채널에 매핑되어 `SimpleTrace`/`SimpleFrame`으로 조립된다.
즉 물리적으로 가장 현실적인, 노이즈 필터링(NF)·신호처리(SP) 이전의 raw ADC에 대응하는 신호를 만드는 경로다.

2. **참값(true signal) 근사 경로**
`Gen::DepoFluxSplat` (`gen/src/DepoFluxSplat.cxx`, 인터페이스 `IDepoFramer`, 문서 `gen/docs/depofluxsplat.org`)이 이 경로를 담당한다.
`DepoTransform`과 달리 전기장 응답과의 컨볼루션을 생략하고, depo의 표류 확산 시그마에 설정 가능한 추가 스미어링(`smear_long`/`smear_tran`)을 제곱합으로 더한 뒤, 그 결과 가우시안 분포를 와이어·시간 격자에 바로 적분(bin)해 `IFrame`을 만든다. 출력은 sparse(depo별로 별도 trace, 채널·tick이 서로 겹칠 수 있음) 또는 dense(채널별로 하나의 trace로 누적) 형태를 고를 수 있다.

문서(`depofluxsplat.org`)는 이 출력을 실제 신호처리 결과와 의미 있게 비교 가능한 참값 신호로 규정하며, `nominal time`(트랙 생성부터 measurement plane 통과까지 걸리는 물리적 시간)과 `acceptance window`(그 nominal time 기준으로 어떤 depo를 받아들일지 정하는 시간창) 개념으로 시간 처리를 설명한다.

3. **파일 저장 / 디버그 검사**
`Sio::NumpyDepoSaver`/`Sio::DepoFileSink`(`sio/`, 인터페이스 `IDepoFilter`)는 [[wirecell_depo_reference#3|§3]]에서 설명한 `.npz` 포맷으로 depo 스트림을 그대로 저장한다.
`WireCell::DumpDepos`(`gen/src/DumpDepos.cxx`, 인터페이스 `IDepoSink`)는 depo를 어디에도 쓰지 않고 개수만 세어 로그로 남기는, 파이프라인 디버깅용 싱크다.

## 5. depo 관련 인터페이스 요약 (`iface/`)
| 인터페이스                 | 흐름                                 | 의미                                                      |
| --------------------- | ---------------------------------- | ------------------------------------------------------- |
| `IDepo`               | -                                  | depo 하나의 값 접근자 (§2.1)                                   |
| `IDepoSet`            | -                                  | depo 벡터 하나의 묶음 (§2.3)                                   |
| `IDepoSource`         | `() -> IDepo`                      | depo 스트림을 생성하는 소스 노드                                    |
| `IDepoSink`           | `IDepo -> ()`                      | depo 스트림을 소비만 하는 싱크 노드                                  |
| `IDepoFilter`         | `IDepo -> IDepo`                   | depo 하나를 받아 depo 하나(또는 없음)를 내는 필터                       |
| `IDrifter`            | `IDepo -> IDepo...` (큐)            | depo 하나를 받아 0개 이상의 depo를 내는 표류/선택기                      |
| `IDepoCollector`      | `IDepo -> IDepoSet...`             | 개별 depo를 모아 depo 집합으로 묶는 노드                             |
| `IDepoFanout`         | `IDepo -> IDepo[N]`                | depo 하나를 N개 출력 포트로 복제                                   |
| `IDepoSetFanout`      | `IDepoSet -> IDepoSet[N]`          | depo 집합을 N개 출력 포트로 복제                                   |
| `IDepoMerger`         | `IDepo,IDepo -> IDepo`             | 두 depo 스트림을 시간순 병합                                      |
| `IDepoSetFilter`      | `IDepoSet -> IDepoSet`             | depo 집합을 받아 집합 하나(변형/필터링됨)를 내는 필터                       |
| `IDepoFramer`         | `IDepoSet -> IFrame`               | depo 집합을 신호 프레임으로 변환 (`DepoTransform`, `DepoFluxSplat`) |
| `IDepos2DeposOrFrame` | `IDepoSet -> IDepoSet` 또는 `IFrame` | depo 집합 유무에 따라 분기 (`DeposOrBust`)                       |
  
## 6. `gen/` 모듈의 depo 관련 컴포넌트 파일 목록
| 파일                                       | 인터페이스                 | 역할                                                                    |
| ---------------------------------------- | --------------------- | --------------------------------------------------------------------- |
| `TrackDepos.cxx`                         | `IDepoSource`         | 직선 트랙을 따라 depo 생성 (§4.1)                                              |
| `Drifter.cxx`                            | `IDrifter`            | 표류 확산/전자수명/시간오프셋 적용 (§4.2)                                            |
| `DepoSetDrifter.cxx`                     | `IDepoSetFilter`      | `IDrifter`를 depo 집합 단위로 어댑팅 (§4.2)                                    |
| `WireBoundedDepos.h`                     | `IDrifter`            | 와이어 착지 구간 기준 선택 (§4.2)                                                |
| `TimeGatedDepos.h`                       | `IDrifter`            | 시간 구간 기준 선택 (§4.2)                                                    |
| `DepoBagger.cxx`                         | `IDepoCollector`      | EOS까지 모아 depo 집합으로 묶기 (§4.3)                                          |
| `DepoChunker.h`                          | `IDepoCollector`      | 슬라이딩 시간창으로 depo 집합 생성 (§4.3)                                          |
| `DepoFanout.cxx`                         | `IDepoFanout`         | 개별 depo 복제 (§4.3)                                                     |
| `DepoSetFanout.h`                        | `IDepoSetFanout`      | depo 집합 복제 (§4.3)                                                     |
| `DepoMerger.cxx`                         | `IDepoMerger`         | 두 depo 스트림 시간순 병합 (§4.3)                                              |
| `DepoSetFilter.h`/`DepoSetFilterYZ.h`    | `IDepoSetFilter`      | 바운딩 박스 기준 필터링 (§4.3)                                                  |
| `DepoSetRotate.h`                        | `IDepoSetFilter`      | 좌표축 전치/스케일 변환 (§4.3)                                                  |
| `DepoSetScaler.h`                        | `IDepoSetFilter`      | `IScaler`를 depo 집합 단위로 어댑팅 (§4.3)                                     |
| `DeposOrBust.h`                          | `IDepos2DeposOrFrame` | 빈 depo 집합을 빈 프레임으로 분기 (§4.3)                                          |
| `DepoTransform.cxx`                      | `IDepoFramer`         | 전기장 응답 컨볼루션 기반 신호화 (§4.4-1)                                           |
| `DepoFluxSplat.cxx`                      | `IDepoFramer`         | 가우시안 스미어링 기반 참값 신호화 (§4.4-2)                                          |
| `DepoPlaneX.h`                           | (저수준 유틸)              | 균일 표류속도로 특정 X 평면까지 depo를 드리프트/정렬하는 자료구조로, `Drifter`류 컴포넌트의 저수준 구현에 사용 |
| `DumpDepos.cxx` (top-level `WireCell::`) | `IDepoSink`           | depo 개수를 세는 디버그 싱크 (§4.4-3)                                           |
  
`sio/` 모듈의 파일 입출력 컴포넌트는 다음과 같다.

| 파일                                                            | 인터페이스          | 역할                                                                 |
| ------------------------------------------------------------- | -------------- | ------------------------------------------------------------------ |
| `NumpyDepoSaver.cxx`                                          | `IDepoFilter`  | 개별 depo 스트림을 `.npz`로 저장 (§3, §4.4-3)                               |
| `DepoFileSink.cxx`                                            | `IDepoFilter`류 | depo 집합을 파일로 저장                                                    |
| `NumpyDepoTools.cxx`                                          | (내부 유틸)        | `.npz`의 `depo_data_N`/`depo_info_N`을 읽어 `IDepo::vector`로 복원 (§3.2) |
| `NumpyDepoLoader.h`/`NumpyDepoSetLoader.h`/`DepoFileSource.h` | `IDepoSource`류 | 저장된 depo 파일을 다시 job graph 소스로 로드 (§4.1)                            |
  


