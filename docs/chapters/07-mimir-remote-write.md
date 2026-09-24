# 7-2 Prometheus remote_write와 Grafana 연결

## 실행 전 상태

7-1: 사용자 출력으로 S3 CRUD/인증, Mimir 준비 상태와 vector(1) 성공 확인 (실험 016).
7-2: 소스 준비, 실제 전송 결과 대기. 사용자 PC에 실행 권한은 있으나 이 작성 환경에서는 그 PC의 Docker를 직접 실행하지 않는다.

## 원리

Prometheus가 기존 타깃에서 계속 수집하고 로컬 TSDB/WAL에 기록한다.
추가한 remote_write 큐가 샘플을 Mimir의 /api/v1/push로 보낸다.
이 과정은 Prometheus 로컬 저장을 없애거나 과거 로컬 보존 데이터 전체를 이관하는 작업이 아니다.
Grafana는 /prometheus 경로를 통해 Mimir를 조회한다.
쓰기와 조회 모두 X-Scope-OrgID: lab을 사용한다. 이는 테넌트 선택이며 사용자 인증을 대체하지 않는다.
새 job mimir는 Mimir 자체 /metrics를 수집한다.

## 변경 내용

- prometheus.yml: 기존 4개 job·규칙·Alertmanager 설정 유지, mimir job과 name=mimir_lab remote_write 추가.
- grafana/provisioning/datasources/mimir.yml: uid=mimir 추가, 기존 기본 데이터 소스와 대시보드는 유지.
- apply-mimir-metrics.sh: 현재 유효 설정 백업, 호스트/컨테이너 마운트 내용 대조, promtool, SIGHUP, 실측 비교.
- check_mimir_metrics.py: 같은 시각에 3개 up 시계열의 라벨·값·원본 timestamp 비교. 전송 대기 최대 약 150초+진행 중 요청.

## 1. 파일 수신과 전송 적용

Git Bash:

```bash
git status --short --branch
git pull --ff-only
bash scripts/apply-mimir-metrics.sh
```

호스트 파일은 pull 때 바뀌지만 실행 중인 Prometheus의 유효 설정은 reload 때 바뀐다.
단, 런타임 auto-reload 등을 별도 활성화했다면 해당 동작은 다를 수 있다.
본 저장소는 기본 Compose 명령에서 auto-reload 플래그를 설정하지 않는다.

백업: .local/mimir/prometheus-before-remote-write.yaml.
첫 실행 시 HTTP status/config의 실제 적용 설정을 저장한다. 재실행 시 기존 백업을 덮어쓰지 않는다.
실제 설정에 민감값이 포함되는 환경에서는 API가 마스킹한 값을 별도로 복구해야 한다.
이 실습의 변경 전 Prometheus 설정은 타깃·규칙·Alertmanager 주소만 포함한다.

Git Bash 경로 변환 방지를 wrapper에서 적용한다.
마운트 내용 불일치면 reload 전에 멈춘다. 이 경우 출력부터 확인한다.
일부 Linux 단일 파일 bind mount는 Git의 파일 교체 후 이전 inode를 계속 볼 수 있다.
원인이 이것으로 확인되면 Prometheus만 재생성해야 하며 짧은 수집·규칙 평가 중단이 생긴다.
확인 전 다른 서비스 전체 재시작이나 볼륨 삭제를 수행하지 않는다.

SIGHUP은 설정 재로드 신호다. compose kill -s SIGHUP의 kill은 여기서 프로세스 종료 요청이 아니다.

## 2. 성공 출력 해석

- PASS: active remote_write and successful reload
- PASS: order-api/payment/mimir up=1 on Prometheus and Mimir
- PASS: identical labels, values and source sample timestamps
- evaluation_time_unix=...
- 각 시계열의 source_timestamp=...

쿼리 평가 시각을 now-30초로 두어 전송 시간을 허용한다.
샘플 timestamp도 비교하므로 단순히 오래된 up=1이 같은 것만으로 통과하지 않는다.
원본 샘플이 평가 시각보다 45초 이상 오래되면 실패한다.
이번 판정은 세 up 시계열의 표본 대조이며 모든 메트릭의 무손실·S3 블록 업로드를 입증하지 않는다.
실패 시에도 전송 설정이 적용됐을 수 있다. 출력과 다음 진단을 확인하고 필요하면 4번으로 원복한다.

## 3. Grafana 등록 (2번 성공 후)

```bash
bash scripts/mimir-compose.sh restart grafana
```

Grafana 화면은 잠시 끊길 수 있으며 Prometheus 수집은 계속된다.
http://localhost:3001 의 Explore에서 Mimir를 선택하고 다음을 조회한다.

```promql
up{job=~"order-api|payment|mimir"}
```

3개가 1인지 확인. 기존 Prometheus 데이터 소스에서도 같은 시간대 대조.
Mimir가 없으면 Grafana 로그에서 provisioning 오류를 확인한다.
자동 검증은 직접 HTTP API를 대조하며 Grafana 화면 성공까지 대신하지 않는다.

## 4. 전송 설정만 원복

```bash
test -s .local/mimir/prometheus-before-remote-write.yaml &&
  cat .local/mimir/prometheus-before-remote-write.yaml > prometheus.yml
bash scripts/mimir-compose.sh exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
```

검사 성공 후:

```bash
bash scripts/mimir-compose.sh kill -s SIGHUP prometheus
```

원복은 prometheus.yml을 로컬 변경 상태로 남긴다. Git 상태를 확인하고 후속 변경 전에 원복/재적용 의도를 정한다.
Mimir에 이미 전송된 데이터와 볼륨은 삭제하지 않는다. Grafana 데이터 소스도 유지된다.

## 장애 진단

```bash
bash scripts/mimir-compose.sh logs --tail=80 prometheus mimir
```

주요 분기:
- 401/no org id: tenant 헤더.
- connection refused/DNS: 주소·네트워크·Mimir 상태.
- 400: 수신 오류 본문, 샘플 시각·순서·테넌트 제한.
- 빈 결과: 시간대·테넌트·전송 지연·실제 remote_write 적용 여부.

공식 근거:
https://grafana.com/docs/mimir/latest/references/http-api/
https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write

## 작성 시 검증

YAML 파싱, 기존 job/rule/alerting 보존 확인, Bash 구문, Python 컴파일 완료.
Docker 엔진이 없는 작성 환경에서 promtool·runtime 실행은 수행하지 않았다.
사용자 PC에서 위 검증이 통과한 후 7-2 완료로 기록한다.
