from __future__ import annotations

import re
from dataclasses import dataclass

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_sqs as sqs,
)
from constructs import Construct


@dataclass(frozen=True)
class S3FileProcessorProps:
    app_name: str = "file-processor"
    lambda_code_path: str = "lambda"
    bucket_name_prefix: str | None = None
    object_prefix: str | None = None
    object_suffix: str | None = None
    log_retention: logs.RetentionDays = logs.RetentionDays.ONE_MONTH
    dlq_retention_days: int = 14
    lambda_timeout_seconds: int = 30
    lambda_memory_size: int = 256
    bucket_removal_policy: RemovalPolicy = RemovalPolicy.RETAIN
    enforce_https: bool = True
    enforce_sse_aes256: bool = True


class S3FileProcessor(Construct):
    """Secure, reusable S3 ingestion pattern with Lambda processing."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        props: S3FileProcessorProps | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        props = props or S3FileProcessorProps()
        stack = Stack.of(self)
        bucket_prefix = _to_bucket_prefix(props.bucket_name_prefix or props.app_name)

        self.bucket = s3.Bucket(
            self,
            "InputBucket",
            bucket_name=f"{bucket_prefix}-input-{stack.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=props.bucket_removal_policy,
            auto_delete_objects=False,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldVersions",
                    enabled=True,
                    noncurrent_version_expiration=Duration.days(30),
                )
            ],
        )

        if props.enforce_https:
            self.bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyInsecureConnections",
                    effect=iam.Effect.DENY,
                    principals=[iam.AnyPrincipal()],
                    actions=["s3:*"],
                    resources=[
                        self.bucket.bucket_arn,
                        self.bucket.arn_for_objects("*"),
                    ],
                    conditions={"Bool": {"aws:SecureTransport": "false"}},
                )
            )

        if props.enforce_sse_aes256:
            self.bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyUploadsWithoutSseAes256",
                    effect=iam.Effect.DENY,
                    principals=[iam.AnyPrincipal()],
                    actions=["s3:PutObject"],
                    resources=[self.bucket.arn_for_objects("*")],
                    conditions={
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": "AES256"
                        }
                    },
                )
            )

        self.dlq = sqs.Queue(
            self,
            "ProcessorDLQ",
            queue_name=f"{props.app_name}-dlq",
            retention_period=Duration.days(props.dlq_retention_days),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        self.log_group = logs.LogGroup(
            self,
            "ProcessorLogGroup",
            log_group_name=f"/app/{props.app_name}",
            retention=props.log_retention,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.processor = lambda_.Function(
            self,
            "ProcessorFunction",
            function_name=props.app_name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                props.lambda_code_path,
                exclude=["tests", "__pycache__", "*.pyc"],
            ),
            timeout=Duration.seconds(props.lambda_timeout_seconds),
            memory_size=props.lambda_memory_size,
            dead_letter_queue=self.dlq,
            retry_attempts=2,
            log_group=self.log_group,
            environment={
                "LOG_LEVEL": "INFO",
                "BUCKET_NAME": self.bucket.bucket_name,
            },
        )

        self.bucket.grant_read(self.processor)

        notification_filters = []
        if props.object_prefix or props.object_suffix:
            notification_filters.append(
                s3.NotificationKeyFilter(
                    prefix=props.object_prefix,
                    suffix=props.object_suffix,
                )
            )

        self.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.processor),
            *notification_filters,
        )

        bucket_output = CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        bucket_output.override_logical_id("BucketName")

        function_output = CfnOutput(self, "FunctionName", value=self.processor.function_name)
        function_output.override_logical_id("FunctionName")

        log_group_output = CfnOutput(self, "LogGroup", value=self.log_group.log_group_name)
        log_group_output.override_logical_id("LogGroup")

        dlq_output = CfnOutput(self, "DLQUrl", value=self.dlq.queue_url)
        dlq_output.override_logical_id("DLQUrl")


def _to_bucket_prefix(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9.-]", "-", value.lower()).strip(".-")
    if not normalized:
        raise ValueError("bucket name prefix must include at least one letter or number")
    return normalized
