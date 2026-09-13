# observability-lab

Windows 호스트의 CPU·메모리·디스크를 Prometheus로 수집하고 Grafana로 확인하는 실무 관측 실습 저장소입니다. 설정 변경, 정상 판정, 장애 분석, 원복 과정을 Git으로 기록합니다.

## 현재 범위

- Windows + Git Bash + Docker Desktop(WSL2 백엔드, Linux 컨테이너)
- Windows에 직접 설치한 windows_exporter
- Prometheus의 자기 메트릭 및 Windows 메트릭 수집
- Grafana 데이터 소스와 대시보드의 파일 기반 provisioning
- CPU·메모리·디스크 사용률·디스크 여유 공간 패널 4개

현재 구성은 `lab/002-windows-metrics` 브랜치에 있습니다. 아래 clone 명령은 이 브랜치를 명시합니다. main 병합 후에는 README의 브랜치 안내도 갱신합니다.

Loki·Tempo·Mimir·주문 API·알림 구성은 후속 실습입니다. 현재 대시보드의 임계값 색상은 알림 규칙이 아닙니다.

## 데이터 흐름과 접속 주소

| 구간 | 주소 | 역할 |
|---|---|---|
| Windows 브라우저 → Grafana | http://localhost:3001 | 대시보드 조회 |
| Windows 브라우저 → Prometheus | http://localhost:9090 | 쿼리·Targets 확인 |
| Windows → windows_exporter | http://localhost:9182/metrics | 메트릭 응답 확인 |
| Prometheus 컨테이너 → Windows | http://host.docker.internal:9182/metrics | Windows 메트릭 수집 |
| Prometheus 컨테이너 → 자기 자신 | http://localhost:9090/metrics | 자기 메트릭 수집 |
| Grafana 컨테이너 → Prometheus | http://prometheus:9090 | PromQL 질의 |

Prometheus는 15초마다 수집합니다. 컨테이너 안의 localhost는 그 컨테이너 자신입니다. Docker Desktop의 host.docker.internal은 Windows 호스트 접근에 사용하며, prometheus는 Compose 서비스 이름입니다.

Grafana·Prometheus의 공개 포트는 127.0.0.1에 바인딩되어 있습니다. 다른 PC에서 재현한다는 것은 저장소를 그 PC에 복제하고 서비스를 실행한다는 뜻입니다.

## 파일 구성

| 경로 | 역할 |
|---|---|
| compose.yaml | 이미지·포트·네트워크·볼륨 |
| prometheus.yml | 수집 대상과 수집 주기 |
| grafana/provisioning/datasources/prometheus.yml | 데이터 소스 자동 등록, UID: prometheus |
| grafana/provisioning/dashboards/local.yaml | 대시보드 파일 provider |
| grafana/dashboards/windows-host-overview.json | Classic JSON, 패널 4개, UID: adgfx7k |
| docs/experiments/ | 실험 결과와 원복 기록 |

대시보드 UID와 데이터 소스 UID를 임의로 변경하지 않습니다. provider는 동일 UID의 기존 대시보드를 갱신할 수 있습니다.

## 다른 Windows PC에서 시작하기

아래 셸 명령은 별도 표시가 없으면 Git Bash에서 실행합니다.

### 1. 사전 요구사항

- Windows x64 PC 기준. ARM PC는 exporter 설치 파일 아키텍처를 맞춥니다.
- Git for Windows(Git Bash 포함)
- Docker Desktop 실행, WSL2 백엔드 및 Linux 컨테이너 모드
- MSI 설치와 Windows 서비스 설치를 허용할 관리자 권한
- 비공개 저장소라면 GitHub 저장소 접근 권한과 Git 인증
- 호스트 포트 3001·9090·9182 사용 가능 여부

확인:

```bash
git --version
docker version
docker compose version
docker info --format '{{.OSType}}'
```

Docker Client·Server가 모두 응답하고 OSType이 linux여야 합니다.

### 2. 저장소 복제

```bash
mkdir -p ~/Desktop/git-devops
cd ~/Desktop/git-devops

git clone --branch lab/002-windows-metrics https://github.com/HwangJungHyo/observability-lab.git
cd observability-lab
```

기존 작업 폴더가 있다면 다시 clone하지 않습니다. 해당 폴더에서 변경 상태를 먼저 확인하고, 같은 브랜치의 변경을 받을 때 다음을 사용합니다.

```bash
git status --short --branch
git pull --ff-only
```

분기되었거나 로컬 변경과 충돌하면 강제 덮어쓰지 말고 변경 내용을 확인합니다.

### 3. windows_exporter 설치

[공식 릴리스](https://github.com/prometheus-community/windows_exporter/releases)에서 Windows 아키텍처에 맞는 MSI를 다운로드하여 실행합니다. 실습에서 선택한 설치 파일은 `windows_exporter-0.31.8-amd64.msi`입니다. 새 PC에서 사용한 버전과 설치 옵션을 기록합니다.

기본 설정은 Windows 서비스 이름 windows_exporter, 포트 9182, 경로 /metrics입니다. 기본 수집기를 사용합니다. MSI 파일 자체는 Git에 올리지 않습니다.

```bash
sc.exe query windows_exporter

curl -sS --max-time 10 -o /dev/null \
  -w "HTTP %{http_code}\n" \
  http://localhost:9182/metrics
```

정상 기준:
- 서비스 상태: RUNNING
- HTTP 응답: 200
- 브라우저에서 /metrics에 Windows 메트릭 출력

Windows 내부 HTTP 200만으로 컨테이너의 접근 성공까지 보장하지는 않습니다. 설치 프로그램이 만든 방화벽 규칙의 범위를 확인하고, 필요한 Docker Desktop → 호스트 통신을 허용합니다. 장애 해결을 위해 Windows 방화벽 전체를 비활성화하지 않습니다.

### 4. 컨테이너 실행

```bash
docker compose config --quiet
```

오류가 없으면 실행합니다.

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 grafana prometheus
```

두 서비스가 실행 중인지 확인합니다. Compose 문법 검사는 Grafana provider나 Prometheus 수집 설정의 정확성까지 보장하지 않습니다.

### 5. 수집 및 화면 검증

기동 후 약 30초 뒤 [Targets](http://localhost:9090/targets)에서 prometheus와 windows가 모두 UP인지 확인합니다.

[Prometheus](http://localhost:9090/query)에서 실행:

```promql
up{job=~"prometheus|windows"}
```

두 대상 모두 1이어야 합니다. up은 수집 성공 여부이며, 애플리케이션의 업무 기능 정상 여부를 보장하지 않습니다.

[Grafana](http://localhost:3001)에 접속합니다. 새로운 grafana-data 볼륨의 초기 계정은 admin / admin이며 최초 로그인 후 비밀번호를 변경합니다. 기존 볼륨을 재사용하면 이전 계정 설정이 유지됩니다.

데이터 소스 Prometheus와 대시보드 Windows Host Overview가 자동 등록되어야 합니다. 수동 데이터 소스 등록이나 JSON import는 필요 없습니다.

| 확인 항목 | 정상 기준 |
|---|---|
| 데이터 소스 | UID prometheus로 연결 |
| 대시보드 | Windows Host Overview, 패널 4개 |
| CPU·메모리 | 수집 시작 이후 그래프 표시 |
| 디스크 | 실제 드라이브별 값 표시 |
| 재조회 | 브라우저 새로고침 후에도 설정 유지 |

새 PC에서는 이전 PC의 메트릭 이력이 복원되지 않습니다. Grafana JSON은 시각화 정의이며 실제 데이터는 Prometheus 볼륨에 저장됩니다.

## 패널 해석

### CPU 사용률

```promql
100 * (
  1 - avg by (instance) (
    rate(windows_cpu_time_total{job="windows",mode="idle"}[5m])
  )
)
```

논리 CPU별 유휴 시간 증가율을 평균내고 1에서 빼는 시간 기반 사용률입니다. 단위는 Percent (0–100)입니다. 최근 5분을 계산 구간으로 사용하므로 짧은 급등은 완만하게 보일 수 있습니다. 전체 평균이 낮아도 특정 코어가 포화될 수 있습니다. 작업 관리자의 계산 방식·평가 구간과 달라 값이 정확히 같을 필요는 없습니다.

### 메모리 사용률

```promql
100 * (
  1 -
  windows_memory_available_bytes{job="windows"}
  /
  windows_memory_physical_total_bytes{job="windows"}
)
```

물리 메모리 중 즉시 사용 가능한 메모리를 제외한 비율입니다. available에는 재사용 가능한 대기 캐시가 포함됩니다. Gauge를 사용하므로 rate()를 적용하지 않습니다.

### 디스크 사용률

```promql
100 * (
  1 -
  windows_logical_disk_free_bytes{job="windows",volume=~"[A-Z]:"}
  /
  windows_logical_disk_size_bytes{job="windows",volume=~"[A-Z]:"}
)
```

드라이브 문자가 있는 볼륨만 표시합니다. 여러 볼륨을 평균내지 않습니다. 이 값은 용량 사용률이며 디스크 I/O 부하율이 아닙니다.

### 디스크 여유 공간

```promql
windows_logical_disk_free_bytes{job="windows",volume=~"[A-Z]:"}
```

Instant 조회와 Bytes (IEC) 단위를 사용합니다. 디스크 free/size 메트릭은 Windows 성능 카운터 특성상 10~15분 지연될 수 있습니다. 파일 생성·삭제 직후 값이 변하지 않는 것만으로 수집 장애를 판단하지 않습니다.

대시보드 JSON의 시간 범위는 최근 15분이며, 현재 자동 새로고침은 꺼져 있습니다. 실시간 확인 시 Refresh를 누르거나 UI에서 새로고침 주기를 선택합니다. 기본값을 지속적으로 바꾸려면 JSON의 refresh를 수정하고 검증·커밋합니다.

Time series 패널은 null 연결을 하지 않도록 설정되어 있습니다. 다만 rate()가 짧은 수집 공백 동안 값을 계속 계산할 수 있으므로, 수집 장애 확인에는 up과 Targets를 함께 사용합니다.

## Provisioning 운영 방식

| 설정 | 현재 값 | 의미 |
|---|---|---|
| provider | observability-lab | 파일 provider 이름 |
| folder | 빈 문자열 | Grafana 기본 위치 |
| path | /var/lib/grafana/dashboards | 컨테이너 내부 JSON 폴더 |
| updateIntervalSeconds | 30 | 파일 변경 polling |
| allowUiUpdates | false | UI에서 원본 대시보드 저장 제한 |
| disableDeletion | true | 파일 제거 시 DB 대시보드 자동 삭제 방지 |

Grafana는 로컬로 마운트된 파일을 읽습니다. GitHub를 직접 읽거나 push에 반응하지 않습니다. 다른 PC에 변경을 적용하려면 그 PC에서 git pull을 수행해야 합니다.

수정 흐름:
1. 로컬 JSON 수정.
2. 30~60초 후 Grafana를 새로고침해 적용 확인.
3. 정상 판정 후 변경 검토·커밋·push.
4. 다른 PC에서 pull하여 반영.

이 실습에서는 로컬 파일 변경이 커밋 전에 실행 중인 Grafana에 반영됩니다. 실제 운영에서는 승인된 커밋만 별도 배포 경로로 전달하는 구성이 필요합니다.

provider YAML이나 Compose 마운트를 변경했다면 다음처럼 Grafana만 재생성합니다. Grafana 접속은 잠시 중단되고 Prometheus 수집은 유지됩니다.

```bash
docker compose config --quiet
docker compose up -d --no-deps --force-recreate grafana
docker compose logs --tail=100 grafana
```

자동 적용 검증은 JSON의 최상위 title을 임시 변경하여 UI 반영을 확인한 뒤 원래 제목으로 돌려 수행할 수 있습니다. UID는 유지합니다. 시험 변경은 원복한 상태로 커밋합니다.

## Prometheus 설정 변경

변경 전 diff와 기존 수집 상태를 확인하고 백업합니다.

```bash
cp prometheus.yml prometheus.yml.before-change.bak
```

설정 수정 후 검사:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml
```

SUCCESS 확인 후 재로드:

```bash
docker compose kill -s SIGHUP prometheus
```

SIGHUP은 설정 재로드 신호입니다. MSYS_NO_PATHCONV=1은 Git Bash의 컨테이너 경로 자동 변환을 방지합니다.

다음 쿼리의 값이 1인지 확인하고, Targets에 예상한 대상이 있는지도 확인합니다.

```promql
prometheus_config_last_reload_successful
```

실패 시 원복:

```bash
cat prometheus.yml.before-change.bak > prometheus.yml

MSYS_NO_PATHCONV=1 docker compose exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml
```

검사 성공 후 SIGHUP을 다시 보내고 기존 대상의 up=1을 확인합니다. 백업 파일은 Git에 포함하지 않습니다.

## 대시보드 변경 원복

직전 대시보드 변경이 별도 커밋이라면 해당 커밋을 git revert하여 복구 기록을 남깁니다. 아직 커밋하지 않은 변경이라면 diff를 확인하고 필요한 내용을 보존한 뒤 다음으로 HEAD 상태를 복구할 수 있습니다.

```bash
git diff -- grafana/dashboards/windows-host-overview.json
git restore -- grafana/dashboards/windows-host-overview.json
```

30~60초 뒤 화면에서 원래 설정이 반영되는지 확인합니다. disableDeletion=true이므로 파일을 삭제하는 방법은 화면 변경 원복이 아닙니다.

## 중지·재시작·데이터 보존

```bash
# 컨테이너 중지
docker compose stop

# 다시 실행
docker compose up -d

# 컨테이너와 기본 네트워크 제거, named volume 유지
docker compose down
```

prometheus-data는 메트릭, grafana-data는 Grafana DB·사용자 설정을 보존합니다. JSON과 YAML은 Windows 작업 폴더에 남습니다. docker compose down -v는 볼륨 데이터까지 삭제하므로 일반 종료 명령으로 사용하지 않습니다.

Compose 중지는 Windows 서비스인 windows_exporter를 중지하지 않습니다. exporter 중단 실험은 Windows 서비스 관리에서 별도로 수행하고 실험 후 다시 시작합니다.

## 장애 점검

| 증상 | 점검 순서 |
|---|---|
| Windows /metrics 접속 실패 | sc.exe query windows_exporter → 포트 수신 상태 → 서비스 설정 |
| Windows HTTP 200, windows 대상 DOWN | Targets 오류 → host.docker.internal 주소 → 수신 주소·방화벽·Docker 통신 |
| Prometheus 설정 변경이 미반영 | promtool → SIGHUP → reload 성공 메트릭·컨테이너 로그 |
| Grafana에 대시보드 없음 | JSON 마운트 → provider path → Grafana 로그 |
| 대시보드는 있으나 No data | Targets → 원본 메트릭 → PromQL 라벨 → datasource UID → 조회 시간 |
| UI 저장이 거부됨 | allowUiUpdates=false의 의도된 동작. JSON을 변경 |
| 디스크 용량이 바로 안 바뀜 | 성능 카운터의 갱신 지연 고려 |
| 포트 사용 중 오류 | 기존 3001·9090·9182 사용 프로세스 확인. 충돌한 서비스만 조정 |

로그 확인:

```bash
docker compose logs --tail=100 grafana prometheus
```

## 버전과 재현성 한계

현재 compose.yaml은 prom/prometheus:latest와 grafana/grafana:latest를 사용합니다. 따라서 구성 절차는 재현할 수 있지만, 다른 날 다운로드한 이미지가 같은 버전임을 보장하지 않습니다. 대시보드 JSON에는 내보낸 패널의 pluginVersion이 13.2.1로 기록되어 있으나 실행 버전의 검증을 대체하지 않습니다.

실제 사용 버전을 기록합니다.

```bash
docker compose exec -T prometheus prometheus --version
docker compose exec -T grafana grafana --version
docker compose images

docker image inspect prom/prometheus:latest --format '{{json .RepoDigests}}'
docker image inspect grafana/grafana:latest --format '{{json .RepoDigests}}'
```

엄격한 버전 재현이 필요하면 실행 중인 컨테이너의 Image ID와 로컬 태그의 Image ID가 같은지도 확인하고, 검증된 이미지 digest 또는 고정 버전을 compose.yaml에 반영합니다. 실제 확인하지 않은 버전이나 성공 결과는 기록하지 않습니다.

## Git 기록과 완료 기준

커밋에는 구성 파일·대시보드 JSON·운영 문서·실험 결과를 포함합니다. 비밀번호·토큰·.env·MSI·임시 백업·볼륨 데이터는 제외합니다.

다른 PC에서의 재현 완료 기준:
- exporter 서비스 RUNNING, /metrics HTTP 200
- Prometheus의 prometheus·windows 대상 모두 UP
- Grafana 데이터 소스와 대시보드 자동 등록
- 패널 4개에서 해당 PC 데이터 확인
- JSON 제목 변경·원복이 polling으로 반영
- 컨테이너 재실행 후 대시보드 유지
- 설치 버전·실행 시각·검증 결과·발생 오류 기록

위 목록은 검증 절차입니다. 이 README 작성 과정에서 별도 Windows PC의 실행 검증을 수행한 것은 아닙니다.

## 공식 문서

- [Docker Desktop Windows 설치](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Desktop 네트워크](https://docs.docker.com/desktop/features/networking/)
- [windows_exporter](https://github.com/prometheus-community/windows_exporter)
- [Prometheus 설치](https://prometheus.io/docs/prometheus/latest/installation/)
- [Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
