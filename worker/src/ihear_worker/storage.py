from __future__ import annotations

from urllib.parse import quote

import httpx


class PrivateStorage:
    def __init__(self, supabase_url: str, service_role_key: str):
        self._base_url = f"{supabase_url.rstrip('/')}/storage/v1"
        self._headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }
        self._client = httpx.Client(timeout=30.0, headers=self._headers)

    def download(self, bucket: str, path: str) -> bytes:
        response = self._client.get(
            f"{self._base_url}/object/authenticated/{quote(bucket, safe='')}/{quote(path, safe='/')}"
        )
        response.raise_for_status()
        return response.content

    def upload_pdf(self, bucket: str, path: str, contents: bytes) -> None:
        response = self._client.post(
            f"{self._base_url}/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
            content=contents,
            headers={"Content-Type": "application/pdf", "x-upsert": "false"},
        )
        if response.status_code == 409:
            return
        response.raise_for_status()

    def delete(self, bucket: str, path: str) -> None:
        response = self._client.delete(
            f"{self._base_url}/object/{quote(bucket, safe='')}/{quote(path, safe='/')}"
        )
        if response.status_code == 404:
            return
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
