# 5장 — Alloy·Loki 로그 조사

[챕터 지도](../roadmap.md)

## 목표와 현재 단계
5-1: 주문·결제 컨테이너의 기존 stdout/stderr 로그를 Grafana에서 검색한다.
5-2: JSON 로그와 request_id 전달을 추가해 주문·결제 요청을 연결한다.
5-3: 장애 재현 → 메트릭의 시간대 확인 → 로그 검색 → 복구·기록.
5-1은 사용자 Grafana 화면에서 주문201·결제200 접근 로그를 확인해 완료했다.
5-2는 Windows에서 같은 request_id의 주문201·결제200 JSON 로그를 확인해 완료했다. 실험 010 참조.

## 구조와 파일

| 저장소 파일 | 적용 대상 | 역할 |
|---|---|---|
| compose.logs.yaml | Docker Compose | Loki·Alloy 서비스와 저장 볼륨 |
| loki/loki.yml | Loki /etc/loki/loki.yml | 단일 프로세스 TSDB·filesystem·7일 보관 |
| alloy/config.alloy | Alloy /etc/alloy/config.alloy | Docker 대상 탐색·라벨 지정·로그 전송 |
| grafana/provisioning/datasources/loki.yml | Grafana 데이터 소스 | 내부 http://loki:3100 조회 |

5-1 당시 주문·결제 app.py는 HTTP 접근 로그를 stderr에 기록했다. 5-2부터 업무 요청 완료 JSON을 stdout에 기록한다. Docker가 이를 보관하고 Alloy가 Docker API로 읽어 Loki로 보낸다.
Grafana는 Loki를 조회한다. 로그 수집 경로에 Prometheus는 들어가지 않는다.
Docker 프로젝트 observability-lab의 order-api, payment 두 서비스만 대상으로 선정한다.
라벨은 service_name, environment=lab, job=order-lab-logs 중심으로 제한한다.
5-1 로그에는 request_id·처리 시간이 없다. 5-2 JSON에 request_id·duration_ms·error 분류를 추가한다.
5-1에서는 healthz·metrics 접근 로그도 수집했다. 5-2부터 해당 접근 로그는 출력하지 않는다.

## 제품과 운영 범위
- grafana/loki:3.7.8, grafana/alloy:v1.19.2 태그 고정. digest 고정은 아직 아니다.
- Loki는 로컬 디스크 단일 인스턴스다. HA·운영 부하 검증 환경이 아니다.
- retention_period=168h와 compactor로 약 7일 보관 정책을 적용한다. 삭제는 비동기이며 용량 상한을 보장하지 않는다.
- Alloy positions는 명명 볼륨에 보존한다. 최초 연결 시 Docker에 남아 있는 이전 로그를 읽을 수 있다.
- 새 로그의 수집을 검증해야 한다. 시작 이전 로그의 완전한 복구를 보장하지 않는다.
- Loki auth_enabled=false. Loki와 Alloy UI 호스트 포트는 127.0.0.1에만 바인딩한다.
- Alloy는 Docker 소켓 접근을 위해 root로 실행한다. 소켓의 :ro 마운트는 Docker API를 읽기 전용으로 제한하지 않는다.
  이 로컬 실습에서 사용하는 직접 소켓 접근 구성은 운영 배포 전 최소 권한 API 중계·노드 로그 접근 방식 등을 재검토해야 한다.
- 수집 대상 필터는 로그 범위를 제한하지만 Docker 소켓 권한 자체를 제한하지 않는다.

## 1. 브랜치 가져오기 (Windows Git Bash)
~~~bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git fetch origin
git switch --track origin/lab/005-logging
~~~
이미 로컬 브랜치가 있으면 git switch lab/005-logging 후 git pull --ff-only를 사용한다.
로컬 변경과 충돌하면 강제로 덮어쓰지 않는다. main은 병합하지 않는다.

## 2. Compose·제품 설정 검사
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml config --quiet
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml run --rm --no-deps loki -config.file=/etc/loki/loki.yml -verify-config=true
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml run --rm --no-deps alloy validate /etc/alloy/config.alloy
~~~
Loki config is valid, Alloy는 오류 없이 종료돼야 한다. 최초 실행은 이미지를 다운로드한다.

## 3. 로그 수집기 실행
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml up -d loki alloy
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml ps loki alloy
curl -sS --max-time 5 http://localhost:3100/ready
curl -sS --max-time 5 http://localhost:12345/-/ready
~~~
Loki는 기동 후 준비까지 수십 초 걸릴 수 있다. 준비 중 메시지가 보이면 잠시 후 다시 확인한다.
서비스 Up은 로그 수집 완료를 뜻하지 않는다.
Alloy UI http://localhost:12345 에서 discovery와 loki 컴포넌트를 점검할 수 있다.
이 실습의 설정 검증 통과는 Docker 소켓 접근·실제 전송 성공을 보장하지 않는다.

## 4. Grafana 데이터 소스 적용
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml restart grafana
~~~
기존 디렉터리 마운트 안에 새 데이터 소스 파일을 추가했으므로 재시작해 provisioning을 읽는다.
Grafana만 잠시 재시작되며 Prometheus 수집과 주문 API는 계속 실행된다.
http://localhost:3001 에서 Explore를 열고 데이터 소스 Loki를 선택한다.

## 5. 5-1 당시 평문 로그 발생과 검색
Alloy 시작 후 대상 탐색까지 약 5~10초 기다린 뒤 주문을 생성한다.
~~~bash
date -Iseconds
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
~~~
201/confirmed 확인. Explore에서 Last15m, 현재 시간으로 조회한다. Code 모드의 LogQL:
~~~logql
{environment="lab", service_name="order-api"} |= "POST /orders"
~~~
~~~logql
{environment="lab", service_name="payment"} |= "POST /payments"
~~~
새 요청 시각에 주문201과 결제200 접근 로그를 확인한다.
5-1 당시에는 request_id가 없어 시간대·서비스·경로·코드로 좁힌다. 동일 요청을 확정적으로 연결하는 것은 다음 단계다.

## 6. 수집 문제 점검
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml logs --since=5m --tail=100 alloy loki
docker compose -f compose.yaml -f compose.orders.yaml logs --since=5m --tail=30 order-api payment
~~~
- API에 로그가 없음: 새 주문을 발생시키고 해당 서비스의 실행·응답 확인.
- API에는 있고 Loki에는 없음: Alloy Docker 접근·discovery 대상·라벨·Loki readiness·전송 오류 확인.
- Loki 데이터 소스 없음: Grafana 재시작 후 provisioning 로그 확인.
- 과거 시각으로 고정된 조회는 해제하고 현재 새 요청 시각으로 확인.
- 전송 오류가 있었다면 readiness 이후 새 요청으로 다시 검증.

## 종료·원복
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml stop alloy loki
~~~
다른 관측·API 서비스를 중지하지 않는다. 볼륨은 남긴다.
계속 실습한다면 종료하지 않고 5-2로 이어간다.

## 검증
준비 환경에서 위 버전 공식 Linux 실행 파일로 Loki -verify-config와 Alloy validate를 실행해 성공했다.
YAML 파싱도 확인했다. 5-1 Docker Desktop 실제 수집과 Grafana 주문·결제 조회는 사용자 캡처로 확인했다.

## 근거
- https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/
- https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.docker/
- https://grafana.com/docs/loki/latest/get-started/quick-start/quick-start/

## 5-2 JSON 로그와 요청 ID

### 무엇이 달라지는가
X-Request-ID 헤더를 읽어 주문에서 결제로 전달하고 각 응답 헤더에도 반환한다.
없거나 허용 형식(영문·숫자·밑줄·하이픈 1~64자)이 아니면 UUID를 생성한다.
입력 ID는 상관관계 검색용이며 인증이나 중복 주문 방지 수단이 아니다. 재사용하면 여러 요청이 함께 검색된다.
각 서비스의 유효 업무 POST 처리 완료 시 JSON 한 줄을 stdout에 기록한다.
기존 기본 access log는 중복을 막기 위해 끈다. healthz·metrics·없는 경로·미지원 메서드는 이번 업무 로그 범위에서 제외한다.
이 로그는 전체 HTTP 보안 감사 로그가 아니다.

필드:
- timestamp: UTC ISO8601(+00:00)
- level: 2xx/3xx info, 4xx warn, 5xx error (우리 실습의 선택)
- service: order-api 또는 payment
- event: request_completed (시작 로그는 service_started)
- request_id: 주문·결제의 같은 요청을 찾는 키
- method, route, status_code: 업무 경로와 응답 코드
- duration_ms: 서버 처리 시간, 밀리초
- error: 성공 시 null, 실패 시 invalid_request/payment_unavailable/payment_timeout 등의 분류

본문·금액·인증 헤더는 기록하지 않는다. request_id는 Prometheus 라벨이나 Loki 수집 라벨로 올리지 않는다.
Alloy는 JSON 원문을 그대로 전송한다. 조회 시 LogQL의 json으로 필드를 추출한다.
기존 평문 로그도 보관 기간 동안 남아 있다.
기존 '|= "POST /orders"' 검색은 새 JSON의 method/route 분리 형식과 일치하지 않으므로 아래 쿼리를 쓴다.

### 반영
~~~bash
git status --short --branch
git pull --ff-only origin lab/005-logging
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml config --quiet
~~~
검사 성공 후:
~~~bash
PAYMENT_DELAY_SECONDS=0.08 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml up -d --build --force-recreate payment order-api
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml ps payment order-api
~~~
두 API가 잠시 중단되고 메모리 Counter가 초기화된다. rate는 카운터 초기화를 처리하지만 재생성 직후 구간을 성능 비교에 쓰지 않는다.
Alloy가 새 컨테이너를 탐색하도록 healthy 이후 약 10초 기다린다. Loki·Alloy·Grafana를 재생성할 필요는 없다.

### 한 요청 추적
~~~bash
request_id="lab-$(date +%s)-$RANDOM"
echo "$request_id"
curl -i --max-time 5 -X POST http://localhost:18080/orders \
  -H 'Content-Type: application/json' \
  -H "X-Request-ID: $request_id" \
  -d '{"amount":10000}'
~~~
201/confirmed와 X-Request-ID 응답 헤더를 확인한다.
Grafana Explore → Loki → Last15m → Code:
~~~logql
{environment="lab", service_name=~"order-api|payment"}
| json
| __error__=""
| request_id="터미널에서 출력한 ID"
~~~
정상 한 요청에 대해 payment200과 order-api201의 request_completed 로그가 각각 한 줄 보이는지 확인한다.
쿼리의 __error__ 필터는 이전 평문 로그의 JSON 파싱 오류를 제외한다. 애플리케이션 오류 로그 자체를 제외하는 뜻은 아니다.

서비스별 JSON 로그:
~~~logql
{environment="lab", service_name="order-api"} | json | __error__="" | event="request_completed"
~~~

### 검증과 한계
준비 환경 실제 HTTP 통신으로 동시 요청 4개의 ID 전달·응답 헤더·JSON 로그를 검증했다.
유효하지 않은 ID 대체 생성, 400 warn·502 error, UTC timestamp, 상태점검 로그 제외 및 request_id 메트릭 라벨 미사용을 확인했다.
기존 201/400/502/504 메트릭 회귀 검사도 통과했다.
재현: requirements 설치 후 python tests/verify_request_logs.py 및 python tests/verify_order_metrics.py.
사용자 Windows에서 새 JSON 수집 및 같은 request_id의 주문·결제 상관 검색을 확인했다. [실험 010](../experiments/010-json-request-correlation.md).
request_id는 로그 연결이며 span 계층·구간별 시간 관계를 제공하는 분산 트레이스는 아니다. Tempo는 6장에서 연결한다.

## 5-3 결제 중단의 장애 로그 분석

상태: 장애502·복구 주문201/결제200 로그 확인 및 기록 완료. [실험 011](../experiments/011-payment-outage-logs.md). 2026-09-18 사용자가 이번 시간대 메트릭 대조와 현재 두 대상 up=1을 확인하여 5장을 완료했다.
목표: 실패한 요청 ID로 주문 오류를 찾고, 컨테이너 상태와 메트릭으로 원인을 교차 확인한다.
로컬 모의 결제만 중지하며 실제 결제 시스템은 아니다.

### 1. 결제 중지와 실패 요청
저장소 루트의 Git Bash에서 실행한다. 반복 실행할 때마다 새로운 ID를 생성한다.
~~~bash
date -Iseconds
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml stop payment
request_id="down-$(date +%s)-$RANDOM"
echo "$request_id"
curl -i --max-time 10 -X POST http://localhost:18080/orders \
  -H 'Content-Type: application/json' \
  -H "X-Request-ID: $request_id" \
  -d '{"amount":10000}'
printf '\n{environment="lab", service_name=~"order-api|payment"} | json | __error__="" | request_id="%s"\n' "$request_id"
~~~
printf가 출력한 쿼리를 Grafana Explore의 Loki / Code에 붙여 넣는다. 조회 범위는 현재 Last15m.
예상: order-api의 status_code=502, level=error, error=payment_unavailable.
환경에 따라 timeout 계열이 나올 수 있으므로 실제 응답을 기록한다.
결제가 중지돼 해당 요청의 payment 완료 로그는 예상하지 않는다. 로그 부재만으로 원인을 단정하지 않는다.

~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml ps -a payment order-api
~~~
Prometheus에서 up{job=~"order-api|payment"}를 조회한다.
다음 scrape 이후 order-api=1, payment=0이 예상된다.
주문 서비스 up=1은 주문 기능 성공을 뜻하지 않는다.
Grafana 오류율은 조회 구간의 실제 트래픽에 따라 달라지므로 반드시 100%라고 가정하지 않는다.

### 2. 복구 (조사에 막혀도 먼저 실행 가능)
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml start payment
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml ps payment order-api
~~~
payment가 healthy인 것을 확인한 후:
~~~bash
request_id="recovered-$(date +%s)-$RANDOM"
echo "$request_id"
curl -i --max-time 10 -X POST http://localhost:18080/orders \
  -H 'Content-Type: application/json' \
  -H "X-Request-ID: $request_id" \
  -d '{"amount":10000}'
printf '\n{environment="lab", service_name=~"order-api|payment"} | json | __error__="" | request_id="%s"\n' "$request_id"
~~~
새 ID의 주문201·결제200, info/error=null 로그와 두 대상 up=1을 확인한다.
최근 rate 조회 구간에 장애 요청이 남아 있으면 복구 후에도 오류율은 즉시 0이 되지 않을 수 있다.

### 3. 기록할 증거
- 중단·복구 시각과 각 요청 ID
- 실패 응답 코드·error·duration_ms 및 복구 응답
- 컨테이너 상태와 up
- 동일 ID의 주문·결제 로그 유무, 수집 문제와 구별한 근거
- 실제 관측과 예상의 차이
