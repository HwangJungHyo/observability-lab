# 실험 007 — 결제 중단에 따른 주문 실패와 복구

[챕터 지도](../roadmap.md) · [주문 API 가이드](../chapters/04-order-api.md)

## 목적과 범위

주문 프로세스가 응답 가능한 상태에서도 결제 의존성 중단으로 주문 기능이 실패하는지 검증한다.
HTTP 응답과 Grafana의 요청량·5xx 오류율·평균·p95를 함께 관측한다.
2026-09-17 Windows Git Bash + Docker Desktop, lab/004-order-api에서 수행.
계측 소스 커밋 33ffa74, 대시보드 커밋 595bbb5.
증거는 사용자가 제공한 터미널 출력과 Grafana 캡처이며, 이 보고서 작성 환경에서 사용자 PC를 직접 실행한 것은 아니다.
원본 캡처 파일은 이 커밋에 포함하지 않는다.

## 진행과 증거 (KST)

| 시점 | 관측 |
|---|---|
| 23:46:37 | date 출력 후 payment stop 실행. Stopped 완료 출력은 약 3.1초 후 |
| 23:46:56 | 주문 /healthz HTTP 200, status=ok, service=order-api (응답 Date에서 환산) |
| 23:47:04 | POST /orders HTTP 502, error=payment_unavailable (응답 Date에서 환산) |
| 장애 요청 반복 | 제공된 27개 출력에서 HTTP 502, curl total 약 3.84~3.90초 |
| 결제 재시작 | Started 확인. 직후 health: starting, 주문 컨테이너는 healthy |
| 약 23:49:56 | 사용자 로컬 date 출력 후 주문 201/confirmed 확인. HTTP Date는 23:49:55로 1초 차이가 있어 정밀 복구시간 산출에 사용하지 않음 |
| 복구 요청 반복 | 제공된 9개 출력에서 HTTP 201, curl total 약 0.28~0.31초 |
| 후속 사용자 확인 | 지표가 점차 하락 중임을 확인 |

반복 명령은 60회로 작성됐으나 출력은 일부만 제공됐다. 60회 모두 성공/실패했다고 기록하지 않는다.
결제 중지부터 첫 성공 확인까지는 약 3분 19초지만 실제 장애 지속 시간이나 MTTR로 확정하지 않는다.
복구 명령 완료 시각과 첫 복구 가능 시점을 연속 측정하지 않았기 때문이다.

## 관측 결과

| 지표 | 캡처에서 확인 | 해석 |
|---|---|---|
| Request Rate | 장애 구간 약 0.2 req/s 수준 | 순차 요청이 약 3.85초 응답 대기 + 1초 sleep로 제한됨 |
| Server Error Rate | 100% 구간 후 하락 | 최근 2분의 실패 요청에 정상 요청이 섞이기 시작 |
| Average Latency | 약 4초 구간 후 하락 | 서버 처리 시간의 이동 구간 평균 |
| P95 Latency | 약 4.875초 구간 후 하락 | Histogram 버킷 기반 추정값 |

순차 요청의 이론적 빈도는 1/(3.85+1) ≈ 0.206 req/s다. 실제 그래프는 수집 간격·이동 구간·부가 실행 시간에 영향을 받는다.
이 요청 생성 방식으로 서비스 최대 처리량이나 독립적인 고객 유입량을 측정했다고 해석하지 않는다.
서버 평균과 curl의 개별 total은 측정 범위와 집계 구간이 다르므로 동일 표본의 값으로 비교하지 않는다.

Histogram 경계에 2.5초와 5초가 있다. 관측값이 모두 이 구간에 있으면 선형 보간 p95는
2.5 + (5 - 2.5) × 0.95 = 4.875초가 될 수 있다.
이는 개별 요청이 실제로 4.875초 걸렸다는 증거가 아니다.

## 재현과 원복

저장소 루트에서 다음 순서로 수행했다.

~~~bash
date -Iseconds
docker compose -f compose.yaml -f compose.orders.yaml stop payment
curl -i --max-time 5 http://localhost:18080/healthz
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
~~~

요청 반복 (장애 중 및 복구 후 각각 사용):

~~~bash
for i in {1..60}; do
  curl -sS --max-time 5 -o /dev/null \
    -w 'HTTP %{http_code} duration=%{time_total}s\n' \
    -X POST http://localhost:18080/orders \
    -H 'Content-Type: application/json' -d '{"amount":10000}'
  sleep 1
done
~~~

원복:

~~~bash
docker compose -f compose.yaml -f compose.orders.yaml start payment
docker compose -f compose.yaml -f compose.orders.yaml ps payment order-api
date -Iseconds
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
~~~

## 판정과 남은 확인

- [x] 주문 healthz=200인 상태에서 실제 주문=502 확인
- [x] 장애 요청의 수 초 지연 및 Grafana 오류율 100% 구간 확인
- [x] 결제 재시작 후 실제 주문=201/confirmed 확인
- [x] 복구 후 오류율·평균·p95 하락 관측
- [ ] 복구 후 두 대상 up=1의 최종 결과 확인
- [ ] 정상 요청 지속 구간에서 오류율 0% 확인
- [ ] 평균·p95의 정상 수준 안정화 확인 (이전 평균 약 86~88ms와 비교)
- [ ] 별도 제어된 결제 지연 주입 실험

HTTP 수준 기능 복구는 확인됐다. 지표의 완전 정상화는 확인 대기다.
복구 후에도 최근 2분 구간에 실패 표본이 남아 있어 지표가 즉시 정상으로 돌아오지 않을 수 있다.
정상 요청을 계속 발생시키며 확인해야 무요청 구간의 NaN과 오류율 0%를 구분할 수 있다.
이번 실험은 주문 오류 알림 규칙이나 Slack/Gmail 통보 검증을 포함하지 않는다.

## 배운 점과 미확정 사항

1. 프로세스 healthz 성공은 고객 주문 기능의 성공을 보장하지 않는다.
2. 결제 중단이 항상 빠른 실패로 이어지지는 않는다. 이번에는 실패 응답까지 약 3.85초가 걸렸다.
3. urlopen(timeout=2)는 전체 주문 요청을 2초 안에 끝내는 엄격한 마감 시간이 아니다.
   약 3.85초 중 DNS·연결·기타 구간의 비중은 미계측이므로 원인을 확정하지 않는다.
4. 순차 부하 생성은 응답 지연에 따라 요청 빈도가 변한다.
5. Histogram의 넓은 버킷은 분위수 해석을 제한한다. 측정 해상도와 운영 임계값은 구분한다.

참고: https://docs.python.org/3/library/urllib.request.html#urllib.request.urlopen
