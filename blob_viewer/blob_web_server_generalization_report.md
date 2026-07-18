# Blob_Web_Server_Generalization_Report

## Document Metadata
* **Created Date:** 2026-07-15
* **Last Updated:** 2026-07-15

## Summary
* [blob_web_server_generalization_plan.md](./blob_web_server_generalization_plan.md)의 계획대로
  `blob_viewer/pdhd_blob_web_server.py`를 `blob_viewer/blob_web_server.py`로 일반화/복구했다.
* Plan 단계에서는 예상하지 못했던 버그 2건(잘못된 `sys.path` 삽입 경로, pyvista
  `Plotter.__init__()`에 없는 `multi_samples` 키워드 인자)이 실제 실행 검증 중 드러나 함께
  수정했다.
* Success Criteria(§3의 실행 검증)는 PDHD 보정값 경로와 범용 기본값 경로 모두에서 통과했다 —
  두 경우 다 `ModuleNotFoundError` 없이 서버가 기동되고 blob/depo 메시가 정상적으로 로드됨을
  확인.
* `blob_viewer/blob_web_server_reference.md`를 작성해 trame/pyvista/VTK 렌더링 스택과 브라우저
  연결 원리를 코드 라인 참조와 함께 문서화했다.

---

## 4. Execution

### 4.1 Implementation Steps

1. **파일 이름 변경**: `blob_viewer/`가 전부 git 미추적 상태임을 확인한 뒤(`git mv`가 아니라
   `mv`로 처리), `pdhd_blob_web_server.py` → `blob_web_server.py`로 이름 변경. 다른 어떤 파일도
   이 이름을 참조하지 않음을 grep으로 재확인.
2. **죽은 코드 제거**: `parse_args()`(정의되지 않은 `OUTPUT_DIR`/`ANODE_INDEX`/`V_DRIFT`/
   `T_OFFSET`/`RESPONSE_PLANE_X`/`SUCCESS_FRAC_WITHIN_1SIGMA`/`N_OUTLIER_PLOTS`를 참조하던,
   호출되지 않는 함수) 삭제.
3. **없어진 모듈 복구**: `from pdhd_blob_to_vtu import _load_and_undrift,
   clusters2blobs_surface_vtk`를 제거하고, 같은 파일 안에 두 함수를 새로 정의:
   - `_load_and_undrift(cluster_file, v_drift, t_offset, response_plane_x)`: 기존
     `utils.load.load_cluster_data`로 그래프를 읽은 뒤,
     `wirecell.img.converter.undrift_blobs(cgraph, speed=v_drift*units.mm/units.us,
     time=t_offset*units.us, x0=response_plane_x*units.mm)`를 그대로 호출 — 물리 변환은
     재구현하지 않고 상위 패키지 것을 그대로 재사용.
   - `_blobs_to_polydata(cgraph)`: `wirecell.img.converter.orderpoints`/`extrude`로 각 blob의
     점/셀 연결정보를 얻고, `pv.PolyData(points, faces=...)` 형식(`[면의 점 개수, 점 인덱스...]`
     플랫 배열)으로 직접 조립. 각 blob의 숫자형 필드(`val` 등)를 `cell_data`에 면 개수만큼
     반복 저장해 `--scalars`로 고를 수 있게 함.
4. **Detector 상수 일반화**: `__main__`의 argparse에 `--v-drift`/`--t-offset`/
   `--response-plane-x`를 추가, 기본값은 `wirecell.img.converter.undrift_blobs` 자체의 범용
   기본값(1.6mm/us, 0, 0)으로 설정 — PDHD 보정값은 이제 하드코딩이 아니라 호출 시 명시적으로
   넘기는 값.
5. **렌더 품질 설정**: `--width`/`--height`(기본 1920x1080)/`--multi-samples`(기본 8)/
   `--depo-theta-res`/`--depo-phi-res` 추가. `serve_blobs()`에서
   `pv.Plotter(window_size=(width, height), line_smoothing=True, point_smoothing=True,
   polygon_smoothing=True)` + `pv.global_theme.multi_samples = multi_samples` 반영.
6. **문서 작성**: `blob_viewer/blob_web_server_reference.md` (원리 설명, 사용자 요청 문서),
   `docs/blob_web_server_generalization_plan.md` (본 Task의 Plan 문서), 본 Report 문서.

### 4.2 Observation

**버그 1 (Plan 단계에서 예상 못함): `sys.path` 삽입 경로가 틀림.** 첫 실행 시
`ModuleNotFoundError: No module named 'utils'` 발생. 원인: 기존 코드가
`sys.path.insert(0, os.path.dirname(__file__))`로 **`blob_viewer/` 자기 자신**을 경로에
추가했는데, 실제 `utils/load.py`는 `scripts/utils/`에 있다(`blob_viewer/`엔 `utils/`가 없음).
이 파일이 원래 `scripts/`에 있다가 `blob_viewer/`로 옮겨지면서 이 줄이 갱신되지 않았던 것으로
보인다. `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))`로 수정.

**버그 2 (Plan 단계에서 예상 못함): `multi_samples`는 `Plotter()` 생성자 인자가 아님.**
`pv.Plotter(..., multi_samples=8)`로 호출하니 `TypeError: Plotter.__init__() got an unexpected
keyword argument 'multi_samples'` 발생. 확인해보니 이 pyvista 버전(0.48.4)에서 MSAA 샘플 수는
생성자 인자가 아니라 **전역 테마 설정** `pv.global_theme.multi_samples`로 조절해야 함. `Plotter()`
호출 전에 `pv.global_theme.multi_samples = multi_samples`를 먼저 설정하도록 수정.

**실행 로그 (수정 후, PDHD 보정값)**:
```
python blob_viewer/blob_web_server.py data/pdhd/test_point_depo/clusters-apa-1.tar.gz \
    --v-drift 1.6 --t-offset 314.5 --response-plane-x 3430.47 --port 18080
```
```
[INFO] Auto-detected depo file: data/pdhd/test_point_depo/depos-drifted-1.zip
[INFO] Building depo center-to-3-sigma density shells...
[INFO] 24 blob faces loaded from data/pdhd/test_point_depo/clusters-apa-1.tar.gz, depo density shells (240 cells) from data/pdhd/test_point_depo/depos-drifted-1.zip
[INFO] Starting web server on port 18080 -- open http://localhost:18080 ...
App running at:
 - Local:   http://0.0.0.0:18080/
```
(`bad X server connection. DISPLAY=` 경고는 EGL off-screen 렌더링으로 정상 폴백되는, 무해한
경고 — `blob_web_server_reference.md` §1에 문서화.)

**실행 로그 (범용 기본값, detector 인자 없음)**: 같은 `clusters-apa-1.tar.gz`에 detector
인자를 전혀 주지 않고 실행 — 동일하게 `24 blob faces loaded`로 정상 기동 확인(절대 x 위치만
미보정 상태로 남는 것은 의도된 동작).

두 실행 모두 `timeout`으로 서버를 종료시킨 뒤 `ps aux`로 잔여 프로세스가 없음을 확인.

---

## 5. Result Verification & Validation

### 5.1 Evaluation

| Success Criteria (Plan §3) | 결과 |
|---|---|
| `python -m py_compile blob_viewer/blob_web_server.py` 통과 | **PASS** |
| PDHD 보정값으로 `ModuleNotFoundError` 없이 기동 + blob 로드 로그 | **PASS** (버그 2건 수정 후) |
| 범용 기본값(무보정)으로도 동일하게 기동 + blob 로드 로그 | **PASS** |
| `blob_web_server_reference.md`가 원리/코드 대응/설정 근거를 모두 포함 | **PASS** (자체 점검 —
  §1 큰 그림, §2 3계층 스택, §3 브라우저 연결, §4 해상도 설정과 실측 근거, §5 코드 훑어보기,
  §6-7 사용법/트러블슈팅 전부 라인 참조 포함) |

브라우저로 직접 열어 화질 개선을 시각적으로 확인하는 것은 이 세션에서는 수행하지 않음(서버
프로세스만 기동 확인 후 `timeout`으로 종료) — §6 Next Action 참고.

### 5.2 Conclusion

**[결과 달성]** — 모든 Success Criteria를 통과했으므로 Task Termination으로 이동.

---

## 6. Task Termination

### 6.1 Summary

* `blob_viewer/blob_web_server.py`가 이제 PDHD 전용 하드코딩 없이 임의의 cluster/depo 파일
  쌍에 대해 동작하며, 없어졌던 blob→3D 메시 변환 기능을 `wirecell.img.converter`의 기존
  유틸(`undrift_blobs`/`orderpoints`/`extrude`)을 재사용해 복구했다(새 물리/기하 로직을
  중복 구현하지 않음).
* 인터랙티브 렌더링 해상도(1024x768 → 1920x1080 기본값)와 안티에일리어싱(line/point/polygon
  smoothing)을 사용자가 확인한 의미("뷰어 자체 품질 상향")대로 개선했다.
* `blob_viewer/blob_web_server_reference.md`에 trame/pyvista/VTK 3계층 스택, 브라우저-서버
  연결이 실제로 이뤄지는 방식(WebSocket, off-screen EGL 렌더링, SSH 포트포워딩), 이번에 바꾼
  해상도 설정의 원리, 코드 각 함수의 역할을 코드 라인 참조와 함께 정리했다 — 렌더링/브라우저
  연결 지식이 없는 사용자가 스스로 이해할 수 있도록 하는 것이 목표였다.

### 6.2 Next Action

* 브라우저로 직접 열어 시각적으로 화질 개선(1920x1080 + smoothing)을 체감 확인하고, 필요하면
  `--width`/`--height`/`--multi-samples`를 추가로 조절.
* PDVD 등 다른 detector의 cluster 파일이 실제로 생기면, 이번에 일반화한 CLI(`--v-drift`/
  `--t-offset`/`--response-plane-x`)로 그 detector의 보정값을 넘겨 동일하게 검증.
* `docs/img_3d_imaging_workflow/`의 Stage 2(WCT job graph tiling cross-validation)가 진행되면,
  그 결과물(`clusters-apa-true-tiled-*.tar.gz`)도 이 뷰어로 바로 열어볼 수 있는지 확인 —
  파일명 규칙이 다르면 `_find_depo_file`의 정규식을 그때 다시 확인해야 함.

---

## Related Documents

* **Parent docs:**
  - [blob_web_server_generalization_plan.md](./blob_web_server_generalization_plan.md): 본
    실행/검증이 따른 계획 문서.
* **Child docs:** 없음.
* **Sibling docs:**
  - [../blob_viewer/blob_web_server_reference.md](../blob_viewer/blob_web_server_reference.md):
    이번 Task로 작성된, 렌더링 스택/브라우저 연결 원리 설명 문서.
  - [time_offset_calibration.md](./time_offset_calibration.md): 이 Task가 재사용한 undrift
    공식과 PDHD 보정값의 출처.
