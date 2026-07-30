# Sensitive-Volume: Sources and How to Derive Full 3D Bounds

## Summary

`scripts/utils/wires.py`의 `face_sensitive_bounds()`는 wire store JSON만으로 $(y,z)$ 경계만 근사한다 (자체 docstring에 명시된 한계).
전체 3D sensitive volume이 필요할 때, 어떤 데이터 소스에서 어떤 값을 가져와야 하는지, 그리고 WCT C++ 코드(`AnodePlane.cxx`)가 실제로 어떻게 이 값을 계산하는지 정리한 문서다.

필요한 데이터 파일: 이 저장소에 새로 추가해야 할 데이터 파일은 없다. 아래 두 소스 모두 이미 디스크에 존재한다.
1. wire geometry JSON: `wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2` (이미 이 저장소 안에 있음) — $y,z$ 경계, 그리고 각 face 내 3개 평면(U/V/W)의 $x$ 위치(약 10mm 폭, drift 전체 길이 아님)를 제공.
2. `simparams.jsonnet`의 `det.volumes` (`/nfs/data/1/yujin/wire-cell-toolkit/cfg/pgrapher/experiment/pdhd/simparams.jsonnet`, `$WIRECELL_PATH`를 통해 sibling 저장소 `wire-cell-toolkit/cfg`에서 resolve됨. 이 저장소의 `wire-cell-cfg/`에는 사본이 없다) — anode cutoff/response/cathode plane의 $x$ 위치(즉 drift 방향 전체 범위)를 제공.

## 1. wire store JSON — $y,z$ 경계, 그리고 좁은 $x$ 범위

`wirecell.util.wires.schema`의 `Point`/`Wire`/`Plane`/`Face`/`Anode`/`Store`는 전부 순수 namedtuple이며 bounds/origin 필드가 없다 (`docs/geometry/wirecell_wires_reference.md` 참고). 즉 sensitive-volume 경계는 wire store 자체에 저장된 필드가 아니라, wire 끝점들로부터 계산해야 하는 파생값이다.

`protodunehd-wires-larsoft-v1.json.bz2`를 실제로 로드하면: 4개 `anode`, 8개 `face`, 24개 `plane`, 22208개 `wire`, 44416개 `point`.

`wirecell-util wires-info <file>` (`wire-cell-python/wirecell/util/wires/info.py`)를 이 파일에 대해 실행한 실측값(8개 anode/face 전부):

```
anode:0 face:0 X=[-3532.02,-3522.19]mm Y=[76.10,6066.70]mm Z=[-1.00,2305.73]mm
anode:0 face:1 X=[-3627.72,-3617.89]mm Y=[76.10,6066.70]mm Z=[-1.00,2305.73]mm
anode:1 face:0 X=[3615.89,3625.72]mm  Y=[76.10,6066.70]mm Z=[-1.00,2305.73]mm
anode:1 face:1 X=[3520.19,3530.02]mm  Y=[76.10,6066.70]mm Z=[-1.00,2305.73]mm
anode:2 face:0 X=[-3532.02,-3522.19]mm Y=[76.10,6066.70]mm Z=[2319.60,4626.33]mm
anode:2 face:1 X=[-3627.72,-3617.89]mm Y=[76.10,6066.70]mm Z=[2319.60,4626.33]mm
anode:3 face:0 X=[3615.89,3625.72]mm  Y=[76.10,6066.70]mm Z=[2319.60,4626.33]mm
anode:3 face:1 X=[3520.19,3530.02]mm  Y=[76.10,6066.70]mm Z=[2319.60,4626.33]mm
```

anode 0/1은 $z\in[-1.00,2305.73]$mm 구간을, anode 2/3은 $z\in[2319.60,4626.33]$mm 구간을 담당한다 (PDHD의 2$\times$2 APA 배치 중 $z$ 방향 분할). `X=[...]`의 폭이 약 10mm밖에 안 되는 이유는 이 범위가 한 face 안의 U/V/W 3개 평면 간 간격만을 나타내기 때문이며, drift 전체 길이(수 미터)와는 무관하다. 이는 `face_sensitive_bounds()`의 docstring이 이미 명시한 한계와 정확히 일치한다.

관련 CLI 명령 (전부 `wirecell.util.wires.info` 기반):
* `wirecell-util wires-info FILE`: 위 표 형식 출력.
* `wirecell-util wire-summary FILE`: 동일 정보를 `det -> anode -> face -> plane` 중첩 dict로, 각 레벨에 `bb: {minp, maxp}`를 담아 반환 (스크립트에서 파싱하기 편함).
* `wirecell-util wires-volumes -a ANODE_DIST -r RESPONSE_DIST -c CATHODE_DIST FILE`: wire store의 평면 $x$ 위치에 사용자가 지정한 anode/response/cathode 오프셋을 더해 `params.det.volumes` jsonnet 조각을 **생성**하는 도구다. `simparams.jsonnet`의 `det.volumes` 블록 자체가 이 명령으로 만들어졌을 가능성이 높다. 즉 cathode $x$는 wire store만으로는 유도할 수 없고, 이 오프셋이 별도로 필요하다.

## 2. `simparams.jsonnet`의 `det.volumes` — drift 방향 전체 범위

파일: `/nfs/data/1/yujin/wire-cell-toolkit/cfg/pgrapher/experiment/pdhd/simparams.jsonnet` (`$WIRECELL_PATH`로 resolve됨, `wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet`이 이미 `local params = import 'pgrapher/experiment/pdhd/simparams.jsonnet';`로 불러오고 있는 바로 그 파일).

`det.volumes`는 anode(APA)마다 두 face의 `{anode, response, cathode}` $x$ 위치(mm)를 담은 배열이다. `wire-cell-python`이 설치된 venv에는 jsonnet 평가용 `_jsonnet` 파이썬 바인딩이 이미 있으므로, `wire-cell`을 직접 실행하지 않고도 다음처럼 값을 뽑아낼 수 있다:

```python
import _jsonnet, json
snippet = '''
local params = import 'pgrapher/experiment/pdhd/simparams.jsonnet';
{ bounds: params.det.bounds, volumes: params.det.volumes }
'''
out = _jsonnet.evaluate_snippet("x.jsonnet", snippet,
                                 jpathdir=["/nfs/data/1/yujin/wire-cell-toolkit/cfg"])
data = json.loads(out)
```

실측 결과 (mm, internal WCT length unit):

| anode(store index) | face | anode $x$ | response $x$ | cathode $x$ | drift 범위 $[\min,\max]$ |
|---|---|---|---|---|---|
| 0 | 0 | -3520.945 | -3430.465 | -1.5875 | [-3520.945, -1.5875] |
| 0 | 1 | -3625.855 | -3716.335 | -7145.2125 | [-7145.2125, -3625.855] |
| 1 | 0 | 3625.855 | 3716.335 | 7145.2125 | [3625.855, 7145.2125] |
| 1 | 1 | 3520.945 | 3430.465 | 1.5875 | [1.5875, 3520.945] |
| 2 | 0 | -3520.945 | -3430.465 | -1.5875 | [-3520.945, -1.5875] |
| 2 | 1 | -3625.855 | -3716.335 | -7145.2125 | [-7145.2125, -3625.855] |
| 3 | 0 | 3625.855 | 3716.335 | 7145.2125 | [3625.855, 7145.2125] |
| 3 | 1 | 3520.945 | 3430.465 | 1.5875 | [1.5875, 3520.945] |

`store.anodes` 리스트 인덱스와 `det.volumes` 리스트 인덱스는 1:1로 대응한다 (`det.volumes[n].wires == n`, 실측 anode/face의 wire-plane $x$와 `det.volumes[n].faces[i].anode`가 1mm 이내로 일치함을 확인했다; wire store는 실제 설치 좌표, `det.volumes`는 `apa_cpa`/`apa_w2w`/`plane_gap` 등 설계 상수로부터 계산된 값이라 소수점 이하 차이는 있음).

참고로 `det.bounds`(`{tail: (-4,0,0)m, head: (4,6.1,7)m}`)는 anode/face별 값이 아니라 전체 검출기를 넉넉히 감싸는 단일 rough box이며, jsonnet 주석에도 "필수는 아니고 jsonnet 쪽에서 쓰기 편하라고 둔 값"이라고 되어 있다 — 개별 anode/face의 sensitive volume에는 쓰지 않는다.

## 3. C++ ground truth — `AnodePlane.cxx`의 실제 `sensvol` 계산

`wire-cell-toolkit/gen/src/AnodePlane.cxx(#L228-317)` (`IAnodeFace` 생성자)는 실제로 각 `IAnodeFace::sensitive()`에 쓰는 `BoundingBox`를 계산하는 로직이다. 

평면(U/V/W)마다:
1. `bb = ws_store.bounding_box(ws_plane)` — 그 평면의 wire 끝점들로부터 얻은 $(x,y,z)$ box, 코너 `v1`, `v2`.
2. `mean_pitch = (pitchmax - pitchmin) / (nwires - 1)` — 그 평면의 평균 pitch 간격.
3. `pext`: pitch 방향이 $z$축에 가까우면(`|pitch_dir.z| > 0.999`) $z$ 방향으로, $y$축에 가까우면 $y$ 방향으로 `0.5 * mean_pitch`만큼 확장하는 벡터 (즉 pitch 방향으로만 반-피치 패딩).
4. `p1 = (anode_x, min(v1.y,v2.y), min(v1.z,v2.z)) - pext`
5. `p2 = (cathode_x, max(v1.y,v2.y), max(v1.z,v2.z)) + pext`
6. 이 `{p1,p2}` box를 그 평면의 sensitive volume 후보로 `bbvols`에 저장.

3개 평면 모두 처리한 뒤:
```
sensvol = bbvols[0]
for bb in bbvols[1:]:
    sensvol = box_intersect(sensvol, bb)
```
즉 **U/V/W 3개 평면이 각각 추정한 box의 교집합**이 최종 `sensvol`이다. $x$는 세 평면 모두 동일한 `anode_x`/`cathode_x`를 쓰므로 교집합에서 변하지 않는다. $y,z$만 평면마다 (trapezoidal 경계로 인해) 미세하게 다를 수 있어 교집합으로 좁혀진다.

`scripts/utils/wires.py`의 `face_sensitive_bounds()`는 이 교집합+반피치패딩 로직을 재현하지 않고, 모든 wire 끝점의 단순 union bounding box를 쓴다 (docstring에 이미 명시된 근사). 이번 확인으로 그 차이의 크기까지 특정할 수 있다: 반피치 패딩은 pitch $\approx$4.67-4.79mm 기준 $\pm$2.3-2.4mm 수준이고, 세 평면 교집합에 의한 축소분은 이 파일에서는 `wires-info`가 보고하는 세 평면의 $Y,Z$ 범위가 서로 거의 동일해 무시할 만하다. grid depo 배치처럼 mm~cm 단위 spacing을 다루는 용도에는 `face_sensitive_bounds()`의 근사로 충분하다.

## 4. PDHD anode 1 (이 저장소 기본값) 최종 근사 sensitive volume

`ANODES="1"`(`run_single_point.sh`/`run_grid_points.sh` 기본값)에 대해, 위 두 소스를 합친 근사 범위 (cm, `wc.point(..., wc.cm)` 관례에 맞춤):

| face | $x$ (drift) [cm] | $y$ [cm] | $z$ [cm] |
|---|---|---|---|
| 0 | [362.5855, 714.52125] | [7.610, 606.670] | [-0.100, 230.573] |
| 1 | [0.15875, 352.0945] | [7.610, 606.670] | [-0.100, 230.573] |

$x$는 `det.volumes[1]`(§2 표)에서, $y,z$는 `wirecell-util wires-info`(§1)에서 가져온 값이다. `run_grid_points.sh`의 `GRID_BOUNDS` 자리표시자(`100 200 250 350 50 150`)는 이 표의 값으로 교체해서 쓰면 된다 — 단, drift 방향 범위가 3.5m가 넘으므로 `--dx` 기본값(10mm)을 그대로 쓰면 격자점이 350개 이상 나올 수 있음에 유의(전체 볼륨을 다 채울 필요가 없다면 관심 있는 부분 범위로 좁혀서 지정).

## 5. Response Plane과 Anode Plane을 구분하는 이유

`util/docs/wct-x-planes.org`(wire-cell-toolkit)에 정의가 명시되어 있다.

> "response :: This is a plane between the anode and cathode. It represents the boundary separating the region where the drift field is considered uniform and the region governed by the detailed 2D field response." (line 89-93)
> "origin :: the distance along the nominal drift direction from the beginning of the FR data to the collection plane. ... For popular FR calculations using GARFIELD and wire detectors, this value is typically 10cm." (line 227-234)

즉 response plane은 drift volume을 물리적으로 서로 다른 두 모델이 적용되는 두 구간으로 나누는 경계다.

* **cathode ~ response** ("bulk"): drift field가 균일하다고 가정 가능한 구간. 여기서는 개별 wire에 대한 유도전류를 계산할 필요 없이, 단순한 1D drift + longitudinal/transverse diffusion + electron-lifetime attenuation 모델만으로 충분하다.
* **response ~ anode** ("near"): wire에 가까워지면서 여러 wire에 걸쳐 유도전류가 위치에 민감하게 발생하는 구간. 이 구간의 물리는 Garfield로 미리 계산한 2D field response 파일(`Response::Schema::FieldResponse`, `util/inc/WireCellUtil/Response.h`)로 표현되며, 이 계산은 collection plane 기준 10cm 폭(`response_plane: 10*wc.cm`)에 대해서만 이루어진다.

이렇게 나누는 이유는 계산 비용이다: wire 단위로 위치에 민감한 field response를 수 미터에 달하는 drift 전체 길이에 대해 Garfield로 계산하는 것은 비현실적이므로, 근접 10cm 슬랩만 상세 계산하고 나머지 대부분(수 미터)은 훨씬 저렴한 analytic diffusion 모델로 대체한다.

## 6. depo 생성 위치에 따른 처리 차이 (`Drifter.cxx`)

`gen/src/Drifter.cxx`(`Drifter::insert`, line 117-186)와 `gen/inc/WireCellGen/Drifter.h`(`CoordRegion`, line 157-208)가 실제 분기 로직을 담고 있다. 모든 depo는 최종적으로 동일한 목표 위치 `respx`(config의 `response` plane 절대 $x$)로 옮겨진다 — 어느 구간에서 생성됐는지는 **그 과정에서 어떤 물리를 적용하는지**만 바꾼다.

depo의 시작 위치 `pos.x()`가 먼저 `near`(anode~response)와 `bulk`(cathode~response) 두 `CoordRegion` 중 어디에 속하는지 판정된다 (`xr.near.inside(...)` / `xr.bulk.inside(...)`).

* **Bulk에서 생성된 경우** (`direction=1.0`, 즉 cathode와 response 사이, 이 저장소 point depo 스크립트들이 쓰는 `x_start`가 보통 여기 해당): 진짜 drift 물리가 전부 적용된다.
  * `dt = (respx - pos.x()) / speed`
  * 전하 손실: `absorbprob = 1 - exp(-dt/lifetime)` (`m_fluctuate`가 켜져 있으면 이항분포로 요동까지 반영)
  * 확산: `dL, dT = sqrt(2*D*dt + dL0^2)` (longitudinal/transverse 각각)
* **Near에서 생성된 경우** (`direction=-1.0`, 즉 response와 anode 사이, wire 바로 앞 ~10cm 슬랩): 코드 주석 그대로 "Back up in space and time. This is a best effort fudge." (`wire-cell-gen#22` 이슈 참조).
  * `dt = |respx - pos.x()| / speed`
  * 전하: `Qf = Qi` (변화 없음)
  * 확산 시그마: 변화 없음 (diffusion/absorption 관련 블록 자체를 건너뜀)
  * 즉 "이 depo가 원래부터 response plane에서 생성된 것"처럼 위치·시간만 이동시키는 근사적 편법이며, 실제 drift 물리(확산 성장, lifetime에 의한 전하 손실)는 반영되지 않는다.

두 경우 모두 `pos.x(respx)`로 끝나므로, 이후 `DepoTransform`(`gen/src/DepoTransform.cxx:180-209`, 실제 신호 생성 단계)은 depo가 원래 near였는지 bulk였는지 구분하지 않는다. `DepoTransform`이 하는 검사는 `Aux::sensitive(*depos, face)`(`aux/src/DepoTools.cxx`)뿐이며, 이는 `face->sensitive()`(anode_x~cathode_x, §3)에 대한 단순 포함 여부 확인이다 — `Drifter`를 거친 depo는 이미 `respx`(당연히 그 구간 안)에 있으므로 이 시점에는 사실상 통과 확인(pass-through)에 불과하다.

**두 영역 어디에도 속하지 않는 depo** (cathode보다 바깥, 또는 anode보다 wire에 더 가까운/넘어선 위치)는 `Drifter::insert`에서 조용히 드롭된다 (`xrit == m_xregions.end()` 이면 `return false`, `n_dropped` 카운터만 증가, clamping이나 경고 없음).

### 이 저장소의 grid/point depo 생성에 대한 함의

이 저장소의 `sim.tracks()` 기반 파이프라인(`wct-sim-nf-sp-img-bdf.jsonnet`/`-grid.jsonnet`)은 `TrackDepos` -> `Drifter` -> ... 순서를 그대로 쓰므로 위 로직이 그대로 적용된다.

* `x_start`(또는 grid 격자의 $x$)를 **response~cathode(bulk) 구간**에 두면, drift 거리에 비례해 diffusion sigma가 자라고 lifetime에 따라 전하가 줄어드는 실제 물리가 반영된다. `x`에 따른 확산/전하손실 의존성을 검증하려는 목적이라면 이 구간을 써야 한다.
* $x$를 **response~anode(near) 구간**(wire에서 10cm 이내)에 두면, diffusion/absorption이 전혀 적용되지 않는 "fudge" 경로를 타게 되어, 원래 그 위치에서 생성된 depo의 실제 확산 정도를 과소평가한다. anode1/face1 기준(§4) `response` $x$=343.0465cm, `anode` $x$=352.0945cm이므로, `x`$\in$[343.05, 352.09]cm는 near(비물리 fudge), `x`$\in$[0.16, 343.05]cm는 bulk(실제 물리)에 해당한다.
* grid의 $x$ 범위를 anode 근처까지 채우고 싶다면 이 경계를 인지하고 있어야 하며, near 구간 결과를 bulk 구간과 같은 잣대로(예: diffusion sigma 대 drift distance) 비교하면 안 된다.

## 7. 재현 방법 요약

```bash
source /nfs/data/1/yujin/wire-cell-python/venv/bin/activate
export PYTHONPATH="/nfs/data/1/yujin/wire-cell-python/venv/lib/python3.11/site-packages:/nfs/data/1/yujin/wire-cell-python"

# y,z 경계 (그리고 좁은 x 범위) - wire store JSON만 필요
wirecell-util wires-info wire-cell-cfg/det_geo/protodunehd-wires-larsoft-v1.json.bz2

# x(drift) 전체 범위 - simparams.jsonnet 필요 ($WIRECELL_PATH에 wire-cell-toolkit/cfg 포함)
python -c "
import _jsonnet, json
snippet = '''
local params = import 'pgrapher/experiment/pdhd/simparams.jsonnet';
params.det.volumes
'''
print(json.dumps(json.loads(_jsonnet.evaluate_snippet('x.jsonnet', snippet,
      jpathdir=['/nfs/data/1/yujin/wire-cell-toolkit/cfg'])), indent=2))
"
```
