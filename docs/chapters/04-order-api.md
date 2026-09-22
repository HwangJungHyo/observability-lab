# 4장. 주문 API 가시화

[챕터 지도](../roadmap.md) · [구조도](../architecture.md)

## 4-1 목적과 범위

Windows → 주문 API → 모의 결제 → 주문 응답 경로를 먼저 검증한다.
observability-lab에는 API 소스가 없으므로 Python 표준 라이브러리로 작은 실습 서비스를 추가했다.
한 소스를 SERVICE_NAME 환경변수로 두 역할에 사용한다. 기존 별도 프로젝트는 수정하지 않는다.

이 서비스는 로컬 관측 실험용이다. DB·영구 주문 저장·중복 결제 방지·실제 결제·인증은 구현하지 않는다.
Python http.server 기반 서버는 운영용 웹 서버로 권장되지 않는다.
향후 임계값 실험의 측정값도 이 합성 서비스와 실행 조건 범위에서만 해석한다.
https://docs.python.org/3/library/http.server.html

## 파일

| 파일 | 역할 |
|---|---|
| compose.orders.yaml | 기존 Compose에 두 API 서비스 추가 |
| services/order-lab/app.py | 주문 검증, 결제 호출, 타임아웃·오류 처리 |
| services/order-lab/Dockerfile | Python 3.12 이미지, UID 10001 |
| services/order-lab/.dockerignore | 필요한 소스만 빌드에 포함 |

이미지 태그 python:3.12-slim은 digest 고정이 아니므로 완전한 빌드 재현은 보장하지 않는다.
주문 API healthz는 해당 프로세스 확인용이며 결제 서비스 정상까지 보장하지 않는다.

## Windows Git Bash 실행

```bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git fetch origin
git switch --track origin/lab/004-order-api
```

같은 이름의 로컬 브랜치가 이미 있다면 git switch lab/004-order-api 후 git pull --ff-only를 사용한다.
로컬 변경이 전환을 막으면 강제 덮어쓰지 않는다.

```bash
docker compose -f compose.yaml -f compose.orders.yaml config --quiet
docker compose -f compose.yaml -f compose.orders.yaml up -d --build payment order-api
docker compose -f compose.yaml -f compose.orders.yaml ps payment order-api
```

두 서비스가 healthy인지 확인한다. 초기 기동 중 starting이면 잠시 후 다시 조회한다.
payment는 내부 포트 8081만 사용하고, order-api만 127.0.0.1:18080에 공개한다.
기존 prometheus·grafana·alertmanager를 재생성할 필요는 없다.

```bash
curl -sS --max-time 5 http://localhost:18080/healthz
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
```

정상 기준: healthz HTTP 200 및 service=order-api, 주문 HTTP 201 및 status=confirmed.
order_id와 payment_id는 매 요청 달라진다. amount는 최소 1, 최대 100000000의 정수다.
모의 결제는 약 80ms 대기 후 승인한다. 이 대기는 실제 CPU 처리 부하 모델이 아니다.

## 오류 점검 및 종료

```bash
docker compose -f compose.yaml -f compose.orders.yaml logs --tail=100 order-api payment
```

| 증상 | 확인 |
|---|---|
| 18080 바인딩 실패 | 기존 사용 프로세스 확인 |
| HTTP 400 | JSON과 amount 정수 범위 |
| HTTP 502 | 결제 서비스 실행·주소·응답 |
| HTTP 504 | 결제 응답 타임아웃(기본 2초) |
| 이미지 빌드 실패 | Docker Desktop 및 이미지 다운로드 연결 |

두 서비스만 중지:

```bash
docker compose -f compose.yaml -f compose.orders.yaml stop order-api payment
```

4장 서비스 작업에는 항상 두 -f 옵션을 함께 사용한다.
전체 down이나 --remove-orphans는 다른 관측 서비스까지 영향을 줄 수 있으므로 이번 종료에 사용하지 않는다.

## 검증 범위

준비 환경 Python에서 HTTP 정상 주문·잘못된 요청·결제 중단 경로를 검사했다.
2026-09-17 사용자 Windows에서 두 컨테이너 healthy, healthz 200, 주문 201/confirmed를 확인했다.
4-1 완료. 4-2 계측 소스는 준비 환경에서 검증했으며 Windows 적용·Prometheus 수집은 별도 확인한다.



## 4-2 메트릭 계측

[app.py 요청 처리 순서](04-app-walkthrough.md)

### 측정 계약

- 각 서비스의 고정 업무 경로 POST /orders 또는 POST /payments만 센다.
- GET /healthz, GET /metrics, 알 수 없는 경로 및 미지원 메서드는 업무 통계에서 제외한다.
- lab_http_requests_total: 응답 코드별 처리 횟수. service, method, route, status_code 라벨.
- lab_http_request_duration_seconds: 서버 핸들러 시작부터 응답 쓰기까지 초 단위 소요 시간. service, method, route 라벨.
- 주문 시간에는 결제 대기가 포함된다. 클라이언트 네트워크 왕복·요청 파싱 전 대기는 포함하지 않는다.
- 상태 코드는 서버가 선택한 응답 코드이며 클라이언트의 수신 완료를 보장하지 않는다.
- 400은 입력 오류, 5xx는 시스템 오류로 나누어 본다. 분모는 유효 경로의 모든 POST(400 포함)다.
- 주문 ID·결제 ID·금액·원문 URL은 라벨로 넣지 않는다.
- Counter는 프로세스 재시작 시 초기화된다. rate()는 카운터 재시작을 처리한다.
- Histogram 버킷은 25ms~5s. 모의 결제 80ms 및 타임아웃 2s 주변을 관찰하기 위한 실습 선택이며 운영 임계값이 아니다.
- prometheus-client==0.22.1로 의존성을 고정한다. 최신 버전이라는 의미는 아니다.

### 반영

저장소 루트, lab/004-order-api에서 실행한다. 로컬 변경이 있으면 내용을 확인하고 pull 충돌을 강제로 덮어쓰지 않는다.

```bash
git status --short --branch
git pull --ff-only origin lab/004-order-api
docker compose -f compose.yaml -f compose.orders.yaml config --quiet
docker compose -f compose.yaml -f compose.orders.yaml up -d --build payment order-api
MSYS_NO_PATHCONV=1 docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
```

promtool SUCCESS를 확인한 뒤에만 설정을 재적용한다. 설정 파일 자체의 바인드 마운트가 파일 교체로 오래된 내용을 가리킬 가능성도 있어 이번에는 Prometheus를 재생성한다. 기존 명명 볼륨의 데이터는 유지되며 잠시 수집이 중단된다.

```bash
docker compose -f compose.yaml -f compose.orders.yaml up -d --no-deps --force-recreate prometheus
curl -fsS --max-time 5 http://localhost:18080/metrics | grep '^lab_http_'
```

Prometheus에서 up{job=~"order-api|payment"}의 두 대상이 모두 1인지 확인한다.
주소는 Docker 네트워크의 order-api:8080, payment:8081이다. localhost:18080은 Windows에서 접근하는 주소다.

### 요청 생성과 확인

먼저 scrape가 2회 이상 끝날 때까지 약 30초 기다린 후 Git Bash에서 실행한다.

```bash
for i in {1..60}; do
  curl -sS --max-time 5 -o /dev/null -w 'HTTP %{http_code} duration=%{time_total}s
' \
    -X POST http://localhost:18080/orders \
    -H 'Content-Type: application/json' -d '{"amount":10000}'
  sleep 1
done
```

이는 순차 요청을 보내 수집을 검증하는 작업이다. 처리량 한계 측정이나 운영 부하 모델이 아니다. 60회 모두 201인지 확인한다.

PromQL:

```promql
sum by (status_code) (lab_http_requests_total{job="order-api",route="/orders"})
```

```promql
sum(rate(lab_http_requests_total{job="order-api",route="/orders"}[2m]))
```

시스템 오류율(%). 무요청 구간 0/0은 NaN으로 남긴다. 정상 요청 구간에서 0인지 확인한다.

```promql
100 * sum(rate(lab_http_requests_total{job="order-api",route="/orders",status_code=~"5.."}[2m]))
/ sum(rate(lab_http_requests_total{job="order-api",route="/orders"}[2m]))
```

평균 서버 처리 시간(초):

```promql
sum(rate(lab_http_request_duration_seconds_sum{job="order-api",route="/orders"}[2m]))
/ sum(rate(lab_http_request_duration_seconds_count{job="order-api",route="/orders"}[2m]))
```

p95(초, 버킷 기반 추정치):

```promql
histogram_quantile(0.95,
  sum by (le) (rate(lab_http_request_duration_seconds_bucket{job="order-api",route="/orders"}[2m]))
)
```

p95는 요청이 적을 때 대표성이 낮다. 버킷 경계 때문에 실제 개별 요청 지연과 차이가 난다.
다음 실습에서 위 쿼리를 Grafana 패널로 구성하고 통제된 오류·지연 실험을 진행한다.

### 준비 환경 검증

Python 프로세스 두 개로 정상201, 입력오류400, 결제중단502, 느린 결제504를 검증했다.
각 코드의 Counter, Histogram 횟수·시간, payment의 처리 횟수, 상태점검·metrics·없는 경로 제외, 초기 0 시계열을 검사했다.
Docker 빌드·Windows 적용 및 실제 Prometheus 수집은 이 검증에 포함하지 않는다.

### 근거

- https://prometheus.github.io/client_python/instrumenting/histogram/
- https://prometheus.github.io/client_python/instrumenting/labels/
