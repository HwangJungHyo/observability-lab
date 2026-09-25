# 7-6. 병합 후 원본 블록 정리와 조회 결과 유지 검증

- 검증일: 2026-09-25 (KST)
- 저장소 / 브랜치: `observability-lab` / `lab/007-mimir`
- 권장 저장 경로: `docs/evidence/007-mimir/7-6-result.md`
- 선행 기록: [7-4 S3 저장](7-4-result.md), [7-5 Store-gateway 조회](7-5-result.md)
- 증거 출처: 사용자가 제공한 실행 설정, 블록 목록 화면, S3 HEAD 응답, 쿼리 응답
- 판정: **선택한 원본 블록의 세 객체 제거 및 동일 과거 구간의 조회 결과 유지 확인**
- 미검증: 7일 보존 만료 삭제, 전체 객체 제거, 전체 데이터 무결성, 캐시 없는 신규 S3 읽기

## 1. 목적

Compactor가 블록을 병합한 뒤 원본에 삭제 표시를 남기고, 삭제 지연 이후 원본 객체를 정리하는 과정을 관찰한다. 원본 객체 제거 후에도 이전과 동일한 과거 메트릭 조회 결과가 반환되는지 비교한다.

이번 단계는 보존 정책 확인에서 시작했지만, 실제 관측한 삭제는 **병합 후 원본 정리**이다. 이를 7일 보존 기간 만료에 따른 삭제 성공으로 기록하지 않는다.

## 2. 실행 설정

실행한 명령:

```bash
curl -fsS --max-time 10 http://localhost:9009/config \
  | awk '
    /^[^[:space:]#][^:]*:/ {section=$0}
    /^[[:space:]]*(compactor_blocks_retention_period|cleanup_interval|deletion_delay|ignore_deletion_marks_delay):/ {
      print section
      print $0
    }
  '
```

출력:

```yaml
limits:
    compactor_blocks_retention_period: 1w
compactor:
    cleanup_interval: 15m0s
compactor:
    deletion_delay: 12h0m0s
```

| 설정 | 값 | 해석 |
|---|---|---|
| compactor_blocks_retention_period | 1w | 7일 보존 정책 설정 |
| cleanup_interval | 15m | 정리 작업 주기 |
| deletion_delay | 12h | 삭제 표시 후 실제 삭제까지의 지연 |

`ignore_deletion_marks_delay`는 출력되지 않아 값을 확정하지 않았다. 위 값은 실행 설정 관측이며, 별도 테넌트별 override 유무는 확인하지 않았다. 삭제 지연 경과 시각은 삭제 가능한 기준 시점으로 사용하며, 실제 삭제 완료 시각과 동일시하지 않는다.

## 3. 병합 관계와 삭제 표시

확인 페이지:

```text
http://localhost:9009/store-gateway/tenant/lab/blocks
```

`Show Deleted`, `Show Sources`를 선택하고 Reload했다.

- 화면 시각: 2026-09-25 08:01:31 UTC / 17:01:31 KST
- 표시 블록: 11개
- Deletion Time 표시: 8개
- Deletion Time 비어 있음: 3개

이 화면의 Deletion Time은 삭제 표시 시각으로 해석했다. 실제 객체 제거 여부는 이후 S3 HEAD로 별도 확인했다.

### 대상 원본 블록

| 항목 | 값 |
|---|---|
| 블록 ID | 01M3A6SZHN02C9EN45XYFRCGE6 |
| 데이터 범위 UTC | 2026-09-24 14:18:32 ~ 16:00:00 |
| Level | 1 |
| 삭제 표시 UTC | 2026-09-24 20:02:49 |
| 삭제 표시 KST | 2026-09-25 05:02:49 |
| 삭제 지연 12시간 경과 UTC | 2026-09-25 08:02:49 |
| 삭제 지연 12시간 경과 KST | 2026-09-25 17:02:49 |

### 관측한 병합 결과

| 항목 | 값 |
|---|---|
| 병합 블록 ID | 01M3B5A9VVNB40Y9XHC6CXDP3F |
| 데이터 범위 UTC | 2026-09-24 14:18:32 ~ 2026-09-25 00:00:00 |
| Level | 3 |
| Sources | 아래 원본 블록 5개 |

```text
01M3A6SZHN02C9EN45XYFRCGE6
01M3ACNAPJ82VD91X6CMP702VF
01M3AKGB9AQQFP32XGS30FV8M7
01M3ATDVQ379JR1E4WQ7SZY9GN
01M3B17Q2V4WMR0WR9WDXBKCQG
```

대상 원본이 병합 블록의 Sources에 포함되어 있고, 원본에는 삭제 표시가 있었다. 데이터 생성 후 7일이 지나지 않은 상태였으며, 병합 후 원본 정리와 부합하는 증거다. 삭제 사유를 기록한 별도 Compactor 로그는 이번에 수집하지 않았다.

Sources는 원본 계보를 보여주는 정보이며, 나열된 원본 5개를 한 번의 작업으로 직접 합쳤다고 단정하지 않는다. Level 3도 입력 블록 3개를 뜻하지 않는다.

## 4. S3 객체 제거 관측

사용한 버킷은 `mimir-lab`, endpoint는 `http://object-store:8333`이다. 기존 `mimir-check` 서비스와 S3 서명 함수를 재사용했다.

실행한 명령:

```bash
MSYS_NO_PATHCONV=1 bash scripts/mimir-compose.sh run \
  --rm --no-deps -T --entrypoint python mimir-check -B - <<'PY'
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/checks")
from check_mimir_storage import s3

prefix = "blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/"
print("확인 시각 UTC:", datetime.now(timezone.utc).isoformat())

for name in ("meta.json", "index", "chunks/000001"):
    status, _ = s3("HEAD", key=prefix + name)
    meaning = {
        200: "객체 존재",
        404: "해당 객체 없음",
    }.get(status, "인증·서버 오류 등 추가 확인 필요")
    print(f"HTTP {status}: {meaning} — {prefix}{name}")
PY
```

이 명령은 세 객체의 존재 여부만 확인한다. PUT·DELETE나 설정 변경은 수행하지 않았고, Mimir를 중지하지 않았다.

### 첫 번째 관측: 삭제 지연 경과 전

```text
확인 시각 UTC: 2026-09-25T08:02:27.971092+00:00
HTTP 200: 객체 존재 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/meta.json
HTTP 200: 객체 존재 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/index
HTTP 200: 객체 존재 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/chunks/000001
```

한국 시각 17:02:27.971이며, 삭제 표시 후 12시간이 되기 약 21초 전이다. 세 객체가 유지되고 있었다.

### 두 번째 관측: 삭제 지연 경과 후

```text
확인 시각 UTC: 2026-09-25T08:25:03.598220+00:00
HTTP 404: 해당 객체 없음 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/meta.json
HTTP 404: 해당 객체 없음 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/index
HTTP 404: 해당 객체 없음 — blocks/lab/01M3A6SZHN02C9EN45XYFRCGE6/chunks/000001
```

한국 시각 17:25:03.598에 동일한 세 키가 더 이상 존재하지 않음을 확인했다. 실제 삭제 순간은 관측하지 않았으므로 17:25:03을 삭제 실행 시각으로 기록하지 않는다.

| 객체 | 17:02:27 KST | 17:25:03 KST |
|---|---|---|
| meta.json | HTTP 200 | HTTP 404 |
| index | HTTP 200 | HTTP 404 |
| chunks/000001 | HTTP 200 | HTTP 404 |

검증한 것은 위 세 객체의 제거다. 해당 접두사 전체가 비었는지, 저장 장치에서 물리적 공간이 즉시 회수됐는지는 별도 검증하지 않았다.

## 5. 원본 객체 제거 후 과거 데이터 재조회

7-5와 동일한 구간·쿼리·평가 간격으로 조회했다.

- UTC: 2026-09-24 14:30:00 ~ 14:40:00
- KST: 2026-09-24 23:30:00 ~ 23:40:00
- 테넌트: lab
- 쿼리: `up{job="prometheus"}`
- 평가 간격: 60초

```bash
curl -fsS --max-time 30 -G \
  -H 'X-Scope-OrgID: lab' \
  'http://localhost:9009/prometheus/api/v1/query_range' \
  --data-urlencode 'query=up{job="prometheus"}' \
  --data-urlencode 'start=2026-09-24T14:30:00Z' \
  --data-urlencode 'end=2026-09-24T14:40:00Z' \
  --data-urlencode 'step=60'
```

응답(가독성을 위해 들여쓰기 조정):

```json
{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {
          "__name__": "up",
          "instance": "localhost:9090",
          "job": "prometheus"
        },
        "values": [
          [1790260200, "1"],
          [1790260260, "1"],
          [1790260320, "1"],
          [1790260380, "1"],
          [1790260440, "1"],
          [1790260500, "1"],
          [1790260560, "1"],
          [1790260620, "1"],
          [1790260680, "1"],
          [1790260740, "1"],
          [1790260800, "1"]
        ]
      }
    ]
  }
}
```

| 비교 항목 | 삭제 전(7-5) | 삭제 후(7-6) |
|---|---|---|
| status | success | success |
| resultType | matrix | matrix |
| 반환 시계열 | up / localhost:9090 / prometheus | 동일 |
| 평가값 개수 | 11개 | 11개 |
| 타임스탬프 | 1790260200~1790260800, 60초 간격 | 동일 |
| 값 | 모두 1 | 모두 1 |

이번 재조회는 1분 간격 평가값을 비교한 것이다. 전체 원본 샘플의 무누락이나 모든 시계열의 동일성을 입증하지 않는다.

## 6. 최종 판정

**선택한 원본 블록의 세 객체가 제거된 후에도 검증한 과거 구간의 조회 결과가 유지됐다.**

확인한 증거의 연결:

1. 병합 블록의 Sources에 대상 원본 ID가 포함됨
2. 원본의 삭제 표시 시각 확인
3. 삭제 지연 경과 전 원본 세 객체 존재(200)
4. 지연 경과 후 동일 세 객체 부재(404)
5. 같은 과거 쿼리의 시계열·타임스탬프·평가값이 삭제 전후 동일

실제로 수행하지 않은 DELETE 명령이나 강제 장애 시험을 수행했다고 기록하지 않는다. 관측 결과는 설정된 병합 후 정리 흐름과 일치하며, 삭제 작업 자체의 실행 로그는 확보하지 않았다.

## 7. 미검증 범위

| 항목 | 현재 상태 |
|---|---|
| 7일 보존 정책 설정 | 1w 확인 |
| 7일 만료에 따른 실제 삭제 | 미검증 |
| 이번 재조회에서 Store-gateway 지표 증가 | 재측정하지 않음. 7-5에서 별도 확인 |
| 캐시 없이 병합 블록을 S3에서 새로 읽었는지 | 미검증 |
| 실제 사용된 블록 ID를 요청 단위로 추적 | 미검증 |
| 원본 접두사의 모든 객체 제거 | 세 키만 확인 |
| 전체 데이터 무결성·원본 샘플 전부 비교 | 미검증 |
| 병합 중 장애 주입과 복구 | 미수행 |

따라서 이번 기록을 “7일 보존 만료 삭제 성공”, “캐시 없는 S3 직접 조회 성공” 또는 “전체 데이터 무손실 보장”으로 확대 해석하지 않는다.

## 8. 재현 시 유의점

- 위 원본 ID는 이번 관측 대상이다. 이미 제거됐으므로 나중에 실행하면 처음부터 404가 나올 수 있다.
- 삭제 전후를 다시 관측하려면, 새롭게 삭제 표시된 원본과 이를 포함하는 병합 블록을 선정한다.
- 삭제 표시 시각과 실제 실행 설정을 확인하고, 지연 전후에 동일 키를 조회한다.
- 보존 기간이 지난 후에도 예시의 고정된 과거 시간대를 계속 조회할 수 있다고 가정하지 않는다.
- 인증정보는 기존 .env.mimir와 Compose 환경변수로 주입하고 문서나 Git에 포함하지 않는다.

## 9. Git 기록

파일을 `docs/evidence/007-mimir/7-6-result.md`에 저장하고 저장소 루트에서 실행한다.

```bash
git branch --show-current
git status --short
git add docs/evidence/007-mimir/7-6-result.md
git diff --cached
git commit -m "docs: record Mimir block cleanup and query verification"
```

브랜치가 `lab/007-mimir`인지, 다른 변경이 staging되어 함께 커밋되는지 확인한다. 이 문서 작성 과정에서 사용자 로컬 저장소의 커밋이나 push는 실행하지 않았다.


