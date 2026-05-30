# Triggered when a file lands in S3.
# Reads the first line, figures out the format, and logs the parsed output.
#
# Handles: JSON, key=value pairs, CSV, and plain text

from __future__ import annotations

import json
import logging
import os
import urllib.parse

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# reuse across warm invocations
s3 = boto3.client("s3")


def handler(event: dict, context) -> dict:
    logger.info("event: %s", json.dumps(event))

    results = [
        _process(r["s3"]["bucket"]["name"], urllib.parse.unquote_plus(r["s3"]["object"]["key"]))
        for r in event.get("Records", [])
    ]

    logger.info("done: %s", json.dumps(results))
    return {"processed": results}


def _process(bucket: str, key: str) -> dict:
    logger.info("processing s3://%s/%s", bucket, key)

    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        lines = [line for line in body.splitlines() if line.strip()]
        parsed = _parse(lines[0] if lines else "")
        logger.info("parsed %s → %s", key, json.dumps(parsed))
        return {"key": key, "status": "success", "data": parsed}

    except ClientError as e:
        code = e.response["Error"]["Code"]
        logger.error("s3 error [%s] on %s: %s", code, key, e)
        return {"key": key, "status": "error", "error": f"{code}: {e}"}

    except UnicodeDecodeError as e:
        logger.error("encoding error on %s: %s", key, e)
        return {"key": key, "status": "error", "error": str(e)}

    except Exception as e:
        logger.error("unexpected error on %s: %s", key, e)
        # re-raise so lambda retries and routes to DLQ if it keeps failing
        raise


def _parse(line: str) -> dict:
    line = line.strip()

    if not line:
        return {"format": "empty", "value": None, "raw": line}

    # try JSON first
    if line.startswith(("{", "[")):
        try:
            return {"format": "json", "value": json.loads(line), "raw": line}
        except json.JSONDecodeError:
            pass

    # key=value pairs
    if "=" in line:
        pairs = {}
        for token in line.split(","):
            if "=" in token:
                k, v = token.split("=", 1)
                pairs[k.strip()] = v.strip()
        if pairs:
            return {"format": "key_value", "value": pairs, "raw": line}

    # CSV
    if "," in line:
        return {"format": "csv", "value": [f.strip() for f in line.split(",")], "raw": line}

    # plain text fallback
    return {"format": "text", "value": line, "raw": line}
