#!/usr/bin/env python3

import aws_cdk as cdk
from cdk_patterns.s3_file_processor import S3FileProcessorProps
from stacks.file_processor_stack import FileProcessorStack

app = cdk.App()

processor_props = S3FileProcessorProps(
    app_name=app.node.try_get_context("app_name") or "file-processor",
    lambda_code_path=app.node.try_get_context("lambda_code_path") or "lambda",
    bucket_name_prefix=app.node.try_get_context("bucket_name_prefix"),
    object_prefix=app.node.try_get_context("object_prefix"),
    object_suffix=app.node.try_get_context("object_suffix"),
)

FileProcessorStack(
    app,
    app.node.try_get_context("stack_name") or "FileProcessorStack",
    processor_props=processor_props,
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
    description="S3 file ingestion and processing pipeline",
)

app.synth()
