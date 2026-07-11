# `wirecell.gen` Reference

## Summary

`wire-cell-python/wirecell/gen/` (`wirecell-gen` CLI 패키지)에 구현된 함수/클래스/CLI 명령을 모듈 단위로 정리한 참고 문서다.
Wire-Cell Toolkit(WCT) 시뮬레이션 입력(depo)을 만들거나, 시뮬레이션 산출물(frame/depo)을 검사 및 시각화하거나, 노이즈/신호 폭 관련 프로토타입 계산을 수행하는 코드가 모여 있다.

## 패키지 구성

| 파일            | 역할                                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `depos.py`    | depo 파일(.npz/.json) 입출력, 단위 변환, 이동/센터링, 2D 히스토그램/스캐터 플롯.                                                                       |
| `depogen.py`  | 무작위 방향의 라인 트랙(`lines`), 구면 껍질(`sphere`) 패턴의 depo 생성 (레거시 API).                                                                 |
| `linegen.py`  | 검출기 좌표계·와이어 평면 각도를 반영한 라인 트랙 depo 생성 (`TrackConfig` 기반, 최신 API).                                                               |
| `morse.py`    | "morse" 패턴(각 와이어 평면을 겨냥한 격자형 짧은 트랙) depo 생성과, 그 결과 신호에서 폭(피크)을 측정하는 분석 함수.                                                     |
| `noise.py`    | 노이즈 스펙트럼 프로토타입 (`Spec` 클래스: 보간/외삽/앨리어싱/리샘플링). `NoiseTools`(C++)의 파이썬 시제품.                                                      |
| `sim.py`      | `.npz`로 저장된 시뮬레이션 frame/depo를 읽어 시각화하는 `Frame`/`Depos` 클래스 (모듈명이 다소 부정확하다고 자체 주석에 명시됨).                                        |
| `plots.py`    | `NumpyFrameSaver` 산출물을 그리는 독립 실행형 스크립트 (레거시, `plots/numpysaver.py`와 거의 중복).                                                    |
| `plots/`      | `wirecell-gen`의 서브플롯 헬퍼 서브패키지: `morse.py`(`width_plots`), `numpysaver.py`.                                                     |
| `test/`       | pytest 테스트(`test_linegen.py`, `test_noise.py`)와 독립 실행 플롯 스크립트(`plot_g4tuple.py`, `plot_impactzipper.py`, ROOT 기반, WCT 자체 개발용). |
| `__main__.py` | `wirecell-gen` Click CLI. 위 모듈 전부를 서브커맨드로 연결한다                                                                                 |
| `__init__.py` | 비어 있음.                                                                                                                         |

## CLI 명령 (`wirecell-gen ...`)

전부 `__main__.py`에 정의되어 있고 `wirecell-gen` Click 그룹 아래 묶여 있다.
공통 유틸 함수 `unitify`/`unitify_parse`(`wirecell.util.functions`)로 `"1*mm"` 같은 단위 표현식 문자열을 파싱한다.

`wirecell-gen <command> --help`로 각 명령의 전체 옵션을 확인할 수 있다.
위 표의 옵션 표기는 축약한 것이다.

| 명령                                            | 기능                                                                                                                                                                                          |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unitify-depos IN OUT`                        | 단위 없는 JSON depo 파일에 지정 단위를 적용해 WCT 내부 단위계 파일로 변환 (`depos.apply_units`).                                                                                                                     |
| `depos-bb FILES...`                           | `.npz` depo 파일들의 각 컬럼(t,q,x,y,z,L,T) 최소/최대값(bounding box)을 출력.                                                                                                                              |
| `shift-depos -c/-o IN OUT`                    | `.npz` depo를 지정한 중심으로 옮기거나(`-c`) 오프셋만큼 이동(`-o`).                                                                                                                                            |
| `move-depos -c/-o IN OUT`                     | JSON depo 파일에 대해 같은 이동/센터링을 수행 (`depos.center`/`depos.move`).                                                                                                                               |
| `plot-depos -p <plot> IN`                     | `depos.py`의 `plot_*` 함수 중 하나(또는 여러 개, `-p` 반복 가능)를 실행해 페이지로 저장. `-s/--speed`를 주면 `x = speed*(t+t0)`로 드리프트 좌표를 계산.                                                                           |
| `plot-test-boundaries -t T1 T2 NPZ PDF`       | `sim.Frame`/`sim.Depos`로 `test_boundaries.jsonnet` 결과를 페이지별로 플롯.                                                                                                                            |
| `plot-sim IN OUT`                             | `sim.Frame`/`sim.Depos`로 임의의 시뮬레이션 `.npz`/아카이브를 프레임 또는 depo 관점에서 플롯 (`--ticks`로 틱/시간 축 선택, `-c`/`-b`로 채널 그룹 지정).                                                                            |
| `depo-morse -o OUT`                           | 지정한 검출기 와이어 기하구조에서 `morse.generate()`로 "morse" 패턴 depo 생성.                                                                                                                                  |
| `morse-summary -o OUT SIGNAL`                 | `morse.frame_peaks()`로 신호 폭을 측정해 JSON으로 요약 저장.                                                                                                                                              |
| `morse-splat -o OUT SUMMARY`                  | morse 요약으로부터 `DepoFluxSplat` 설정에 맞는 `smear_long`/`smear_tran`(JSON) 또는 org-table 텍스트를 생성.                                                                                                   |
| `morse-plots -o OUT SIGNAL`                   | `plots/morse.py`의 `width_plots()`로 진단 플롯 PDF 생성. `-S`로 기존 요약 JSON 재사용 가능.                                                                                                                   |
| `depo-line -f/-l -o OUT`                      | 두 점 사이 단일 직선 트랙 depo 생성 (`depogen`을 거치지 않는 인라인 구현).                                                                                                                                         |
| `depo-lines -t/-s -o OUT`                     | 경계 상자 안 다중 무작위 트랙 depo 세트 생성 (`depogen.lines`). `--track-info`로 트랙 메타데이터를 별도 JSON으로 뺄 수 있음.                                                                                                 |
| `depo-point -n -t -p -o OUT`                  | 단일 점 depo(전자 수 `-n`, 위치 `-p`, 시간 `-t`) 생성.                                                                                                                                                  |
| `depo-sphere -r -o OUT`                       | 경계 상자 안 무작위 위치를 중심으로 한 구형 껍질 depo 패턴 생성 (`depogen.sphere`).                                                                                                                                 |
| `frame-stats -o OUT` (프레임 입력 필요)              | 평면별(U/V/W) 시간/채널 합산 파형의 평균/RMS/이상치(outlier) 개수 통계를 JSON으로 출력.                                                                                                                               |
| `linegen --phi -c -o OUT`                     | 와이어 평면 회전각(`--phi`)을 직접 지정해 라인 트랙 depo와 메타데이터 생성 (`linegen.generate_and_save_line_track`). `linegen_args` 데코레이터로 `-e/-S/-T/--theta_y/--theta_xz/-l/--track-speed/--angle-coords` 공통 옵션을 공유. |
| `detlinegen -d --apa --plane --offset -o OUT` | 실제 검출기 이름/APA/평면을 지정해 그 기하구조 기준으로 라인 트랙 depo 생성 (`linegen.generate_and_save_line_track_in_detector`).                                                                                       |

# Detail Explanation

## `depos.py` — depo 파일 입출력과 기본 변환

* **`load(depofile, index=0, generation=0)`**
    * 파일 경로 또는 이미 로드된 `ario` 딕셔너리를 받아 `depo_data_<index>`/`depo_info_<index>`를 읽고, `info`의 `gen` 컬럼이 주어진 `generation`과 일치하는 행만 골라 `todict()`로 변환해 반환한다.
    * 배열이 `(7, n)` 형태로 저장돼 있으면 자동으로 전치(`.T`)해서 `(n, 7)`로 맞춘다.
    * 해당 `index`나 `generation`이 없으면 `KeyError`를 던진다.
* **`stream(depofile, generation=0)`**
    * `load()`를 `index=0,1,2,...` 순으로 반복 호출하는 제너레이터다.
    * `KeyError`가 나오면 멈춘다.
    * 파일 하나에 여러 depo 세트가 들어 있을 때 순회하는 용도다.
* **`todict(depos)`**
    * `(n, 7)` 배열을 `{'t':..., 'q':..., 'x':..., 'y':..., 'z':..., 'L':..., 'T':...}` 형태의 딕셔너리(컬럼별 1D 배열)로 바꾼다.
* **`remove_zero_steps(depos)`**
    * 딕셔너리 형태의 depos에서 스텝 크기(`'s'` 키)가 0인 행을 제거한다.
    * *(주: 현재 `columns`에는 `'s'`가 없어 이 함수는 구버전 컬럼 스키마를 전제로 한 듯 보인다.)*
* **`apply_units(depos, distance_unit, time_unit, energy_unit, step_unit=None, electrons_unit="1.0")`**
    * 단위가 없는 raw 배열에 `wirecell.units` 표현식으로 지정한 단위를 곱해 WCT 내부 단위계로 변환한 새 배열을 반환한다.
    * CLI `unitify-depos`가 이 함수를 감싼다.
* **`dump(output_file, depos, jpath="depos")`**
    * depo 배열을 JSON(`.json`) 또는 bz2 압축 JSON (`.json.bz2`)으로 저장한다.
    * bz2가 plain JSON 대비 5~10배 작다는 주석이 있다.
* **`move(depos, offset)` / `center(depos, point)`**
    * 전체 depo 집합을 벡터만큼 평행이동하거나, 전하 미가중 평균 위치가 주어진 점에 오도록 이동한다.
* **플롯 함수들** *(전부 `matplotlib` 기반이며 저장(`savefig`)은 호출자(CLI의 `image_output` 데코레이터)가 담당한다.)*
    * `plot_qxz` / `plot_qxy` / `plot_qzy` / `plot_qxt` / `plot_qzt`: `_abc_hist()`를 통해 위치 두 축을 cm(또는 시간축은 us) 단위로 비닝한 2D 히스토그램에 전하(`|q|`)를 가중치로 채워 `imshow`한다.
    * `plot_t` / `plot_x`: 시간/x 위치의 1D 히스토그램(가중치 없음, 단순 카운트).
    * `plot_xzqscat` / `plot_xyqscat` / `plot_tzqscat` / `plot_tyqscat`: `_plot_abc()`를 통해 `scatter`로 점별 전하를 색상(`colorbar`)으로 표시한다.

## `depogen.py` — 레거시 트랙/구면 depo 생성기

`linegen.py`보다 오래된 단순한 API 구성을 가지며, CLI의 `depo-lines`/`depo-sphere` 명령이 이 모듈을 사용한다.

* **`lines(tracks, sets, p0, p1, time, eperstep, step_size, track_speed)`**
    * 경계 상자 `[p0, p1]` 안에서 위치와 방향이 균등분포로 무작위 추출된 직선 트랙을 `tracks`개씩 묶어 `sets`개의 depo 세트를 생성한다.
    * 각 트랙은 경계 상자 벽까지 연장한 뒤 `step_size` 간격으로 점을 찍고, `track_speed`로 점 사이 시간 간격을 정한다.
    * `time`이 스칼라면 모든 트랙이 같은 시작 시각을, 2-튜플이면 그 범위에서 균등분포로 뽑은 시작 시각을 갖는다.
    * 반환값은 `depo_data_<i>`/`depo_info_<i>`/`track_info_<i>`(트랙별 시작/끝점, 시간, 스텝, 전하 메타데이터, `track_info_types` dtype) 키를 가진 딕셔너리다.
* **`sphere(origin, p0, p1, radius=100*units.cm, eperstep=5000, step_size=1*units.mm)`**
    * 경계 상자 안에서 무작위 방향을 뽑아 `origin`에서 `radius`만큼 떨어진 지점에 depo를 배치해, 인위적인 구형 껍질 패턴을 만든다.
    * 점 개수는 `0.3*(radius/step_size)**2`로 어림잡는다.

## `linegen.py` — 검출기 좌표계 기반 라인 트랙 생성기 (최신 API)

`depogen.lines`보다 구조화된 버전으로, 와이어 평면 회전각과 전역 좌표계 사이 변환을 명시적으로 다룬다.
`TrackConfig`(dataclass)로 파라미터를 묶고, 결과 메타데이터를 `TrackMetadata`(dataclass) 형태로 JSON 저장한다.
CLI의 `linegen`/`detlinegen` 명령이 이 모듈을 쓴다.

* **`TrackConfig`**
    * `length`, `t0`, `eperstep`, `step_size`, `track_speed`, `theta_y`, `theta_xz`, `global_angles`(각도가 전역 좌표계 기준인지 와이어 평면 좌표계 기준인지) 필드를 갖는 설정 dataclass다.
    * `from_dict`/`to_dict`로 JSON과 상호 변환이 가능하다.
* **`generate_line_track_depos(p0, p1, t0, eperstep, step_size, track_speed)`**
    * 두 점 사이를 균등 간격으로 나눠 시간/위치/전하 배열 `(times, points, charges)`를 반환하는 저수준 함수다 (`depogen.lines`의 단일-트랙 로직과 동등).
* **`midpoint_length_direction_to_endpoints(p_mid, length, direction)`**
    * 중점, 길이, 방향으로부터 트랙 양 끝점 `(p0, p1)`을 계산한다.
* **`tpc_angles_to_direction(theta_y, theta_xz)` / `direction_to_tpc_angles(direction)`**
    * LArTPC 각도 관례(`arXiv:1802.08709` Figure 8)와 방향코사인 벡터 `(cos_x, cos_y, cos_z)` 사이의 상호 변환을 수행한다.
    * 후자는 각도를 180도 모듈로 반환한다.
* **`plane_yy_to_rotation_matrix(plane_yy)`**
    * 와이어 평면의 Y축 회전각으로부터 좌표 회전 행렬을 생성한다.
* **`wp_direction_to_global_direction(R, dir_wp)` / `global_direction_to_wp_direction(R, dir_glb)`**
    * 와이어 평면 좌표계와 전역 좌표계 사이의 방향벡터를 변환한다 (회전 행렬 `R`은 위 함수로 획득).
* **`pack_track_data(times, points, charges, start_idx=0)`**
    * `(times, points, charges)`를 `depo_data`/`depo_info` 형식의 `(N,7)`/`(N,4)` numpy 배열로 패킹한다.
* **`generate_line_track_depo_set(...)`**
    * `generate_line_track_depos`와 `pack_track_data`를 합쳐 `depo_data_0`/`depo_info_0` 딕셔너리와 원본 `(times, points, charges)`를 함께 반환한다.
* **`TrackMetadata`**
    * 트랙 시작/끝점, 시간, 각 평면 회전 행렬(`R_wps`), 전역/평면별 방향벡터와 각도, `eperstep`, `track_speed`, 검출기/APA/평면 식별자를 담는 dataclass다.
    * `to_dict()`는 numpy 배열을 JSON 직렬화 가능한 리스트로 변환한다.
* **`pack_track_metadata(points, times, dir_wps, dir_glb, tconf, R_wps)`**
    * 생성된 트랙 정보로부터 `TrackMetadata` 인스턴스를 채운다.
* **`generate_line_track(center, tconf, R_wps, plane_idx)`**
    * `tconf.global_angles` 값에 따라 전역 또는 특정 평면 좌표계에서 지정한 각도로 방향을 계산하고, `center`를 중심으로 트랙을 생성해 `(depo_sets, metadata)`를 반환한다.
* **`generate_and_save_line_track(center, track_config, phi, path_depo, path_meta, plane_idx=0)`**
    * 평면별 회전각 `phi`(3개)로부터 회전 행렬들을 만들고 `generate_line_track`을 호출한 뒤, depo는 `.npz`로, 메타데이터는 `path_meta`가 주어지면 JSON으로 저장한다.
* **`load_wp_spec(detector, apa_idx)`**
    * `wirecell.util.wires`의 와이어 스키마를 로드해, 지정한 검출기/APA의 세 평면 각각에 대해 평면 중심(`wp_centers`)과 회전 행렬(`wp_rots`)을 계산한다.
* **`generate_and_save_line_track_in_detector(detector, apa_idx, plane_idx, offset, track_config, path_depo, path_meta)`**
    * `load_wp_spec`으로 실제 검출기 기하구조에서 평면 중심을 구하고 `offset`을 더해 트랙 중심을 정한 뒤 `generate_line_track`을 호출 및 저장한다.
    * `detlinegen` CLI 명령이 이 함수를 감싼다.

## `morse.py` — "morse" 패턴 depo 생성과 신호 폭 분석

모듈 docstring에 ASCII 다이어그램으로 설명되어 있듯, 각 와이어 평면을 순차적으로(시간축으로 분리하여) 겨냥하는 짧은 트랙들의 격자 패턴("모스 부호"처럼 보임)을 만든다.
이를 WCT 시뮬레이션 및 신호처리에 통과시킨 결과에서 신호 폭(확산 외 부가적 퍼짐)을 측정해 `DepoFluxSplat`용 스미어링 파라미터를 추정하는 데 쓰인다.

* **`generate(plane_wires, refx, charge, length, planes=(0,1,2), time_jump=500*units.us, pitch_jump=25, impact_jump=0.1)`**
    * 각 평면에 대해, 평면 중앙 와이어 근처부터 시작해 pitch 방향으로 `pitch_jump + n*impact_jump`씩 진행하는 여러 개의 짧은(길이 `length`) 트랙을 생성한다.
    * 평면마다 다른 시각(`time_jump*(0.5+plane)`)에 배치해 시뮬레이션 응답이 겹치지 않게 한다.
    * `depo_data`/`depo_info` 형식의 `(N,7)`/`(N,4)` 배열 쌍을 반환한다.
* **`gauss(x, A, mu, sigma, *p)`**
    * 피팅용 가우시안 모델 함수다.
* **`load_depos(fname)` / `load_frame(fname)`**
    * `.npz`에서 세대 0의 depo, 또는 프레임(`frame_*_0`)을 로드하는 헬퍼 함수다.
* **`WavePeak`**
    * 1D 파형에서 찾은 피크 하나의 정보를 담는 dataclass다: 위치(`peak`), 반치전폭(`fwhm`), 반치고(`hh`), 좌우 경계(`left`/`right`), 적분값(`tot`), 마스크(`mask`), 가우시안 피팅 파라미터(`A`, `mu`, `sigma`)와 공분산(`cov`).
    * `from_dict()`로 JSON에서 복원 가능하다 (마스크는 `slice`로, 공분산은 배열로 변환).
* **`wave_peaks(wave, which_peaks=None, threshold=0.1)`**
    * `scipy.signal.find_peaks`로 피크를 찾고 `peak_widths`로 반치전폭을 구한 뒤, 각 피크 주변만 남긴 파형에 `gauss()`를 `curve_fit`으로 피팅해 `WavePeak` 리스트를 반환한다 (`which_peaks`가 정수면 단일 `WavePeak`).
    * 피팅 실패 시 경고를 출력하고 `A`/`mu`/`sigma`/`cov`를 `None`으로 채운다.
* **`FramePeaks`**
    * 한 평면에 대한 분석 결과 묶음을 정의하는 dataclass다: 채널 방향 합산 파형에서 찾은 전체 피크(`total`), 각 임팩트 위치별 시간(tick) 방향 피크 리스트(`tick`), 채널 방향 피크 리스트(`chan`).
    * `from_dict()`를 제공한다.
* **`load_frame_peaks(src)`**
    * 파일 경로, 파일 객체, JSON 문자열, dict, list 중 어떤 형태로 주어지든 `FramePeaks` (또는 그 리스트)로 파싱한다.
* **`Encoder`**
    * `json.JSONEncoder` 서브클래스로 numpy 스칼라/배열, `slice`, dataclass를 JSON으로 직렬화할 수 있게 확장한다.
* **`dump_frame_peaks(dst, peaks)`**
    * `Encoder`를 사용해 `FramePeaks`(들)를 JSON으로 저장한다.
* **`scale_slice(s, r)`**
    * 슬라이스 `s`의 길이를 비율 `r`만큼 양쪽으로 확장한 새 슬라이스를 반환한다.
* **`patch_chan_mask(fp)`**
    * `FramePeaks.chan`의 모든 마스크를 아우르는 채널 방향 슬라이스를 계산한다.
* **`frame_peaks(signal, channel_ranges)`**
    * 실제 시뮬레이션 신호(`signal`, `nchan x ntick`)와 평면 경계 채널 리스트(`channel_ranges`)를 입력받아 다음을 수행하며, 평면별 `FramePeaks` 리스트를 반환한다.
    * CLI `morse-summary`가 이 함수를 호출한다.
        1. 채널 합산 파형에서 그 평면에 해당하는 피크 검색
        2. 해당 피크 시각에서 채널 방향 파형의 개별 피크(각 임팩트 위치) 검색
        3. 각 채널 피크 위치에서 다시 시간 방향 파형의 피크 검색

## `noise.py` — 노이즈 스펙트럼 프로토타입

모듈 주석에 "이것은 `NoiseTools`(C++)에 있는 것을 파이썬으로 시제품화한 것"이라고 명시되어 있다.
`wirecell.gen.test.test_noise`가 이 모듈로 진단용 플롯을 만든다.

* **`rayleigh(x, sigma=1)`**
    * Rayleigh 분포 확률밀도함수다.
* **`fictional(freqs, rel=0.1)`**
    * `freqs` 위에서 폭이 `freqs[-1]*rel`인 Rayleigh 분포 형태의 "가상" 스펙트럼을 만들고 `hermitian_mirror()`(`wirecell.lmn`에서 임포트)로 대칭화한다.
* **`frequencies(n, period)`**
    * 샘플링 주기 `period`에 대해 0부터 나이퀴스트 주파수 직전까지 `n`개의 주파수 배열을 생성한다.
* **`Collect`**
    * 여러 파형의 FFT 크기를 누적 평균하는 클래스다.
    * `add(wave)`로 파형을 추가하면 `.linear`(평균 진폭), `.square`(평균 파워), `.energy`(파워를 샘플 수로 나눈 값)를 제공한다.
* **`Spec`**
    * 스펙트럼 진폭(`amp`)과 샘플링 주기(`period`)를 감싸는 핵심 클래스다.
    * 생성 시 `amp`를 `hermitian_mirror()`로 대칭화한다.
    * **속성**: `size`, `half`(나이퀴스트 빈 인덱스), `frayleigh`, `fnyquist`, `fsample`, `sigma` (진폭→시그마 환산), `energy`.
    * `random_sigmas` / `random_wave`: 스펙트럼으로부터 무작위 위상의 복소 스펙트럼 샘플을 생성하고 역FFT로 시간영역 파형 하나를 만든다.
    * `waves(nwaves=None)`: `random_wave`를 `nwaves`번 반복해 `(nwaves, size)` 배열을 생성한다.
    * `roundtrip(nwaves=None)`: 파형을 생성했다가 다시 FFT해서 얻은 새 `Spec` (검증용 왕복 테스트).
    * `time_energy(nwaves=None)` / `time_rms(nwaves=None)`: 생성한 파형들의 평균 에너지/RMS를 반환한다.
    * `interp(newsize)`: 주파수축 선형보간으로 크기를 변경하고(주기는 유지), `sqrt(newsize/size)`로 정규화한다.
    * `interp_fft(newsize)`: FFT 왕복으로 보간을 시도하지만 위상 정보를 잃어버려 "실제로는 잘 동작하지 않는다"고 docstring에 명시된 실험적 메서드다.
    * `extrap(newsize, constant=None)`: 중앙 확장(고주파 빈 추가)으로 크기를 늘린다.
      시간축에서의 보간과 동등하며, 전체 파형 지속시간은 유지되고 샘플링/나이퀴스트 주파수가 늘어나므로 `period`가 비례해서 줄어든다.
    * `alias(newsize)`: 주파수 앨리어싱으로 시간축 다운샘플링을 수행한다.
      `newsize`가 원래 크기의 약수일 때 정확하며, `frayleigh`를 유지하면서 크기를 줄인다.
    * `resample(size, period)`: `interp` 후 `period` 비교에 따라 `extrap` 또는 `alias`를 적용하는 통합 리샘플링 메서드다.
    * `dup()`: 자기 자신의 복사본을 반환한다.
* **`gaussian_wave(rms, nsamples)` / `gaussian_waves(rms, nsamples, nwaves=None)`**
    * 정규분포 노이즈 파형(들)을 생성한다.
* **`waves_energy(waves)` / `waves_rms(waves)`**
    * `(nwaves, nsamples)` 파형 집합의 평균 에너지/RMS를 계산한다.
* **`gaussian_spec(rms, nsamples, nwaves=None)`**
    * 가우시안 노이즈 파형들을 생성해 FFT하고, 평균 진폭 스펙트럼과 시간/주파수 영역 평균 에너지·RMS를 함께 반환한다.

## `sim.py` — 시뮬레이션 산출물(frame/depo) 검사용 클래스

모듈 자체 주석에 "이 모듈 이름은 잘못 지어졌다(poorly named)"고 적혀 있다.
CLI의 `plot-test-boundaries`/`plot-sim` 명령이 여기 클래스들을 사용한다.

* **`baseline_subtract(frame)`**
    * 채널(행)별로 중앙값(median)을 빼서 베이스라인을 제거한 새 프레임 배열을 반환한다.
* **`parse_channel_boundaries(cb)`**
    * 콤마로 구분된 문자열 또는 이미 파싱된 시퀀스를 정수 튜플로 정규화한다.
* **`group_channel_indices(channels)`**
    * 정렬된 채널 번호 리스트를 연속 구간(inclusive) 튜플들로 묶는다.
    * *(주: 함수 본문이 `boundaries`라는 정의되지 않은 변수를 참조하고 있어 현재 코드 상태로는 호출 시 `NameError`가 발생하는 버그가 있다.)*
* **`Frame`**
    * `.npz`(또는 `ario`로 로드한) 아카이브에서 `frame_<tag>_<ident>` / `channels_<tag>_<ident>` / `tickinfo_<tag>_<ident>` 세 배열을 읽어 프레임 하나를 감싼다.
    * `plot_ticks(tick0=0, tickf=-1, raw=True, chinds=())`: 틱(샘플) 인덱스 기준으로 채널 그룹별 서브플롯을 그린다.
      `raw=False`면 `baseline_subtract`를 적용한다.
    * `plot(t0=None, tf=None, raw=True, chinds=None)`: 시간(ms) 기준으로 같은 방식의 플롯을 생성한다.
      각 서브플롯의 컬러맵은 `seismic`이며 대칭 컬러 스케일(`vmin=-vmax, vmax=vmax`)을 자동 계산한다.
* **`Depos`**
    * `.npz`에서 `depo_data_<ident>`/`depo_info_<ident>`를 읽어 `t`/`q`/`x`/`y`/`z` 프로퍼티로 노출한다.
    * `plot()`: 시간 히스토그램(좌상), X-Z 스캐터(좌하), Y-Z 스캐터(우하), 3D X-Y-Z 스캐터(우상)를 한 화면에 그린 `Figure`를 반환한다.
* **`NumpySaver`**
    * `reload()`에서 정의되지 않은 `filename` 변수를 참조하는 미완성 클래스로 보인다.
    * *(사실상 사용 불가능한 죽은 코드)*

## `plots.py` — `NumpyFrameSaver` 산출물 플롯 (레거시 독립 스크립트)

`wirecell-gen` CLI에 연결되어 있지 않은 독립 실행형 스크립트다 (`if __name__ == '__main__':`로 `sys.argv`를 직접 읽음).
`plots/numpysaver.py`와 로직이 거의 동일해 중복 코드로 분류된다.

* **`numpy_saver(filename, outfile)`**
    * `NumpyFrameSaver`가 만든 `.npz`에서 `frame__0`/`channels__0`을 읽고, 채널 번호가 불연속으로 점프하는 지점을 기준으로 그룹을 나눠 그룹별 `imshow` 서브플롯을 그린 뒤 `outfile`에 저장한다.

## `plots/` 서브패키지 — CLI가 실제로 쓰는 플롯 헬퍼

* **`plots/morse.py`**
    * `width_plots(out, signal, fps, channel_ranges, tick)` 함수를 포함한다.
    * `wirecell.gen.morse`의 `frame_peaks()` 결과(`fps`)를 바탕으로 PDF 페이지(`out`)에 다음 흐름대로 진단 플롯을 순서대로 그린다.
    * CLI `morse-plots` 명령이 호출한다.
        1. 전체 신호에 평면별 패치 위치를 사각형으로 표시한 개요도
        2. 평면별 확대 패치
        3. 채널 방향 개별 임팩트 폭(가우시안 피팅 곡선 포함)
        4. 시간(tick) 방향 전체 폭
        5. 임팩트별 시간 방향 폭
* **`plots/numpysaver.py`**
    * `numpy_saver(filename, outfile)` 함수를 포함한다.
    * 8절의 `plots.numpy_saver`와 거의 동일한 로직(채널 불연속 지점 기준 그룹핑 후 `imshow`)이지만, 이쪽은 내부에서 `plt.savefig(outfile)` 호출이 포함되어 실제 저장이 수행된다.
    * 단, 어느 쪽도 `__main__.py`의 CLI 서브커맨드로는 노출되어 있지 않다.

## `test/` — pytest 테스트와 개발용 스크립트

`wirecell-gen` CLI와는 무관하며, WCT 자체 개발 과정에서 함수의 정확성을 검증하거나(pytest) ROOT 기반 산출물을 훑어보기 위한(스크립트) 보조 코드가 모여 있다.

* **`test_linegen.py`**
    * `linegen.py`의 각도↔방향벡터 변환 함수들(`direction_to_tpc_angles`, `tpc_angles_to_direction`, `wp_direction_to_global_direction`, `global_direction_to_wp_direction`)이 왕복 변환 과정에서 원본 값을 정상적으로 복원하는지 검증하는 pytest 테스트 코드다.
* **`test_noise.py`**
    * `noise.py`의 `Spec` 클래스로 다양한 크기/주기 조합에 대해 보간/외삽/앨리어싱/왕복(roundtrip) 결과를 PDF로 그려 비교하는 진단 스크립트다.
    * (pytest 프레임워크로 실행되지만 실질적으로는 플롯 생성 목적임)
* **`plot_g4tuple.py`**
    * Geant4 ntuple 형태로 저장된 구버전 JSON depo 포맷(`xyzqtsn` 컬럼)을 읽는 `load_depos()`를 포함하고 있으며, 현재 `depos.columns`(`tqxyzLT`)와는 다른 레거시 스키마를 다루는 스크립트다.
* **`plot_impactzipper.py`**
    * ROOT 히스토그램을 "bilog"(부호별 로그 스케일)로 재조정하는 `bilogify()` 등, ROOT 기반 impact-zipper 관련 플롯 유틸리티를 포함한다.
    * `wirecell-gen` 패키지 자체에서는 ROOT를 직접 사용하지 않으므로 참고용 데이터로만 의미가 있다.
