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
| 6-1 | Tempo 저장·조회 기반 | ready 및 Grafana Tempo 연결 | 소스 준비 / 사용자 실행 대기 |
| 6-2 | 앱 OpenTelemetry 계측·Alloy OTLP 전달 | 주문 server → 결제 client → 결제 server span 연결 | 예정 |
| 6-3 | trace_id 로그 연계 | 한 요청의 로그와 트레이스 상호 조회 | 예정 |
| 6-4 | 제어된 지연·중단·복구 | 지연 span, 오류 span 비교 및 원복·기록 | 예정 |

## 6-1 구성
공식 v3.0.3 single-binary 예제를 기반으로 필요한 저장·수신·조회만 구성한다.
metrics-generator·service graph·MCP는 이번 단계에서 활성화하지 않는다.
모놀리식 로컬 저장 방식이며 HA·운영 규모 검증은 범위 밖이다.
tempo-data 볼륨에 저장한다. 보관 기간·용량 정책은 아직 별도로 설정하지 않았다.
OTLP 4317/4318은 Docker 내부만 사용하고 호스트에는 조회·ready용 3200만 localhost로 공개한다.
6-2 예정 경로: 앱 SDK → Alloy OTLP receiver → batch → Tempo → Grafana 조회.
현재 Alloy 로그 설정과 앱 코드는 변경하지 않는다.

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
준비 환경에서는 공식 버전 예제와 설정 구조를 대조했다. Docker Desktop 실제 기동·Grafana 연결은 사용자 검증 대기다.

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
