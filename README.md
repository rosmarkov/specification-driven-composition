# Specification-Driven Composition on AWS
```md
## What this example shows 
- Define data workflows as specifications (JSON)
- Register reusable transformation functions (AWS Lambda)
- Generate and invoke workflows dynamically (AWS Step Functions)
---
## Key idea
You change pipeline behavior by updating the specification, not the code.
---
## Prerequisites
- AWS CLI configured
- AWS SAM CLI installed
- Python 3.12
---
## Installation steps
1. Deploy the infrastructure
```bash
sam build
sam deploy --guided
2. Retrieve stack outputs
STACK_NAME=<your-stack-name>
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactsBucketName'].OutputValue" \
  --output text)
TABLE=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='RegistryTableName'].OutputValue" \
  --output text)
FORMAT_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='FormatDateFunctionArn'].OutputValue" \
  --output text)
NORMALIZE_ARN=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='NormalizeCurrencyFunctionArn'].OutputValue" \
  --output text)
COMPOSER=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ComposerFunctionName'].OutputValue" \
  --output text)
3. Register capabilities
aws dynamodb put-item \
  --table-name "$TABLE" \
  --item '{"capability_name":{"S":"format_date"},"lambda_arn":{"S":"'"$FORMAT_ARN"'"}}'
aws dynamodb put-item \
  --table-name "$TABLE" \
  --item '{"capability_name":{"S":"normalize_currency"},"lambda_arn":{"S":"'"$NORMALIZE_ARN"'"}}'
4. Upload input data and specification
aws s3 cp input/raw_orders.json "s3://$BUCKET/input/raw_orders.json"
aws s3 cp specs/orders-spec.json "s3://$BUCKET/specs/orders-spec.json"
5. Prepare invocation event
Create events/composer-event.json:
{
  "spec_s3_uri": "s3://REPLACE_BUCKET/specs/orders-spec.json",
  "input_s3_uri": "s3://REPLACE_BUCKET/input/raw_orders.json",
  "state_machine_name": "orders-transform"
}
Replace placeholder:
sed "s/REPLACE_BUCKET/$BUCKET/g" events/composer-event.json > /tmp/composer-event.json
6. Run the workflow
aws lambda invoke \
  --function-name "$COMPOSER" \
  --payload fileb:///tmp/composer-event.json \
  /tmp/composer-response.json
Inspect response:
cat /tmp/composer-response.json
Expected output includes:
- state_machine_arn
- execution_arn
- final_output_s3_uri
7. Inspect results
aws s3 cp "s3://$BUCKET/runs/2_normalize_currency.json" -
Example output:
[
  {
    "order_id": "A1001",
    "order_date": "2026-03-01",
    "amount": "100.50",
    "currency": "USD",
    "amount_normalized": 100.5
  },
  {
    "order_id": "A1002",
    "order_date": "2026-03-02",
    "amount": "250,00",
    "currency": "EUR",
    "amount_normalized": 250.0
  }
]
You can also:
- View execution in AWS Step Functions
- Inspect logs in Amazon CloudWatch
---
## Cleanup
Delete the state machine:
aws stepfunctions list-state-machines
aws stepfunctions delete-state-machine --state-machine-arn <STATE_MACHINE_ARN>
Empty the bucket:
aws s3 rm s3://$BUCKET --recursive
Delete the stack:
sam delete