# 7-1 Mimir + SeaweedFS 기동

> 이 문서의 준비·대기 표시는 작성 당시 상태다. 현재 진행 상태와 잔여 검증은 [챕터 지도](../roadmap.md)의 7장 체크포인트를 기준으로 확인한다.

작성일 2026-09-24. 브랜치 lab/007-mimir.
상태: 설치 소스 준비·정적 검증 완료, 사용자 PC의 통합 시험 결과 대기.

## 이전 단계 증거

사용자 출력: prepare-mimir-images.sh PASS.
스냅샷 .local/images-20260924T135514Z-5336.
Mimir 3.2.1, e49585d4, Go 1.26.7, linux/amd64 버전 실행 성공.
Mimir registry digest: sha256:92838f113ba54230014e79bc812e57ca90bb9ebc06e665f59e4f700098c2dd04.
Prometheus 3.14.0, Grafana 13.2.1, Alertmanager 0.34.0 및 기존 3개 이미지 식별자는 해당 스냅샷에 보관.
Image ID와 RepoDigest는 별개 개념이며 이번 출력에서 같더라도 항상 같다고 가정하지 않는다.

## 저장소 결정 변경

MinIO 후보를 SeaweedFS 4.47의 mini/S3 모드로 변경한다.
이유: MinIO community의 archive·컨테이너 소스 빌드 요구와 비교해,
SeaweedFS는 조회 시점 최근 릴리스(4.47, 2026-09-14), 공식 Docker 이미지, 인증된 S3 API와 시작 시 버킷 생성을 제공한다.
Mimir의 특정 벤더 공식 인증을 주장하지 않는다. 이 조합의 호환성은 아래 기능 시험으로 검증한다.

- 공식 릴리스: https://github.com/seaweedfs/seaweedfs/releases/tag/4.47
- 해당 버전 사용법: https://github.com/seaweedfs/seaweedfs/blob/4.47/README.md
- 해당 버전 mini 구현: https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/mini.go
- Mimir 기준 설정: https://github.com/grafana/mimir/blob/mimir-3.2.1/docs/configurations/single-process-config-blocks.yaml
- Mimir 설정 명세: https://github.com/grafana/mimir/blob/mimir-3.2.1/docs/sources/mimir/configure/configuration-parameters/index.md

Docker Registry API로 아래 태그의 digest와 amd64 manifest 존재를 확인했다.
SeaweedFS: chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882.
검사용 Python: python:3.12.14-alpine@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111.
Python은 검사가 끝나면 제거되는 일회성 컨테이너다.

## 구조와 범위

Mimir 단일 인스턴스, classic, replication_factor=1, tenant=lab.
Mimir CPU 2/메모리 4GiB, SeaweedFS CPU 1/메모리 2GiB.
각각 전용 named volume을 사용한다. 단일 Windows/WSL 호스트이므로 HA 검증이 아니다.
Mimir HTTP만 127.0.0.1:9009에 공개한다.
SeaweedFS는 내부 네트워크 mimir-storage에서만 접근 가능하며 S3 외 관리 포트를 호스트에 공개하지 않는다.
S3는 내부 HTTP이며 운영 TLS/테넌트 인증 gateway 구성은 별도다.
S3 접근 키는 임의 생성해 Git 제외 .env.mimir에 저장한다. Docker 관리자에게는 환경변수가 보일 수 있다.
.env.mimir와 원문 docker inspect/config 전체 출력은 공유하지 않는다.
이 키는 로컬 학습용 S3 초기 관리자 자격증명이며 운영 최소 권한 정책 구현을 대체하지 않는다.

## 실행 (Git Bash)

```bash
git status --short --branch
git pull --ff-only
bash scripts/start-mimir.sh .local/images-20260924T135514Z-5336
```

스크립트가 하는 일:
1. 기존 3개 서비스의 이미지 고정 override를 .local/mimir에 복사.
2. .env.mimir가 없을 때만 임의 키 생성. 재실행해도 키를 변경하지 않음.
3. Compose 문법 검사 및 새 구성의 digest 고정 이미지 다운로드.
4. Mimir -modules 실행으로 YAML 파싱과 설정 Validate 수행. -version만으로 설정 검증을 대신하지 않음.
5. SeaweedFS만 기동 (--no-deps).
6. 서명된 버킷 HEAD, 임시 객체 PUT/GET/LIST, 무인증 GET 거부, DELETE와 삭제 후 HEAD 404 확인.
7. S3 시험 성공 후 Mimir만 기동 (--no-deps).
8. /ready HTTP 200, tenant lab에서 vector(1) 응답 1 확인.
9. 새 서비스 상태와 실제 Memory/NanoCPUs 제한 출력.

프로브의 시작 대기는 각 최대 120초 + 현재 요청 timeout이다. 실패 시 다음 단계로 진행하지 않는다.
S3 프로브는 _lab_probe/ 아래 자체 UUID 객체만 쓰고 지운다.
이 단계는 Prometheus/Grafana 재시작, remote_write 추가, 데이터 소스 변경을 수행하지 않는다.
기존 3개 이미지 고정 override는 이후에도 mimir-compose.sh를 통해 사용한다.
기존 compose.yaml만 직접 실행하면 원래 latest 설정을 읽으므로 다음 운영 명령은 wrapper를 사용한다.

## 통과 증거

- PASS: signed bucket HEAD
- PASS: signed PUT/GET/LIST and unsigned GET denied
- PASS: DELETE and missing object confirmed
- PASS: Mimir /ready
- PASS: tenant lab query vector(1); ingestion not tested yet
- 최종 PASS: S3 CRUD/auth and Mimir ready/query. remote_write is not enabled yet.
- object-store Memory=2147483648, NanoCPUs=1000000000
- mimir Memory=4294967296, NanoCPUs=2000000000

/ready와 vector(1)은 준비 상태·쿼리 엔진 검사다. 메트릭 수신·블록 업로드·재전송·7일 보존 검증은 이후 단계다.
조회 엔진의 상수 응답은 S3에 메트릭이 저장됐다는 증거가 아니다.
7일 retention은 compactor 정책이며 즉시 삭제 또는 7일치 저장 완료를 뜻하지 않는다.

## 실패 시 진단과 원복

```bash
bash scripts/mimir-compose.sh ps -a object-store mimir
bash scripts/mimir-compose.sh logs --tail=80 object-store mimir
```

로그를 공유하기 전 자격정보가 없는지 확인한다. 구성 전체 출력은 불필요하다.
실패 원인은 image pull, config validation, S3 인증·쓰기, Mimir readiness를 구분한다.
기존 서비스에 영향이 있거나 새 서비스의 자원 사용이 과하면 다음으로 추가 서비스만 중지한다.

```bash
bash scripts/mimir-compose.sh stop mimir object-store
```

볼륨과 .env.mimir는 보존한다. down -v 또는 전체 prune을 사용하지 않는다.
원인 수정 후 같은 start-mimir.sh 명령을 재실행할 수 있다.

## 작성 환경 검증과 한계

Bash 구문, YAML 파싱, Python 컴파일 검사를 수행했다.
SeaweedFS 동일 버전 실행 파일의 native 시험을 시도했으나 작성 환경의 서버 소켓 제한으로 완료하지 못했다.
Docker 엔진이 없어 Compose 실행과 이 조합의 통합 성공은 아직 확인하지 않았다.
사용자 PC의 위 PASS 출력이 확보되기 전 7-1 완료로 표시하지 않는다.
