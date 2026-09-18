# 005. Slack·Gmail 장애 및 복구 알림 검증

## 결론

2026-09-16, WindowsExporterDown 알림을 Slack과 Gmail SMTP 이메일 양쪽으로 전송했다.
사용자는 장애 메시지에 이어 **복구 메시지도 두 채널에서 수신**했다고 확인했다.

- 장애 전송: 사용자 수신 확인 및 Alertmanager DEBUG 성공 로그로 확인.
- 복구 수신: 사용자 확인을 근거로 기록. 복구 시각·본문·서버 로그는 추가 제공되지 않았다.
- 이메일 장애가 발생했다고 단정할 근거는 없었다. INFO에서 성공 로그가 보이지 않는 현상을 진단했고 DEBUG에서 전송 성공을 확인했다.

## 환경과 설정

| 항목 | 실습 값 |
|---|---|
| 환경 | Windows + Git Bash + Docker Desktop |
| 브랜치 | lab/003-alerting |
| Alertmanager | 실행 로그에서 0.34.0 확인 |
| 대상 | host.docker.internal:9182, job=windows, environment=lab |
| 알림 | WindowsExporterDown |
| 조건 / 지속 시간 | up{job="windows"} == 0 / 1m |
| 수집 / 평가 | 각각 15초 |
| receiver | lab-notifications |
| 전송 채널 | Slack Incoming Webhook + Gmail SMTP |
| SMTP | smtp.gmail.com:587, require_tls: true |
| 인증 | 발송 계정의 앱 비밀번호 파일 |
| 복구 전송 | 두 integration에 send_resolved: true |
| 진단 로그 수준 | --log.level=debug |
| group_wait / group_interval / repeat_interval | 10s / 1m / 4h |

이메일 주소, 앱 비밀번호, Webhook URL은 이 기록에 포함하지 않는다.
호스트 파일 secrets/gmail-app-password를 alertmanager 컨테이너의
/run/secrets/gmail-app-password에 읽기 전용으로 마운트하고 auth_password_file로 참조했다.
Slack 파일도 같은 서비스에 별도로 연결한다.

## 증거

[DEBUG 로그 발췌](evidence/005-alertmanager-debug.txt)

로그 파일은 사용자가 제공한 출력의 선택된 줄·필드를 정리한 발췌본이다.
전체 원본 로그 파일이 아니며, 전송 성공 시각·integration·attempts·duration을 보존했다.
로그의 Z는 UTC이며 아래 표에는 KST를 함께 표시한다.

| UTC | KST | 사건 |
|---|---|---|
| 02:18:41.004 | 11:18:41.004 | Alertmanager 0.34.0 시작 |
| 02:20:20.813 | 11:20:20.813 | WindowsExporterDown 활성 알림 수신 및 그룹 처리 |
| 02:20:21.129 | 11:20:21.129 | slack[0] Notify success |
| 02:20:23.887 | 11:20:23.887 | email[0] Notify success |
| 별도 제공 없음 | 별도 제공 없음 | 양쪽 복구 메시지 수신: 사용자 확인 |

| 채널 | 시도 횟수 | 로그의 처리 시간 |
|---|---|---|
| Slack | attempts=1 | 316.117788ms |
| 이메일 | attempts=1 | 3.073624617s |

duration은 전송 처리 시간이다. 장애 시작부터 사용자 수신까지의 전체 지연이나 사용자가 읽은 시간을 뜻하지 않는다.
Notify success만으로 받은편지함 배달을 확정하지 않고 사용자 수신 확인을 함께 근거로 삼았다.

## 실험 및 진단 과정

1. email_configs를 기존 lab-notifications receiver에 추가했다.
2. Gmail 앱 비밀번호 파일을 로컬에 저장하고 Compose 마운트를 추가했다.
3. docker compose config 및 amtool check-config를 실행했다. 사용자가 SUCCESS 출력을 제공했다.
4. 변경을 적용하기 위해 Alertmanager를 재생성했다.
5. Windows exporter 중지·복구로 알림을 검증했다.
6. Slack 메시지는 도착했으나 INFO 수준에서 실시간 전송 로그가 보이지 않아 진단했다.
7. 사용자에게서 이메일도 도착했다는 확인을 받았다.
8. --log.level=debug를 추가하고 재생성한 뒤 새 알림에서 양쪽 Notify success를 확인했다.
9. 사용자에게서 양쪽 복구 메시지도 수신했다는 확인을 받았다.

### 로그를 보는 명령

```bash
docker compose logs -f --since=1m alertmanager
```

-f는 새로 기록되는 로그를 따라가는 옵션이다.
애플리케이션이 기록하지 않은 상세 이벤트를 생성하거나 INFO를 DEBUG로 바꾸지 않는다.
이번 성공 로그는 level=DEBUG에 기록되므로 기본 INFO에서 보이지 않았던 것이 확인됐다.

### 임시 DEBUG 설정

compose.yaml의 alertmanager 서비스 command에만 추가한다.

```yaml
- --log.level=debug
```

재생성 후에는 로그 조회 명령도 다시 연결한다.
이미 완료된 전송의 DEBUG 로그는 나중에 로그 수준을 바꿔도 소급 생성되지 않는다.

## 운영상 해석

- flushing은 그룹을 전송 처리 단계로 넘기는 이벤트이며 실제 발송 성공 증거와 구분한다.
- 활성 알림을 반복 수신했다고 새로운 장애가 매번 발생한 것은 아니다.
- 설정 검사 성공은 SMTP 인증·실제 전달 성공을 보장하지 않는다.
- 수집 중단은 exporter·네트워크·방화벽 문제 등을 포함하며 Windows 전체 장애로 단정하지 않는다.
- 로그의 "TLS is disabled."는 해당 로그 문맥에서 Alertmanager HTTP 수신 서버를 가리키며 SMTP TLS 설정의 판정 근거로 사용하지 않는다.
- 로그·전송 지표·수신 확인을 함께 사용해 전송 단계와 최종 도착을 구분한다.

## 원복 및 소스 반영 상태

DEBUG 진단은 종료하고 command의 --log.level=debug를 제거한 뒤 다음 명령으로 적용한다.

```bash
docker compose config --quiet
docker compose up -d --no-deps --force-recreate alertmanager
sc.exe query windows_exporter
```

기본 INFO 복귀 및 최종 RUNNING 재확인 출력은 이 보고서 작성 시 추가 제공되지 않았다.
복구 알림 수신과 별도로 해당 원복 확인을 남긴다.

보고서 작성 시 GitHub의 compose.yaml과 alertmanager/alertmanager.yml은 Slack만 연결된 상태였다.
따라서 이번 Gmail 수신은 로컬 변경으로 검증된 결과이며,
실제 검증한 Gmail 설정과 파일 마운트는 로컬에서 커밋·push해야 한다.
인증 파일 자체는 포함하지 않는다.

## 완료 범위와 후속 작업

- 완료: Slack·이메일 장애 수신, DEBUG 전송 성공 확인, 양쪽 복구 수신 확인.
- 남은 정리: DEBUG 원복 확인, Gmail 설정 소스 push.
- 다음 실습: CPU 부하 임계값과 지속 시간을 정하고 알림 발생·해제 검증.

## 관련 기록

- [003. Windows 수집 중단 알림](003-windows-exporter-alerting.md)
- [004. Slack 장애·복구 수신](004-slack-notification.md)
