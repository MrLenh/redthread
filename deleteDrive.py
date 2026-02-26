from flask import Flask, jsonify, send_from_directory, request, render_template, Response
from flask_cors import CORS
import requests
import json

from lark_oapi.core.utils import *
import lark_oapi as lark  # Changed from 'import lark' to 'import lark_oapi as lark'
from lark_oapi.api.bitable.v1 import *
from lark_oapi.api.bitable.v1.model import *
from lark_oapi.api.drive.v1 import *

import qrcode
from reportlab.lib.pagesizes import mm
from reportlab.pdfgen import canvas
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
import tempfile
from googleapiclient.discovery import build
from google.oauth2 import service_account
from urllib.parse import urlparse, urlunparse
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
import os, re, io, sys
import shutil
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import time
import threading

# Hàm lấy dữ liệu bảng
def get_table_data(base_id, table_id, token):
    has_more = True
    page_token = ''
    all_data = []
    # init client
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()
    while has_more:
        # Delay 1 giây trước khi query tiếp
        time.sleep(1)
        # send request
        request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .user_id_type("user_id") \
            .page_token(page_token) \
            .page_size(100) \
            .request_body(SearchAppTableRecordRequestBody.builder()
                .field_names(["Design Link"])
                .filter(FilterInfo.builder()
                    .conjunction("and")
                    .conditions([
                        Condition.builder()
                        .field_name("Personalized")
                        .operator("isNotEmpty")
                        .value([])
                        .build(),
                        Condition.builder()
                        .field_name("Design Link")
                        .operator("isNotEmpty")
                        .value([])
                        .build(),
                        Condition.builder()
                        .field_name("Delete Status")
                        .operator("isEmpty")
                        .value([])
                        .build(),
                        Condition.builder()
                        .field_name("Working Status")
                        .operator("is")
                        .value(["archived"])
                        .build()
                        ])
                    .build())
                .build()) \
            .build()

        # request execution
        response: SearchAppTableRecordResponse = client.bitable.v1.app_table_record.search(request)

        # error handling
        if not response.success():
            lark.logger.error(
                f"client.bitable.v1.app_table_record.search failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
            return

        # print response data
        #lark.logger.info(lark.JSON.marshal(response.data, indent=4))
        # Lưu xuống file JSON local
        response_data = json.loads(lark.JSON.marshal(response.data, indent=4))
        #print("[get_table_data] response_data: ", response_data)   
        urlData = extract_drivelink_from_json(response_data)
        update_lark_record(BASE_ID, TABLE_ID, token, urlData)
        #all_data.extend(orderData)
        #if isinstance(response_data, str):
           #data = json.loads(response_data)
        #else:
            #data = response_data
        #sys.exit()   # Graceful exit 
        has_more = response_data['has_more']
        if has_more:
            page_token = response_data['page_token']
        #with open("order_data.json", "w", encoding="utf-8") as f:
            #json.dump(all_data, f, ensure_ascii=False, indent=4)
    return all_data
def update_lark_record(base_id, table_id, token, record):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_id}/tables/{table_id}/records/batch_update"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    payload = {"records": record}

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        print("Update thành công:", response.json())
    else:
        print("Error:", response.status_code, response.text)

    # print response data
    #lark.logger.info(lark.JSON.marshal(response.data, indent=4))
    
def extract_drivelink_from_json(json_data):
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data
    #print("[extract_orders_from_json] data: ", data)   
    urls = []
    for item in data.get('items', []):
        record_id = item.get('record_id', '')
        print("[extract_orders_from_json] record_id: ", record_id) 
        try:
            drive_link = item.get('fields', {}).get('Design Link', {}).get('link', '')
            folder_id = extract_folder_id(drive_link)
            drive_service.files().delete(fileId=folder_id, supportsAllDrives=True).execute()
        except Exception as e:
            print("[extract_orders_from_json] driveID: ", folder_id) 
        url = {
            'record_id': record_id,
            'fields': {
                'Delete Status': "YES"
            }
        }
        #if driveID:   
        urls.append(url)
    return urls


# Hàm lấy access token
def get_access_token(app_id, app_secret):
    url = "https://open.larksuite.com/open-apis/auth/v3/app_access_token/internal"
    payload = { "app_id": app_id, "app_secret": app_secret }
    res = requests.post(url, json=payload)
    return res.json().get("app_access_token")

def extract_folder_id(url):
    # Trường hợp 1: dạng /folders/<id>
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)

    # Trường hợp 2: dạng ?id=<id>
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    folder_id = query_params.get("id", [None])[0]
    return folder_id

# Thông tin app từ Lark Developer Console
APP_ID = "cli_a43d7cf7e478900a"
APP_SECRET = "t1RUv1nEWQY83zbVj3TUShLALphOIB7x"
BASE_ID = "TQ89bWqckadWnosNj3ilxhvOgAf"
TABLE_ID = "tblzFF3kz5s30HYx"
#GG define
#SERVICE_ACCOUNT_FILE = "credentials.json"
#SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

#creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(
    'credentials.json', scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

token = get_access_token(APP_ID, APP_SECRET)
data = get_table_data(BASE_ID, TABLE_ID, token)