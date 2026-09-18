# 004. Slack 장애·복구 알림 수신 검증

## 목적과 결과

Windows 메트릭 수집 중단과 복구를 Slack 메시지로 확인한다.

**결과: Slack에서 FIRING과 RESOLVED 메시지 모두 수신 완료.**
근거는 사용자가 제공한 Slack 메시지 본문과 표시 시각이다. 실행 환경에 직접 접속하여 재검증한 결과는 아니다.

## 증거와 시간

실험일: 2026-09-15. 시각은 사용자 환경의 KST(UTC+09:00) 기준이다.
Slack 표시 이름: observability-test. 이 이름만으로 채널 이름을 확정하지 않는다.

| 시각 | 증거 | 판정 |
|---|---|---|
| 22:18 (분 단위) | [FIRING] WindowsExporterDown | 장애 메시지 수신 |
| 22:19 (분 단위) | [RESOLVED] WindowsExporterDown | 복구 메시지 수신 |
| 22:19:09 | sc.exe start: 오류 1056, sc.exe query: RUNNING | 해당 시점에 서비스가 이미 실행 중 |

오류 1056 출력은 이 명령으로 서비스를 새로 시작했다는 뜻이 아니다.
정확한 최초 중지·재시작 시각과 메시지의 초 단위 시각은 제공되지 않았다.
따라서 감지 시간, 복구 전송 지연, 전체 장애 시간을 1분으로 단정하지 않는다.

### 수신 메시지

```text
22:18
[FIRING] WindowsExporterDown
대상: host.docker.internal:9182
환경: lab
상태: firing
내용: host.docker.internal:9182 수집 실패가 1분 이상 지속됩니다.
      exporter 서비스, 네트워크, 방화벽을 확인하세요.

22:19
[RESOLVED] WindowsExporterDown
대상: host.docker.internal:9182
환경: lab
상태: resolved
내용: Windows 메트릭 수집이 복구되었습니다.
```

## 구성과 데이터 흐름

windows_exporter가 Windows 메트릭을 제공하고 Prometheus가 수집한다.
WindowsExporterDown 규칙이 수집 실패 지속을 감지하면 Alertmanager로 알림을 전달한다.
Alertmanager의 lab-notifications receiver가 Incoming Webhook을 통해 Slack으로 전송한다.

| 항목 | 실습 구성 |
|---|---|
| 규칙 | up{job="windows"} == 0, for: 1m |
| 수집 / 평가 주기 | 각각 15초 |
| receiver | lab-notifications |
| Slack 복구 전송 | send_resolved: true |
| 최초 그룹 대기 | group_wait: 10s |
| 그룹 변경 통지 주기 | group_interval: 1m |
| 반복 알림 주기 | repeat_interval: 4h |
| 호스트 인증 파일 | secrets/slack-webhook-url |
| 컨테이너 인증 파일 | /run/secrets/slack-webhook-url |
| 파일을 읽는 서비스 | alertmanager |
| 이메일 | 아직 미구성·미검증 |

인증 파일은 URL 한 줄을 담고, /secrets/를 .gitignore로 제외한다.
실제 Webhook URL은 이 보고서에 포함하지 않는다.

### 소스 반영 상태

보고서 작성 시 원격 lab/003-alerting 브랜치의 설정은 아직 lab-ui-only receiver였고,
Compose에도 Webhook 파일 마운트가 없었다.
Slack 수신은 로컬에 적용한 설정으로 검증한 결과다.
실제 로컬 compose.yaml, alertmanager/alertmanager.yml, .gitignore의 커밋·push가 필요하다.

필요한 마운트는 alertmanager 서비스의 volumes 아래에 위치한다.

```yaml
- ./secrets/slack-webhook-url:/run/secrets/slack-webhook-url:ro
```

Alertmanager의 slack_configs는 api_url_file로 위 컨테이너 경로를 참조한다.
read-only 마운트와 Git 제외는 파일 암호화 기능이 아니다.

## 실험 절차

1. amtool check-config로 설정을 검사한다.
2. Alertmanager 컨테이너를 재생성하여 파일 마운트를 적용한다.
3. 컨테이너에서 인증 파일의 존재·유형·읽기 가능 여부·크기를 확인한다.
4. Windows 대상 UP과 알림 Inactive를 확인한다.
5. 관리자 권한 터미널에서 exporter를 중지한다.
6. Prometheus Firing과 Slack 장애 메시지를 확인한다.
7. exporter를 시작하고 Slack 복구 메시지를 확인한다.
8. exporter가 RUNNING인지 확인하고 수신 시각을 기록한다.

```bash
sc.exe stop windows_exporter
sc.exe query windows_exporter

# 장애 메시지 확인 후 복구
sc.exe start windows_exporter
sc.exe query windows_exporter
```

## 발생한 문제와 조치

| 증상 | 원인·확인 내용 | 조치 |
|---|---|---|
| undefined receiver "lab-ui-only" | route와 receivers의 이름 불일치 | 양쪽을 lab-notifications로 일치 |
| Webhook 파일 검사에 출력 없음 | 초기 검사는 실패 이유를 구분하지 않음 | 존재·파일 유형·읽기 권한·크기를 분리 검사 |
| 재생성 후에도 MISSING | Webhook 마운트가 prometheus 서비스에 있었음 | alertmanager로 이동하고 변경 서비스 재생성 |
| StartService 실패 1056 | 이미 실행 중인 서비스에 시작 요청 | query의 RUNNING 상태 확인, 불필요한 재시작 생략 |

사용자 대화 중 공유된 YAML은 들여쓰기도 불명확하여 전체 구조를 정리했다.
실제 amtool 오류로 확정된 원인은 receiver 이름 불일치였다.

## 후속 개선

- 수신 메시지 제목 링크가 컨테이너 호스트 이름(d46a8b04f106:9093)을 가리킨다.
  브라우저 접근성이 확인된 주소를 external URL 또는 메시지 링크로 지정하고 별도 검증한다.
  현재 Slack 수신 성공이 해당 링크 접근 성공까지 의미하지는 않는다.
- 로컬에서 검증한 Slack 설정 소스를 GitHub에 반영한다.
- 같은 receiver에 이메일을 추가하고 양쪽 채널의 장애·복구 수신을 검증한다.
- 운영에서는 허용 감지 시간과 오탐 빈도에 맞춰 지속 시간·전송 간격을 결정한다.

## 관련 기록

- [003. Windows 수집 중단 알림 발생·복구 검증](003-windows-exporter-alerting.md)
