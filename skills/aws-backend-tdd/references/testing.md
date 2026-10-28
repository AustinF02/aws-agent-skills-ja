# AWS・バックエンドのテスト

今回影響する対象だけ確認する。既存ツールを優先し、追加依存は必要な場合だけ導入する。

| 選択肢 | 適する確認 |
| --- | --- |
| botocore Stubber | Python SDKの要求・応答・サービスエラー |
| moto | 対応サービスの状態を使うPythonテスト |
| aws-sdk-client-mock | JavaScript SDK v3のコマンドと応答 |
| DynamoDB Local | 保存・取得・条件付き更新 |
| SAM local invoke | Lambda実行環境とイベント入力 |
| LocalStack | 対応サービスを組み合わせた連携 |

対応範囲と実際の接続先を確認する。SAMからも実AWSを呼び出せる。
ローカル統合は専用ポートとテストデータを使い、期限付きhealth checkで起動完了を待つ。
準備に失敗した場合は環境障害として扱い、業務コードを修正しない。

## 対象別の観測

- **API**：入力、認可境界、応答、エラー契約。
- **SDK**：要求、ページネーション、失敗・再試行。
- **Lambda**：公式仕様、SAM generate-event、匿名化済みイベントからfixtureを作る。
  API Gatewayの形式やSQS・S3・EventBridgeの構造を推測で混在させない。
- **非同期**：ローカルでは時計・待機・乱数・失敗を制御し、固定sleepに依存しない。
  処理済み状態、重複排除、部分失敗応答を観測する。
  コードの応答とサービスによる実際のDLQ配送は別の検証。
- **永続化**：条件付き更新、競合、失敗後の状態。
  DynamoDBのGSIは結果整合性。S3のオブジェクト読み取りは強い整合性。
  通知・レプリケーション・競合更新は別に確認する。
- **運用**：必要なログ項目・メトリクスの名称、値、単位と秘密情報の非出力。
  ログ全文や任意の文言は固定しない。

## RED → GREENの例（未実行）

契約：空のIDを拒否する。
既存の `validate_item_id` は入力をそのまま返すものとする。

```python
# tests/test_validation.py
import unittest
from validation import validate_item_id

class ValidationTests(unittest.TestCase):
    def test_rejects_empty_item_id(self):
        with self.assertRaises(ValueError):
            validate_item_id("")
```

`python -m unittest discover -s tests -p test_validation.py -v` を実行し、
ValueErrorが発生しないため失敗することを確認する。importエラーでは代用しない。

```python
# validation.py
def validate_item_id(value):
    if value == "":
        raise ValueError("item_id must not be empty")
    return value
```

同じコマンドで成功を確認する。整理が不要ならREFACTORは省略する。
