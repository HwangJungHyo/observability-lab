# 014 — 결제 1초 지연·복구 트레이스 비교

## 목적과 실행 근거
결제 내부 대기가 주문 전체 지연에 어떻게 반영되는지 SERVER / CLIENT span으로 확인한다.
2026-09-21 사용자 Windows / Docker Desktop / Git Bash, lab/006-tracing (구성 기준 703b26f).
근거는 사용자 터미널 출력, Grafana의 지연·복구 트레이스 화면, 복구 JSON 로그다.
한 요청씩 관찰한 결과이며 처리 용량이나 운영 임계값을 산출하는 부하 시험이 아니다.

## 요청 식별자

| 구간 | Request ID | Trace ID |
|---|---|---|
| 변경 전 정상 | link-1789986327-30862 | 3cad91432540a592e5a81dd2e7d28571 |
| 1초 지연 | delay1s-1789986725-15377 | 3dd6efa224fe90eb53ee4f045e15c633 |
| 최종 복구 | recovered-1789986969-2212 | 8fe06bf1dd7a33597f7877e8e75dfffa |

## 변경·검증·복구 순서
1. 정상 요청 HTTP 201과 X-Trace-ID 확인.
2. PAYMENT_DELAY_SECONDS=1로 payment만 재생성.
3. 컨테이너 printenv 값 1, 주문·결제 healthy 확인.
4. 지연 요청 HTTP 201, curl 전체 시간 1.221444초 확인.
5. 0.08로 복구한 뒤 실수로 1을 재적용했다. 이 중간 상태를 최종 복구로 판정하지 않았다.
6. 다시 0.08로 재생성하고 실제 printenv 0.08, 두 서비스 healthy 확인.
7. 복구 요청 HTTP 201, curl 전체 시간 0.301197초 및 복구 트레이스·로그 확인.

## 실측

| 항목 | 지연 | 복구 |
|---|---:|---:|
| PAYMENT_DELAY_SECONDS | 1 | 0.08 |
| 주문 HTTP | 201 | 201 |
| curl time_total | 1.221444s | 0.301197s |
| order-api SERVER /orders | 화면 1s | 82.73ms |
| order-api CLIENT /payments | 화면 1s | 82.34ms |
| payment SERVER /payments | 화면 1s | 80.77ms |

지연 트레이스 시작: 화면 2026-09-21 19:31:54.225 KST.
복구 트레이스 시작: 화면 2026-09-21 19:35:57.876 KST.
두 화면 모두 Services 2 / spans 3, 주문 응답 201.
지연 span의 1s는 화면 반올림 표시다. 정확한 소수점 duration을 확보한 것으로 기록하지 않는다.

복구 로그: 결제200 / 80.549ms / error=null, 주문201 / 82.604ms / error=null.
원문과 span_id는 [실험 013](013-log-trace-correlation.md)에 기록했다.

## 해석
- curl 두 표본의 차이는 0.920247초이며 설정 감소분 0.92초와 거의 일치한다.
- 결제 SERVER 복구 시간 80.77ms는 내부 대기 80ms와 부합한다.
- 결제 내부 대기가 증가하자 이를 기다리는 CLIENT와 주문 SERVER도 함께 길어졌다.
- 세 span은 포함 관계이므로 duration을 더하지 않는다.
- 두 화면은 시간축이 각각 약 1초 / 82.73ms로 자동 조정된다. 막대의 화면 길이만 비교하지 않는다.
- 복구 CLIENT와 결제 SERVER 차이 약 1.57ms를 순수 네트워크 시간으로 단정하지 않는다.
- curl 301.197ms와 주문 span 82.73ms는 측정 범위가 다르다. 차이 약 218.467ms의 세부 원인은 추가 계측 없이 확정하지 않는다.
- 로그 duration_ms는 로그 출력 전 계산하고 span은 블록 종료 시 끝나므로 로그와 trace 시간이 조금 다르다.
- 단일 요청의 duration은 평균·p95·SLO 판정이 아니다. 오류율 0%도 이번 201 응답만으로 확정하지 않는다.

## 재현 명령
저장소 루트에서 실행한다. 먼저 두 서비스가 정상인 상태에서 기준 요청을 남긴다.
payment 재생성으로 해당 프로세스의 메모리 메트릭 카운터는 초기화된다.

~~~bash
PAYMENT_DELAY_SECONDS=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml up -d --no-deps --force-recreate payment
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml exec -T payment printenv PAYMENT_DELAY_SECONDS
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml ps payment order-api
~~~

값 1과 healthy 확인 후 요청한다.

~~~bash
request_id="delay1s-$(date +%s)-$RANDOM"
curl -i --max-time 10 -w '\nHTTP %{http_code} duration=%{time_total}s\n' -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -H "X-Request-ID: $request_id" -d '{"amount":10000}'
~~~

응답의 X-Trace-ID로 Tempo에서 세 span을 비교하고, 로그 링크를 확인한다.
관찰 후 다음 명령으로 복구한다.

~~~bash
PAYMENT_DELAY_SECONDS=0.08 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml up -d --no-deps --force-recreate payment
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml exec -T payment printenv PAYMENT_DELAY_SECONDS
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml ps payment order-api
~~~

값 0.08과 healthy 확인 후 새 recovered 접두사 요청으로 201과 시간 감소를 확인한다.
명령 앞 환경변수는 해당 Compose 실행에 전달된다. YAML 기본값 0.08을 수정하지 않는다.
컨테이너 생성 당시의 값은 유지되므로 파일의 기본값만 보고 복구를 판정하지 않는다.

## 완료 범위와 다음 단계
6-4a 제어된 1초 지연·복구·기록 완료.
6-4b 결제 중단 시 오류 span·로그 비교와 복구는 아직 미수행이다.
5장의 결제 중단 로그 실험을 6장의 오류 trace 검증으로 대신하지 않는다.
6장 전체 완료는 남은 중단 실험 이후 판단한다.

[6장 가이드](../chapters/06-tracing.md) / [챕터 지도](../roadmap.md)
