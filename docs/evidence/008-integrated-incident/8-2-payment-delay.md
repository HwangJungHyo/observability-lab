# 8-2 payment 지연 주입·관측·복구 결과

기록일: 2026-10-01. 실행 환경: Windows Git Bash와 Docker Desktop. 브랜치: `lab/008-integrated-incident`. 아래 결과는 사용자가 제공한 실행 출력, CSV 본문, Grafana 화면을 근거로 한다. 시각은 별도 표시가 없으면 KST다.

## 목적과 결론

결제 서비스의 처리 지연이 주문 응답 시간에 전파되는지 확인했다. 오류 없이 느린 상태를 로그·트레이스·메트릭으로 관측하고, 설정 복원 후 응답 시간 회복을 확인했다.

- 5분간 134건 모두 HTTP 201과 curl 종료 코드 0으로 성공했다.
- 클라이언트 평균은 1,002.655ms, 서버 평균은 order-api 1,002.204ms와 payment 1,000.599ms였다.
- 정상 기준선 평균 82.65ms보다 약 920ms 증가해 지연 설정 차이와 일치했다.
- 반복 실험 후 복구 요청은 HTTP 201, confirmed, 86.740ms였다.
- 단일 요청 추적과 반복 측정·복구 검증을 완료했다. 최대 처리량이나 장기 복구 안정성을 검증한 결과는 아니다.

## 사전 상태와 설정

변경 파일이 없는 실습 브랜치에서 두 서비스가 healthy임을 확인했다. 실행 중 컨테이너의 환경변수는 payment 지연 `0.08`, order-api 타임아웃 `2`였다.

| 항목 | 정상 | 지연 실험 |
|---|---:|---:|
| PAYMENT_DELAY_SECONDS | 0.08초 | 1초 |
| PAYMENT_TIMEOUT_SECONDS | 2초 | 2초 유지 |
| 접속 | curl -4 | curl -4 유지 |
| 요청 | POST /orders, amount=10000 | 동일 |

1초는 기존 지연에 추가하는 값이 아니라 기존 0.08초를 대체한다. 컨테이너 재생성 구간과 부하 측정 구간을 분리하는 절차로 진행했다. 지연 적용 후 환경변수 출력과 healthy 출력 자체는 이번 제공 증거에 포함되지 않았다.

### 지연 적용 명령

```bash
PAYMENT_DELAY_SECONDS=1 \
  bash scripts/mimir-compose.sh up -d \
  --no-deps --force-recreate --no-build --pull never payment
```

### 복원 명령

```bash
PAYMENT_DELAY_SECONDS=0.08 \
  bash scripts/mimir-compose.sh up -d \
  --no-deps --force-recreate --no-build --pull never payment
```

환경변수는 해당 Compose 명령에만 전달되지만 생성된 컨테이너에는 다음 재생성까지 적용된다. 복원 후 실제 환경값과 healthy 출력은 별도로 보존하지 못했으며, 성공 응답과 시간 회복을 복구의 직접 근거로 삼았다.

## 단일 요청: 지연과 원인 서비스 확인

- 요청 ID: `delay-1s-20261001T124017Z`.
- Trace ID: `56415d9b5236bd48549f59d3c81bd008`.
- Tempo 시작: 21:40:19.145.
- HTTP 응답: 21:40:20, 201, confirmed.

| 근거 | 시간 | 상태 |
|---|---:|---|
| 클라이언트 curl | 1,014.787ms | 201, confirmed |
| order-api 완료 로그 | 1,004.255ms | 201, error=null |
| payment 완료 로그 | 1,000.363ms | 200, error=null |
| Tempo 개요 | 약 1초 | 2개 서비스, 동일 Trace ID |

두 로그의 요청 ID와 Trace ID가 일치했다. payment를 기다리는 시간이 order-api 처리 시간에 포함되므로 두 시간을 합산하지 않는다. INFO와 error=null만으로 정상 응답 속도를 보장할 수 없다는 사례다.

단일 실험 후 복구 요청 `recovery-20261001T124631Z`는 21:46:33에 HTTP 201, confirmed, 86.190ms를 반환했다. Trace ID는 `835e94388d8d27b89d4906aa001ead88`이다.

## 5분 반복 측정

- 실행 ID: `delay-1s-ipv4-20261001T124911Z`.
- UTC: 2026-10-01T12:49:11Z~12:54:11Z.
- KST: 21:49:11~21:54:11, 300초.
- 조건: 순차 요청 1개, 응답 완료 후 1초 대기, curl -4, 요청당 최대 10초.
- 성공 판정: HTTP 201 AND curl 종료 코드 0. 응답 본문은 버리므로 134건 전체의 업무 상태 필드까지 검사한 것은 아니다.

| 항목 | 정상 IPv4 기준선 | 1초 지연 |
|---|---:|---:|
| 요청 수 | 232 | 134 |
| 성공 / 실패 | 232 / 0 | 134 / 0 |
| 성공률 | 100% | 100% |
| 평균 | 82.65ms | 1,002.655ms |
| p50 | 82.154ms | 1,000.799ms |
| p95 | 84.241ms | 1,015.798ms |
| p99 | 90.775ms | 1,020.190ms |
| 최대 | 96.818ms | 1,021.579ms |
| 평균 요청률 | 약 0.77건/초 | 약 0.45건/초 |

백분위는 제공된 134개 시간값을 정렬한 뒤 ceil(p × N)번째 값을 선택했다. p95는 128번째, p99는 133번째 값이다. 오류 파일은 제공된 출력에서 비어 있었다.

사용자 PC의 원본 경로:

```text
/tmp/observability-lab/delay-1s-ipv4-20261001T124911Z/requests.csv
/tmp/observability-lab/delay-1s-ipv4-20261001T124911Z/curl-errors.log
```

이번 문서는 제공된 CSV 본문으로 계산한 요약을 보존한다. 위 임시 경로의 원본 파일은 저장소에 추가하지 않았다. 74번의 985.848ms처럼 1초보다 짧은 클라이언트 측정값이 있으며, 서버 로그와 해당 요청을 대조하지 않아 원인은 미확정이다.

응답을 기다린 뒤 다음 요청을 보내므로 지연 증가 시 요청률도 감소한다. 232건에서 134건으로 줄었다는 결과만으로 서버의 최대 처리 능력이 감소했다고 해석하지 않는다. 정상 기준선은 9월 27일, 지연 실험은 10월 1일이므로 동일 시점의 대조군은 아니다.

## 서버 메트릭 대조

평가 시각: `2026-10-01T12:54:30Z`. 조회 범위: 330초, KST 21:49:00~21:54:30. Prometheus `/api/v1/query`에서 time을 고정했다.

```promql
sum by (job, status_code) (
  increase(lab_http_requests_total{job=~"order-api|payment"}[330s])
)
```

| 계열 | 추정 증가량 |
|---|---:|
| payment / 200 | 135.96092778224923 |
| order-api / 201 | 139.62588280206145 |
| 두 서비스의 400·500·502·504 | 모두 0 |

```promql
1000 * sum by (job) (
  increase(lab_http_request_duration_seconds_sum{job=~"order-api|payment"}[330s])
) / sum by (job) (
  increase(lab_http_request_duration_seconds_count{job=~"order-api|payment"}[330s])
)
```

| 서비스 | 평균 처리 시간 |
|---|---:|
| payment | 1,000.5992868682371ms |
| order-api | 1,002.2040709500425ms |

increase는 외삽과 관측된 카운터 초기화 보정을 포함한다. 두 서비스의 수집 시각과 조회 경계가 달라질 수 있으므로 추정 증가량 차이를 결제 누락으로 단정하지 않는다. 실제 차이의 원인은 원본 샘플을 대조하지 않아 미확정이다. 카운터 초기화가 이번 조회 창 안에 있었는지도 별도로 확인하지 않았다.

## 반복 실험 후 복구

- 요청 ID: `recovery-repeat-20261001T125538Z`.
- Trace ID: `09559fd6bcf91e49be64bb767299ad18`.
- 응답 시각: 2026-10-01 21:55:39 KST.
- 결과: HTTP 201, confirmed, 86.740ms.

단일 복구 요청의 기능·응답 시간 회복을 확인했다. 지속 부하에서의 복구 안정성은 미검증이다.

## 검증 범위와 다음 단계

완료: 지연 재현, 성공 응답 유지, 동일 요청의 로그·트레이스 연결, 반복 측정, 서버 평균 대조, 복구 요청 확인.

미검증: 지연 중 up=1 유지, 경보 발생, 최대 처리량, 전체 요청의 일대일 로그 대조, 장기 안정성, 1초 미만 측정값의 원인, 추정 증가량 차이의 정확한 원인.

8-3에서는 payment를 중단해 성공하지만 느린 상태와 의존 서비스 장애로 실패하는 상태를 비교한다. order-api 응답, 두 서비스의 up, 오류 로그·트레이스, 복구 후 성공을 확인한다. HTTP 502가 예상되지만 실제 오류 유형과 소요 시간은 관측값으로 판정한다. 중단 실습은 아직 실행하지 않았다.

## 참고

- [8-1 정상 기준선](8-1-baseline.md)
- [Prometheus increase](https://prometheus.io/docs/prometheus/latest/querying/functions/#increase)
