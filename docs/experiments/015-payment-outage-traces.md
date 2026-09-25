# 실험 015: 결제 중단·복구 트레이스와 6장 종료

- 실험일: 2026-09-22
- 기록 기준 소스: 512a8cb0ec86da81f8c34fd7343bfd44d33150d0
- 브랜치: lab/006-tracing
- 환경: 사용자 Windows / Git Bash / Docker Desktop
- 판정: 6장 기능 실험 완료. 장애·복구 트레이스와 로그는 사용자가 확인 완료를 보고했다.
- 이번 문서 갱신 과정에서 해당 PC의 실험을 재실행한 것은 아니다.

## 목적과 절차

payment 중단 → 주문 오류 요청 → payment 재시작 → 주문 성공 요청 → Tempo/Loki 비교.
정상 경로의 세 span과 중단 시 주문 측 두 span을 비교하는 실험이다.
전체 구조와 지연 실험은 실험 012~014를 참조한다.

## 제공된 원시 출력으로 확인한 결과

| 항목 | 장애 | 복구 |
|---|---|---|
| HTTP | 502 Bad Gateway | 201 Created |
| 결과 | payment_unavailable | confirmed |
| curl 전체 시간 | 4.187035초 | 0.291379초 |
| Request ID | trace-down-1790086379-14989 | trace-recovered-1790086401-3667 |
| Trace ID | 321ff4f0ee85c5fcd9a3e97f23f8d946 | 4f9579d9bfd184aa1793e5d3e48f3791 |
| HTTP Date | 2026-09-22 14:13:04 UTC | 2026-09-22 14:13:07 UTC |

장애 주문 로그:

```json
{"timestamp":"2026-09-22T14:13:04.299+00:00","level":"error","service":"order-api","event":"request_completed","request_id":"trace-down-1790086379-14989","method":"POST","route":"/orders","status_code":502,"duration_ms":3973.388,"error":"payment_unavailable","trace_id":"321ff4f0ee85c5fcd9a3e97f23f8d946","span_id":"a10ab175837f1f19"}
```

로그의 처리 시간은 3973.388ms, curl 전체 시간은 4187.035ms이며 차이는 213.647ms다.
측정 범위가 다르므로 이 차이 전체를 네트워크 지연으로 단정하지 않는다.
약 4초라는 값만으로 timeout이나 재시도 횟수를 확정하지 않는다.

## 증거 구분

- 제공된 출력: 장애 502·복구 201, 각 Trace ID, curl 시간, 장애 주문 JSON 로그.
- 사용자 확인: 장애·복구 트레이스와 로그 확인 완료 (2026-09-22).
- 상세 미전사: 각 span의 정확한 Duration, CLIENT의 error.type/exception 원문, 복구된 두 서비스의 JSON 로그, 최종 healthy/up 화면.
- 복구 직후 ps 출력에서 payment는 health: starting이었다. 이후 주문 201로 업무 요청 성공은 확인했지만, 이 ps 출력을 healthy의 증거로 취급하지 않는다.
- 장애·복구 span 수와 상태의 상세 기계 판독 증거는 추가 수집 시 기록한다. 확인하지 않은 화면의 속성값은 보완하지 않는다.

## 조사 시 주의 사항

Tempo에 Loki 쿼리와 printf를 붙였을 때 발생한 400은 검색 구문 오류이며 저장 실패의 증거가 아니었다.
Tempo는 Trace ID로 조회하고 Loki는 LogQL로 검색한다.
span이 없다는 사실만으로 서비스 중단과 계측·전송 누락을 구분할 수 없다. 컨테이너 상태, CLIENT 예외, 수집 경로 상태를 함께 확인한다.

## 증거 보강에 필요한 항목

1. 장애 CLIENT span의 Duration, Status, error.type, exception.message 원문.
2. 복구 Trace ID의 span 목록과 각 Duration·Status, order-api/payment JSON 로그.
3. 최종 payment/order-api healthy, Prometheus 대상 up=1, PAYMENT_DELAY_SECONDS=0.08.
4. 가능하면 두 Trace JSON. 저장 로그는 대상 Trace ID로 제한하고 자격 증명이나 불필요한 개인정보를 포함하지 않는다.

Request ID 안의 숫자는 임의 식별자이며 시각의 근거로 사용하지 않는다. HTTP Date와 로그 timestamp를 기록한다.
숫자 부분과 로그 시각이 일치하지 않으므로 이후에는 호스트·컨테이너 시각도 확인한다.

## 6장 완료 범위

Tempo 연결, 정상 호출 관계, 로그↔트레이스, 1초 지연·복구, 중단·복구 기능 실험을 완료했다.
상세 원문 추가 저장과 약 4초의 시간 내역 조사는 남은 작업으로 추적한다.
성능·장애 허용·SLO 달성·운영 준비 완료 판정은 아니다.
후속 과정은 Mimir 연결과 지속 트래픽 아래 장애·재전송·저장·알림·복원 시험이다.
