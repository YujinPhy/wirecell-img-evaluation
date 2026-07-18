# Blob_Web_Server_Generalization_Plan

## Document Metadata
* **Created Date:** 2026-07-15
* **Last Updated:** 2026-07-15

## Summary
* `blob_viewer/pdhd_blob_web_server.py`(reco blob + depo를 브라우저에서 실시간 3D로 보여주는
  trame/pyvista 웹 서버)를 PDHD에 국한되지 않고 임의의 cluster/depo 데이터 파일에 대해 동작하도록
  일반화하고, 렌더링 품질(해상도)을 높이고, 사용자가 원리를 모르는 브라우저 렌더링 스택
  (trame/pyvista/VTK)을 처음부터 이해할 수 있도록 문서화하는 Task의 계획 문서.
* 조사 결과 이 파일은 현재 **실행 자체가 안 되는 상태**였음이 드러남(임포트하는 모듈이 저장소에
  없음) — 단순 파라미터 일반화가 아니라, 없어진 기능을 복구하는 작업이 선행되어야 함.

---

## 1. Task/Component Identification

* **Context:** depo(참값)와 reco blob(재구성 결과)을 비교하는 기존 워크플로우
  (`scripts/position_center_comparison.py`, `scripts/pdhd_true_blob_check.py` 등)는 전부 2D
  플롯/수치 비교 위주다. `blob_viewer/`는 여기에 "3D 형태를 직접 눈으로 확인"하는 보완 도구를
  두려는 목적으로 만들어졌고, 이미 PDHD 데이터로 한 번 작동했던 `pdhd_blob_web_server.py`가
  존재한다.
* **Target Component:**
  - `blob_viewer/pdhd_blob_web_server.py` → `blob_viewer/blob_web_server.py`로 일반화/수정.
  - 신규: `blob_viewer/blob_web_server_reference.md` (렌더링 원리 설명 문서, 사용자가 명시적으로
    요청).
* **Dependency:** 없음. 다만 이 Task 도중 `blob_viewer/pdhd_blob_web_server.py`가 참조하는
  `pdhd_blob_to_vtu.py`가 저장소 어디에도 없다는(git 이력에도 없음, `scripts/__pycache__/`에
  컴파일된 `.pyc`만 남음) 사실을 발견 — 이 Task는 그 복구도 함께 다룬다.

---

## 2. Background Knowledge & Information Gathering

* **Reference Materials:**
  - `docs/time_offset_calibration.md`: PDHD의 `v_drift`(1.6mm/us), `t_offset`(314.5us),
    `response_plane_x`(3430.47mm) 보정값의 근거. 이 값들은 detector마다 다르므로, 일반화된
    스크립트에서는 하드코딩이 아니라 CLI 인자로 노출해야 한다.
  - `blob_viewer/wirecell_bee_reference.md`: 같은 디렉터리에 이미 존재하는, 비슷한 깊이/스타일의
    "원리 설명" 문서 — 새 문서의 구성/톤의 모델로 삼음.
  - `scripts/position_center_comparison.py`: `blob_center()`가 쓰는 `x = response_plane_x -
    v_drift * (t_us - t_offset)` undrift 공식 — `blob_web_server.py`가 그대로 재사용해야 할
    동일한 물리.
* **Claude Command for Gathering (조사로 확인한 사실):**
  - `blob_viewer/pdhd_blob_web_server.py:34`의 `from pdhd_blob_to_vtu import _load_and_undrift,
    clusters2blobs_surface_vtk` — 이 모듈은 저장소/git 이력 어디에도 없음(`ModuleNotFoundError`
    로 재현 확인). `blob_viewer/`는 전체가 untracked라 이 파일이 언제 어떻게 없어졌는지 git으로는
    추적 불가.
  - `blob_viewer/pdhd_blob_web_server.py:40-78`의 `parse_args()`는 `scripts/position_center_comparison.py`의
    `parse_args()`를 그대로 복사한 죽은 코드(정의되지 않은 상수 참조, 어디서도 호출되지 않음) —
    삭제 대상.
  - 이웃 패키지 `/nfs/data/1/yujin/wire-cell-python/wirecell/img/converter.py`에 없어진 두 함수의
    사실상 대체품이 이미 설치되어 있음:
    - `undrift_blobs(cgraph, speed, time, x0, drift_index)` (converter.py:35) — 없어진
      `_load_and_undrift`가 하려던 일과 동일한 시간→x 변환. 기본값(`speed=1.6*units.mm/units.us,
      time=0`)이 이미 범용(특정 detector 비특정) 값이라, 일반화된 스크립트의 기본값으로 그대로
      채택 가능.
    - `orderpoints(pointset)`/`extrude(pts, dx)` (converter.py:92, 66) — blob의 2D `corners`
      다각형을 각도순 정렬 + x축으로 두께만큼 밀어(extrude) 3D 솔리드를 만드는, 없어진
      `clusters2blobs_surface_vtk`가 필요로 했을 정확한 기하 연산.
    - `clusters2blobs(gr)` (converter.py:145)는 같은 연산으로 `tvtk.UnstructuredGrid`를 만들지만,
      이 저장소 가상환경에는 `tvtk`/`mayavi`가 설치돼 있지 않음(`ModuleNotFoundError`로 확인) —
      그래서 pyvista `PolyData` 기반으로 별도 조립이 필요함(재구현이 아니라, 자료구조 조립부만
      새로 작성).
  - `scripts/utils/load.py`의 `load_generation_data`/`load_cluster_data`/`load_graph_nodes`는
    이미 완전히 detector 무관(경로/anode 개수 하드코딩 없음, 순수 파일 포맷 wrapper) — 수정 불필요.
  - blob 렌더링 경로(`clusters2blobs_surface_vtk` 대체품)와 depo 밀도 shell
    (`_depo_density_shells`) 모두 wire geometry(`utils/wires.py`/`PlaneGeometry`)를 전혀 쓰지
    않음 — wire-store 경로는 이번 일반화의 관심사가 아님.
  - `data/pdhd/*`의 파일명 규칙(`clusters-apa-<N>.tar.gz`, `depos-drifted-<N>.zip`)은
    detector와 무관한 순수 명명 규칙이라 `_find_depo_file`은 이미 일반적으로 동작함.
  - 저장소 전체에서 `pdhd_blob_web_server.py`를 참조하는 다른 파일 없음(grep으로 확인) — 파일명
    변경이 다른 곳을 깨지 않음.
  - 사용자에게 "고해상도"의 의미를 직접 질문해 확인: **뷰어 자체의 인터랙티브 렌더링 품질**을
    높이는 것(별도의 고해상도 스크린샷 저장 기능이 아님). 설치된 pyvista/trame 버전을 직접
    조회해 실제 조절 지점을 확인:
    - `pv.global_theme.window_size` 기본값 `[1024, 768]` — 실제 렌더 해상도 상한.
    - `line_smoothing`/`point_smoothing`/`polygon_smoothing` `Plotter.__init__` 기본값 전부
      `False`.
    - `multi_samples`(MSAA) 테마 기본값은 이미 `8`.
    - trame `interactive_ratio`/`still_ratio`(드래그 중 해상도를 낮추는 메커니즘, 흔히 "trame은
      회전 중엔 저화질"의 원인으로 알려짐) 둘 다 이 설치 버전에서는 이미 `1`(다운스케일 없음)로
      확인 — 손댈 필요 없음.
    - 렌더 백엔드가 `vtkEGLRenderWindow`(모니터 없이 GPU로 직접 렌더링하는 EGL 기반 off-screen
      렌더링)임을 직접 확인 — 문서화에 필요한 사실.

---

## 3. Task Planning

* **Objective:**
  1. `blob_viewer/blob_web_server.py`(리네임)가 PDHD 전용 하드코딩 없이 임의의
     `clusters-apa-<N>.tar.gz` (+선택적 `depos-drifted-<N>.zip`)에 대해 동작하게 한다.
  2. 없어진 `pdhd_blob_to_vtu.py`의 기능(`_load_and_undrift`, blob→3D 메시)을 `wire-cell-python`의
     기존 `wirecell.img.converter` 유틸을 재사용해 복구한다.
  3. 인터랙티브 뷰의 렌더링 품질(해상도/안티에일리어싱)을 사용자가 확인한 의미대로 높인다.
  4. `blob_viewer/blob_web_server_reference.md`에 trame/pyvista/VTK 스택과 브라우저 연결 원리를
     처음 보는 사람 기준으로, 코드 각 부분과 대응시켜 문서화한다.
* **Success Criteria:**
  - `python -m py_compile blob_viewer/blob_web_server.py` 통과.
  - PDHD 보정값(`--v-drift 1.6 --t-offset 314.5 --response-plane-x 3430.47`)과, 아무 detector
    인자도 주지 않은 범용 기본값 두 경우 모두, `data/pdhd/test_point_depo/clusters-apa-1.tar.gz`에
    대해 `ModuleNotFoundError` 없이 서버가 기동되고 `[INFO] N blob faces loaded ...` 로그가
    찍히는 것을 실행으로 확인.
  - `blob_web_server_reference.md`가 (a) 왜/어떻게 브라우저가 렌더링 결과를 받아보는지, (b)
    VTK/pyvista/trame 각 계층의 역할, (c) 이번에 바꾼 해상도 관련 설정과 그 원리, (d) 코드
    각 함수가 무엇을 하는지를 모두 다루는지 자체 점검.
* **Action Items:**
  1. `blob_viewer/pdhd_blob_web_server.py` → `blob_viewer/blob_web_server.py` 이름 변경(다른
     파일에서 참조 없음 확인됨, 안전).
  2. 죽은 `parse_args()` 삭제.
  3. `_load_and_undrift`/blob→메시 함수를 `wirecell.img.converter.undrift_blobs`/`orderpoints`/
     `extrude`를 재사용해 이 파일 안에 직접 구현(범용 기본값 사용, detector 보정값은 CLI 인자로).
  4. `__main__`의 argparse에 `--v-drift`/`--t-offset`/`--response-plane-x`(범용 기본값) 및
     `--width`/`--height`/`--multi-samples`/`--depo-theta-res`/`--depo-phi-res`(해상도/품질)
     추가.
  5. `serve_blobs()`에서 `pv.Plotter(window_size=..., line_smoothing=True, point_smoothing=True,
     polygon_smoothing=True)` + `pv.global_theme.multi_samples`로 품질 설정 반영.
  6. 실행 검증(§ Result Verification, Report 문서에 기록).
  7. `blob_viewer/blob_web_server_reference.md` 작성.
  8. (사용자의 전역 Task_Plan_and_Report_Workflow 정책에 따라) 본 Plan 문서와 대응하는 Report
     문서를 `docs/`에 작성.

---

## Related Documents

* **Parent docs:** 없음 (독립 Task).
* **Child docs:**
  - [blob_web_server_generalization_report.md](./blob_web_server_generalization_report.md): 본
    계획에 따른 실행/검증 결과 리포트.
* **Sibling docs:**
  - [../blob_viewer/wirecell_bee_reference.md](../blob_viewer/wirecell_bee_reference.md): 같은
    깊이/스타일로 작성된, Bee(업로드형 뷰어) 쪽 원리 설명 문서 — 신규 문서의 스타일 모델.
  - [time_offset_calibration.md](./time_offset_calibration.md): 이 Task가 재사용하는 undrift
    공식과 PDHD 보정값의 출처.
  - [position_center_comparison_plan.md](./position_center_comparison_plan.md): 같은 undrift
    공식을 쓰는 선행 Task, Plan/Report 문서 템플릿의 참고 사례.
