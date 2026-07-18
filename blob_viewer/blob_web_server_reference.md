# `blob_web_server.py` Reference — 브라우저 3D 뷰어의 원리

## 이 문서가 다루는 범위

`blob_viewer/blob_web_server.py`는 reco blob(재구성된 3D volume 조각)과 depo(참값 전하 분포)를
**브라우저에서 실시간으로 회전/확대해가며** 볼 수 있게 해주는 로컬 웹 서버다. 같은 디렉터리의
`wirecell_bee_reference.md`가 다루는 **Bee**(BNL이 운영하는, zip을 업로드하는 별도의 외부
웹사이트)와는 완전히 다른 종류의 "3D 보기"다 — 이 문서와 그 문서를 다음 표로 구분해서 읽으면 된다.

| | `wirecell.bee` (`wirecell_bee_reference.md`) | `blob_web_server.py` (이 문서) |
|---|---|---|
| 렌더링은 어디서? | 외부 BNL 서버 (이 저장소 코드 없음) | **이 컴퓨터** (지금 실행 중인 파이썬 프로세스) |
| 업로드 필요? | 필요 (zip을 BNL에 POST) | 불필요 — 로컬 파일을 즉시 그대로 렌더링 |
| 데이터 형태 | 점(point cloud)만 | blob의 실제 3D 폴리곤 solid + depo 밀도 shell |
| 이 저장소 코드의 역할 | JSON 포맷 변환/요약/비교 (렌더링 없음) | **렌더링 자체 + 웹 서버** |

즉 Bee는 "그림을 그려서 남에게 보내는" 방식이고, `blob_web_server.py`는 "내 컴퓨터가 그림을
계속 새로 그려서 브라우저 화면에 실시간으로 스트리밍하는" 방식이다. 이 문서는 후자가 대체
어떻게 가능한 것인지, 처음 보는 사람 기준으로 원리부터 설명한다.

---

## 1. 큰 그림: "서버가 그리고, 브라우저는 그림만 받는다"

핵심 아이디어는 하나다: **3D 렌더링(도형을 픽셀로 바꾸는 계산)은 이 서버가 다 하고, 브라우저는
그 결과 화면만 전달받아 보여준다.** 브라우저는 3D 지오메트리(수만 개의 폴리곤 좌표)를 직접
가지고 있지 않아도 된다 — 서버가 이미 그린 이미지를 그냥 표시하는 것뿐이라, 마치 화면 공유
(remote desktop)를 보는 것과 원리가 같다.

이게 왜 필요한가 하면, 렌더링 화면을 볼 물리 모니터가 이 서버(원격 리눅스 머신)에 연결되어
있지 않기 때문이다. VTK(아래 §2)는 그래도 "화면 없는" GPU 렌더링을 할 수 있는데, 이를
**off-screen rendering**이라고 한다. 이 스크립트 맨 위의 `pv.OFF_SCREEN = True`
(`blob_web_server.py:48`)가 그 모드를 켜는 코드다. 실제로 이 서버에서 VTK가 무엇을 쓰는지
직접 확인해보면:

```
>>> vtk.vtkRenderWindow().GetClassName()
'vtkEGLRenderWindow'
```

`vtkEGLRenderWindow`는 **EGL**(모니터 없이 GPU에 직접 접근하는 표준 인터페이스, 헤드리스
서버에서 흔히 쓰임)을 이용한 GPU 렌더링이다. 소프트웨어로 흉내내는 게 아니라 실제 GPU가
그린다 — 그래서 이 스크립트를 실행하면 `bad X server connection. DISPLAY=` 라는 경고가 뜨는데
(모니터용 X서버가 없다는 뜻), 이건 무시해도 되는 정상적인 경고다. EGL로 잘 넘어가기 때문이다.

이제 "서버가 그린 그림"을 브라우저까지 어떻게 전달하는지가 남는다. 이건 trame(§2, §4)이
맡는다 — HTTP+WebSocket 서버를 열어서, 브라우저가 마우스로 뭘 하든(회전, 확대) 그 조작 정보만
서버로 보내고, 서버는 그 조작을 반영해 다시 그린 뒤 그 결과를 브라우저로 돌려보낸다.

---

## 2. 3계층 스택: VTK → PyVista → trame

이 파일의 임포트(`blob_web_server.py:34-46`)에 등장하는 라이브러리들은 아래처럼 3겹으로
쌓여 있다. 아래로 갈수록 저수준(low-level), 위로 갈수록 "웹페이지"에 가깝다.

```
trame            (웹 서버 + UI. Plotter를 "웹페이지"로 만든다)
  ↑
pyvista          (VTK를 파이썬답게 감싼 것. Plotter, PolyData 등)
  ↑
VTK              (실제 렌더링 엔진. C++ 라이브러리, 폴리곤 -> 픽셀)
```

* **VTK** (`import vtk`): 3D 도형을 픽셀로 그려주는 엔진 이 파일에서 raw `vtk.*` API를
  직접 쓰는 곳은 `_depo_density_shells`(`blob_web_server.py:162-238`)뿐이다 — `vtkSphereSource`
  (구 템플릿) + `vtkGlyph3D`(그 구를 수천 개 depo 위치에 각각 다른 스케일로 복제, 아래 §6.3 참고)
  처럼, pyvista가 아직 감싸지 않은 저수준 필터가 필요할 때만 등장한다.

* **PyVista** (`import pyvista as pv`): VTK를 파이썬스럽게 감싼 래퍼.
이 파일에서 실제로 "장면(scene)"을 구성하는 건 전부 pyvista API다:
  - `pv.Plotter` (`blob_web_server.py:264`): 카메라, 조명, 렌더 윈도우를 갖는 "화면" 객체.
  - `pv.PolyData` (`blob_web_server.py:156`): 점+폴리곤으로 이루어진 표면 메시 자료구조 —
    blob 하나하나를 이 형태로 만든다 (§5.4).
  - `pv.wrap(...)` (`blob_web_server.py:236`): raw VTK 객체(`vtkGlyph3D`의 출력)를 pyvista
    객체로 감싸서, 이후 pyvista API(`.merge()` 등)를 쓸 수 있게 해준다.
  - `plotter.add_mesh(...)` (`blob_web_server.py:270, 273`): 메시를 화면에 추가하고, 어떤
    필드로 색칠할지(`scalars=...`), 색상 맵(`cmap=...`), 투명도(`opacity=...`) 등을 지정.

* **trame** (`from trame...`): pyvista의 `Plotter`를 실제 웹페이지로 바꿔주는 계층. 이 파일에서:
  - `get_server()` (`blob_web_server.py:278`): trame 서버 인스턴스. `server.state`는 브라우저
    쪽 UI 위젯(체크박스/슬라이더 등)과 파이썬 변수를 실시간으로 동기화해주는 "공유 상태" 객체다.
  - `plotter_ui(plotter)` (`blob_web_server.py:312`): pyvista `Plotter` 하나를 통째로 받아서,
    "마우스로 회전 가능한 3D 뷰" 웹 컴포넌트로 바꿔주는 한 줄. 이게 이 스택에서 가장 중요한
    한 줄이다 — VTK/pyvista가 만든 장면과 trame의 웹 서버를 실제로 연결하는 지점이기 때문.
  - `SinglePageLayout`, `vuetify3.VContainer/VCheckbox/VSlider/VSpacer` (`blob_web_server.py:308-329`):
    페이지 레이아웃과 UI 위젯(제목 표시줄, "Blobs"/"Depos" 체크박스, 각각의 투명도 슬라이더).
    `vuetify3`는 구글의 Material Design과 비슷한, 웹 프론트엔드에서 흔히 쓰는 기성 UI 컴포넌트
    모음(Vue.js 생태계의 Vuetify)이다 — 이 코드는 그 컴포넌트를 파이썬에서 선언적으로 배치할
    뿐, 실제 HTML/CSS/JS는 trame이 알아서 만들어준다.
  - `server.start(port=..., host="0.0.0.0", ...)` (`blob_web_server.py:336`): 이 모든 걸
    합쳐서 실제 HTTP+WebSocket 서버를 켜는 마지막 줄. 이 호출이 반환되지 않고 계속 실행되는
    상태가 "서버가 떠 있다"는 뜻이다 (Ctrl+C로 종료하기 전까지 블로킹).

---

## 3. 브라우저 연결이 실제로 이뤄지는 방식

1. `server.start(port=P, host="0.0.0.0")`가 이 머신의 포트 `P`에서 HTTP 서버 하나를 연다.
   `host="0.0.0.0"`은 "이 머신의 어느 네트워크 인터페이스로 들어와도 받는다"는 뜻 — SSH 터널이
   `localhost`로 연결해오는 것도 이걸로 받는다.
2. 브라우저에서 `http://localhost:P`를 열면, 서버가 작은 JS 클라이언트(trame/VTK.js 런타임)를
   내려준다. 이 JS가 로드되자마자 **같은 서버로 다시 WebSocket 연결**을 연다 — 이때부터가 진짜
   "실시간 연결"이다.
3. 마우스로 화면을 드래그(회전)하거나 휠(확대)하면, 그 동작이 "카메라를 이렇게 옮겨라"라는
   작은 메시지로 그 WebSocket을 통해 서버로 전송된다.
4. 서버(이 파이썬 프로세스)는 그 메시지를 받아 `Plotter`의 카메라를 갱신하고, VTK가 §1에서
   설명한 off-screen EGL 렌더링으로 새 프레임을 그린 뒤, 그 결과를 다시 WebSocket으로 브라우저에
   보낸다. 브라우저는 그걸 받아 화면의 `<canvas>`에 그려 넣는다.
5. 이 왕복(마우스 조작 → 서버 렌더 → 이미지 전송 → 화면 갱신)이 매 프레임 반복되는 게
   "회전시켜서 볼 수 있다"의 정체다 — 브라우저가 3D 연산을 하는 게 아니라, 서버가 대신 그려주는
   그림을 빠르게 이어 붙여 보여주는 것.

**왜 지금 이게 "그냥" 되는가 (포트 포워딩)**: 위 통신은 전부 `localhost:P` 기준이라, 로컬 브라우저가
직접 원격 서버의 포트에 접속할 수는 없다 — 그래서 포트 포워딩이 필요하다. VSCode의
Remote-SSH로 이 서버에 붙어 있으면, VSCode가 원격에서 새로 열리는 포트를 감지해 자동으로
포워딩해주고 "Open in Browser" 알림을 띄운다. 그게 아니라면 터미널에서 직접
`ssh -L P:localhost:P <host>`로 터널을 열어야 한다 — 이 명령의 의미는 "내 로컬 머신의 포트 P로
들어오는 연결을, SSH 터널을 통해 원격 머신의 localhost:P로 그대로 전달해라"이다. 스크립트
실행 시 뜨는 안내 메시지(`blob_web_server.py:325-326`)가 바로 이 절차를 알려주는 것.

---

## 4. "고해상도"로 바꾼 부분과 그 원리

기존 코드는 `pv.Plotter()`를 인자 없이 호출해 pyvista 기본값을 그대로 썼다. 그 기본값을
실제로 조회해보면:

| 설정 | 기존(pyvista 기본값) | 의미 |
|---|---|---|
| `window_size` | `[1024, 768]` | 실제 렌더링 해상도(픽셀). 브라우저 창 크기와 무관하게, VTK가 내부적으로 그리는 이미지 크기의 상한. |
| `multi_samples` | `8` | MSAA(Multi-Sample Anti-Aliasing) 샘플 수. 폴리곤 가장자리의 계단현상(jagged edge)을 얼마나 부드럽게 처리할지. |
| `line_smoothing`/`point_smoothing`/`polygon_smoothing` | 전부 `False` | 선/점/폴리곤 각각에 대한 추가 안티에일리어싱. blob을 `show_edges=True`로 그리므로(경계선이 많이 보임) 특히 영향이 크다. |
| trame `interactive_ratio`/`still_ratio` | 둘 다 `1` (이 설치 버전 기준 실측 확인) | 마우스로 드래그하는 동안 대역폭을 아끼려고 해상도를 낮췄다가, 멈추면 원래 해상도로 다시 그리는 메커니즘. **"드래그 중엔 화질이 낮아진다"는 흔한 trame 특성이 바로 이것인데, 이 설치 버전에서는 둘 다 1(다운스케일 없음)로 이미 꺼져 있어 해당사항 없음.** |

즉 실제 체감 해상도를 낮추던 주범은 트레이드오프 메커니즘(`interactive_ratio` 등)이 아니라,
그냥 **`window_size`가 1024x768로 작게 고정**되어 있었고 **가장자리 스무딩이 다 꺼져** 있었던
것이다. 그래서 `serve_blobs`(`blob_web_server.py:263-269`)에서 바꾼 것:

```python
pv.global_theme.multi_samples = multi_samples   # 기본 8 유지, --multi-samples로 조절 가능
plotter = pv.Plotter(
    window_size=(window_width, window_height),  # 기본 1920x1080 (CLI: --width/--height)
    line_smoothing=True,
    point_smoothing=True,
    polygon_smoothing=True,
)
```

(`multi_samples`는 `Plotter()`의 생성자 인자가 아니라 **전역 테마 설정**이라, 렌더 윈도우를
만들기 전에 `pv.global_theme.multi_samples`를 먼저 바꿔야 한다 — 실행해보고서야 확인한 이
설치 버전의 API 형태다.)

CLI에서 `--width`/`--height`/`--multi-samples`로 필요하면 더 조절할 수 있다
(`blob_web_server.py:358-361`). 참고로 depo 밀도 shell의 구 템플릿 해상도(`--depo-theta-res`/
`--depo-phi-res`, 기본 10/6)도 낮은 값인데, 이건 화질이 아니라 **성능** 트레이드오프다 — depo
개수가 많을 때(수천 개) 폴리곤 수가 `len(ks) * n_depos`로 곱해져 늘어나므로 일부러 낮춰둔
것(`_depo_density_shells`의 docstring, `blob_web_server.py:186-189`). depo 수가 적은 데이터셋을
볼 때는 이 값을 올려 depo 타원체(ellipsoid)를 더 매끈하게 볼 수 있다.

블롭/뎁포 각각의 표시 여부(체크박스)와는 별개로, §5.5에서 다루는 "Blob opacity"/"Depo opacity"
슬라이더로 각 레이어의 투명도도 실시간으로 조절할 수 있다 — 화질과는 다른 축이지만, 두 레이어가
겹칠 때 서로 가리는 걸 조절하는 용도라 여기서 같이 언급해둔다.

---

## 5. 코드 훑어보기

### 5.1 서버 재시작 메커니즘 (`_pid_file`/`_stop_previous_server`/`_register_current_server`, `blob_web_server.py:66-94`)

같은 포트로 스크립트를 두 번 실행하면 원래 "주소 이미 사용 중"(`address already in use`) 에러가
난다. 이를 피하려고, 실행할 때마다 `/tmp/blob_web_server_port<PORT>.pid`에 자기 PID를 적어두고
(`_register_current_server`), 다음 실행 시 그 파일에 적힌 이전 PID가 아직 살아있으면
`psutil`로 종료(`SIGTERM`, 5초 내로 안 죽으면 `SIGKILL`)시킨 다음 시작한다
(`_stop_previous_server`). 매번 재실행이 "그냥 되게" 만드는 장치다.

### 5.2 blob의 시간 → x 좌표 변환 (`_load_and_undrift`, `blob_web_server.py:96-113`)

reco blob의 `corners` 필드는 원래 `[t_ns, y_mm, z_mm]` — 첫 번째 값이 실제 x가 아니라
**시간(ns)**이다 (drift 시간이 곧 x위치라는 물리적 사실은 알지만, 그래프에 저장된 원값은
아직 변환 전 시간값이라는 뜻). 이걸 실제 mm 단위 x로 바꾸는 걸 "undrift"라 부르고, 공식은
`docs/time_offset_calibration.md`에 자세히 나온 것과 동일하다:

```
x = response_plane_x - v_drift * (t_us - t_offset)
```

이 변환 자체는 새로 짠 게 아니라, `wire-cell-python` 패키지의
`wirecell.img.converter.undrift_blobs`를 그대로 가져다 썼다 — `position_center_comparison.py`의
`blob_center()`가 쓰는 것과 완전히 같은 공식이라, 물리 로직이 이 저장소 안에 두 벌로 흩어지지
않는다. `v_drift`/`t_offset`/`response_plane_x`는 **detector마다 다른 값**이라(PDHD 기준
1.6mm/us, 314.5us, 3430.47mm) 이번에 CLI 인자로 뺐고, 아무 값도 안 주면 상위 라이브러리
자체의 범용 기본값(1.6mm/us, 0, 0)을 쓴다 — 즉 아직 시간축 보정이 안 된 detector의 데이터라도
일단 형태(shape)는 정확하게 뜨고, 절대 x위치만 미보정 상태로 남는다.

### 5.3 blob을 3D 메시로 만들기 (`_blobs_to_polydata`, `blob_web_server.py:116-159`)

undrift가 끝난 blob 하나의 `corners`는 "한 x(=시간 슬라이스) 위치에 놓인 2D 다각형"이다.
이 다각형을 그 blob의 두께(`span`, 슬라이스 두께)만큼 x축으로 밀어서(**extrude**) 만든 3D
솔리드가 곧 그 blob의 형태다 — 종이 도장(2D 다각형)을 한 방향으로 쭉 밀어 만든 입체라고 생각하면
된다.

이 계산도 새로 짜지 않고 `wirecell.img.converter`의 두 함수를 그대로 썼다:
- `orderpoints(corners)`: 다각형의 점들을 중심점 기준 각도순으로 정렬 (안 하면 지그재그로
  잘못 이어진 다각형이 나온다).
- `extrude(pts, span)`: 정렬된 점들의 "윗면"(원래 다각형)과 "아랫면"(x로 `span`만큼 민 복사본),
  그리고 옆면 사각형들(윗면-아랫면을 잇는 4각형, 다각형 변 개수만큼)의 점 인덱스 목록을 만든다.

원래 `wirecell.img.converter.clusters2blobs()`는 이 결과로 `tvtk.UnstructuredGrid`(Mayavi의
자료구조)를 만드는데, 이 프로젝트가 쓰는 가상환경에는 `tvtk`/`mayavi`가 설치돼 있지 않다(확인
완료). 그래서 같은 점/셀 정보를 pyvista가 이해하는 형식(`faces` 배열: `[각 폴리곤의 점 개수,
점 인덱스들, ...]`을 이어붙인 1차원 배열)으로 직접 조립해 `pv.PolyData(points, faces=...)`를
만드는 부분만 이 파일이 새로 담당한다 — 기하 계산(각도 정렬, extrude)은 재사용, 자료구조
조립만 pyvista용으로 새로 쓴 것.

각 blob의 `val`(전하량) 등 숫자 필드는 그 blob에 속한 모든 면(윗면/아랫면/옆면)에 동일한 값으로
반복 저장되어(`cell_scalars`), `--scalars val`처럼 어떤 필드로 색칠할지 고를 수 있게 한다.

### 5.4 depo 밀도 shell (`_depo_density_shells`, `blob_web_server.py:162-238`)

blob과 별개로, depo(참값 전하)는 한 점이 아니라 "확산된 3D 가우시안 구름"이다 — drift 축(x)
방향 표준편차는 `L`, 가로 방향(y, z)은 등방적으로 `T`. 이 함수는 `k=1,2,3` 시그마에 해당하는
타원체 껍질(shell)을 그려서, 전하가 중심에서 가장자리로 갈수록 옅어지는 걸 시각적으로 보여준다.

전 depo에 대해 파이썬 for문으로 각각 메시를 만들면 5000개 depo 기준 약 215초가 걸렸는데,
`vtkGlyph3D`(구 하나를 "템플릿"으로 두고, 여러 위치/스케일에 한 번에 복제해 붙여주는 필터)를
쓰면 같은 작업이 약 0.2초로 끝난다(1000배 이상 차이) — 벡터화된 필터 호출 한 번이 파이썬
반복문보다 훨씬 빠른, VTK를 쓸 때 흔한 최적화 패턴이다.

### 5.5 `serve_blobs`: 장면 조립과 반응형 체크박스/슬라이더 (`blob_web_server.py:241-336`)

여기서 지금까지의 조각(blob 메시, depo shell 메시)을 하나의 `Plotter`에 올리고, "Blobs"/"Depos"
체크박스와 그 옆의 투명도 슬라이더를 만든다. `@state.change("show_blobs")`
(`blob_web_server.py:282`)로 데코레이트된 함수는 **브라우저에서 체크박스를 누를 때마다 자동으로
호출되는 콜백**이다 — trame의 `state`가 파이썬 변수와 브라우저 UI를 양방향으로 동기화해주기
때문에, "체크박스/슬라이더 상태가 바뀌면 이 파이썬 함수를 실행해라" 같은 이벤트 리스너를 따로
짤 필요 없이 이 데코레이터 하나로 끝난다. 콜백 안의 `view.update()`가 "이제 이 변경사항을
반영해서 다시 그려라"라는 신호다.

같은 패턴으로 `@state.change("blob_opacity")`/`@state.change("depo_opacity")`
(`blob_web_server.py:295, 301`)가 "Blob opacity"/"Depo opacity" 슬라이더(`blob_web_server.py:317,
325`, 0~1, 기본 1.0)를 각 actor의 `prop.opacity`(`blob_web_server.py:297, 303`)에 그대로
반영한다. depo actor는 이미 밀도 기반 그라데이션 투명도(`opacity=[0.0, 0.7]`,
`blob_web_server.py:274`)가 걸려 있는데, `prop.opacity`는 그 위에 곱해지는 전체 배율이라
그라데이션 형태는 유지한 채 전체적으로 더 흐리게/진하게 조절할 수 있다.

---

## 6. 사용법

```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"

# PDHD (calibrated) — docs/time_offset_calibration.md의 값, blob/depo 파일을 각각 명시
python blob_viewer/blob_web_server.py \
    --blob-file data/pdhd/test_point_depo/clusters-apa-1.tar.gz \
    --depo-file data/pdhd/test_point_depo/depos-drifted-1.zip \
    --v-drift 1.6 --t-offset 314.5 --response-plane-x 3430.47 \
    --port 8080

# 아직 시간축 보정이 안 된(uncalibrated) 임의의 detector 데이터 — 기본값 그대로, depo 없이 blob만
python blob_viewer/blob_web_server.py --blob-file path/to/clusters-apa-0.tar.gz --port 8080
```

`--blob-file`은 필수, `--depo-file`은 선택이다 — 예전엔 생략 시 같은 디렉터리에서
`depos-drifted-<N>.zip`을 자동으로 찾는 기능(`_find_depo_file`)이 있었지만, 이제는 그 자동 탐색
없이 **`--depo-file`을 명시한 경우에만** 그 파일을 그대로 불러온다; 생략하면 depo 오버레이 없이
blob만 그린다. 절대 x 보정이 안 된 두 번째 예시에서도 blob의 상대적 크기/모양/서로의 배치는
정확하다 — 오직 "이 blob이 실제로 검출기 안 몇 mm 지점에 있는가"만 미보정 상태다.

---

## 7. 문제 해결 체크리스트

- **"address already in use" 에러**: 보통 §5.1의 pid-file 메커니즘이 알아서 이전 프로세스를
  죽이고 재시작하므로 발생하지 않는다. 그래도 나면, `/tmp/blob_web_server_port<PORT>.pid`에
  적힌 PID가 이미 다른 무언가(같은 포트를 쓰는 별개 프로세스)에게 재사용된 경우일 수 있다 —
  그 파일을 지우고 다시 실행.
- **브라우저가 흰/검은 화면만 뜨고 아무것도 안 보임**: 서버 로그에서 `[INFO] N blob faces
  loaded ...` 줄이 찍혔는지 먼저 확인(§1의 EGL 렌더링/포트 자체는 살아있다는 뜻). 그래도
  안 보이면 포트 포워딩이 실제로 걸려 있는지(브라우저 주소창의 포트가 서버가 출력한 포트와
  일치하는지) 확인.
- **회전/확대해도 화면이 갱신 안 됨**: 브라우저 쪽 WebSocket 연결이 끊어졌을 가능성 — 페이지
  새로고침으로 대개 해결된다 (WebSocket을 다시 열어 서버와 재연결).
- **새 결과인데 예전 화면처럼 보임**: 같은 포트로 재실행했는데 브라우저 탭을 새로고침하지
  않은 경우 — 재실행 자체는 §5.1 메커니즘으로 항상 새 프로세스이므로, 브라우저만 새로고침하면
  된다.
