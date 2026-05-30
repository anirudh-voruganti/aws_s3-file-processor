from aws_cdk import Stack
from cdk_patterns.s3_file_processor import S3FileProcessor, S3FileProcessorProps
from constructs import Construct


class FileProcessorStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        processor_props: S3FileProcessorProps | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        S3FileProcessor(
            self,
            "FileProcessor",
            props=processor_props,
        )
