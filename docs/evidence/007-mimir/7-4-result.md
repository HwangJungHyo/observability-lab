# 7-4. Mimir TSDB 블록의 S3 저장 검증

- 검증일: 2026-09-25 (KST)
- 저장소 / 브랜치: `observability-lab` / `lab/007-mimir`
- 권장 저장 경로: `docs/evidence/007-mimir/7-4-result.md`
- 증거 출처: 사용자가 실행해 제공한 명령 출력 및 Ingester TSDB 상태 화면
- 판정: **블록 생성 및 S3 저장 확인 완료**
- 검증 경계: 선택한 블록의 `meta.json` GET 성공 및 `index`, `chunks/000001` 목록상 존재 확인. 모든 데이터 파일의 전체 읽기·무결성, Store-gateway 조회 경로, 7일 보존 정책의 실제 삭제 동작은 미검증.

## 1. 목적

7-3의 Mimir 메트릭 조회 성공에 이어, 수신 데이터가 TSDB 블록으로 생성되어 SeaweedFS의 S3 호환 저장소에 업로드되는지 확인한다.

최근 메트릭은 Ingester의 Head에서도 조회할 수 있으므로, 조회 성공만으로 S3 저장이나 S3를 통한 조회를 입증하지 않는다.

## 2. 확인한 구성

| 항목 | 확인값 |
|---|---|
| 환경 | Windows + Git Bash + Docker Desktop |
| Mimir 이미지 | grafana/mimir:3.2.1 |
| 실행 방식 | target: all |
| 구조 | ingest_storage.enabled: false (classic) |
| 멀티테넌시 / 실습 테넌트 | true / lab |
| S3 endpoint | http://object-store:8333 |
| S3 버킷 | mimir-lab |
| 실제 객체 접두사 | blocks/lab/ |
| 로컬 데이터 볼륨 | observability-lab_mimir-data → /data |
| TSDB 경로 | /data/tsdb |
| Store-gateway 동기화 경로 | /data/tsdb-sync |
| Compactor 작업 경로 | /data/compactor |
| block_ranges_period | 2h |
| head_compaction_interval | 1m |
| head_compaction_idle_timeout | 1h |
| ship_interval | 1m |
| TSDB retention_period | 13h |
| compactor_blocks_retention_period | 168h（7일） |

주기 설정은 실제 실행 중인 `/config` 출력에서 확인했다. `blocks/lab/`은 S3 목록 조회로 확인한 실제 경로다. 13h는 로컬 블록 보존 관련 설정이며, 168h는 객체 저장소 블록의 보존 정책이다. 이번 실습에서 보존 기한에 따른 실제 삭제는 검증하지 않았다.

## 3. 초기 상태와 판단

### 3.1 업로드 전 관측

| 관측 항목 | 결과 |
|---|---|
| 로컬 테넌트 디렉터리 | chunks_head, wal, mimir.shipper.json |
| 완료된 로컬 블록 디렉터리 | 당시 목록에 없음 |
| mimir.shipper.json | `{"version": 1, "shipped": {}}` |
| cortex_ingester_shipper_uploads_total | 0 |
| cortex_ingester_shipper_upload_failures_total | 0 |
| cortex_ingester_shipper_last_successful_upload_timestamp_seconds | 0 |
| cortex_ingester_tsdb_compactions_triggered_total | 32 |
| cortex_ingester_tsdb_compactions_total | 0 |
| cortex_ingester_tsdb_compactions_failed_total | 0 |
| cortex_ingester_tsdb_compaction_duration_seconds_count | 0 |

트리거 32회는 블록 32개 생성이나 실패 32회를 뜻하지 않는다. 실제 TSDB compaction 실행과 업로드가 아직 기록되지 않은 상태였다. 재시작으로 누적 지표가 초기화될 수 있으므로 전체 과거 이력으로 확대 해석하지 않았다.

### 3.2 Head 시간 범위 확인

상태 페이지: `http://localhost:9009/ingester/tsdb/lab`

- 화면 시각: 2026-09-24 15:51:23 UTC
- 시계열 수: 10,521
- Head Min Time: 2026-09-24 14:18:32 UTC
- Head Max Time: 2026-09-24 15:51:29 UTC
- 표시 시각 기준 데이터 범위: 약 1시간 32분 57초
- Blocks 목록: 비어 있음

설정된 블록 시간 범위 2h보다 데이터 범위가 짧아, 블록 생성 조건을 기다리는 상태와 부합한다고 판단했다. 정확히 수집 시작 2시간 뒤에 반드시 업로드된다고 단정하지 않았다. 수집을 유지하고 후속 상태를 관찰했다.

## 4. 블록 생성 및 업로드 후 관측

2026-09-25 06:49:52 UTC（15:49:52 KST）상태 화면에서 확인했다.

- 로컬 Blocks: 7개
- 7개 모두 Uploaded 열에 시각 표시
- 블록 데이터 범위: 2026-09-24 14:18 UTC부터 2026-09-25 04:00 UTC까지
- Head 시계열 수: 10,240
- Head Min Time: 2026-09-25 04:00:02 UTC
- Head Max Time: 2026-09-25 06:49:45 UTC

이 화면은 Mimir가 로컬 블록을 생성하고 업로드 완료를 기록했다는 증거다. 이어 S3 객체를 직접 조회했다.

## 5. 조회 경로 오류와 해결

| 순서 | 조회 | 결과 / 판단 |
|---|---|---|
| 1 | mimir-lab 버킷에서 prefix=lab/ | 객체 0개. 해당 접두사에 객체가 없다는 의미 |
| 2 | 버킷 최상위, delimiter=/ | PREFIX: blocks/ 확인 |
| 3 | prefix=blocks/lab/ | 객체 53개, meta.json이 있는 블록 11개 확인 |

초기 `lab/` 조회 결과를 업로드 실패로 판단하지 않았다. 실제 저장 접두사 `blocks/`를 누락한 조회 경로 문제였으며, 올바른 경로에서 블록을 확인했다.

별도의 조회 문제로 Mimir 이미지 내부에서 `ls` 실행 파일이 없어 디렉터리 조회가 실패했다. 이 오류는 Mimir 중지를 의미하지 않는다. 기존 Python 실행 가능 이미지를 임시 컨테이너로 사용해 데이터 볼륨을 읽기 전용으로 조회했다.

## 6. S3 실물 검증 결과

### 6.1 전체 목록

`mimir-lab/blocks/lab/` 아래에서 객체 53개와 블록 메타데이터 11개를 확인했다.

```text
01M3A6SZHN02C9EN45XYFRCGE6
01M3ACNAPJ82VD91X6CMP702VF
01M3AG6XBR8V33F18ZYXJVSGYK
01M3AKGB9AQQFP32XGS30FV8M7
01M3ATDVQ379JR1E4WQ7SZY9GN
01M3B17Q2V4WMR0WR9WDXBKCQG
01M3B5A9VVNB40Y9XHC6CXDP3F
01M3B83CTC1NYNYEKVQHYRD8FE
01M3BEZ2T8KPVWH11GA3Y4K1MF
01M3BKCH8R0TQHYC81JFF9AVRY
01M3BNTR6G0063CGZQDM31ZQ49
```

앞서 로컬 화면에 표시된 7개 블록 ID가 이 목록에 포함되어 있다. 관측 시점과 저장 위치가 다르며, 추가 4개 블록 각각의 생성 원인은 이번에 조사하지 않았다. 11개는 meta.json 존재 기준 개수로, 모두 현재 조회에 사용되는 활성 블록이라고 판정한 것은 아니다.

### 6.2 선택한 블록

검증 코드는 블록 키를 정렬해 마지막 항목을 선택했다. 데이터 시간이 가장 최신인 블록을 별도로 검색한 것은 아니다.

| 항목 | 값 |
|---|---|
| ULID | 01M3BNTR6G0063CGZQDM31ZQ49 |
| 객체 경로 | blocks/lab/01M3BNTR6G0063CGZQDM31ZQ49/ |
| Min Time（UTC） | 2026-09-25T04:00:02.574000+00:00 |
| Max Time（UTC） | 2026-09-25T06:00:00+00:00 |
| Min Time（KST） | 2026-09-25 13:00:02.574 |
| Max Time（KST） | 2026-09-25 15:00:00 |
| numSamples | 4,685,316 |
| numFloatSamples | 4,685,316 |
| numSeries | 10,065 |
| numChunks | 31,676 |

통계와 시간은 S3에서 GET한 meta.json의 값이다. 시간 범위는 메타데이터의 경계이며, 마지막 샘플이 Max Time에 정확히 존재한다는 의미는 아니다.

| 객체 | 크기（bytes） | 검증 방식 |
|---|---:|---|
| chunks/000001 | 11,419,926 | S3 LIST에서 키·크기 확인 |
| index | 1,166,707 | S3 LIST에서 키·크기 확인 |
| meta.json | 659 | S3 LIST 및 GET·JSON 파싱 성공 |

최종 출력:

```text
구성 확인: meta.json=GET 성공, index=True, chunks=True
```

## 7. 재현 명령

저장소 루트의 Git Bash에서 실행한다. 기존 `scripts/mimir-compose.sh`, `.env.mimir`, `mimir-check` 서비스와 `scripts/check_mimir_storage.py`를 사용한다.

아래 명령은 파일 수정이 아닌 일회성 조회다. 기존 스크립트의 S3 서명 함수를 import하고 LIST·GET만 호출한다. PUT·DELETE가 포함된 `storage()`와 `vector(1)`을 조회하는 `mimir()`는 호출하지 않는다. 실행 후 임시 검사 컨테이너는 삭제되며 기존 서비스는 중지하지 않는다.

```bash
MSYS_NO_PATHCONV=1 bash scripts/mimir-compose.sh run \
  --rm --no-deps -T --entrypoint python mimir-check -B - <<'PY'
import sys
import json
import datetime
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, "/checks")
from check_mimir_storage import s3

def request_get(key="", query=""):
    status, body = s3("GET", key=key, query=query)
    if status != 200:
        raise SystemExit(f"조회 실패: HTTP {status}, key={key!r}")
    return body

search_prefix = "blocks/lab/"
objects = {}
token = None

while True:
    params = {"list-type": "2", "prefix": search_prefix}
    if token:
        params["continuation-token"] = token
    query = urllib.parse.urlencode(
        sorted(params.items()), quote_via=urllib.parse.quote
    )
    root = ET.fromstring(request_get(query=query))
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    for item in root.findall("Contents"):
        objects[item.findtext("Key")] = int(item.findtext("Size"))
    if root.findtext("IsTruncated", "false").lower() != "true":
        break
    token = root.findtext("NextContinuationToken")
    if not token:
        raise SystemExit("다음 페이지 토큰이 없습니다.")

metas = sorted(
    key for key in objects
    if len(key.split("/")) == 4 and key.endswith("/meta.json")
)
print(f"조회 경로: {search_prefix}")
print(f"객체 수: {len(objects)}")
print(f"meta.json이 있는 블록 수: {len(metas)}")
for key in metas:
    print("BLOCK:", key.split("/")[-2])
if not metas:
    raise SystemExit("해당 경로에서 블록 meta.json을 찾지 못했습니다.")

key = metas[-1]
meta = json.loads(request_get(key=key))
prefix = key.rsplit("/", 1)[0] + "/"

def utc(ms):
    return datetime.datetime.fromtimestamp(
        ms / 1000, datetime.timezone.utc
    ).isoformat()

print("\n확인 대상:", prefix)
print("ULID:", meta.get("ulid"))
print("Min Time:", utc(meta["minTime"]))
print("Max Time:", utc(meta["maxTime"]))
print("Stats:", json.dumps(meta.get("stats", {}), ensure_ascii=False))
print("\n블록 구성 객체:")
for name, size in sorted(objects.items()):
    if name.startswith(prefix):
        print(f"{size:>12} bytes  {name}")
has_index = prefix + "index" in objects
has_chunks = any(name.startswith(prefix + "chunks/") for name in objects)
print(f"\n구성 확인: meta.json=GET 성공, index={has_index}, chunks={has_chunks}")
PY
```

재실행 시 수집·블록 생성·병합·삭제 진행에 따라 객체 수, 블록 ID, 통계가 달라질 수 있다. LIST와 GET은 하나의 원자적 스냅샷이 아니므로 조회 도중 대상이 변경되면 재조회가 필요할 수 있다.

## 8. 완료 범위와 후속 과제

| 항목 | 판정 |
|---|---|
| Head·WAL 및 로컬 블록 생성 관측 | 확인 |
| Ingester의 업로드 완료 기록 | 확인 |
| 올바른 S3 객체 경로 식별 | 확인 |
| S3 블록 meta.json 읽기 | 선택한 1개 블록에서 확인 |
| index·chunks 객체 존재 | 선택한 1개 블록에서 확인 |
| 전체 블록·파일의 무결성 및 전체 읽기 | 미검증 |
| Store-gateway를 통한 과거 데이터 조회 | 미검증 |
| 7일 보존 정책에 따른 실제 삭제 | 미검증 |

이번 결과로 Mimir가 수신 데이터를 블록화해 S3에 저장했다는 증거를 확보했다. 다음 실습은 Store-gateway 조회 경로를 검증하고, 일반적인 과거 쿼리 성공만으로 S3 조회를 단정하지 않도록 읽기 경로의 증거를 함께 수집한다.

## 9. Git 기록

이 문서를 `docs/evidence/007-mimir/7-4-result.md`로 저장한 후 저장소 루트에서 실행한다.

```bash
git branch --show-current
git status --short
git add docs/evidence/007-mimir/7-4-result.md
git diff --cached -- docs/evidence/007-mimir/7-4-result.md
git commit -m "docs: record Mimir S3 block storage verification"
```

브랜치가 `lab/007-mimir`인지 확인하고, 커밋 전 이미 staging된 다른 변경이 있는지도 확인한다. 인증 키, 비밀키, `.env.mimir` 내용은 이 기록에 포함하지 않는다.


