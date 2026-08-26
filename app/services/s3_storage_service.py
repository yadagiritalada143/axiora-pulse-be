"""
app/services/s3_storage_service.py
────────────────────────────────────────────────────────────────────────────────
AWS S3 Storage Manager.

Two storage contexts:
  1. Chat Attachments (axiora-pulse-attachments bucket)
     · upload_file_bytes()  — upload raw bytes
     · upload_base64()      — decode base64 then upload

  2. Workspace Asset Uploads (axiora-assets bucket)
     · upload_workspace_asset()  — upload raw bytes to per-user/per-workspace S3 path
     · delete_workspace_asset()  — remove an object from the assets bucket

Falls back to local filesystem storage under uploads/workspaces/{workspace_id}/
when AWS credentials are not configured.
"""
import base64
import os
import uuid
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class S3StorageService:

    def __init__(self):
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME", "axiora-pulse-attachments")
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")

        # Assets bucket (public workspace file uploads)
        self.assets_bucket_name = os.getenv("AWS_ASSETS_BUCKET_NAME", "axiora-assets")
        self.assets_region = os.getenv("AWS_ASSETS_REGION", "ap-south-1")

        self._s3_client = None
        self._init_s3_client()

    def _init_s3_client(self):
        """Lazy initialize boto3 S3 client if AWS credentials exist."""
        if self.aws_access_key and self.aws_secret_key:
            try:
                import boto3

                client_kwargs = {
                    "aws_access_key_id": self.aws_access_key,
                    "aws_secret_access_key": self.aws_secret_key,
                    "region_name": self.aws_region,
                }
                if self.endpoint_url:
                    client_kwargs["endpoint_url"] = self.endpoint_url

                self._s3_client = boto3.client("s3", **client_kwargs)
                logger.info("[S3StorageService] S3 client initialized for bucket '%s'", self.bucket_name)
            except Exception as e:
                logger.warning("[S3StorageService] Could not initialize boto3 S3 client: %s. Using local fallback.", e)
                self._s3_client = None
        else:
            logger.info("[S3StorageService] AWS credentials not set. Operating in local storage mode.")

    def generate_presigned_url(
        self,
        s3_key: str,
        bucket_name: str | None = None,
        expiration: int = 3600,
    ) -> str:
        """
        Generates a presigned URL for downloading an S3 object securely.
        If S3 is not configured or fails, returns local file endpoint URL.
        """
        if not s3_key:
            return ""

        clean_key = s3_key
        if "amazonaws.com/" in s3_key:
            clean_key = s3_key.split("amazonaws.com/")[-1]

        target_bucket = bucket_name or self.assets_bucket_name
        if self._s3_client and clean_key and not clean_key.startswith("http"):
            try:
                url = self._s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": target_bucket, "Key": clean_key},
                    ExpiresIn=expiration,
                )
                return url
            except Exception as e:
                logger.error("[S3StorageService] Failed to generate presigned URL for key %s: %s", clean_key, e)

        if s3_key.startswith("http://") or s3_key.startswith("https://") or s3_key.startswith("/"):
            return s3_key
        return f"/uploads/{clean_key}"

    # ── Chat Attachment Uploads (axiora-pulse-attachments) ────────────────────

    def upload_file_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        workspace_id: str | int,
        content_type: str = "application/octet-stream"
    ) -> Tuple[str, str]:
        """
        Uploads file bytes to S3 or local storage (chat attachments bucket).
        Returns Tuple[file_url, storage_path]
        """
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "attachment.dat"
        s3_key = f"workspaces/{workspace_id}/attachments/{unique_id}_{safe_filename}"

        if self._s3_client:
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                file_url = self.generate_presigned_url(s3_key, bucket_name=self.bucket_name)
                logger.info("[S3StorageService] Uploaded %s to S3 (%s)", safe_filename, file_url)
                return file_url, s3_key
            except Exception as e:
                logger.error("[S3StorageService] S3 upload failed: %s. Falling back to local storage.", e)

        # Fallback to local storage
        local_dir = os.path.join("uploads", "workspaces", str(workspace_id), "attachments")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{unique_id}_{safe_filename}")

        with open(local_path, "wb") as f:
            f.write(file_bytes)

        file_url = f"/uploads/workspaces/{workspace_id}/attachments/{unique_id}_{safe_filename}"
        logger.info("[S3StorageService] Saved %s locally (%s)", safe_filename, local_path)
        return file_url, local_path

    def upload_base64(
        self,
        base64_data: str,
        filename: str,
        workspace_id: str | int,
        content_type: str = "application/octet-stream"
    ) -> Tuple[str, str]:
        """Decodes base64 string and uploads to S3 or local storage."""
        if "," in base64_data:
            header, base64_str = base64_data.split(",", 1)
            if "image/png" in header:
                content_type = "image/png"
            elif "image/jpeg" in header or "image/jpg" in header:
                content_type = "image/jpeg"
            elif "application/pdf" in header:
                content_type = "application/pdf"
        else:
            base64_str = base64_data

        try:
            file_bytes = base64.b64decode(base64_str)
        except Exception as e:
            logger.error("[S3StorageService] Failed to decode base64 string: %s", e)
            file_bytes = b""

        return self.upload_file_bytes(file_bytes, filename, workspace_id, content_type)

    # ── Workspace Asset Uploads (axiora-assets, private) ─────────────────────

    def upload_workspace_asset(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: int | str,
        workspace_id: int | str,
        file_type: str,
        content_type: str = "application/octet-stream",
    ) -> Tuple[str, str]:
        """
        Upload a workspace file to the axiora-assets bucket under a structured path:
          Assets/users/{user_id}/workspaces/{workspace_id}/{type_folder}/{uuid}_{filename}

        file_type should be one of: 'image', 'pdf', 'doc'

        Returns Tuple[presigned_file_url, s3_key].
        Falls back to local storage if AWS credentials are not configured.
        """
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "file.dat"
        type_folder = {"image": "images", "pdf": "pdfs", "doc": "docs"}.get(file_type, "files")
        s3_key = f"Assets/users/{user_id}/workspaces/{workspace_id}/{type_folder}/{unique_id}_{safe_filename}"

        if self._s3_client:
            try:
                # Private object upload (no public-read ACL)
                self._s3_client.put_object(
                    Bucket=self.assets_bucket_name,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                file_url = self.generate_presigned_url(s3_key)
                logger.info(
                    "[S3StorageService] Uploaded workspace asset %s → %s",
                    safe_filename, file_url
                )
                return file_url, s3_key
            except Exception as e:
                logger.error(
                    "[S3StorageService] Assets bucket upload failed for %s: %s. Falling back to local.",
                    safe_filename, e
                )

        # Local fallback
        local_dir = os.path.join(
            "uploads", "assets", "users", str(user_id),
            "workspaces", str(workspace_id), type_folder
        )
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{unique_id}_{safe_filename}")

        with open(local_path, "wb") as f:
            f.write(file_bytes)

        file_url = (
            f"/uploads/assets/users/{user_id}/workspaces/{workspace_id}"
            f"/{type_folder}/{unique_id}_{safe_filename}"
        )
        logger.info("[S3StorageService] Saved workspace asset locally (%s)", local_path)
        return file_url, s3_key

    def get_public_url(self, s3_key: str, bucket_name: str | None = None) -> str:
        """
        Constructs a direct, public S3 HTTPS URL for an object key.
        Example: https://axiora-assets.s3.ap-south-1.amazonaws.com/avatars/1/8a2f1b9c_avatar.png
        """
        if not s3_key:
            return ""
        if s3_key.startswith("http://") or s3_key.startswith("https://"):
            return s3_key

        target_bucket = bucket_name or self.assets_bucket_name
        clean_key = s3_key.lstrip("/")
        if clean_key.startswith("uploads/"):
            clean_key = clean_key[len("uploads/"):]

        return f"https://{target_bucket}.s3.{self.assets_region}.amazonaws.com/{clean_key}"

    def get_proxy_avatar_url(self, user_id: int | str, s3_key_or_url: str | None = None) -> str:
        """
        Constructs a fully-qualified public HTTP/HTTPS proxy URL for an avatar image.
        Example: https://qa.axiorapulse.com/api/users/4/avatar
        """
        if not s3_key_or_url:
            return ""

        base_url = (
            os.getenv("PUBLIC_APP_URL")
            or os.getenv("BASE_URL")
            or os.getenv("BACKEND_URL")
            or os.getenv("SERVER_HOST", "http://localhost:8000")
        )
        base_url = base_url.strip().rstrip("/")
        return f"{base_url}/api/users/{user_id}/avatar"

    def upload_avatar(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: int | str,
        content_type: str = "image/png",
    ) -> Tuple[str, str]:
        """
        Upload a user profile avatar to the assets bucket under:
          avatars/{user_id}/{uuid}_{filename}

        Returns Tuple[public_s3_url, s3_key].
        Falls back to local storage if AWS credentials are not configured.
        """
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "avatar.png"
        s3_key = f"avatars/{user_id}/{unique_id}_{safe_filename}"

        if self._s3_client:
            try:
                put_kwargs = {
                    "Bucket": self.assets_bucket_name,
                    "Key": s3_key,
                    "Body": file_bytes,
                    "ContentType": content_type,
                    "ACL": "public-read",
                }
                try:
                    self._s3_client.put_object(**put_kwargs)
                except Exception as acl_err:
                    err_str = str(acl_err)
                    if "AccessControlListNotSupported" in err_str or "InvalidBucketAclWithObjectOwnership" in err_str:
                        put_kwargs.pop("ACL")
                        self._s3_client.put_object(**put_kwargs)
                    else:
                        raise acl_err

                file_url = self.get_public_url(s3_key)
                logger.info(
                    "[S3StorageService] Uploaded user avatar %s → %s",
                    safe_filename, file_url
                )
                return file_url, s3_key
            except Exception as e:
                logger.error(
                    "[S3StorageService] S3 avatar upload failed for %s: %s. Falling back to local.",
                    safe_filename, e
                )

        # Local fallback
        local_dir = os.path.join("uploads", "avatars", str(user_id))
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{unique_id}_{safe_filename}")

        with open(local_path, "wb") as f:
            f.write(file_bytes)

        file_url = self.get_public_url(s3_key)
        logger.info("[S3StorageService] Saved avatar locally (%s)", local_path)
        return file_url, s3_key

    def get_avatar_bytes(self, s3_key_or_url: str) -> Tuple[bytes | None, str]:
        """
        Retrieves avatar image bytes and content-type from S3 or local disk.
        """
        if not s3_key_or_url:
            return None, "image/png"

        clean_key = s3_key_or_url
        if "amazonaws.com/" in s3_key_or_url:
            clean_key = s3_key_or_url.split("amazonaws.com/")[-1]
        elif clean_key.startswith("/uploads/"):
            clean_key = clean_key[len("/uploads/"):]
        elif clean_key.startswith("uploads/"):
            clean_key = clean_key[len("uploads/"):]

        content_type = "image/png"
        if clean_key.endswith(".jpg") or clean_key.endswith(".jpeg"):
            content_type = "image/jpeg"

        if self._s3_client:
            try:
                res = self._s3_client.get_object(Bucket=self.assets_bucket_name, Key=clean_key)
                body = res["Body"].read()
                c_type = res.get("ContentType", content_type)
                return body, c_type
            except Exception as e:
                logger.error("[S3StorageService] Failed to fetch avatar from S3 (%s): %s", clean_key, e)

        # Local fallback read
        local_path = os.path.join("uploads", *clean_key.split("/"))
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return f.read(), content_type

        return None, content_type

    def delete_workspace_asset(self, s3_key: str) -> bool:
        """
        Delete a workspace asset from the axiora-assets bucket by its S3 key.
        Returns True on success, False on failure or if running locally.
        """
        if not self._s3_client:
            logger.info("[S3StorageService] No S3 client — skipping remote delete for key: %s", s3_key)
            # normalize the leading segment so this matches on case-sensitive filesystems too.
            key_parts = s3_key.split("/")
            if key_parts and key_parts[0] == "Assets":
                key_parts[0] = "assets"
            # Support avatars delete fallback as well if key starts with avatars
            if key_parts and key_parts[0] == "avatars":
                pass
            local_path = os.path.join("uploads", *key_parts)
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                    logger.info("[S3StorageService] Deleted local file: %s", local_path)
            except Exception as e:
                logger.warning("[S3StorageService] Could not delete local file %s: %s", local_path, e)
            return False

        try:
            self._s3_client.delete_object(Bucket=self.assets_bucket_name, Key=s3_key)
            logger.info("[S3StorageService] Deleted S3 asset: %s", s3_key)
            return True
        except Exception as e:
            logger.error("[S3StorageService] Failed to delete S3 asset %s: %s", s3_key, e)
            return False


s3_storage_service = S3StorageService()
