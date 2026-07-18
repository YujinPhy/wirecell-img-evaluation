# Wire Geometry (`wirecell.util.wires`) in Wire-Cell Context

## Summary

wire geometry(와이어 기하 정보)의 데이터 구조에 대해 설명한 문서로 `wirecell.util.wires.persist`/`schema`코드의 docstring의 내용을 정리하였다. 또한 `utils/wires.py`가 이를 소비하는 방식을 정리한 문서다.

## 1. wire geometry가 왜 필요한가

WCT에서 하나의 wire plane(U/V/W 중 하나)은 서로 평행한 여러 개의 와이어로 이루어진다.
각 와이어는 검출기 안의 실제 3차원 직선(정확히는 두 끝점을 잇는 선분)이며, 그 와이어가 신호를 받는 pitch 방향 위치가 곧 "이 depo/전하가 어느 채널에 걸리는가"를 정하는 좌표축이다.
각 평면에 속한 와이어들의 실제 3D 끝점 좌표가 있어야 하고, 그 좌표를 담고 있는 파일이 wire store(와이어 기하 JSON 파일)이며, 이를 읽고 다루는 파이썬 코드가 `wirecell.util.wires.schema`/`persist`다.

## 2. `wire-cell-python/wirecell/util/wires/schema.py` — wire geometry의 데이터 모델
모듈 자체 docstring은 이 계층 구조를 다음과 같이 명시한다.
```
Detector -> Anode -> Face -> Plane -> Wire -> Point
```

### 2.1 각 타입의 의미
모든 타입은 `collections.namedtuple`로 정의된 불변 값 객체다.

| 타입         | 필드                                                | 의미                                                                                                                                 |
| ---------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `Point`    | `x, y, z`                                         | 전역(global) 좌표계의 한 위치. WCT 단위계(길이는 mm)로 표현된다.                                                                                       |
| `Wire`     | `ident, channel, segment, tail, head`             | 와이어 하나(=하나의 물리적 도체 세그먼트). `channel`은 그 와이어가 연결된 전자공학 채널 번호, `segment`는 채널 입력까지 사이에 낀 다른 와이어 개수, `tail`/`head`는 끝점 좌표 자체가 아니라 인덱스다. |
| `Plane`    | `ident, wires`                                    | 같은 평면에 속한 와이어들의 묶음. `wires`는 `Store.wires`에 대한 인덱스 리스트다.                                                                           |
| `Face`     | `ident, planes`                                   | anode(APA)의 한 면. `planes`는 `Store.planes`에 대한 인덱스 리스트다.                                                                            |
| `Anode`    | `ident, faces`                                    | anode(예: APA 하나). `faces`는 `Store.faces`에 대한 인덱스 리스트다. MicroBooNE처럼 면이 하나뿐인 검출기도 있고, ProtoDUNE-SP/HD처럼 anode 하나당 면이 둘인 경우도 있다.     |
| `Detector` | `ident, anodes`                                   | anode들의 묶음(검출기 전체).                                                                                                                |
| `Store`    | `detectors, anodes, faces, planes, wires, points` | 위 모든 타입의 리스트를 한데 모은 평평한(flat) 저장소.                                                                                                 |
  

> `Wire.tail`/`Wire.head`는 `Point` 객체 자체가 아니라 `Store.points` 리스트의 인덱스다.
> 실제 좌표를 얻으려면 `store.points[wire.tail]`, `store.points[wire.head]`처럼 한 단계 더 조회해야 한다.
> `Store`가 이런 간접 참조(인덱스) 구조를 쓰는 이유는 docstring에 명시돼 있는데, 여러 객체가 같은 대상(예: 같은 `Point`)을 서로 다른 문맥에서 함께 참조할 수 있게 하면서도 각 객체가 별도의 "포인터"를 직접 들고 다닐 필요가 없게 하기 위해서다.

### 2.2 정렬 순서 보장
docstring은 두 가지 정렬 규칙을 명시적으로 보장한다.

- `face.planes`는 전하가 드리프트하는 순서, 즉 U/V/W 순서로 정렬되어 있다.
	- `face.planes`를 순서대로 순회하면 자동으로 평면 0, 1, 2가 U, V, W에 대응한다.
- `plane.wires`는 pitch 방향으로 증가하는 순서로 정렬되어 있으며, 이 순서는 와이어 방향 벡터와 pitch 방향 벡터의 외적이 그 평면에 수직이면서 표류 방향과 반대 방향을 가리키는 관례를 따른다.
	- `plane.wires`를 순서대로 읽으면 자동으로 pitch가 증가하는 순서가 된다.

### 2.3 `ident`의 의미
대부분의 객체가 `ident` 필드를 갖으며 유일한 값으로 취급된다.
같은 대상이 여러 문맥(예: wire plane과 field response plane)에서 함께 참조된다면 그 `ident`가 반드시 일치해야 한다는 제약만 있을 뿐, 값 자체에 의미를 부여하지 않는다.
`utils/wires.py`의 `build_plane_geometries`는 이 `ident`를 직접 쓰지 않고, `Store` 안에서의 리스트 인덱스(`anode_index`, `face_index`)만으로 필요한 객체에 접근한다.

### 2.4 `wire_plane_id`/`plane_face_apa` — 비트로 압축된 평면 식별자
```python
layer_mask = 0x7
face_shift = 3
face_mask = 0x1
apa_shift = 4

def wire_plane_id(plane, face, apa):
    return (plane & layer_mask) | (face << face_shift) | (apa << apa_shift)

def plane_face_apa(wpid):
    return (wpid & layer_mask, (wpid & (1 << face_shift)) >> 3, wpid >> apa_shift)
```

이 두 함수는 `Store` 계층 구조와는 별개로, C++ `WirePlaneId`가 평면/면/APA 정보를 정수 하나에 비트로 압축해 넣는 방식을 파이썬에서 인코딩/디코딩하는 헬퍼다.
- `plane` 성분은 순차 인덱스(0, 1, 2)가 아니라 비트 마스크(U=1, V=2, W=4)로 인코딩된다.
- `layer_mask = 0x7`(하위 3비트)이 여러 평면의 조합(예: "U와 V 모두"를 뜻하는 값 3)까지 표현할 수 있도록 설계되었기 때문이다.
- `face`는 4번째 비트 하나, `apa`는 그보다 상위 비트 전체를 쓴다.

## 3. `persist.py` — wire store 파일 입출력
### 3.1 `todict`/`fromdict` — namedtuple ↔ JSON 직렬화

```python
def todict(obj):
    for typename in [c.__name__ for c in schema.classes()]:
        if typename == type(obj).__name__:
            cname = obj.__class__.__name__
            return {cname: {k: todict(v) for k, v in obj._asdict().items()}}
    if isinstance(obj, numpy.ndarray):
        ...
    if isinstance(obj, list):
        return [todict(ele) for ele in obj]
    return obj
```

`todict`는 `schema.py`에 정의된 타입(`Point`, `Wire`, `Plane`, `Face`, `Anode`, `Detector`, `Store`)의 인스턴스를 만나면 `{클래스이름: {필드이름: 값, ...}}` 형태의 중첩 딕셔너리로 바꾼다.
- 재귀적으로 리스트/다른 schema 객체를 파고든다.
- `numpy.ndarray`도 `{"array": {"shape": ..., "elements": ...}}` 형태로 직렬화할 수 있게 처리한다.

`fromdict`는 그 반대 방향으로, 딕셔너리에서 어떤 schema 클래스 이름을 발견하면 그 타입의 생성자에 각 필드를 재귀적으로 복원해 넣어준다.
`fromdict`에는 이전 버전 파일과의 호환 코드가 하나 남아 있는데, `Store` 딕셔너리에 `detectors` 키가 없으면(스키마에 `Detector`가 추가되기 전의 옛 파일) `anodes` 개수만큼 기본 `Detector`를 하나 만들어 채워 넣는다.

### 3.2 `load(name)` — 파일 경로 또는 검출기 이름으로 로드

```python
def load(name):
    if '.json' in name:
        return fromdict(jsio.load(name))
    return fromdict(detectors.load(name, "wires"))
```

`load()`는 인자로 받은 문자열에 `'.json'`이 들어 있으면 그 문자열을 파일 경로로 보고 `wirecell.util.jsio.load()`로 직접 읽는다.
그렇지 않으면(예: `"pdsp"`, `"uboone"` 같은 검출기 이름을 줬다면) `wirecell.util.detectors` 레지스트리를 통해 그 이름에 대응하는 실제 wires 파일 경로를 찾아서 로드한다.
`jsio.load()`는 파일 확장자에 따라 압축을 자동으로 해제한다.
- `.bz2`는 `bz2.open`으로 처리된다.
- `.gz`도 마찬가지 방식으로 처리된다.

그래서 `persist.load()`에 `.json.bz2` 경로를 그대로 넘겨도 별도 압축 해제 없이 바로 `Store` 객체를 얻을 수 있다.

---

## Related Documents

* **Parent docs:**
    - `wire-cell-python/wirecell/util/wires/schema.py`, `persist.py`: Source Scripts
* **Child docs:** 없음.

* **Sibling docs:** 
    - `utils/wires.py`: 와이어 데이터 구조를 로드하고, 위의 일부 기능을 간단히 포팅한 스크립트
    - `docs/geometry/wires_geometry_walkthrough.md`: `utils/wires.py`의 작동 예시를 정리한 문서
