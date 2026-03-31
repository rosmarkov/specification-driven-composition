import json
import os
from urllib.parse import urlparse

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sfn = boto3.client("stepfunctions")

REGISTRY_TABLE = os.environ["REGISTRY_TABLE"]
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
STATE_MACHINE_ROLE_ARN = os.environ["STATE_MACHINE_ROLE_ARN"]


def lambda_handler(event, context):
    try:
        spec = load_json_from_s3(event["spec_s3_uri"])
        mappings = spec["mappings"]

        capabilities = {}
        for mapping in mappings:
            name = mapping["transformation"]["capability"]
            capabilities[name] = get_capability(name)

        state_machine_name = event.get("state_machine_name", "orders-transform")
        definition = build_definition(mappings, capabilities)

        state_machine_arn = upsert_state_machine(state_machine_name, definition)

        execution_input = {
            "current_s3_uri": event["input_s3_uri"]
        }

        response = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(execution_input)
        )

        final_output_s3_uri = f"s3://{OUTPUT_BUCKET}/runs/{len(mappings)}_{mappings[-1]['transformation']['capability']}.json"

        return {
            "state_machine_arn": state_machine_arn,
            "execution_arn": response["executionArn"],
            "final_output_s3_uri": final_output_s3_uri
        }
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        raise

def load_json_from_s3(s3_uri):
    parsed = urlparse(s3_uri)
    obj = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    return json.loads(obj["Body"].read().decode("utf-8"))


def get_capability(name):
    table = dynamodb.Table(REGISTRY_TABLE)
    response = table.get_item(Key={"capability_name": name})
    item = response.get("Item")
    if not item:
        raise ValueError(f"Capability not found: {name}")
    return item


def build_definition(mappings, capabilities):
    states = {}

    for i, mapping in enumerate(mappings, start=1):
        capability_name = mapping["transformation"]["capability"]
        capability = capabilities[capability_name]

        state_name = f"Step{i}_{capability_name}"
        output_s3_uri = f"s3://{OUTPUT_BUCKET}/runs/{i}_{capability_name}.json"

        states[state_name] = {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
                "FunctionName": capability["lambda_arn"],
                "Payload": {
                    "current_s3_uri.$": "$.current_s3_uri",
                    "output_s3_uri": output_s3_uri,
                    "mapping": mapping
                }
            },
            "ResultSelector": {
                "current_s3_uri.$": "$.Payload.output_s3_uri"
            },
            "ResultPath": "$"
        }

        if i < len(mappings):
            next_name = f"Step{i+1}_{mappings[i]['transformation']['capability']}"
            states[state_name]["Next"] = next_name
        else:
            states[state_name]["End"] = True

    return json.dumps({
        "StartAt": list(states.keys())[0],
        "States": states
    })


def upsert_state_machine(name, definition):
    for sm in sfn.list_state_machines()["stateMachines"]:
        if sm["name"] == name:
            sfn.update_state_machine(
                stateMachineArn=sm["stateMachineArn"],
                definition=definition,
                roleArn=STATE_MACHINE_ROLE_ARN
            )
            return sm["stateMachineArn"]

    response = sfn.create_state_machine(
        name=name,
        definition=definition,
        roleArn=STATE_MACHINE_ROLE_ARN,
        type="STANDARD"
    )
    return response["stateMachineArn"]