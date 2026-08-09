from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BlobDownload:
    content: bytes
    content_type: str | None = None


class BlobStorageService(Protocol):
    async def upload_blob(
        self,
        blob_name: str,
        content: bytes,
        content_type: str,
    ) -> None: ...

    async def download_blob(self, blob_name: str) -> BlobDownload: ...

    async def delete_blob(self, blob_name: str) -> None: ...