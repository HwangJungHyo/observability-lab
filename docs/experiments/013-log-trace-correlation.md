# 013 — 로그·트레이스 양방향 연결 검증

## 환경과 근거
- 실행일: 2026-09-21, Windows / Git Bash / Docker Desktop
- 브랜치: lab/006-tracing, 실행 구성 기준 커밋: 703b26f
- 근거: 사용자 제공 응답 헤더·JSON 로그·Grafana 화면과 양방향 링크 클릭 성공 확인.
- 이 보고서는 사용자 환경의 관찰 기록이다. 별도 환경에서 재실행한 결과가 아니다.

## 연결 대상
- Request ID: recovered-1789986969-2212
- Trace ID: 8fe06bf1dd7a33597f7877e8e75dfffa
- 응답: HTTP 201, X-Trace-ID가 위 ID와 일치.
- Grafana: Services 2, spans 3.

| 로그 서비스 | 작업 | HTTP | duration_ms | span_id |
|---|---|---:|---:|---|
| payment | POST /payments | 200 | 80.549 | 6b94d70320984e4a |
| order-api | POST /orders | 201 | 82.604 | 14e39c58522f82b6 |

두 로그는 같은 request_id와 trace_id, 서로 다른 SERVER span_id를 갖는다.
CLIENT span에는 별도의 request_completed 로그를 생성하지 않으므로 완료 로그는 두 줄이다.

## 실제 확인한 탐색 흐름
1. Tempo에서 복구 trace의 SERVER span을 선택하고 Logs for this span으로 Loki 로그를 조회했다.
2. 위 주문·결제 로그의 trace_id가 복구 trace와 일치함을 확인했다.
3. 로그의 View trace로 같은 trace의 세 span 화면에 돌아왔음을 사용자가 확인했다.

6-3 완료. 역방향 쿼리는 선택한 span 하나가 아니라 동일 trace의 두 서비스 로그를 조회한다.

~~~logql
{environment="lab", service_name=~"order-api|payment"}
| json
| __error__=""
| trace_id="8fe06bf1dd7a33597f7877e8e75dfffa"
~~~

조회 시간 범위에는 2026-09-21 19:35:57 KST (10:35:57 UTC)를 포함한다.

## 복구 로그 원문
~~~json
{"timestamp":"2026-09-21T10:35:57.958+00:00","level":"info","service":"payment","event":"request_completed","request_id":"recovered-1789986969-2212","method":"POST","route":"/payments","status_code":200,"duration_ms":80.549,"error":null,"trace_id":"8fe06bf1dd7a33597f7877e8e75dfffa","span_id":"6b94d70320984e4a"}
{"timestamp":"2026-09-21T10:35:57.959+00:00","level":"info","service":"order-api","event":"request_completed","request_id":"recovered-1789986969-2212","method":"POST","route":"/orders","status_code":201,"duration_ms":82.604,"error":null,"trace_id":"8fe06bf1dd7a33597f7877e8e75dfffa","span_id":"14e39c58522f82b6"}
~~~

## 설정과 한계
- grafana/provisioning/datasources/loki.yml: derivedFields로 JSON의 trace_id에서 Tempo로 연결한다.
- grafana/provisioning/datasources/tempo.yml: tracesToLogsV2로 동일 trace_id를 Loki에서 검색한다. 시간 범위는 span 전후 1분이다.
- trace_id / span_id는 JSON 필드이며 Loki 인덱스 라벨이나 Prometheus 라벨에 추가하지 않는다.
- ID가 있어도 샘플링·전송 실패·보관 기간에 따라 연결할 trace가 없을 수 있다.
- 이번에는 정상·복구 요청의 연결을 확인했다. 중단 장애의 오류 span과 로그 비교는 다음 실험에서 확인한다.

관련: [1초 지연·복구](014-payment-delay-traces.md) / [6장](../chapters/06-tracing.md)
