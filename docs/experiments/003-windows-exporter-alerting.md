# 003. Windows 수집 중단 알림 발생·복구 검증

## 목적

Windows 메트릭 수집 중단을 Prometheus 알림 규칙으로 감지하고,
서비스 복구 후 알림이 해제되는지 검증한다.

## 구성 소스

- [Compose](../../compose.yaml): Prometheus·Grafana·Alertmanager 실행
- [Prometheus 설정](../../prometheus.yml): 수집·평가 주기, 규칙 파일, Alertmanager 연결
- [Windows 알림 규칙](../../prometheus/rules/windows.yml): WindowsExporterDown
- [Alertmanager 설정](../../alertmanager/alertmanager.yml): 라우팅 및 receiver

## 설계

| 항목 | 실습 설정 |
|---|---|
| 수집 대상 | host.docker.internal:9182 |
| 알림 이름 | WindowsExporterDown |
| 조건 | up{job="windows"} == 0 |
| 지속 시간 | 1m |
| 수집 주기 | 15s |
| 평가 주기 | 15s |
| severity | warning |
| Alertmanager 주소 | alertmanager:9093 |
| receiver | lab-ui-only |
| 외부 알림 전송 | 미구성 |

Prometheus가 조건을 평가하고, Firing 상태의 알림을 Alertmanager로 전달한다.
Grafana는 이번 알림의 평가 주체가 아니다.

for: 1m은 실패 조건이 평가 시점마다 1분간 유지되어야 한다는 뜻이다.
서비스 중지 후 정확히 60초에 알림이 발생한다는 의미는 아니다.
수집·평가·전달 시점에 따라 지연이 추가된다.

## 수행 절차

1. promtool과 amtool로 설정을 검사한다.
2. 컨테이너 기동 후 Windows 대상 UP과 알림 규칙 로드를 확인한다.
3. 관리자 권한 Git Bash에서 Windows exporter를 중지한다.
4. Prometheus의 Pending·Firing과 Alertmanager 수신을 관찰한다.
5. Windows exporter를 다시 시작한다.
6. 수집 복구와 알림 해제를 확인한다.

중지:

```bash
sc.exe stop windows_exporter
sc.exe query windows_exporter

복구:
sc.exe start windows_exporter
sc.exe query windows_exporter

확인 쿼리:
up{job="windows"}
ALERTS{alertname="WindowsExporterDown"}
ALERTS는 Pending 또는 Firing일 때 해당 시계열 값이 1이다.
해제 후 시계열이 사라지는 것을 0으로 바뀌는 것과 혼동하지 않는다.

운영 해석과 한계
- 이 알림은 Windows 메트릭 수집 실패를 뜻한다.
- Windows 자체 장애로 단정하지 않는다.
- exporter 서비스, 네트워크, 방화벽, 수집 설정 순으로 원인을 확인한다.
- 대상이 수집 설정에서 삭제되어 시계열 자체가 없어지는 상황은 별도 규칙이 필요하다.
- Prometheus 자체가 중단되면 이 규칙도 평가되지 않는다.
- lab-ui-only에는 외부 전송 설정이 없으므로 담당자 통보까지 검증한 것은 아니다.
- 1분 지속 시간은 실습 조건이며 운영 기준은 허용 감지 시간과 오탐을 고려해 결정한다.
