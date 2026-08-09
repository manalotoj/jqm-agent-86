from agent_86.services.blob_storage_service import BlobDownload


class AzureBlobStorageService:
    def __init__(self, connection_string: str, container_name: str) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        self._client = BlobServiceClient.from_connection_string(connection_string)
        self._container_name = container_name

    async def upload_blob(
        self,
        blob_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        from azure.storage.blob import ContentSettings

        blob_client = self._client.get_blob_client(
            container=self._container_name,
            blob=blob_name,
        )
        await blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    async def download_blob(self, blob_name: str) -> BlobDownload:
        blob_client = self._client.get_blob_client(
            container=self._container_name,
            blob=blob_name,
        )
        downloader = await blob_client.download_blob()
        properties = await blob_client.get_blob_properties()
        content_type = None
        if properties.content_settings is not None:
            content_type = properties.content_settings.content_type
        return BlobDownload(
            content=await downloader.readall(),
            content_type=content_type,
        )

    async def delete_blob(self, blob_name: str) -> None:
        blob_client = self._client.get_blob_client(
            container=self._container_name,
            blob=blob_name,
        )
        await blob_client.delete_blob(delete_snapshots="include")