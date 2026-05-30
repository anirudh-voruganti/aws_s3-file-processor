#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy the reusable S3 file processor pattern with team-specific settings."
    )
    parser.add_argument("--app-name", default="file-processor")
    parser.add_argument("--stack-name", default="FileProcessorStack")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--account")
    parser.add_argument("--bucket-name-prefix")
    parser.add_argument("--lambda-code-path", default="lambda")
    parser.add_argument("--object-prefix")
    parser.add_argument("--object-suffix")
    parser.add_argument("--profile")
    parser.add_argument("--synth", action="store_true", help="Run cdk synth instead of cdk deploy.")
    parser.add_argument(
        "--require-approval",
        choices=["never", "any-change", "broadening"],
        default="broadening",
        help="CDK approval policy for deploy operations.",
    )

    args = parser.parse_args()
    command = [
        "cdk",
        "synth" if args.synth else "deploy",
        "--context",
        f"app_name={args.app_name}",
        "--context",
        f"stack_name={args.stack_name}",
        "--context",
        f"region={args.region}",
        "--context",
        f"lambda_code_path={args.lambda_code_path}",
    ]

    optional_context = {
        "account": args.account,
        "bucket_name_prefix": args.bucket_name_prefix,
        "object_prefix": args.object_prefix,
        "object_suffix": args.object_suffix,
    }
    for key, value in optional_context.items():
        if value:
            command.extend(["--context", f"{key}={value}"])

    if args.profile:
        command.extend(["--profile", args.profile])

    if not args.synth:
        command.append("--require-approval")
        command.append(args.require_approval)

    env = os.environ.copy()
    env["PATH"] = f"{os.path.dirname(sys.executable)}{os.pathsep}{env.get('PATH', '')}"

    subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
