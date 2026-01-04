"""Lark API client for fetching data from Lark Base."""

import json
import os
import time
from typing import Any
from urllib.parse import urlparse

import requests

from config import Config


class LarkClient:
    """Client for interacting with Lark Base API."""

    BASE_URL = "https://open.larksuite.com/open-apis"

    def __init__(self):
        self.app_id = Config.LARK_APP_ID
        self.app_secret = Config.LARK_APP_SECRET
        self.base_app_token = Config.LARK_BASE_APP_TOKEN
        self.table_id = Config.LARK_TABLE_ID
        self._access_token = None
        self._token_expires_at = 0

    def _get_access_token(self) -> str:
        """Get or refresh the tenant access token."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise Exception(f"Failed to get access token: {data.get('msg')}")

        self._access_token = data.get("tenant_access_token")
        # Token expires in 2 hours, refresh 5 minutes early
        self._token_expires_at = time.time() + data.get("expire", 7200) - 300

        return self._access_token

    def _get_headers(self) -> dict:
        """Get request headers with authorization."""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def get_records(
        self,
        filter_factory_status: str = "Processing",
        page_size: int = 100,
        page_token: str | None = None
    ) -> dict[str, Any]:
        """
        Fetch records from Lark Base with optional filtering.

        Args:
            filter_factory_status: Filter by Factory Status field value
            page_size: Number of records per page (max 500)
            page_token: Token for pagination

        Returns:
            Dictionary containing records and pagination info
        """
        url = f"{self.BASE_URL}/bitable/v1/apps/{self.base_app_token}/tables/{self.table_id}/records/search"

        # Build filter for Factory Status = "Processing"
        payload = {
            "page_size": min(page_size, 500),
        }

        if filter_factory_status:
            payload["filter"] = {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": Config.FACTORY_STATUS_FIELD,
                        "operator": "is",
                        "value": [filter_factory_status]
                    }
                ]
            }

        if page_token:
            payload["page_token"] = page_token

        response = requests.post(
            url,
            headers=self._get_headers(),
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            raise Exception(f"Failed to fetch records: {data.get('msg')}")

        return data.get("data", {})

    def get_all_processing_records(self) -> list[dict]:
        """
        Fetch all records with Factory Status = Processing.
        Handles pagination automatically.

        Returns:
            List of all matching records
        """
        all_records = []
        page_token = None

        while True:
            result = self.get_records(
                filter_factory_status="Processing",
                page_token=page_token
            )

            items = result.get("items", [])
            all_records.extend(items)

            if not result.get("has_more", False):
                break

            page_token = result.get("page_token")

        return all_records

    def get_orders_with_processing_records(self) -> dict[str, list[dict]]:
        """
        Get all orders that have at least one processing record.
        Groups records by Order ID.

        Returns:
            Dictionary mapping Order ID to list of records
        """
        records = self.get_all_processing_records()
        orders = {}

        for record in records:
            fields = record.get("fields", {})
            order_id = fields.get(Config.ORDER_ID_FIELD)

            if order_id:
                # Handle if order_id is a list or single value
                if isinstance(order_id, list):
                    order_id = order_id[0] if order_id else "Unknown"
                elif isinstance(order_id, dict):
                    order_id = order_id.get("text", str(order_id))

                order_id = str(order_id)

                if order_id not in orders:
                    orders[order_id] = []
                orders[order_id].append(record)
            else:
                # Records without order ID go to "Unassigned"
                if "Unassigned" not in orders:
                    orders["Unassigned"] = []
                orders["Unassigned"].append(record)

        return orders

    def get_attachment_url(self, file_token: str) -> str:
        """
        Get download URL for an attachment.

        Args:
            file_token: The file token from the attachment field

        Returns:
            Download URL for the file
        """
        url = f"{self.BASE_URL}/drive/v1/medias/{file_token}/download"

        response = requests.get(
            url,
            headers=self._get_headers(),
            allow_redirects=False,
            timeout=30
        )

        if response.status_code == 302:
            return response.headers.get("Location", "")

        response.raise_for_status()
        return ""

    def download_attachment(
        self,
        file_token: str,
        filename: str,
        save_dir: str | None = None
    ) -> str:
        """
        Download an attachment from Lark.

        Args:
            file_token: The file token from the attachment field
            filename: Original filename
            save_dir: Directory to save the file (default: Config.ATTACHMENTS_DIR)

        Returns:
            Path to the downloaded file
        """
        save_dir = save_dir or Config.ATTACHMENTS_DIR
        os.makedirs(save_dir, exist_ok=True)

        # Get download URL
        url = f"{self.BASE_URL}/drive/v1/medias/{file_token}/download"

        response = requests.get(
            url,
            headers=self._get_headers(),
            stream=True,
            timeout=120
        )
        response.raise_for_status()

        # Sanitize filename
        safe_filename = "".join(
            c for c in filename if c.isalnum() or c in "._- "
        ).strip()
        if not safe_filename:
            safe_filename = file_token

        filepath = os.path.join(save_dir, safe_filename)

        # Handle duplicate filenames
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return filepath

    def extract_attachments_from_records(
        self,
        records: list[dict]
    ) -> list[dict[str, Any]]:
        """
        Extract all attachment information from records.

        Args:
            records: List of records from Lark Base

        Returns:
            List of attachment info dictionaries
        """
        attachments = []

        for record in records:
            record_id = record.get("record_id", "")
            fields = record.get("fields", {})

            for field_name, field_value in fields.items():
                # Check if field contains attachments
                if isinstance(field_value, list):
                    for item in field_value:
                        if isinstance(item, dict) and "file_token" in item:
                            attachments.append({
                                "record_id": record_id,
                                "field_name": field_name,
                                "file_token": item.get("file_token"),
                                "name": item.get("name", "unknown"),
                                "size": item.get("size", 0),
                                "type": item.get("type", ""),
                                "url": item.get("url", "")
                            })

        return attachments

    def batch_download_attachments(
        self,
        attachments: list[dict],
        save_dir: str | None = None,
        progress_callback=None
    ) -> list[dict]:
        """
        Download multiple attachments.

        Args:
            attachments: List of attachment info from extract_attachments_from_records
            save_dir: Directory to save files
            progress_callback: Optional callback(current, total, filename)

        Returns:
            List of download results with status
        """
        results = []
        total = len(attachments)

        for i, attachment in enumerate(attachments):
            file_token = attachment.get("file_token")
            filename = attachment.get("name", file_token)

            if progress_callback:
                progress_callback(i + 1, total, filename)

            try:
                filepath = self.download_attachment(file_token, filename, save_dir)
                results.append({
                    **attachment,
                    "status": "success",
                    "local_path": filepath,
                    "error": None
                })
            except Exception as e:
                results.append({
                    **attachment,
                    "status": "error",
                    "local_path": None,
                    "error": str(e)
                })

        return results


def save_records_to_json(records: list[dict], filename: str = "records.json") -> str:
    """
    Save records to a JSON file.

    Args:
        records: List of records to save
        filename: Output filename

    Returns:
        Path to the saved file
    """
    Config.ensure_directories()
    filepath = os.path.join(Config.DATA_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return filepath


def save_orders_to_json(
    orders: dict[str, list[dict]],
    filename: str = "orders.json"
) -> str:
    """
    Save orders grouped data to a JSON file.

    Args:
        orders: Dictionary of Order ID to records
        filename: Output filename

    Returns:
        Path to the saved file
    """
    Config.ensure_directories()
    filepath = os.path.join(Config.DATA_DIR, filename)

    # Create summary with order info
    output = {
        "total_orders": len(orders),
        "total_records": sum(len(records) for records in orders.values()),
        "orders": orders
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return filepath
