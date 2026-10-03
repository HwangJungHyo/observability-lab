# 8-5 자원 제한과 중단 기준

2026-10-03 기준 smoke와 단계 부하를 완료했다. 이 문서는 재현 절차다. 두 앱의 메모리 상한 512MiB는 확인했으며 CPU·스왑·생성기 제한 적용값 및 자동 중단 발동은 미검증이다. [실행 결과와 범위](../evidence/008-integrated-incident/8-5-load-results.md)를 함께 확인한다.

## 실험 조건

이 값은 학습을 위한 초기 예산이다. 운영 환경 권장 사양이나 PC 전체의 안전 보장으로 해석하지 않는다.

| 서비스 | CPU 실행 시간 상한 | 메모리 상한 | 스왑 |
|---|---|---|---|
| order-api | 논리 CPU 0.5개 상당 | 512MiB | 미허용 |
| payment | 논리 CPU 0.5개 상당 | 512MiB | 미허용 |
| k6 | 논리 CPU 1개 상당 | 512MiB | 미허용 |

cpus는 CPU를 전용 예약하거나 특정 코어에 고정하는 설정이 아니다. 세 컨테이너 상한 합계는 CPU 2개 상당·메모리 1.5GiB이며 Docker/WSL, Prometheus, Mimir, Loki, Tempo, Grafana 등의 자원은 별도다. 디스크 사용량은 이 설정으로 제한되지 않는다.

memswap_limit를 mem_limit와 같게 두어 해당 컨테이너의 스왑을 허용하지 않는다. 메모리 한계에서는 프로세스가 OOM으로 종료될 수 있다. 스왑 제한을 지원하지 않는다는 Docker 경고가 나오면 적용 완료로 판단하지 않는다.

## 1. 제한 적용

기존 기본 Compose 파일 대신 추가 overlay를 사용한다. 두 서비스를 재생성하므로 메모리 내 메트릭 카운터는 초기화된다. 이전 수집 시계열과 실험 구간을 구분한다.

```bash
PAYMENT_DELAY_SECONDS=0.08 \
  bash scripts/mimir-compose.sh -f compose.load-limits.yaml up -d \
  --no-deps --force-recreate --no-build --pull never payment order-api

docker inspect --format '{{.Name}} CPU={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}' \
  observability-lab-order-api-1 observability-lab-payment-1

bash scripts/mimir-compose.sh ps order-api payment
```

두 서비스 각각 예상: CPU=500000000, Memory=536870912, MemorySwap=536870912. healthy 확인 후 부하를 시작한다. 제한 없이 실행되는 것을 막기 위한 적용 검증이며 단순 정상 요청 반복과 목적이 다르다.

## 2. 새 기준선과 단계 부하

```bash
bash scripts/run-k6-orders.sh smoke
```

실패 0건, 정상 기준과 유사한 지연, 결과 파일 저장 여부를 확인한다. 시험 조건이 바뀌었으므로 이 한 번의 기준선 갱신은 필요하다. 이후 다음 명령을 실행한다.

```bash
bash scripts/run-k6-orders.sh steps
```

runner가 limits overlay를 포함하지만 run --no-deps로는 기존 애플리케이션의 자원 설정을 바꾸지 않는다. 위 1번 적용을 먼저 해야 한다.

## 3. 중단 기준

| 기준 | 방식 |
|---|---|
| 시작 30초 이후 누적 업무 실패율 5% 이상 | k6 자동 중단 |
| 시작 30초 이후 누적 HTTP p95 1000ms 이상 | k6 자동 중단 |
| 애플리케이션이나 관측 서비스가 종료·재시작됨 | 수동 중단 후 원인 기록 |
| Windows 가용 메모리 2GiB 미만, 지속적인 조작 지연 | 수동 중단 |
| Docker 데이터 또는 결과 저장 드라이브 여유 5GiB 미만 | 다음 실행 금지·진행 중이면 중단 |
| k6가 CPU 상한에 계속 붙거나 OOM으로 종료 | 부하 생성기 병목으로 판정 보류 |

위 수치는 이번 실습용 기준이며 운영 SLO가 아니다. CPU가 상한에 가까워졌다는 이유만으로 대상 앱 시험을 즉시 종료하지는 않는다. CPU 제한에 따른 지연 변화가 관측 목표이기 때문이다. 반면 PC 조작이나 관측이 어려워지면 즉시 중단한다.

자동 중단 평가는 실행 전체의 누적 지표를 사용한다. 급격한 최근 악화를 늦게 반영할 수 있으므로 수동 중단을 대체하지 않는다. 종료 유예 설정과 달리 abortOnFail은 진행 중 요청을 끊을 수 있다. 출력의 interrupted iterations를 함께 기록한다.

별도 터미널에서 docker stats로 앱·k6·관측 서비스 상태를 본다. Windows 작업 관리자는 호스트 가용 메모리 확인에 사용한다. 자동 중단 조건은 이 호스트 자원을 감시하지 않는다.

```bash
docker stats
```

수동 중단은 실행 터미널의 Ctrl+C. 종료 후 실제 주문 1건으로 복구를 확인한다. 임시 k6 컨테이너가 계속 남아 실행 중이면 출력된 컨테이너 이름으로 docker stop을 실행한다.

## 4. 실습 제한 해제

이번 추가 파일을 제외하고 기존 구성을 재적용한다. 원래 Compose 설정의 자원 정책으로 돌아간다.

```bash
PAYMENT_DELAY_SECONDS=0.08 \
  bash scripts/mimir-compose.sh up -d \
  --no-deps --force-recreate --no-build --pull never payment order-api
```

부하 비교 중에는 제한을 유지한다. 다른 작업에서 overlay 없이 두 서비스를 재생성하면 제한이 제거될 수 있으므로 기록한 조건과 실제 설정을 일치시킨다.

## 근거

- https://docs.docker.com/reference/compose-file/services/
- https://docs.docker.com/engine/containers/resource_constraints/
- https://grafana.com/docs/k6/latest/using-k6/thresholds/
