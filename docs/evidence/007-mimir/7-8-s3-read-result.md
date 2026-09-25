# 7-8. 과거 메트릭 조회 시 실제 S3 읽기 검증

- 실습일: 2026-09-25 (KST)
- 브랜치: `lab/007-mimir`
- 권장 경로: `docs/evidence/007-mimir/7-8-s3-read-result.md`
- 판정: **결과·청크 캐시 비활성 상태에서 과거 조회와 함께 Store-gateway의 S3 Range GET 및 읽기 바이트 증가 확인**

## 1. 목적

과거 데이터 조회 성공만으로는 S3에서 새로 읽었는지 알 수 없다. 이번 실습에서는 동일한 조회 직전·직후의 Store-gateway 객체 저장소 지표를 비교해 실제 읽기 발생을 확인했다.

이 기록은 보존 만료로 삭제한 별도 테스트 테넌트가 아니라, 기존 `lab` 테넌트의 과거 `up` 조회에 관한 기록이다. 파일 번호는 문서 분류용이며 실제 읽기 검증은 보존 만료 테스트보다 먼저 수행했다.

## 2. 환경과 캐시 설정

| 항목 | 확인값 |
|---|---|
| Mimir | 3.2.1 |
| 테넌트 | `lab` |
| 객체 저장소 | SeaweedFS S3 호환 API |
| 버킷 / 데이터 접두사 | `mimir-lab` / `blocks/lab/` |
| `frontend.cache_results` | `false` |
| 결과 캐시 backend | 빈 값 |
| 청크 캐시 backend | 빈 값 |
| 메타데이터 캐시 backend | 빈 값 |
| 인덱스 캐시 backend | `inmemory` |
| `query_store_after` | `12h` |
| `query_ingesters_within` | `13h` |
| `ignore_blocks_within` | `10h` |

**인덱스 메모리 캐시는 활성화되어 있었다.** 따라서 모든 계층의 캐시가 없는 상태나 완전한 콜드 스타트를 검증했다고 표현하지 않는다. 검증한 것은 결과·청크 캐시가 비활성화된 구성에서 해당 조회 구간에 새로운 객체 저장소 읽기가 발생했다는 점이다.

## 3. 조회 요청과 응답

```bash
curl -fsS --max-time 30 -G \
  -H 'X-Scope-OrgID: lab' \
  'http://localhost:9009/prometheus/api/v1/query_range' \
  --data-urlencode 'query=up{job="prometheus"}' \
  --data-urlencode 'start=2026-09-24T14:30:00Z' \
  --data-urlencode 'end=2026-09-24T14:40:00Z' \
  --data-urlencode 'step=60'
```

| 응답 항목 | 결과 |
|---|---|
| status | `success` |
| resultType | `matrix` |
| 메트릭 | `up{instance="localhost:9090",job="prometheus"}` |
| 반환 시계열 | 1개 |
| 평가 시점 | `1790260200`부터 `1790260800`까지 60초 간격 |
| 반환 값 | 11개 모두 `1` |

반환 값 11개는 60초 간격의 쿼리 평가 결과다. 원본 저장 샘플 수가 11개라는 뜻은 아니다.

## 4. 조회 전후 지표

아래 지표의 `component`는 모두 `store-gateway`다. 객체 저장소 지표는 `operation="get_range"`, `bucket=""` 라벨을 가진 시계열을 비교했다. `bucket` 라벨의 빈 값이 실제 버킷 이름이 없다는 뜻은 아니다.

| 지표 | 조회 전 | 조회 후 | 증가량 |
|---|---:|---:|---:|
| `cortex_bucket_store_partitioner_requested_bytes_total{data_type="chunks"}` | 210 | 420 | 210 bytes |
| `cortex_bucket_store_series_result_series_sum` | 1 | 2 | 1 |
| `cortex_bucket_store_series_result_series_count` | 1 | 2 | 1 |
| `thanos_objstore_bucket_operation_duration_seconds_count{operation="get_range"}` | 7 | 8 | 1 |
| `thanos_objstore_bucket_operation_failures_total{operation="get_range"}` | 0 | 0 | 0 |
| `thanos_objstore_bucket_operation_fetched_bytes_total{operation="get_range"}` | 210425 | 210635 | 210 bytes |

지표 스냅샷 명령:

```bash
curl -fsS --max-time 10 http://localhost:9009/metrics \
  | grep -E '^(cortex_bucket_store_partitioner_requested_bytes_total|cortex_bucket_store_series_result_series_(count|sum)|thanos_objstore_bucket_operation_duration_seconds_count|thanos_objstore_bucket_operation_failures_total|thanos_objstore_bucket_operation_fetched_bytes_total)(\{|[[:space:]])' \
  | grep 'component="store-gateway"'
```

수집 순서는 **지표 스냅샷 → 과거 메트릭 조회 → 지표 스냅샷**이다. 재현 시 누적값 자체가 같을 필요는 없으며 전후 차이를 비교한다. 다른 쿼리와 프로세스 재시작이 측정에 섞이지 않도록 한다.

## 5. 증거 해석

1. 조회 성공과 11개 결과 값으로 과거 데이터가 반환됨을 확인했다.
2. Store-gateway의 결과 시계열 관측 지표가 증가했다.
3. 객체 저장소 `get_range` 작업 횟수가 1 증가했다.
4. 해당 작업의 읽기 바이트가 210 증가했으며 청크 요청 바이트 증가량도 210이었다.
5. 같은 구간의 `get_range` 실패 카운터 증가는 없었다.

이를 통해 측정 구간에 **Store-gateway가 객체 저장소에서 새로 210바이트를 읽었음**을 확인했다. 조회와 청크 요청 증가가 함께 관측된 점은 해당 조회가 S3 읽기를 유발했다는 근거다. 다만 지표는 요청 ID별 추적이 아닌 누적 카운터이므로, 해당 조회만의 효과라고 귀속하려면 동시 조회·백그라운드 작업의 간섭이 없다는 조건이 필요하다.

`series_result_series_count`는 결과 시계열 수 관측 횟수이고 `sum`은 관측한 시계열 수의 합이다. 전체 사용자 HTTP 요청 수나 데이터 샘플 수로 해석하지 않는다.

## 6. 판정과 한계

- [x] 결과 캐시 비활성 설정 확인
- [x] 청크 캐시 backend 미설정 확인
- [x] 과거 메트릭 조회 성공
- [x] Store-gateway 객체 저장소 Range GET 1회 증가
- [x] 객체 저장소 읽기 210바이트 증가
- [x] 해당 작업 실패 카운터 증가 없음

이번 검증만으로 주장하지 않는 내용:

- 인덱스 캐시, 로컬 색인 파일, OS 캐시, 저장소 서버 캐시까지 모두 비활성화
- 모든 조회가 항상 S3 읽기를 발생시킴
- 단일 요청과 개별 S3 객체 키를 접근 로그로 일대일 연결
- 객체 저장소의 물리 디스크에서 직접 읽었음
- S3 장애 시 동작이나 전체 데이터 무결성 검증

결론: **과거 메트릭 조회 전후에 Store-gateway의 S3 Range GET과 읽기 바이트가 증가했으며, 결과 캐시만으로 응답한 상황과 구분되는 실제 객체 저장소 읽기 증거를 확보했다.**

## 7. 고객 설명 문장

> 과거 메트릭이 조회되는 것뿐 아니라, 조회 전후에 저장소 읽기 횟수와 전송량이 증가하는지 확인했습니다. 결과·청크 캐시를 사용하지 않는 구성에서 S3 읽기 1회와 210바이트 증가를 관측했습니다. 다만 인덱스 캐시는 활성 상태였으므로 모든 캐시를 제거한 테스트라고 표현하지는 않습니다.

