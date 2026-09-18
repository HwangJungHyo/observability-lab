# 010 — JSON 로그의 정상 요청 연결

- 날짜: 2026-09-18
- 챕터: 5-2 완료
- 실행 환경: 사용자 Windows / Docker Desktop / Git Bash
- 근거: 사용자가 공유한 Grafana Loki 조회 화면. 아래는 화면 관측값을 옮긴 기록이며 원본 로그 파일 첨부는 아니다.
- 소스: 7ccf246 (JSON 로그 및 요청 ID 전달)
- request_id: `lab-1789712062-6849`

## 관측

| 필드 | 주문 | 결제 |
|---|---|---|
| service | order-api | payment |
| event | request_completed | request_completed |
| route | /orders | /payments |
| method | POST | POST |
| status_code | 201 | 200 |
| duration_ms | 88.904 | 80.738 |
| level | info | info |
| error | null | null |
| timestamp (UTC) | 2026-09-18T06:14:20.687+00:00 | 2026-09-18T06:14:20.686+00:00 |

두 로그의 request_id가 일치한다. Grafana 표시 시각은 두 줄 모두 15:14:20.687이었다.
앱 JSON timestamp와 수집 로그의 표시 시각은 출처가 다르므로 구분한다.

## 검색

~~~logql
{environment="lab", service_name=~"order-api|payment"}
| json
| __error__=""
| request_id="lab-1789712062-6849"
~~~

## 해석과 한계

- 주문 API가 결제를 호출하고 같은 요청 ID를 전달한 정상 경로를 확인했다.
- 주문 시간에는 결제 대기가 포함된다. 두 시간을 더하지 않는다.
- 차이 8.166ms는 주문 측 추가 처리와 통신 등의 합이며 순수 네트워크 지연으로 단정할 수 없다.
- 단일 요청 결과로 평균·p95·처리 용량을 판단하지 않는다.
- Backward 조회는 최신 로그를 먼저 표시한다. 화면 순서만으로 호출 순서를 판단하지 않는다.
- request_id 연결은 분산 트레이스의 span 계층·구간 분석을 대체하지 않는다.

## service_name과 service

service_name은 alloy/config.alloy의 discovery.relabel이 Docker Compose 서비스 이름에서 만든 Loki 수집 라벨이다.
service는 services/order-lab/app.py가 JSON 본문에 기록한 애플리케이션 필드다.
이 실습에서는 값이 같지만 생성 주체가 다르다.
request_id는 JSON 필드로 남기고 Loki 수집 라벨이나 Prometheus 라벨로 만들지 않는다.

## 다음

5-3 결제 중단의 오류 로그와 복구 로그를 비교한다. 해당 실험은 아직 실행 결과 확인 전이다.
