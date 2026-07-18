# `wirecell.bee` Reference

## Summary

`../wire-cell-python/wirecell/bee/`(패키지 `wirecell.bee`, CLI 진입점 `wirecell bee ...`)에 대한 구조/동작 원리 정리 문서다.
이 패키지는 딱 세 개의 짧은 파일(`data.py`, `ana.py`, `__main__.py`)로 이루어져 있고, 역할은 **"Bee" JSON 데이터 포맷을 파이썬 객체로 읽어 들이고, 그 내용을 요약(summary)하거나 두 파일을 비교(diff)하는 것**뿐이다. 3D 렌더링이나 웹 UI는 이 패키지에 전혀 없다 — Bee는 BNL이 운영하는 별도의(이 저장소 바깥의) 웹 서비스이고, `wirecell.bee`는 그 서비스가 먹는/뱉는 JSON 파일을 다루는 보조 도구일 뿐이다. 이 문서의 §1과 §7은 그 "웹 브라우저 쪽" 맥락을 최대한 쉽게 채워 넣기 위한 부분이다.

```bash
source ../wire-cell-python/venv/bin/activate
export PYTHONPATH="/home/yujin/projects/WireCell"
wirecell bee --help
```

---

## 1. Bee란 무엇인가 (웹 뷰어와 이 패키지의 관계)

**Bee**는 Wire-Cell 커뮤니티(BNL)가 운영하는 3D 이벤트 디스플레이 웹사이트다 (`https://www.phy.bnl.gov/twister/bee`). 사용자가 특정 포맷의 JSON(또는 그 JSON들을 담은 zip)을 업로드하면, 웹사이트가 그 안의 3D 점(point cloud)들을 브라우저에서 회전/확대 가능한 3D 산점도(scatter plot)로 그려준다. 원리 자체는 아주 단순해서, matplotlib으로 `ax.scatter(x, y, z, c=q)`를 그리는 것과 개념적으로 동일하다 — 다만 그것을 각 사용자의 로컬 파이썬 환경이 아니라 브라우저에서, 마우스로 회전시켜 가며 볼 수 있게 만든 것이 Bee다. `type`(알고리즘 이름, 예: `"rec"`/`"bdf"`)이 다른 여러 JSON을 하나의 이벤트에 올려두면, 웹 UI에서 레이어 켜고 끄듯 서로 다른 알고리즘 결과를 겹쳐보거나 비교해볼 수 있다.

중요한 점: **`wirecell.bee` 패키지는 이 웹사이트의 코드가 아니다.** 이 저장소(`wire-cell-python`) 안에는 브라우저에서 실행되는 JS/렌더링 코드가 전혀 없다. `wirecell.bee`가 실제로 하는 일은:

1. Bee가 요구하는 JSON 스키마(§3)에 맞춰 파일을 만들거나 읽는 것 (`data.py`)
2. 읽어 들인 내용을 텍스트로 요약하거나 두 파일을 비교하는 것 (`ana.py`, `__main__.py`)

즉 이 패키지는 Bee 웹사이트에 **업로드하기 전/후**에 그 데이터를 파이썬에서 검증·분석하기 위한 헬퍼일 뿐이고, 실제 업로드와 3D 렌더링은 순수 웹의 영역이다. 이 저장소(`wirecell-img-evaluation`)에서 실제 업로드가 어떻게 이뤄지는지는 `wire-cell-cfg/pdhd/upload-to-bee.sh`에서 볼 수 있다 — `curl`로 로그인 페이지에서 Django CSRF 토큰을 받아온 뒤, 그 토큰과 함께 zip 파일을 `.../bee/upload/`에 POST하면 서버가 UUID를 돌려주고, `.../bee/set/<UUID>/event/list/` 같은 URL이 곧 "이 데이터를 볼 수 있는 웹페이지 링크"가 된다. 이 스크립트가 하는 것이 딱 "웹 브라우저로 하는 일"의 전부이며, 그 뒤로는 사람이 그 URL을 브라우저로 열어서 보는 것 외에 별다른 로직이 없다.

---

## 2. 패키지 구성

| 파일 | 역할 |
|---|---|
| `data.py` | Bee JSON/zip 파일을 로드해서 `Cluster` / `Grouping` / `Ensemble` / `Series` 객체 계층으로 구조화. |
| `ana.py` | 그 객체 계층을 원하는 깊이(depth)까지 들여쓰기된 텍스트로 요약하는 `Summary` 클래스. |
| `__main__.py` | `wirecell bee summary` / `wirecell bee diff` 두 개의 CLI 서브커맨드. `data.load()` + `ana.Summary`를 얇게 감싼 것. |

---

## 3. Bee JSON 데이터 포맷

Bee 공식 문서(`https://bnlif.github.io/wire-cell-docs/viz/uploads/`, `data.py` 상단 docstring에 링크됨)가 정의하는 스키마는 다음과 같다.

| 필드 | 필수 여부 | 의미 |
|---|---|---|
| `x`, `y`, `z` | **필수** | 3D 점 좌표 배열 (단위: cm). 세 배열의 길이가 같아야 하며, 인덱스 `i`가 하나의 점을 이룬다. |
| `q` | 선택 | 각 점의 전하량(charge). |
| `cluster_id` | 선택 | 같은 클러스터(연결된 덩어리)에 속한 점들을 묶는 정수 ID. |
| `runNo`, `subRunNo`, `eventNo` | 선택 | DAQ 이벤트 식별 번호. |
| `geom` | 선택 | 검출기 지오메트리 이름 (기본값 `"uboone"`; 이 저장소는 `"protodunehd"` 사용). |
| `type` | 선택 | 이 JSON을 생성한 알고리즘 이름 (예: `"rec"`, `"bdf"`, `"cluster"`). |

`x`,`y`,`z`,`q`만 있으면 하나의 점(point)이 정의되고, `cluster_id`가 있으면 그 점들이 클러스터로 묶인다 — `wirecell.bee`의 객체 계층(§4)은 바로 이 `cluster_id` 기준 묶음을 그대로 반영한 것이다.

**파일/디렉터리 명명 규칙**: Bee에 올리는 zip은 `data/<eventID>/<eventID>-<algName>.json` 구조를 갖는다 (예: `data/0/0-apa0-rec.json`, `data/0/0-apa0-bdf.json` — 이 저장소의 `wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py`가 실제로 만드는 이름). `data.py`의 `parse_pathname()`은 파일 이름(확장자 뺀 stem)을 **첫 번째 `-`를 기준으로 딱 한 번만** 나눠서 `(index, algname)`을 뽑는다: `"0-apa0-rec"` → `index="0"`, `algname="apa0-rec"`. 이 `index`가 §4의 `Series`를 인덱싱하는 키가 되고, `algname`이 `Ensemble` 안에서 알고리즘을 구분하는 키가 된다.

(참고: 이 JSON을 실제로 만드는 CLI는 `wirecell.bee`가 아니라 이웃 패키지 `wirecell.img`의 `wirecell-img bee-blobs` 명령이다. 클러스터 그래프의 blob 볼륨을 `--sampling uniform/center`로 점 구름으로 샘플링해 위 스키마의 JSON을 뱉어준다. `wirecell.bee`는 그렇게 만들어진 JSON을 **읽는** 쪽만 담당한다.)

---

## 4. `data.py` — JSON을 객체 계층으로 구조화하기

객체 계층은 위에서 아래로 `Series → Ensemble → Grouping → Cluster → points` 순서다.

* **`Cluster(ident, points)`**: 같은 `cluster_id`를 공유하는 점들의 묶음. `points`는 `(N,3)` numpy 배열. 두 속성은 처음 접근할 때만 계산되어 캐시되는 lazy property다.
  * `kd`: `scipy.spatial.KDTree(points)` — 최근접 점 탐색용.
  * `pca_eigen`: `wirecell.util.points.pca_eigen(points)`가 반환하는 `(고유벡터 목록, 고유값 목록)` — 점 구름의 주축(principal axis)과 그 분산을 내림차순으로 준다.

* **`Grouping(index, algname, content)`**: 하나의 JSON 파일(§3 스키마 하나) 전체에 대응. `content`(JSON을 그대로 파싱한 dict)에서:
  * `self.name = content["type"]`, `self.rse = (runNo, subRunNo, eventNo)`, `self.geom`
  * `self.points`: `x`,`y`,`z` 세 배열을 쌓아 만든 `(N,3)` 배열
  * `self.clusters`: `cluster_id`별로 점 인덱스를 모아(`collections.defaultdict(list)`) 각각을 `Cluster`로 감싼 `dict`

* **`Ensemble = dict`**: 단순 타입 별칭. 같은 이벤트(`index`) 안에서 `algname → Grouping`으로 알고리즘별 결과를 모은 것 (예: `{"apa0-rec": Grouping(...), "apa0-bdf": Grouping(...)}`).

* **`Series(dict)`**: `index → Ensemble`. 여러 이벤트/여러 파일을 누적해서 담는 최상위 컨테이너. 누적용 메서드 세 개가 있는데 이름 그대로 한 단계씩 아래 것을 감싼다:
  * `add_group(grp)`: `Grouping` 하나를 해당 `index`의 `Ensemble`에 추가 (없으면 새로 만듦).
  * `add_ensemble(ens)`: `Ensemble`(`algname → Grouping` dict) 하나를 통째로 순회하며 `add_group` 반복.
  * `add_series(ser)`: 다른 `Series` 하나를 통째로 순회하며 `add_ensemble` 반복. zip 하나에 여러 이벤트가 들어 있을 때 이걸로 병합한다.

* **`load_json(json_file)`**: JSON 파일 하나 → `Grouping` 하나. 파일명에서 `parse_pathname`으로 `(index, algname)`을 뽑고, 파일 내용을 그대로 `json.loads`해서 `Grouping(index, algname, content)`를 만든다.

* **`load_zip(zip_file)`**: zip 파일 하나 → `Series`. `wirecell.util.ario.load(zip_file)`로 zip을 지연 로딩되는(lazy) `dict`처럼 취급해서(`{멤버이름: 파싱된내용}`, `.json`/`.npy`와 `.gz`/`.bz2`/`.xz` 압축을 자동 판별해 해제 후 파싱), 각 멤버를 `Grouping`으로 만들고 `Series.add_group`으로 쌓는다.

* **`load(sources)`**: 최상위 공개 함수. `str`/`Path` 하나 또는 그 목록을 받아 확장자로 분기한다 — `.json`이면 `load_json` 결과를 바로 추가, `.zip`이면 `load_zip` 결과를 `add_series`로 병합, 그 외 확장자는 경고 로그만 남기고 건너뛴다. 여러 파일을 한 번에 넘기면 전부 같은 `Series`로 합쳐진다.

---

## 5. `ana.py` — 요약(Summary)과 비교(diff)의 원리

`levels = ["point","shape","cluster","grouping","ensemble"]`는 §4의 계층 구조를 얕은 것부터 깊은 것 순으로 나열한 목록이고, `level_index(lvl)`은 문자열이든 정수든 그 안에서의 인덱스(0~4)로 바꿔주는 헬퍼다.

`Summary(ser, level='cluster')`는 이 인덱스를 `self._level`로 들고 있다가, 재귀적으로 텍스트를 만들 때 "**어디까지 세부 내용을 펼쳐 보일지**"를 결정하는 기준으로 쓴다. 동작을 실제 조건으로 풀어보면:

* `cluster(cls, tab)`: 항상 `"Cluster: id:.. npts:.."` 한 줄은 찍는다. 거기에 더해,
  * `level <= level_index("shape")`(즉 요청 깊이가 `shape` 이하로 세밀할 때)면 PCA 고유벡터/고유값을 한 줄씩 덧붙인다.
  * `level <= level_index("point")`(요청 깊이가 `point`일 때)면 클러스터에 속한 점 좌표를 전부 덧붙인다.
* `grouping(grp, tab)`: `"Grouping ind:.. nclusters:.. npoints:.. rse:.. alg:.. type:.."` 한 줄을 찍는다. `level < level_index("grouping")`이면(요청 깊이가 `grouping`보다 세밀하면) 그 안의 각 `cluster()`를 재귀 호출해서 붙인다. 요청 깊이가 `grouping`이나 `ensemble`이면 여기서 멈춘다.
* `ensemble(ens, ind, tab)`: `"Ensemble <ind>"` 한 줄을 찍고, `level < level_index("ensemble")`이면 그 안의 각 `grouping()`을 재귀 호출한다.
* `series(ser)`: 최상위 진입점. `Series`의 모든 `(index, ensemble)` 쌍에 대해 `ensemble()`을 호출해서 이어붙인다.

정리하면 `depth`(=`level`) 파라미터는 "이 깊이까지는 헤더 한 줄, 이 깊이보다 세밀하면 자식들도 펼쳐서 보여줘"라는 하나의 임계값 역할을 한다:

| `depth` 값 | 실제로 보이는 것 |
|---|---|
| `ensemble` | 이벤트(Ensemble)별 한 줄 헤더만 |
| `grouping` | + 알고리즘(Grouping)별 한 줄 헤더(클러스터 개수/점 개수/rse 포함) |
| `cluster` (기본값) | + 클러스터별 한 줄 헤더(id, 점 개수) |
| `shape` | + 클러스터별 PCA 주축/고유값 |
| `point` | + 클러스터에 속한 모든 점의 실제 좌표 |

`diff` 커맨드는 별도의 비교 로직을 갖고 있지 않다 — 두 파일 각각에 대해 **같은 depth로 `Summary` 텍스트를 만든 뒤, 그 텍스트 두 개를 `difflib.unified_diff`로 비교**할 뿐이다. 즉 "무엇이 다른지"는 항상 "그 depth에서 `summary` 커맨드가 찍는 텍스트가 다른지"로 정의된다 — 예를 들어 `depth=cluster`(기본값)로 diff했는데 차이가 나면, 정확히 어떤 점 좌표가 다른지 보려면 `depth=point`로 다시 diff하거나 각 파일에 대해 `summary -d point`를 따로 찍어보면 된다.

---

## 6. CLI — `wirecell bee ...` (`__main__.py`)

`@context("bee")`는 `wirecell.util.cli`가 제공하는 공통 헬퍼로, "wirecell 하위 패키지들이 공유하는 표준 Click 그룹 + 로깅 설정"을 붙여준다 (다른 `wirecell-<pkg>` CLI들도 전부 이 데코레이터를 쓴다). 이 패키지는 그 위에 서브커맨드 두 개만 얹는다.

* **`wirecell bee summary [-d/--depth LEVEL] FILES...`**: 파일(`.zip` 또는 `.json`, 여러 개 가능)마다 `data.load(fname)`으로 `Series`를 만들고, `Summary(series, depth)`를 문자열로 찍는다. 파일 하나당 `"<파일명>:\n<요약텍스트>"` 형태로 출력.
* **`wirecell bee diff [-d/--depth LEVEL] FILE1 FILE2`**: 정확히 두 파일을 받아 각각 §5의 `Summary` 텍스트를 만든 뒤 `unified_diff`로 비교해서 출력.

---

## 7. 이 저장소에서의 전체 흐름 (End-to-end)

이 문서가 다루는 `wirecell.bee`는 아래 파이프라인의 **③, ④** 단계에만 관여한다.

1. **시뮬레이션/재구성**: `wirecell-img-evaluation`의 WCT 설정(`wire-cell-cfg/pdhd/wct-sim-nf-sp-img-bdf.jsonnet` 등)을 돌려 `clusters-apa-<N>.tar.gz` 같은 클러스터 그래프 파일을 만든다 (`wirecell.img` 패키지가 다루는 영역, `wirecell.bee`와 무관).
2. **Bee JSON으로 변환**: `wire-cell-cfg/pdhd/wct-img-2-bee-hd-bdf.py`가 anode별 클러스터 파일을 `wirecell-img bee-blobs` CLI(패키지: `wirecell.img`)에 넘겨, blob 볼륨을 점 구름으로 샘플링한 뒤 §3 스키마의 JSON(`data/0/0-apaN-rec.json`, `data/0/0-apaN-bdf.json`)으로 저장하고 `upload.zip`으로 묶는다.
3. **업로드 (여기가 유일한 "웹 브라우저" 관련 단계)**: `wire-cell-cfg/pdhd/upload-to-bee.sh`가 이 zip을 BNL Bee 서버로 업로드하고, 결과를 볼 수 있는 웹페이지 URL을 돌려준다. 이 시점부터 3D 렌더링/회전/레이어 토글은 순수 브라우저 쪽 일이며, `wirecell.bee`도 이 저장소의 다른 파이썬 코드도 관여하지 않는다.
4. **검증/분석 (다시 `wirecell.bee`)**: 업로드하기 전이나 후에, 같은 zip/json을 `wirecell bee summary`/`wirecell bee diff`로 열어 클러스터 개수·점 개수·rse가 예상대로 나왔는지 텍스트로 빠르게 확인하거나, `wirecell.bee.data.load()`로 직접 불러와 `Series`/`Grouping`/`Cluster` 객체를 파이썬에서 다뤄가며(PCA 축, KDTree 최근접 탐색 등) 커스텀 분석을 할 수 있다.
