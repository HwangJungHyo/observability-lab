# 7-0b 실행 이미지 고정과 Mimir 이미지 준비

> 이 문서의 준비·대기 표시는 작성 당시 상태다. 현재 진행 상태와 잔여 검증은 [챕터 지도](../roadmap.md)의 7장 체크포인트를 기준으로 확인한다.

## 확인된 실행 버전

사용자 PC 출력: Prometheus 3.14.0, Grafana 13.2.1, Alertmanager 0.34.0, linux/amd64.
Alertmanager의 /bin/alertmanager 경로는 Git Bash의 자동 경로 변환 때문에 처음 실패했고,
MSYS_NO_PATHCONV=1 적용 후 정상 버전 출력. 서비스 장애 증거가 아니다.

## 실행

Git Bash, 저장소 루트:

```bash
git status --short --branch
git pull --ff-only
bash scripts/prepare-mimir-images.sh
```

스크립트는 실행 컨테이너의 Image ID -> 해당 로컬 이미지의 RepoDigests를 조회하고,
그 digest가 같은 Image ID를 가리키는지 확인한다.
기존 :latest 태그는 pull하지 않는다. Mimir 3.2.1만 linux/amd64로 pull하고,
그 digest를 고정하여 네트워크 없는 일회성 컨테이너에서 -version을 실행한다.
마지막으로 기존 3개 서비스용 Compose 이미지 override를 config --quiet로 검사한다.
up/restart/down은 실행하지 않는다. Mimir 서버는 아직 설치·기동 완료가 아니다.

성공하면 .local/images-<UTC>-<PID>/ 아래:
- compose.images.lock.yaml: 기존 3개 서비스의 repository@sha256 이미지 지정.
- images.tsv: 기존 실행 이미지 ID와 digest, Mimir 이미지 ID와 digest.
- mimir-image.env: 후속 설치에서 사용할 MIMIR_IMAGE.

.local은 Git에서 제외한다. 출력된 이미지 식별자는 비밀번호가 아니며 다음 검토용으로 공유 가능하다.
고정값은 후속 Compose에 실제 연결하고 적용 확인해야 실행 구성 고정 완료로 판정한다.
기존 Compose 본문은 이번 단계에서 변경하지 않았다. 전체 서비스 명령에는 기존 orders/logs/traces overlay를 유지해야 한다.

RepoDigests가 없으면 스크립트는 중단한다. sha256 Image ID를 repository digest로 대신 쓰지 않는다.
pull 실패 시 임의의 latest로 바꾸지 않고 해당 오류를 확인한다.
버전 확인용 컨테이너는 --rm으로 종료 후 제거하며 서비스 볼륨은 마운트하지 않는다.

## Mimir와 저장소 공급 경로

Mimir 3.2.1 공식 릴리스 및 해당 태그의 공식 classic 예제를 확인했다.
https://github.com/grafana/mimir/releases/tag/mimir-3.2.1
https://github.com/grafana/mimir/blob/mimir-3.2.1/docs/sources/mimir/get-started/play-with-grafana-mimir/config/mimir.yaml

앞선 MinIO 후보 선정은 수정이 필요하다.
MinIO community 저장소는 2026-04-25 archive 상태이며,
최신 공개 릴리스 RELEASE.2025-10-15T17-29-55Z는 컨테이너 소스 빌드를 안내한다.
따라서 해당 릴리스 이름의 공식 컨테이너가 배포돼 있다고 가정하지 않는다.
https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z

7-1 저장소 선택은 유지보수 중인 S3 호환 대안의 Mimir 호환성·인증·이미지 배포 경로를 검토하거나,
MinIO 고정 소스의 재현 빌드와 유지보수 한계를 명시한 학습용 구성 중에서 결정한다.
아직 특정 대안이 호환 검증됐다고 기록하지 않는다. 기존 운영 서비스에는 영향이 없다.

## 검증 범위

작성 환경에는 Docker CLI/daemon이 없어 실제 pull·Compose·기동을 실행하지 못했다.
bash -n 구문 검사를 통과했다. 사용자 PC에서 스크립트 결과를 확인한 뒤 다음 설치 단계로 진행한다.
