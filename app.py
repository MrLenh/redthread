"""Flask web application for Lark Data Fetcher."""

import json
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file

from config import Config
from lark_client import (
    LarkClient,
    save_records_to_json,
    save_orders_to_json
)

app = Flask(__name__)

# Global storage for fetched data
cached_data = {
    "records": [],
    "orders": {},
    "attachments": [],
    "last_fetch": None
}


def get_lark_client() -> LarkClient:
    """Create and return a LarkClient instance."""
    try:
        Config.validate()
        return LarkClient()
    except ValueError as e:
        raise Exception(f"Configuration error: {e}")


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html", data=cached_data)


@app.route("/api/fetch", methods=["POST"])
def fetch_data():
    """Fetch data from Lark Base with Factory Status = Processing."""
    try:
        client = get_lark_client()

        # Fetch all processing records
        records = client.get_all_processing_records()

        # Group by orders
        orders = client.get_orders_with_processing_records()

        # Extract attachments
        attachments = client.extract_attachments_from_records(records)

        # Update cache
        cached_data["records"] = records
        cached_data["orders"] = orders
        cached_data["attachments"] = attachments
        cached_data["last_fetch"] = datetime.now().isoformat()

        # Save to JSON files
        Config.ensure_directories()
        records_path = save_records_to_json(records)
        orders_path = save_orders_to_json(orders)

        return jsonify({
            "success": True,
            "message": "Data fetched successfully",
            "stats": {
                "total_records": len(records),
                "total_orders": len(orders),
                "total_attachments": len(attachments),
                "last_fetch": cached_data["last_fetch"]
            },
            "files_saved": {
                "records": records_path,
                "orders": orders_path
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/data")
def get_data():
    """Get currently cached data."""
    return jsonify({
        "success": True,
        "data": {
            "records": cached_data["records"],
            "orders": cached_data["orders"],
            "attachments": cached_data["attachments"],
            "last_fetch": cached_data["last_fetch"]
        },
        "stats": {
            "total_records": len(cached_data["records"]),
            "total_orders": len(cached_data["orders"]),
            "total_attachments": len(cached_data["attachments"])
        }
    })


@app.route("/api/records")
def get_records():
    """Get all fetched records."""
    return jsonify({
        "success": True,
        "records": cached_data["records"],
        "count": len(cached_data["records"])
    })


@app.route("/api/orders")
def get_orders():
    """Get orders grouped data."""
    return jsonify({
        "success": True,
        "orders": cached_data["orders"],
        "count": len(cached_data["orders"])
    })


@app.route("/api/attachments")
def get_attachments():
    """Get list of all attachments."""
    return jsonify({
        "success": True,
        "attachments": cached_data["attachments"],
        "count": len(cached_data["attachments"])
    })


@app.route("/api/attachments/download", methods=["POST"])
def download_attachments():
    """
    Download selected attachments.
    Request body can contain:
    - all: true to download all
    - file_tokens: list of specific file tokens to download
    """
    try:
        client = get_lark_client()
        data = request.get_json() or {}

        if not cached_data["attachments"]:
            return jsonify({
                "success": False,
                "error": "No attachments available. Fetch data first."
            }), 400

        # Determine which attachments to download
        if data.get("all", False):
            to_download = cached_data["attachments"]
        elif data.get("file_tokens"):
            tokens = set(data["file_tokens"])
            to_download = [
                a for a in cached_data["attachments"]
                if a["file_token"] in tokens
            ]
        else:
            to_download = cached_data["attachments"]

        if not to_download:
            return jsonify({
                "success": False,
                "error": "No attachments selected for download."
            }), 400

        # Create timestamped download directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_dir = os.path.join(Config.ATTACHMENTS_DIR, f"batch_{timestamp}")

        # Download attachments
        results = client.batch_download_attachments(to_download, download_dir)

        # Count successes and failures
        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")

        return jsonify({
            "success": True,
            "message": f"Downloaded {success_count} files, {error_count} errors",
            "download_dir": download_dir,
            "results": results,
            "stats": {
                "total": len(results),
                "success": success_count,
                "errors": error_count
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/attachments/download/<file_token>", methods=["GET"])
def download_single_attachment(file_token):
    """Download a single attachment by file token."""
    try:
        client = get_lark_client()

        # Find attachment info
        attachment = next(
            (a for a in cached_data["attachments"] if a["file_token"] == file_token),
            None
        )

        if not attachment:
            return jsonify({
                "success": False,
                "error": "Attachment not found"
            }), 404

        filename = attachment.get("name", file_token)
        filepath = client.download_attachment(file_token, filename)

        return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/save", methods=["POST"])
def save_data():
    """Save current data to JSON files."""
    try:
        if not cached_data["records"]:
            return jsonify({
                "success": False,
                "error": "No data to save. Fetch data first."
            }), 400

        Config.ensure_directories()

        # Save records
        records_path = save_records_to_json(
            cached_data["records"],
            f"records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Save orders
        orders_path = save_orders_to_json(
            cached_data["orders"],
            f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Save attachments list
        attachments_path = os.path.join(
            Config.DATA_DIR,
            f"attachments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(attachments_path, "w", encoding="utf-8") as f:
            json.dump(cached_data["attachments"], f, ensure_ascii=False, indent=2)

        return jsonify({
            "success": True,
            "message": "Data saved successfully",
            "files": {
                "records": records_path,
                "orders": orders_path,
                "attachments": attachments_path
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/load", methods=["POST"])
def load_data():
    """Load data from saved JSON files."""
    try:
        data = request.get_json() or {}
        records_file = data.get("records_file", "records.json")
        orders_file = data.get("orders_file", "orders.json")

        Config.ensure_directories()

        records_path = os.path.join(Config.DATA_DIR, records_file)
        orders_path = os.path.join(Config.DATA_DIR, orders_file)

        if os.path.exists(records_path):
            with open(records_path, "r", encoding="utf-8") as f:
                cached_data["records"] = json.load(f)

        if os.path.exists(orders_path):
            with open(orders_path, "r", encoding="utf-8") as f:
                orders_data = json.load(f)
                cached_data["orders"] = orders_data.get("orders", orders_data)

        # Re-extract attachments from records
        if cached_data["records"]:
            client = get_lark_client()
            cached_data["attachments"] = client.extract_attachments_from_records(
                cached_data["records"]
            )

        cached_data["last_fetch"] = f"Loaded from file at {datetime.now().isoformat()}"

        return jsonify({
            "success": True,
            "message": "Data loaded successfully",
            "stats": {
                "total_records": len(cached_data["records"]),
                "total_orders": len(cached_data["orders"]),
                "total_attachments": len(cached_data["attachments"])
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/files")
def list_saved_files():
    """List all saved JSON files."""
    try:
        Config.ensure_directories()

        files = []
        for filename in os.listdir(Config.DATA_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(Config.DATA_DIR, filename)
                files.append({
                    "name": filename,
                    "size": os.path.getsize(filepath),
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).isoformat()
                })

        files.sort(key=lambda x: x["modified"], reverse=True)

        return jsonify({
            "success": True,
            "files": files
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    Config.ensure_directories()
    print(f"Starting Lark Data Fetcher on http://{Config.HOST}:{Config.PORT}")
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
