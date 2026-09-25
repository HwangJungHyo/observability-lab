# 7-0 Mimir 구성 결정과 변경 전 기준선

> 이 문서의 준비·대기 표시는 작성 당시 상태다. 현재 진행 상태와 잔여 검증은 [챕터 지도](../roadmap.md)의 7장 체크포인트를 기준으로 확인한다.

기록일: 2026-09-24. 출처: 사용자가 제공한 명령 출력과 Docker Desktop 설정 화면.
기준 소스: 46307c07779c8c15b9b345ed445ac259d6d65253. 데이터 수집 시각은 출력에 없으므로 기록일과 구분한다.

## 자원 확인

| 항목 | 관측값 |
|---|---|
| Docker backend | WSL2 |
| Docker 가용 논리 CPU | 24 |
| Docker MemTotal | 33205784576 bytes = 약 30.93GiB |
| 컨테이너 8개 메모리 합계 | 880.41MiB (약 0.86GiB), 단일 시점 |
| CPU 사용률 합계 | 1.35% (docker stats의 코어 기준 표시 합계), 단일 시점 |
| Windows C: 여유 | 출력 FreeGB 475.7. PowerShell /1GB는 GiB 단위 |
| 디스크 이미지 위치 | C:\Users\PC\AppData\Local\Docker\wsl |
| Docker 이미지 | 8개, 3.878GB |
| Docker 볼륨 | 6개, 1.404GB |
| 빌드 캐시 | 4.6GB, 회수 가능 4.406GB |
| Git 상태 | lab/006-tracing, 추적 변경 표시 없음. status만으로 원격 최신 여부 보장하지 않음 |

payment와 order-api는 healthy. 나머지 6개는 Up이며 이것만으로 각 readiness·수집 정상 판정을 대체하지 않는다.
메모리 30.93GiB는 각 컨테이너가 전용으로 예약한 양이 아니다. 호스트 Windows/WSL 메모리 여유와도 구분한다.
WSL 가상 디스크 한도는 호스트의 실제 남은 공간이 아니다.
제공된 PowerShell 명령의 '$*.'는 문서 복사 과정의 변형 가능성이 있다. 재실행할 때 속성 참조는 '$_.Used', '$_.Free'를 사용한다.

## 결정

7장의 초기 토폴로지는 Mimir 1개(monolithic), classic 수집 아키텍처, 별도 S3 호환 저장소 1개다.
Prometheus의 수집·로컬 저장·기존 규칙·Alertmanager를 유지하고 remote_write를 추가한다.
Grafana에 Mimir 데이터 소스를 별도로 추가하여 같은 시계열·시간 구간을 비교한다.
기존 Alloy/Loki/Tempo는 유지한다. Kafka를 요구하는 ingest-storage는 후속 별도 설계 항목이다.
S3 호환 저장소의 초기 제품 후보는 공식 Mimir 실습과 같은 MinIO다. 실행 이미지 공급 경로·버전·보안 상태·digest 검증 후 고정한다.

공식 Play with Mimir는 classic, monolithic Mimir 3개와 MinIO 등을 사용한다.
본 과정은 우선 1개로 축소해 수신 중단·재전송·저장을 검증하므로 해당 예제의 HA 속성을 주장하지 않는다.
https://grafana.com/docs/mimir/latest/get-started/play-with-grafana-mimir/

### 초기 한도와 정책

| 대상 | CPU 한도 | 메모리 한도 | 영속성 |
|---|---|---|---|
| Mimir | 2 CPU | 4GiB | WAL/작업 디렉터리에 전용 named volume |
| S3 호환 저장소 | 1 CPU | 2GiB | 오브젝트 데이터 전용 named volume |

이는 로컬 소규모 실험의 초기 한도이며 공식 최소 사양·예약 자원·운영 용량 산정 결과가 아니다.
기준선·부하·복구 재전송 시 최대값과 OOM/CPU 제한에 따른 지연을 측정하여 조정한다.
기존 볼륨을 삭제하거나 캐시를 정리할 필요는 현재 증거상 없다.

중앙 메트릭 보존은 실습용 7일을 초기 설계값으로 삼고 실제 설정 지원과 compactor 동작을 검증한다.
Prometheus의 기존 보존 설정은 먼저 확인해 기록한다. 보존 기간 차이에 따른 공백과 전송 실패를 구분한다.
초기 저장량 관찰 예산은 신규 데이터 20GiB, C: 여유 100GiB 미만이면 실험 중단·점검으로 정한다.
이는 자동 디스크 quota가 아니며 파일시스템 여유와 볼륨 증가량을 별도로 관찰한다.
Windows 메모리 압박, OOM, 예상 밖 주문 실패 시 부하를 중단한다.

호스트 관리 포트는 필요한 것만 127.0.0.1에 바인딩하고 내부 통신은 Compose 서비스 이름을 사용한다.
자격정보는 Git에 넣지 않고 로컬 비밀 파일로 제공한다. tenant 헤더는 인증을 대체하지 않는다.
컨테이너별 자원 제한은 Compose에 명시하고 실제 적용값을 inspect로 확인한다.

## 다음 단계와 완료 기준

- [x] 7-0a 자원 기준선과 초기 토폴로지·예산 결정
- [ ] 7-0b Mimir/저장소의 구체 버전·digest·설정 호환 검증
- [ ] 7-0b 기존 Prometheus/Grafana/Alertmanager 실행 버전·이미지 ID·RepoDigests 기록
- [ ] 7-1 Compose overlay·설정·provisioning 작성 및 정적 검증
- [ ] 7-1 사용자 PC에서 저장소/Mimir 기동, readiness·영속 볼륨·자원 제한 확인
- [ ] 7-2 remote_write 설정 검사·적용, 수집 유지·전송 성공·Grafana 대조
- [ ] 7-3 지속 트래픽 중 수신 중단·복구, backlog·재시도·데이터 공백 검증
- [ ] 7-4 실제 오브젝트 업로드 증거와 재시작 후 과거 데이터 조회

한 단계의 실제 결과를 확인한 후 다음 변경으로 진행한다.
첫 기동과 remote_write 적용을 나누어 변경 영향과 실패 원인을 구분한다.
7-0a는 완료지만 이미지 고정과 소스 실행 검증 전에는 7-0 전체나 설치 완료로 기록하지 않는다.

## 다음 사용자 확인 (Git Bash)

```bash
docker compose exec -T prometheus prometheus --version
docker compose exec -T grafana grafana --version
docker compose exec -T alertmanager /bin/alertmanager --version
docker inspect observability-lab-prometheus-1 observability-lab-grafana-1 observability-lab-alertmanager-1 --format '{{.Name}} image={{.Image}}'
```

실행 컨테이너가 사용하는 image ID를 기준으로 docker image inspect하여 RepoDigests를 후속 확인한다.
latest를 새로 pull하거나 컨테이너를 일괄 재생성하기 전에 현재 실행 이미지를 식별한다.
