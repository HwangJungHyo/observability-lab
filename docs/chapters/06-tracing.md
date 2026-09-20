# 6장 — OpenTelemetry와 Tempo

[챕터 지도](../roadmap.md)

## 목표와 완료 기준
한 주문의 호출 관계와 구간별 시간을 확인해 지연·실패 지점을 좁힌다.
Trace는 한 요청의 처리 흐름, Span은 그 안에서 측정하는 작업 구간이다.
request_id는 기존 업무 로그 연결용으로 유지한다. trace_id는 분산 트레이스의 식별자이며 자동으로 같은 값이 되지 않는다.
Tempo는 트레이스 저장·조회, OpenTelemetry는 계측·문맥 전달·전송, Grafana는 시각화를 맡는다.
설치만으로 과거 로그가 트레이스로 변환되지 않는다.

| 단계 | 범위 | 완료 기준 | 상태 |
|---|---|---|---|
| 6-1 | Tempo 저장·조회 기반 | ready 및 Grafana Tempo 연결 | 사용자 확인 완료 (2026-09-20) |
| 6-2 | 앱 OpenTelemetry 계측·Alloy OTLP 전달 | 주문 server → 결제 client → 결제 server span 연결 | 코드·HTTP 검증 완료 / Windows 수집 확인 대기 |
| 6-3 | trace_id 로그 연계 | 한 요청의 로그와 트레이스 상호 조회 | 예정 |
| 6-4 | 제어된 지연·중단·복구 | 지연 span, 오류 span 비교 및 원복·기록 | 예정 |

## 6-1 구성
공식 v3.0.3 single-binary 예제를 기반으로 필요한 저장·수신·조회만 구성한다.
metrics-generator·service graph·MCP는 이번 단계에서 활성화하지 않는다.
모놀리식 로컬 저장 방식이며 HA·운영 규모 검증은 범위 밖이다.
tempo-data 볼륨에 저장한다. 보관 기간·용량 정책은 아직 별도로 설정하지 않았다.
OTLP 4317/4318은 Docker 내부만 사용하고 호스트에는 조회·ready용 3200만 localhost로 공개한다.
6-2 경로: 앱 SDK → Alloy OTLP receiver → batch → Tempo → Grafana 조회.
6-1 당시에는 앱 계측 전이었다. 6-2에서 앱 계측과 Alloy OTLP 수신·전송 설정을 추가한다.

| 파일 | 역할 |
|---|---|
| compose.traces.yaml | Tempo 컨테이너·포트·볼륨 |
| tempo/tempo.yml | OTLP 수신 및 로컬 저장 |
| grafana/provisioning/datasources/tempo.yml | Grafana에서 http://tempo:3200 조회 |

### Windows Git Bash
~~~bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git fetch origin
git switch --track origin/lab/006-tracing
~~~
이미 브랜치가 있으면 git switch lab/006-tracing 후 git pull --ff-only를 사용한다.
로컬 수정이 있다면 덮어쓰지 않고 먼저 확인한다.

~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml config --quiet
~~~
오류가 없으면:
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml up -d tempo
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml ps tempo
curl -i --max-time 5 http://localhost:3200/ready
~~~
초기 준비 중이면 잠시 후 ready를 다시 확인한다. 200과 ready가 목표다.
그 후:
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml restart grafana
~~~
Grafana 데이터 소스 Tempo에서 연결 테스트를 하고 Explore에 Tempo가 나타나는지 확인한다.
Tempo 주소는 http://tempo:3200. Windows 브라우저용 localhost:3200과 구분한다.
현재 앱 계측 전이므로 트레이스 검색 결과가 비어 있는 것이 예상된다.

### 실패 점검·원복
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml logs --tail=100 tempo
~~~
기동 검증 없이 다음 계측 단계로 넘어가지 않는다.
Tempo만 중지하려면 같은 compose 인수 뒤에 stop tempo를 사용한다. down -v를 실행하지 않는다.
준비 환경에서는 공식 버전 예제와 설정 구조를 대조했다. Docker Desktop 실제 ready, 데이터 소스 uid=tempo 등록 및 연결 테스트는 2026-09-20 사용자 확인으로 완료했다.

## 추가로 알게 되는 것
메트릭은 발생 시각·빈도·영향 크기를, 로그는 특정 요청의 사건·오류 내용을 보여준다.
트레이스는 계측한 호출의 부모·자식 관계와 시작·종료 시간을 보여준다.
주문 전체 시간에는 결제 대기가 포함되므로 span 시간을 단순 합산하지 않는다.
DNS/TCP 세부 지연은 별도 계측 없이는 구분되지 않을 수 있다.
결제 프로세스가 중지된 경우 결제 server span이 없고 주문 측 client span만 실패할 수 있다.
트레이스는 수집·샘플링 범위의 증거이며 부재만으로 호출이 없었다고 확정하지 않는다.

## 근거
- https://github.com/grafana/tempo/tree/v3.0.3/example/docker-compose/single-binary
- https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/deploy/locally/

## 6-2 주문·결제 계측

### 파일과 데이터 흐름
- services/order-lab/app.py: 수동 server/client span, W3C traceparent 추출·전달, X-Trace-ID 응답 헤더.
- services/order-lab/requirements.txt: OpenTelemetry API/SDK/OTLP HTTP exporter 1.44.0 직접 의존성 고정. 전체 전이 의존성 잠금은 아직 아니다.
- compose.traces.yaml: 두 앱에 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://alloy:4318/v1/traces 전달.
- alloy/config.alloy: OTLP HTTP 수신 → batch → OTLP gRPC로 tempo:4317 전송. 기존 Docker 로그 → Loki는 별도 경로로 유지.
- tests/verify_order_traces.py: 실제 앱 프로세스와 HTTP/Protobuf 수신기로 계층·전파·오류 검증.

정상 요청의 span:
1. order-api / POST /orders / SERVER
2. order-api / POST /payments / CLIENT (1의 자식)
3. payment / POST /payments / SERVER (2의 자식)

공통 trace_id와 서로 다른 span_id를 갖는다. 두 POST /payments는 같은 서비스의 중복 로그가 아니라 호출자와 수신자의 측정이다.
request_id는 기존 로그 연결용으로 유지하며 trace_id와 별개다. 6-3에서 JSON 로그 연계를 추가한다.
측정 대상은 고정된 업무 POST 경로다. healthz, metrics, 알 수 없는 경로는 span을 생성하지 않는다.
HTTP server 5xx 및 외부 호출 예외는 ERROR, 정상 및 server 4xx는 UNSET으로 둔다. UNSET은 실패라는 뜻이 아니다.
추적 root는 실습에서 100% 샘플링하고 자식은 부모의 sampling flag를 따른다. 운영 비율은 별도 결정한다.
인증 헤더·본문·금액·원본 예외 메시지는 span에 기록하지 않는다. trace_id를 메트릭 라벨로 넣지 않는다.
OTLP endpoint가 없으면 전송하지 않으므로 기존 메트릭·로그 실습도 가능하다.
SDK는 bounded memory queue와 batch 전송을 사용한다. 수집기 장애가 주문 실패를 유발하지 않도록 분리하지만,
강제 종료·장기 전송 장애·큐 포화 때 span 유실이 가능하다. 무손실 전송 보장은 이번 범위 밖이다.

### 1. 소스 반영 및 검사
~~~bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git pull --ff-only origin lab/006-tracing
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml config --quiet
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml run --rm --no-deps alloy validate /etc/alloy/config.alloy
~~~
오류가 있으면 다음 단계로 넘어가지 않는다.

### 2. 수집기 반영 후 앱 재빌드
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml restart alloy
PAYMENT_DELAY_SECONDS=0.08 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml up -d --build payment order-api
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml ps alloy tempo payment order-api
~~~
API 재생성으로 잠시 중단되며 메모리 카운터가 초기화된다. Loki·Tempo 데이터 볼륨은 유지된다.
두 앱 healthy와 Alloy/Tempo Up 확인 후 주문을 만든다. Alloy가 Docker 로그 대상도 다시 탐색하도록 약 10초 여유를 둔다.

### 3. 주문 한 건과 Trace ID
~~~bash
request_id="trace-$(date +%s)-$RANDOM"
curl -i --max-time 10 -X POST http://localhost:18080/orders \
  -H 'Content-Type: application/json' \
  -H "X-Request-ID: $request_id" \
  -d '{"amount":10000}'
~~~
HTTP 201, X-Request-ID, X-Trace-ID(32자리 16진수)를 확인한다.
X-Trace-ID를 복사하고 수 초 후 Grafana Explore → Tempo에서 Trace ID 조회를 한다.
Trace ID 직접 조회 모드에서는 복사한 ID만 입력한다.
서비스로 검색할 때는 Last15m 범위에서:
~~~traceql
{ resource.service.name = "order-api" }
~~~
목록에서 방금 발생한 요청을 열어 세 span의 부모·자식 관계를 확인한다.
전송이 비동기라 응답 직후에는 보이지 않을 수 있다. 몇 초 후 새로고침한다.

### 4. 검색 실패 진단
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml logs --since=5m --tail=100 order-api payment alloy tempo
~~~
- X-Trace-ID 없음: 앱 이미지 갱신 및 OTLP endpoint 환경 변수 적용 확인.
- 헤더는 있지만 검색 안 됨: 앱 exporter 오류 → Alloy receiver/exporter 오류 → Tempo 순서로 조사.
- 서로 다른 trace로 분리: traceparent 전달 및 두 서비스 최신 이미지 여부 확인.
6-2 완료는 사용자 Grafana에서 실제 주문·결제 세 span을 확인한 뒤 기록한다.

### 원복
traces overlay를 제외하고 두 앱을 재생성하면 OTLP endpoint가 제거되어 앱 트레이스 전송이 꺼진다.
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml up -d --force-recreate payment order-api
~~~
이 명령은 Loki/Tempo 볼륨을 삭제하지 않는다. 실습을 계속하면 원복하지 않는다.

### 검증 근거
준비 환경 Python 3.12에서 requirements 설치 후 세 테스트를 실행했다.
- verify_order_traces.py: 실제 OTLP HTTP protobuf 수신, 동시 요청 trace 분리, 3-span 부모 관계, 외부 traceparent 전파, 400/502 상태, 수집기 없이도 주문 성공.
- verify_order_metrics.py: 기존 201/400/502/504 카운터·히스토그램 및 상태 점검 제외.
- verify_request_logs.py: 기존 request_id 전파, JSON 수준·오류·시각, 동시 요청 연결.
공식 Alloy v1.19.2 Linux 실행 파일의 validate 검사도 통과했다.
이는 앱 → 테스트 수신기 검증이다. 사용자 Docker Desktop의 Alloy → Tempo → Grafana 종단 검증은 별도 대기다.

참고:
- https://opentelemetry.io/docs/languages/python/instrumentation/
- https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.receiver.otlp/
- https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlp/
