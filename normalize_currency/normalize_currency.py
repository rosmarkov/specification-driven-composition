import json
from urllib.parse import urlparse

import boto3

s3 = boto3.client("s3")


def lambda_handler(event, context):
    rows = load_rows(event["current_s3_uri"])
    mapping = event["mapping"]

    source = mapping["source_field"]
    target = mapping["target_field"]

    for row in rows:
        row[target] = normalize_amount(row[source])

    save_rows(rows, event["output_s3_uri"])
    return {"output_s3_uri": event["output_s3_uri"]}


def normalize_amount(value):
    text = str(value).strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    return round(float(text), 2)


def load_rows(s3_uri):
    parsed = urlparse(s3_uri)
    obj = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    return json.loads(obj["Body"].read().decode("utf-8"))


def save_rows(rows, s3_uri):
    parsed = urlparse(s3_uri)
    s3.put_object(
        Bucket=parsed.netloc,
        Key=parsed.path.lstrip("/"),
        Body=json.dumps(rows)
    )