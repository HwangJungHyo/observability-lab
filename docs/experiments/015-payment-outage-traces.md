# 실험 015: 결제 중단·복구 트레이스와 6장 종료

- 실험일: 2026-09-22
- 기록 기준 소스: 512a8cb0ec86da81f8c34fd7343bfd44d33150d0
- 브랜치: lab/006-tracing
- 환경: 사용자 Windows / Git Bash / Docker Desktop
- 판정: 6장 기능 실험 완료. 장애·복구 트레이스와 로그는 사용자가 확인 완료를 보고했다.
- 이번 문서 갱신 과정에서 해당 PC의 실험을 재실행한 것은 아니다.

## 목적과 절차

payment 중단 → 주문 오류 요청 → payment 재시작 → 주문 성공 요청 → Tempo/Loki 비교.
정상 경로의 세 span과 중단 시 주문 측 두 span을 비교하는 실험이다.
전체 구조와 지연 실험은 실험 012~014를 참조한다.

## 제공된 원시 출력으로 확인한 결과

| 항목 | 장애 | 복구 |
|---|---|---|
| HTTP | 502 Bad Gateway | 201 Created |
| 결과 | payment_unavailable | confirmed |
| curl 전체 시간 | 4.187035초 | 0.291379초 |
| Request ID | trace-down-1790086379-14989 | trace-recovered-1790086401-3667 |
| Trace ID | 321ff4f0ee85c5fcd9a3e97f23f8d946 | 4f9579d9bfd184aa1793e5d3e48f3791 |
| HTTP Date | 2026-09-22 14:13:04 UTC | 2026-09-22 14:13:07 UTC |

장애 주문 로그:

```json
{"timestamp":"2026-09-22T14:13:04.299+00:00","level":"error","service":"order-api","event":"request_completed","request_id":"trace-down-1790086379-14989","method":"POST","route":"/orders","status_code":502,"duration_ms":3973.388,"error":"payment_unavailable","trace_id":"321ff4f0ee85c5fcd9a3e97f23f8d946","span_id":"a10ab175837f1f19"}
```

ログの処理時間は3973.388ms、curl全体は4187.035ms。差は213.647ms。
測定範囲が異なり、この差全体をネットワーク遅延と断定しない。
約4秒という値だけでtimeoutや再試行回数を確定しない。

## 証拠の区分

- 提供された出力: 障害502・復旧201、各Trace ID、curl時間、障害注文JSONログ。
- ユーザー確認: 障害・復旧のトレースとログを確認完了 (2026-09-22)。
- 詳細未転記: 各spanの正確なDuration、CLIENTのerror.type/exception原文、復旧2サービスのJSONログ、最終healthy/up画面。
- 復旧直後のps出力はpaymentがhealth: starting。後続注文201により業務リクエスト成功は確認済みだが、このps出力をhealthyの証拠として扱わない。
- 障害・復旧span数/状態の詳細な機械可読証拠は追加取得時に追記。見ていない画面の属性値は補完しない。

## 調査上の注意

TempoへLokiクエリとprintfを貼った際の400は検索構文エラーであり、保存失敗の証拠ではなかった。
TempoはTrace IDで取得し、LokiはLogQLで検索する。
spanがないことだけではサービス中断と計測/配送欠落を区別できない。コンテナ状態・CLIENT例外・収集系状態を併用する。

## 証拠を補強する場合に必要なもの

1. 障害CLIENT spanのDuration、Status、error.type、exception.messageの原文。
2. 復旧Trace IDのspan一覧と各Duration・Status、order-api/paymentのJSONログ。
3. 最終payment/order-api healthy、Prometheus対象up=1、PAYMENT_DELAY_SECONDS=0.08。
4. 可能なら両Trace JSON。保存済みログは対象Trace IDに限定し、資格情報や不要な個人情報を含めない。

Request IDに含めた数値は任意の識別子であり時刻の根拠にはしない。HTTP Dateとログtimestampを記録する。
数値部分とログの時刻に不一致があるため、以後はホスト/コンテナ時刻も確認する。

## 6章の完了範囲

Tempo接続、正常の呼び出し関係、ログ↔トレース、1秒遅延と復旧、中断と復旧の機能実験を完了。
詳細原文の追加保存と約4秒の時間内訳調査は残件として追跡する。
性能・耐障害性・SLO達成・本番運用準備完了の判定ではない。
後続はMimir接続に加え、継続トラフィック下での障害・再送・保存・アラート・復元試験を行う。
