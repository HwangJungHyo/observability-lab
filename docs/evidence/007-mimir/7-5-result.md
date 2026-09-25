# 7-5. Store-gateway를 통한 과거 메트릭 조회 검증

> 아래 완료·미검증 표시는 해당 실험 시점의 범위다. 후속 검증은 [7장 체크포인트](../../roadmap.md), [보존 만료 삭제](7-7-retention-result.md), [실제 S3 읽기](7-8-s3-read-result.md)를 참조한다.

- 검증일: 2026-09-25 (KST)
- 저장소 / 브랜치: `observability-lab` / `lab/007-mimir`
- 권장 저장 경로: `docs/evidence/007-mimir/7-5-result.md`
- 선행 실습: [7-4. Mimir S3 블록 저장 검증](7-4-result.md)
- 증거 출처: 사용자가 제공한 실행 설정, 블록 목록, 쿼리 응답 및 조회 전후 지표
- 판정: **과거 메트릭 조회 성공 및 Store-gateway의 조회 참여 확인**
- 한계: 요청 시점의 신규 S3 객체 읽기와 캐시 사용 여부는 미검증

## 1. 목적과 판단 기준

7-4에서는 Mimir가 생성한 TSDB 블록이 SeaweedFS의 S3 호환 저장소에 실제 존재함을 확인했다. 이번에는 과거 메트릭 조회가 Store-gateway를 거치는지 확인한다.

최근 데이터는 Ingester에서 조회될 수 있으므로 쿼리 성공만으로 Store-gateway 참여를 확정하지 않는다. 아래 증거를 함께 사용한다.

1. 실제 적용된 조회 경로 설정을 확인한다.
2. Ingester 조회 범위보다 오래됐으며 저장 블록에 포함된 시간대를 선택한다.
3. 과거 쿼리에서 실제 메트릭 값을 반환받는다.
4. 조회 전후 Store-gateway 결과 지표의 증가를 확인한다.

## 2. 실행 중인 설정과 검증 시간대

확인 명령:

```bash
curl -fsS --max-time 10 http://localhost:9009/config \
  | grep -nE '^[[:space:]]*(query_ingesters_within|query_store_after|ignore_blocks_within):'
```

관측값:

```text
259:    query_store_after: 12h0m0s
647:    query_ingesters_within: 13h
1261:        ignore_blocks_within: 10h0m0s
```

| 항목 | 값 | 의미 |
|---|---|---|
| query_store_after | 12h | 오래된 데이터에 대한 Store-gateway 조회 기준 |
| query_ingesters_within | 13h | 최근 데이터에 대한 Ingester 조회 기준 |
| ignore_blocks_within | 10h | Store-gateway의 최근 블록 로드 제외 기준 |

이 값은 관측한 실행 설정이다. 별도의 테넌트별 override 유무는 이번 기록의 증거에 포함되지 않는다. 경계에 걸치지 않는 충분히 오래된 시간대를 선택하고 실제 Store-gateway 지표 변화로 교차 확인했다.

| 구분 | 선택한 구간 |
|---|---|
| UTC | 2026-09-24 14:30:00 ~ 14:40:00 |
| KST | 2026-09-24 23:30:00 ~ 23:40:00 |
| 조회 실행 시각 | 2026-09-25 16:55 KST경 |
| 당시 데이터 나이 | 약 17시간 전, 13시간 범위 밖 |

`ignore_blocks_within`은 블록 보존 기간이 아니다. 위 설정을 개별 샘플의 정확한 삭제 시점으로 해석하지 않는다.

## 3. 저장 블록 범위 확인

확인 페이지:

```text
http://localhost:9009/store-gateway/tenant/lab/blocks
```

화면 시각: 2026-09-25 07:52:55 UTC  
테넌트: `lab`

| 블록 ID | Min Time (UTC) | Max Time (UTC) | Level | 크기 |
|---|---|---|---:|---|
| 01M3B5A9VVNB40Y9XHC6CXDP3F | 2026-09-24 14:18:32 | 2026-09-25 00:00:00 | 3 | 50 MiB |
| 01M3BKCH8R0TQHYC81JFF9AVRY | 2026-09-25 00:00:00 | 2026-09-25 04:00:00 | 2 | 23 MiB |
| 01M3BNTR6G0063CGZQDM31ZQ49 | 2026-09-25 04:00:02 | 2026-09-25 06:00:00 | 1 | 12 MiB |

선택한 14:30~14:40 UTC는 첫 번째 블록의 시간 범위 안에 있다.

이 페이지는 테넌트의 블록 목록이며, 표시된 블록 모두가 로드됐거나 실제 쿼리에 사용됐다는 증거는 아니다. 개별 블록 ID가 해당 요청에서 사용됐음을 보여주는 트레이스는 이번에 수집하지 않았다.

## 4. 조회 전 기준값

`/metrics`에서 Store-gateway 관련 지표와 HELP/TYPE을 확인했다.

| 지표 | 조회 전 값 | 의미 |
|---|---:|---|
| cortex_bucket_store_blocks_loaded | 1 | 현재 로드된 블록 수 |
| cortex_bucket_store_block_loads_total | 2 | 누적 원격 블록 로드 시도 수 |
| cortex_bucket_store_blocks_loaded_size_bytes | 203239 | 해당 지표가 보고한 로드 블록 크기 값 |
| cortex_bucket_store_series_result_series_count | 0 | 결과 시계열 수 관측 횟수 |
| cortex_bucket_store_series_result_series_sum | 0 | 관측한 결과 시계열 수 누적 합 |

관련 라벨은 `component="store-gateway"`이며, 크기 지표에는 `user="lab"`도 있었다. 크기 지표를 S3 전체 블록 크기나 이번 요청의 다운로드량으로 해석하지 않았다.

핵심 결과 지표의 실제 설명:

```text
# HELP cortex_bucket_store_series_result_series Number of series observed in the final result of a query after merging identical series from different blocks.
# TYPE cortex_bucket_store_series_result_series summary
cortex_bucket_store_series_result_series_sum{component="store-gateway"} 0
cortex_bucket_store_series_result_series_count{component="store-gateway"} 0
```

## 5. 과거 메트릭 조회

실행한 명령:

```bash
curl -fsS --max-time 30 -G \
  -H 'X-Scope-OrgID: lab' \
  'http://localhost:9009/prometheus/api/v1/query_range' \
  --data-urlencode 'query=up{job="prometheus"}' \
  --data-urlencode 'start=2026-09-24T14:30:00Z' \
  --data-urlencode 'end=2026-09-24T14:40:00Z' \
  --data-urlencode 'step=60'
```

응답(가독성을 위해 들여쓰기만 조정):

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

해석:

- 요청 처리 성공: `status=success`
- 시계열 1개: `up{instance="localhost:9090",job="prometheus"}`
- 시작·종료를 포함한 1분 간격 평가값 11개 반환
- 평가값은 모두 `1`
- `up=1`은 각 평가 시점에서 선택된 해당 타깃의 수집 상태가 정상이었음을 뜻함
- 1분 간격 평가 결과는 원본 수집 샘플 전체 목록이 아니며, 원본 샘플의 전 구간 무누락이나 서비스 전체 정상까지 입증하지 않음

## 6. 조회 직후 지표 변화

실행 명령:

```bash
curl -fsS --max-time 10 http://localhost:9009/metrics \
  | grep -E '^cortex_bucket_store_series_result_series_(count|sum)(\{|[[:space:]])'
```

출력:

```text
cortex_bucket_store_series_result_series_sum{component="store-gateway"} 1
cortex_bucket_store_series_result_series_count{component="store-gateway"} 1
```

| 지표 | 조회 전 | 조회 후 | 변화 |
|---|---:|---:|---:|
| series_result_series_count | 0 | 1 | +1 |
| series_result_series_sum | 0 | 1 | +1 |

`count`는 이 summary 지표의 관측 횟수이며, 외부 HTTP 요청 수와 항상 1:1이라고 일반화하지 않는다. 쿼리 분할·재시도 등으로 달라질 수 있다.

`sum=1`은 샘플 1개라는 뜻이 아니다. Store-gateway 결과에서 관측한 시계열 수의 합이 1이다. 이번 외부 쿼리 응답은 시계열 1개에 평가값 11개를 포함했다.

## 7. 판정과 한계

**판정: 과거 메트릭 조회 성공 및 Store-gateway의 조회 참여를 확인했다.**

근거:

1. 선택 구간은 관측한 Ingester 조회 기준인 13시간보다 오래됐다.
2. 동일 구간을 포함하는 저장 블록이 테넌트 블록 목록에 있었다.
3. 과거 쿼리에서 실제 시계열과 값이 반환됐다.
4. 조회 전후 Store-gateway의 결과 관측 횟수와 시계열 수 합이 각각 0에서 1로 증가했다.

검증의 한계:

- 해당 요청에서 신규 S3 GET이 발생했는지, 청크·인덱스 등 캐시를 사용했는지는 구분하지 않았다.
- 결과 지표는 Store-gateway 구성요소 단위이며 요청 ID나 테넌트 라벨로 이 요청에 직접 연결한 것은 아니다. 다른 동시 쿼리가 있었다면 영향을 줄 수 있다.
- 선택한 블록 ID가 실제 조회에 사용됐다는 블록 단위 추적 증거는 수집하지 않았다.
- S3 저장소 중단 시 동작, 전체 데이터 무결성, 7일 보존 정책의 실제 삭제는 이번 검증 범위 밖이다.

따라서 기록은 “Store-gateway의 저장 블록 조회 경로 확인”으로 표현하고, “이번 요청이 캐시 없이 S3를 직접 읽었다” 또는 “전체 데이터 무누락 보장”으로 확대하지 않는다.

## 8. 재검증 순서

1. Mimir가 실행 중인지 확인하고, 다른 수동 쿼리나 Grafana 자동 새로고침을 줄인다.
2. 실행 설정과 블록 목록을 확인해 보존 중인 과거 구간을 고른다.
3. 6장의 지표 명령을 실행해 조회 전 값을 기록한다.
4. 5장의 쿼리를 실행한다.
5. 즉시 같은 지표를 다시 읽어 차이를 비교한다.

재검증 시 누적값이 반드시 0과 1일 필요는 없다. 조회 전후 증가량을 사용한다. 결과 캐시가 이미 존재하거나, 보존 정책으로 데이터가 삭제됐거나, 서비스 재시작으로 카운터가 초기화된 경우는 별도로 해석한다. 날짜가 지난 뒤에도 고정된 2026-09-24 구간을 계속 사용할 수 있다고 가정하지 않는다.

## 9. 현재 진행 위치와 다음 실습

| 단계 | 상태 |
|---|---|
| 7-4: 블록 생성 및 S3 저장 | 완료 |
| 7-5: Store-gateway 과거 조회 참여 | 완료 |
| 요청별 신규 S3 읽기와 캐시 구분 | 추가 검증 가능, 미수행 |
| 보존 정책과 Compactor 삭제 처리 | 다음 실습, 미검증 |

## 10. Git 기록

파일을 `docs/evidence/007-mimir/7-5-result.md`로 저장한 후 저장소 루트에서 실행한다.

```bash
git branch --show-current
git status --short
git add docs/evidence/007-mimir/7-5-result.md
git diff --cached
git commit -m "docs: record Mimir store-gateway query verification"
```

브랜치가 `lab/007-mimir`인지, staging된 다른 변경이 함께 포함되는지 커밋 전에 확인한다. 이 문서를 생성한 시점에는 사용자 로컬 저장소에 대한 커밋이나 push를 실행하지 않았다.


