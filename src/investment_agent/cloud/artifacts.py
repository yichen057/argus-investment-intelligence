from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Protocol

from investment_agent.config import Settings


class ArtifactStore(Protocol):
    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> str: ...

    def put_file(self, key: str, path: Path, *, content_type: str) -> str: ...

    def delete(self, key: str) -> None: ...


class LocalArtifactStore:
    def __init__(self, root: Path = Path("artifacts")) -> None:
        self._root = root

    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> str:
        del content_type
        target = self._target_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target.resolve().as_uri()

    def put_file(self, key: str, path: Path, *, content_type: str) -> str:
        del content_type
        target = self._target_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        return target.resolve().as_uri()

    def delete(self, key: str) -> None:
        target = self._target_for_key(key)
        target.unlink(missing_ok=True)

        root = self._root.resolve()
        parent = target.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def _target_for_key(self, key: str) -> Path:
        root = self._root.resolve()
        target = (root / key).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Artifact key must stay inside the artifact root")
        return target


class S3ArtifactStore:
    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "argus",
        region: str = "us-west-2",
        client: Any | None = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def put_bytes(self, key: str, content: bytes, *, content_type: str) -> str:
        object_key = self._object_key(key)
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return f"s3://{self._bucket}/{object_key}"

    def put_file(self, key: str, path: Path, *, content_type: str) -> str:
        object_key = self._object_key(key)
        self._client.upload_file(
            str(path),
            self._bucket,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
                "ServerSideEncryption": "AES256",
            },
        )
        return f"s3://{self._bucket}/{object_key}"

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._object_key(key))

    def _object_key(self, key: str) -> str:
        return f"{self._prefix}/{key}" if self._prefix else key


def make_artifact_store(settings: Settings) -> ArtifactStore:
    if settings.s3_bucket:
        return S3ArtifactStore(
            settings.s3_bucket,
            prefix=settings.s3_prefix,
            region=settings.aws_region,
        )
    return LocalArtifactStore()
