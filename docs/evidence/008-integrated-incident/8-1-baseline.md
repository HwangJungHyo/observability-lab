# 8-1 정상 기준선과 localhost 연결 지연 분석

## 결론

IPv4로 접속 조건을 고정한 5분 실험에서 232건 모두 HTTP 201과 curl 종료 코드 0으로 성공했다. 클라이언트 평균은 82.65ms, p95는 84.241ms였다. 이후 지연·중단 실습은 같은 IPv4 조건을 사용한다.

기본 localhost 요청에서 관측된 약 200ms의 추가 시간은 연결 구간에 집중됐다. IPv4 강제 비교에서 연결 시간이 크게 줄었다. IPv6 우선 연결 시도와 IPv4 전환 대기가 유력하지만, 상세 연결 시도 로그를 확보하지 않아 Happy Eyeballs를 확정 원인으로 기록하지 않는다.

## 측정 조건

- `POST http://localhost:18080/orders`, JSON 본문 `{"amount":10000}`.
- 동시 요청 1개, 응답 완료 후 `sleep 1`, 약 300초 반복.
- 요청당 `--max-time 10`, 요청마다 새 curl 프로세스 실행.
- `X-Request-ID`에 실행 ID와 일련번호 전달.
- 성공 판정: HTTP 201 AND curl 종료 코드 0.
- 응답 본문은 `/dev/null`로 보내므로 전체 요청의 `confirmed`나 결제 ID는 검사하지 않았다.
- CSV 열: `request_id,http_code,time_total_seconds,curl_exit_code`.
- 요약: 전체·성공·실패 수, 성공률, 성공 요청 평균·최대 시간.
- 이는 응답에 따라 요청률이 변하는 순차 부하이며 고정 RPS나 최대 처리량 시험이 아니다.

## 최초 기준선과 IPv4 기준선

| 항목 | 기본 localhost | localhost + `curl -4` |
|---|---|---|
| 실행 ID | `baseline-20260927T024933Z` | `baseline-ipv4-20260927T033613Z` |
| 시작 UTC | 2026-09-27T02:49:33Z | 2026-09-27T03:36:13Z |
| 종료 UTC | 2026-09-27T02:54:34Z | 2026-09-27T03:41:13Z |
| KST 구간 | 11:49:33~11:54:34 | 12:36:13~12:41:13 |
| 실행 시간 | 301초 | 300초 |
| 전체 / 성공 / 실패 | 199 / 199 / 0 | 232 / 232 / 0 |
| 평균 | 290.65ms | 82.645901ms |
| 최대 | 303.031ms | 96.818ms |
| 실행 구간 평균 요청률 | 약 0.66건/초 | 약 0.77건/초 |
| 통신 오류 파일 | 비어 있음 | 비어 있음 |

IPv4 원본은 [requests-ipv4.csv](requests-ipv4.csv)에 보관했다. 사용자 첨부 텍스트의 CSV 행을 추출했으며 요청 번호 1~232, 중복 없음, 모두 201/종료 코드 0을 확인했다. 최초 199건 결과는 제공된 출력의 요약이며 이 폴더에 원본 CSV를 별도로 포함하지 않았다.

### IPv4 CSV 분포

| 통계 | ms |
|---|---:|
| 최소 | 81.208 |
| p50 | 82.154 |
| p95 | 84.241 |
| p99 | 90.775 |
| 최대 | 96.818 |

백분위는 오름차순 정렬 후 `ceil(p × N)`번째 값을 선택하는 nearest-rank 방식이다. N=232이며 p95는 221번째, p99는 230번째 값이다. Prometheus 히스토그램 추정 백분위와 구분한다. 표본이 적어 장기 꼬리 지연의 보장값으로 사용하지 않는다.

## 동일 요청의 CSV·로그·트레이스 대조

최초 실험 76번 요청을 대조했다.

- 요청 ID: `baseline-20260927T024933Z-76`.
- Trace ID: `1297adc5f7e0959cda5cb35a1d2c3cf7`.
- Tempo 시작: 2026-09-27 11:51:27.799 KST.

| 근거 | 시간 | 결과 |
|---|---:|---|
| 클라이언트 CSV | 303.031ms | HTTP 201, 종료 코드 0 |
| order-api 완료 로그 | 91.595ms | HTTP 201, error=null |
| order-api 서버 span | 91.71ms | POST /orders |
| payment 호출 span | 91.31ms | POST /payments |
| payment 서버 span | 80.68ms | POST /payments |
| payment 완료 로그 | 80.547ms | HTTP 200, error=null |

두 서비스 로그의 요청 ID와 Trace ID가 일치했다. span은 서로 포함되므로 시간을 더하지 않는다. 클라이언트와 주문 서버 span의 차이는 약 211.321ms였으나, 그 차이만으로 전부 네트워크 지연이라고 판단하지 않았다.

## 연결 시간 비교

같은 주문 요청을 기본 localhost와 `curl -4`로 각각 3회 전송했다. curl 시간은 시작부터의 누적 초 단위 값이다.

| 조건 / 요청 | 이름 조회 | 연결 완료 | 전송 준비 | 첫 바이트 | 전체 |
|---|---:|---:|---:|---:|---:|
| 기본 1 | 0.000026 | 0.215566 | 0.215682 | 0.297287 | 0.297346 |
| 기본 2 | 0.000028 | 0.212056 | 0.212149 | 0.294018 | 0.294064 |
| 기본 3 | 0.000025 | 0.216520 | 0.216657 | 0.297455 | 0.297513 |
| IPv4 1 | 0.000025 | 0.000827 | 0.000883 | 0.081986 | 0.082046 |
| IPv4 2 | 0.000026 | 0.000852 | 0.000911 | 0.081728 | 0.081794 |
| IPv4 3 | 0.000030 | 0.000962 | 0.001018 | 0.082984 | 0.083044 |

위 6건은 모두 HTTP 201이었고 최종 연결 주소는 127.0.0.1이었다.

평균 연결 완료 시간은 약 214.71ms에서 0.88ms로, 전체 시간은 약 296.31ms에서 82.29ms로 감소했다. 전송 준비부터 첫 응답까지는 약 81.42ms와 81.30ms로 거의 같았다.

## Prometheus 확인

평가 시각은 `2026-09-27T03:41:30Z`, 조회 창은 330초(KST 12:36:00~12:41:30)로 고정했다.

```promql
sum by (job, status_code) (
  increase(lab_http_requests_total{job=~"order-api|payment"}[330s])
)
```

| 계열 | 추정 증가량 |
|---|---:|
| order-api / 201 | 239.72645633195978 |
| payment / 200 | 239.72570569724297 |
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
| order-api | 82.81118960816268ms |
| payment | 81.25472335782904ms |

`increase()`는 수집 시각 사이의 변화를 조회 구간 끝까지 외삽하므로 소수나 실제 전송 수와의 차이가 생길 수 있다. 239.73을 정확한 주문 수로 사용하지 않는다. 이번 차이를 외삽만으로 설명할 수 있는지는 원본 샘플과 다른 요청 여부를 대조하지 않아 미확정이다.

클라이언트 평균 82.65ms와 서버 평균 82.81ms는 집계 구간과 표본이 완전히 같지 않다. 차이를 빼서 통신 시간을 계산하지 않는다.

## 8-2 인계 사항

사용자의 `git grep` 출력에서 아래 설정을 확인했다. 소스 설정 확인이며 실행 중 프로세스의 환경값을 직접 확인한 것은 아니다.

| 파일 | 설정과 구현 |
|---|---|
| compose.orders.yaml | `PAYMENT_DELAY_SECONDS: "${PAYMENT_DELAY_SECONDS:-0.08}"` |
| compose.orders.yaml | `PAYMENT_TIMEOUT_SECONDS: "2"` |
| services/order-lab/app.py | 지연은 유한한 값이며 0~10초로 제한 |
| services/order-lab/app.py | `time.sleep(PAYMENT_DELAY)` |
| services/order-lab/app.py | 시간 초과는 504, 그 밖의 연결 장애는 502로 분류하는 구현 확인 |

다음은 타임아웃보다 짧은 지연을 적용하고 IPv4 조건에서 측정한 뒤 로그·트레이스를 비교하고 설정을 복원한다. 지연 주입과 복원, 장애 후 측정은 아직 수행하지 않았다.

## 참고 자료

- [curl: 시간 측정 변수와 연결 옵션](https://curl.se/docs/manpage.html)
- [curl: Happy Eyeballs 대기값](https://curl.se/libcurl/c/CURLOPT_HAPPY_EYEBALLS_TIMEOUT_MS.html)
- [Prometheus: increase](https://prometheus.io/docs/prometheus/latest/querying/functions/#increase)
- [Grafana k6: 개방형·폐쇄형 부하 모델](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/)
