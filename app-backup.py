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
import os, re, io
import shutil
from urllib.parse import urlparse, parse_qs
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # file chứa thông tin xác thực
ROLE_USER = 'SHIPPER'  # Vai trò người dùng trong Lark Base [WORKER, SHIPPER, ADMIN]

app = Flask(__name__, static_folder='templates/static')
CORS(app) 

DOWNLOAD_DIR = "downloaded_files"
#os.makedirs(DOWNLOAD_DIR, exist_ok=True)

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Tạo thư mục lưu QR
#os.makedirs("qr_codes", exist_ok=True)

# Thông tin app từ Lark Developer Console
APP_ID = "cli_a43d7cf7e478900a"
APP_SECRET = "t1RUv1nEWQY83zbVj3TUShLALphOIB7x"
BASE_ID = "AAL2bJHG7anPynsmOKJlJPNmgze"
TABLE_ID = "tbldUgUoSqPBy77B"
#user_token = 'u-d74Xx0BFJagUYqDDpWWzEG10n0HX40WrViGaqQS00ykS'  # Thay bằng token thực tế của bạn

# Route giao diện
@app.route("/")
def index():
    return send_from_directory(os.getcwd(), "index.html")

# Route lấy dữ liệu từ Lark Base
@app.route("/api/larkbase")
def fetch_lark_data():
    token = get_access_token(APP_ID, APP_SECRET)
    data = get_table_data(BASE_ID, TABLE_ID, token)
    return data

# Route cho trang orders
@app.route("/orders")
def orders_page():
    return send_from_directory('templates', 'orders.html')

# API endpoint lấy danh sách orders
@app.route("/api/orders")
def get_orders():
    token = get_access_token(APP_ID, APP_SECRET)
    data = get_table_data(BASE_ID, TABLE_ID, token)
    return data

# Hàm lấy access token
def get_access_token(app_id, app_secret):
    url = "https://open.larksuite.com/open-apis/auth/v3/app_access_token/internal"
    payload = { "app_id": app_id, "app_secret": app_secret }
    res = requests.post(url, json=payload)
    return res.json().get("app_access_token")

# Hàm lấy dữ liệu bảng
def get_table_data(base_id, table_id, token):
    # init client
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # send request
    request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
        .app_token(BASE_ID) \
        .table_id(TABLE_ID) \
        .user_id_type("user_id") \
        .page_size(20) \
        .request_body(SearchAppTableRecordRequestBody.builder()
            .filter(FilterInfo.builder()
                .conjunction("and")
                .conditions([
                    Condition.builder()
                    .field_name("Factory Status")
                    .operator("is")
                    .value(["Processing"])
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
    return lark.JSON.marshal(response.data, indent=4)
def getOrderID(order_id, record_id=None):
    # init client
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # send request
    if record_id:
        request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
        .app_token(BASE_ID) \
        .table_id(TABLE_ID) \
        .user_id_type("user_id") \
        .page_size(2) \
        .request_body(SearchAppTableRecordRequestBody.builder()
            .filter(FilterInfo.builder()
                .conjunction("and")
                .conditions([
                    Condition.builder()
                    .field_name("Record ID")
                    .operator("is")
                    .value([record_id])
                    .build()
                    ])
                .build())
            .build()) \
        .build()
    else:
        request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .user_id_type("user_id") \
            .page_size(20) \
            .request_body(SearchAppTableRecordRequestBody.builder()
                .filter(FilterInfo.builder()
                    .conjunction("and")
                    .conditions([
                        Condition.builder()
                        .field_name("Order ID")
                        .operator("contains")
                        .value([order_id])
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
    orderData = extract_orders_from_json(lark.JSON.marshal(response.data, indent=4))
    return orderData
# Kích thước trang PDF: 70mm x 25mm
PAGE_WIDTH, PAGE_HEIGHT = 70 * mm, 22 * mm
COLS = 2
CELL_WIDTH = PAGE_WIDTH / COLS
CELL_HEIGHT = PAGE_HEIGHT
# Route xử lý đơn hàng
@app.route("/api/process-orders", methods=['POST'])
def process_orders():
    #from flask import request
    # Tạo thư mục lưu QR
    #os.makedirs("qr_codes", exist_ok=True)
    data = fetch_lark_data()
    orders = extract_orders_from_json(data)
    create_qr_labels(orders)
    return jsonify({"status": "success", "message": "QR labels created."})
# Parse JSON data
def extract_orders_from_json(json_data):
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data
    print("data: ", data)   
    orders = []
    for item in data.get('items', []):
        order = {
            "order_id": item['fields'].get('Order ID', [{}])[0].get('text', ''),
            "record_id": item.get('record_id', ''),
            "status": item['fields'].get('Factory Status'),
            "style": item['fields'].get('Style'),
            "size": item['fields'].get('Size'),
            "color": item['fields'].get('Color'),
            "qty": item['fields'].get('Quantity*'),
            "custom": item['fields'].get('Personalization', [{}])[0].get('text', ''),
            "label": item['fields'].get('Label URL', [{}])[0].get('text', ''),
            #"design_link": item['fields'].get('Link Design').get('link', ''),
            "batch_name": item['fields'].get('BatchName', [{}])[0].get('text', ''),
            "shop_name": item['fields'].get('ShopName', [{}])[0].get('text', '')
        }
        if("Color Index" in item["fields"]): 
            order["color_index"] = item["fields"]["Color Index"][0]["file_token"]
        if(order["shop_name"].find("PGS") != -1): 
            order["design_link"] =  {
                'artwork': item['fields'].get('Artwork', [{}]),
                'order_id': order['order_id']
            }
            order["color_index"] =  item["fields"]["Mockup"][0]["file_token"]
            order["order_id"] = order["order_id"].replace("#", "")
        if item['fields'].get('Link Design') is not None:
           order["design_link"] = item['fields'].get('Link Design').get('link', '')
            #order["shop_name"] = item["fields"]["ShopName"]
        orders.append(order)
    return orders


def create_qr_labels(orders):
    # Tạo file PDF
    #print("[create_qr_labels] orders: ", orders)   
    qrlabelname = "qr_labels_70x25mm.pdf"
    c = canvas.Canvas(qrlabelname, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    col = 0
    urls = []
    pgs_design_links = []
    batchfilename = "batch1"
    i=0
    for idx, order in enumerate(orders):
        # Tạo QR code content với API endpoint
        api_url = f"http://localhost:5000/api/update-status/{order['record_id']}?order_id={order['order_id']}"
        print("✅[create_qr_labels] api_url:", api_url)
        qr_content = api_url  # QR code sẽ chứa URL để update status
        #designlink = read_url_list(order['design_link'])
        if order['shop_name'].find("PGS") != -1:
            pgs_design_links.append(order['design_link'])
        else:
            urls.append(order['design_link'])
        i += 1
        if batchfilename == "batch1" and order['batch_name'] != "":
            batchfilename = order['batch_name']
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            box_size=3,  # Reduced size
            border=1
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Vị trí cho cột hiện tại
        x = col * CELL_WIDTH
        y = 0

        # Kích thước QR code: 20mm x 20mm
        QR_WIDTH_MM = 18
        QR_HEIGHT_MM = 18
        QR_WIDTH_PT = QR_WIDTH_MM * mm
        QR_HEIGHT_PT = QR_HEIGHT_MM * mm

        # Lưu ảnh tạm
        temp_img = f"temp_{idx}.png"
        qr_img.save(temp_img)

        # Tính vị trí ảnh QR trong ô
        img_x = x + (CELL_WIDTH - QR_WIDTH_PT) / 2
        img_y = y + (CELL_HEIGHT - QR_HEIGHT_PT) / 2+2

        # Chèn ảnh QR
        c.drawImage(temp_img, img_x, img_y, width=QR_WIDTH_PT, height=QR_HEIGHT_PT)

        # Chèn Order ID bên dưới
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + CELL_WIDTH / 2, y + 2, order['order_id']+'_'+order['batch_name']+"_"+str(i))
        #c.drawCentredString(img_x +QR_WIDTH_PT/2 + 2, img_y, order['batch_name'])
        # Xóa ảnh tạm
        os.remove(temp_img)

        # Cập nhật vị trí tiếp theo
        col += 1
        if col >= COLS:
            c.showPage()
            col = 0    

    # Lưu PDF
    os.makedirs(batchfilename, exist_ok=True)
    c.save()
    #print("✅ Đã tạo file qr_labels_70x25mm.pdf thành công. batch name:", batchfilename)
    downloadFiles(urls, batchfilename)
    downloadpgsFiles(pgs_design_links, batchfilename)
    # Tạo đường dẫn đích
    target_file = os.path.join(batchfilename, os.path.basename(qrlabelname))

    # Sao chép file
    shutil.copy(qrlabelname, target_file)
    
status_flow = ["New", "Processing", "In-Production", "Done", "Shipped"]
def get_next_status(current_status):
    try:
        current_index = status_flow.index(current_status)
        next_index = (current_index + 1) % len(status_flow)
        return status_flow[next_index]
    except ValueError:
        return "New"  # Mặc định nếu status không hợp lệ
# Route cập nhật status từ QR code scan
@app.route("/api/update-status/<record_id>", methods=['GET', 'POST'])
def update_status_from_qr(record_id, status ="Done"):
    try:
        order_id = request.args.get('order_id', '')
        recordData = getOrderID(order_id, record_id)
        print("[update_status_from_qr] recordData: ", recordData) 
        if( recordData[0]["color_index"] != None):
            preview_url = get_lark_file_preview_url(recordData[0]["color_index"])
        else:
            preview_url = get_drive_preview_url(recordData[0]['design_link'])
        print("[update_status_from_qr] preview_url: ", preview_url) 
        label_pdf = recordData[0]['label']
        current_status = recordData[0]['status']
        if ROLE_USER == 'WORKER':
            status = "In-Production"
        else:
            if request.args.get("status") is not None:
                status = request.args.get("status")
            if ROLE_USER == 'ADMIN':
                status = None
        print("✅[Debug] update_status_from_qr :", record_id, status, order_id, current_status)
        if get_next_status(current_status) == status or status == "New":
            update_record_status(record_id, status)
        # Thành công: trả HTML cho GET (auto POST), JSON cho POST
        if ROLE_USER != 'WORKER':
            recordData = getOrderID(order_id, None)
            for record in recordData:
                if record['status'] == "New" or record['status'] == "Processing" or record['status'] == "In-Production": 
                    label_pdf = None
        #print("✅[Debug] recordData[0]['design_link']:", recordData[0])
        #print("✅[Debug] Preview URL: ", preview_url)
        if request.method == 'GET':
            print("✅[Debug] get Order.html : ", order_id, recordData, record_id, label_pdf, preview_url, ROLE_USER)
            return render_template("orders.html", order_id=order_id, records=recordData, active_record_id=record_id, label_pdf=label_pdf, design_link=preview_url, roles =ROLE_USER)
        # POST -> JSON success
        return jsonify({"status": "success", "message": f"Order data: {recordData}"})
        #return jsonify(recordData)
        #return render_template("orders.html", order_id=order_id, records=recordData, active_record_id=record_id, label_pdf=label_pdf, design_link=preview_url)

    except Exception as e:
        lark.logger.error(f"Exception updating record {record_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
def get_lark_file_preview_url(file_token):
    #record_id = request.args.get("record_id")
    url = "https://open.larksuite.com/open-apis/drive/v1/medias/batch_get_tmp_download_url?file_tokens="+file_token
    user_token = get_access_token(APP_ID, APP_SECRET)
    if not user_token:
        return jsonify({'success': False, 'error': 'Missing USER_ACCESS_TOKEN env var'}), 500
    # Khởi tạo client (enable_set_token để dùng user token)
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()
    try:
        request: BatchGetTmpDownloadUrlMediaRequest = BatchGetTmpDownloadUrlMediaRequest.builder() \
        .file_tokens(file_token) \
        .build()
        option = lark.RequestOption.builder().user_access_token(user_token).build()
        response: BatchGetTmpDownloadUrlMediaResponse = client.drive.v1.media.batch_get_tmp_download_url(request, option)
        if not response.success():
            lark.logger.error(
                f"client.drive.v1.media.batch_get_tmp_download_url failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
            return
        file_data = json.loads(lark.JSON.marshal(response.data, indent=4))
        print("✅[Debug] file_data:", file_data['tmp_download_urls'])
        tmp_download_url = file_data['tmp_download_urls'][0]['tmp_download_url']
        folder = "templates/static/tmp"
        os.makedirs(folder, exist_ok=True)
        #file_name = file_token# + ".png"
        filepath = os.path.join(folder, file_token)
        if os.path.exists(f"static/tmp/{file_token}"):
            print("✅ File already exists locally:", file_token)
            return file_token
        dataResponse = requests.get(tmp_download_url)
        print("✅[Debug] dataResponse:", dataResponse)
        if dataResponse.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(dataResponse.content)
            print("✅[Debug] filepath:", filepath)
            return file_token
        else:
            print("❌ Lỗi tải ảnh:", dataResponse.status_code)
            return None
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def list_png_files(folder_id):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    query = f"'{folder_id}' in parents and mimeType='image/png'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    #print("✅[Debug] files:", files)
    return files

def extract_folder_id(url):
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else None

@app.route("/api/update-order-status", methods=["POST"])
def update_order_status():
    data = request.json
    order_id = data.get("order_id")
    print("✅[Debug] update_order_status:", order_id)
    records = getOrderID(order_id)
    if not records:
        return jsonify({"status": "error", "message": "Order not found."}), 404 
    for record in records:
        try:
            record_id = record["record_id"]
            update_record_status(record_id, "Shipped")
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "success", "message": f"Order {order_id} status updated to Shipped."})

def update_record_status(record_id, status):
    try:
        # user access token must be provided via env var for security
        user_token = get_access_token(APP_ID, APP_SECRET)
        if not user_token:
            return jsonify({'success': False, 'error': 'Missing USER_ACCESS_TOKEN env var'}), 500
        # Khởi tạo client (enable_set_token để dùng user token)
        client = lark.Client.builder() \
            .enable_set_token(True) \
            .log_level(lark.LogLevel.DEBUG) \
            .build()

        # Chuẩn bị request update
        request_obj: UpdateAppTableRecordRequest = UpdateAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .record_id(record_id) \
            .user_id_type("user_id") \
            .ignore_consistency_check(True) \
            .request_body(AppTableRecord.builder()
                .fields({"Factory Status": status})
                .build()) \
            .build()

        option = lark.RequestOption.builder().user_access_token(user_token).build()
        response: UpdateAppTableRecordResponse = client.bitable.v1.app_table_record.update(request_obj, option)

        if not response.success():
            # try to extract API detail
            detail = None
            try:
                detail = json.loads(response.raw.content)
            except Exception:
                detail = response.raw.content.decode() if hasattr(response.raw, "content") else str(response.raw)
            lark.logger.error(f"Update failed: code={response.code} msg={response.msg} detail={detail}")
            return jsonify({'success': False, 'msg': response.msg, 'detail': detail}), 400
    except Exception as e:
        lark.logger.error(f"Exception updating record {record_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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

def read_url_list(file_path):
    with open(file_path, "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def list_files_in_folder(folder_id):
    page_token = None
    files = []
    while True:
        response = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return files

def download_file(file_id, file_name, pathname):
    request = drive_service.files().get_media(fileId=file_id)
    file_path = os.path.join(pathname, file_name)

    with io.FileIO(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Downloading {file_name}: {int(status.progress()*100)}%")
    return file_path

def downloadFiles(urls, filename):
    i=0
    print(f"✅ downloadFiles urls:", urls)
    for url in urls:
        i += 1
        folder_id = extract_folder_id(url)
        if not folder_id:
            print(f"❌ Invalid folder link: {url}")
            continue

        print(f"\n📂 Folder: {url}")
        files = list_files_in_folder(folder_id)

        if not files:
            print("⚠️ No files found OR no permission")
            continue

        print(f"✅ Found {len(files)} files")
        for file in files:
            print(f"⬇️ {file['name']}")
            if(file['name'].lower().endswith(".dst")):
                clsfilename = clean_filename(file["name"])
                download_file(file["id"], filename+"_"+str(i)+"_"+clsfilename, filename)
            if file['name'].lower().endswith('.png') or file['name'].lower().endswith('.jpg') or file['name'].lower().endswith('.jpeg'):
                #file_id = file['id']    
                #ext = Path(file['name']).suffix
                #file_name = clean_filename(file['name'])#"preview_image" + ext
                download_png(file["id"])

def downloadpgsFiles(urls, filepath):
    #path = filepath
    for url in urls:
        #print(f"✅ [downloadpgsFiles] url:", url)
        order_id = url['order_id'].replace("#", "")
        orderpath = os.path.join(filepath, order_id)
        #print(f"✅ [downloadpgsFiles] orderpath:", orderpath)
        os.makedirs(orderpath, exist_ok=True)
        i=0
        print(f"✅ [downloadpgsFiles] url['artwork']:", url['artwork'])
        if(len(url['artwork']) == 1):
            fulprint = url['artwork'][0]['text'].split("\n")
            print(f"✅ [downloadpgsFiles] fulprint:", fulprint) 
            artwords = []
            for art in fulprint:
                artwords.append({'type':'url', 'link': art.split(": ")[1]})
        else:
            artwords = url['artwork']
        print(f"✅ [downloadpgsFiles] artwords:", artwords)
        for artwork in artwords:
            i += 1
            #print(f"✅ [downloadpgsFiles] artwork:", artwork)
            if artwork['type'] == 'url':
                link = artwork['link']
                # Lấy tên file từ link
                filename = os.path.basename(link)
                # Ghép đường dẫn đầy đủ
                artworkpath = os.path.join(orderpath, filename)
                response = requests.get(link)
                if response.status_code == 200:
                    with open(artworkpath, "wb") as f:
                        f.write(response.content)
                else:
                    print("❌ Lỗi tải ảnh:", response.status_code)
                    return None
            


def clean_filename(filename):
    # Tách phần tên và phần đuôi
    name, ext = os.path.splitext(filename)
    # Giữ lại chữ cái, số, dấu gạch dưới, dấu cách và dấu gạch ngang
    name = name.replace(" ", "_")
    clean_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', name)
    # Ghép lại với phần đuôi
    return f"{clean_name}{ext}"


def get_drive_preview_url(folder_url):
    folder_id = extract_folder_id(folder_url)
    files = list_files_in_folder(folder_id)
    if not files:
        return None
    for file in files:
        if file['name'].lower().endswith('.png') or file['name'].lower().endswith('.jpg') or file['name'].lower().endswith('.jpeg'):
            download_png(file["id"])
            return file["id"]
    return None

def make_file_public(file_id):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    access_token = creds.token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "role": "reader",
        "type": "anyone"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.status_code == 200 or response.status_code == 204

def download_png(file_id):
    print("✅ [download_png] file_id:", file_id)
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    folder = "templates/static/tmp"
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, file_id)
    if os.path.exists(f"static/tmp/{file_id}"):
        print("✅ File already exists locally:", file_id)
        return filepath
    response = requests.get(url)
    if response.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(response.content)
        return filepath
    else:
        print("❌ Lỗi tải ảnh:", response.status_code)
        return None

@app.route("/proxy-pdf")
def proxy_pdf():
    pdf_url = request.args.get("url")

    if not pdf_url:
        return {"error": "Missing pdf url"}, 400

    # Tải PDF từ CloudFront
    r = requests.get(pdf_url, stream=True)

    if r.status_code != 200:
        return {"error": "PDF not found"}, 404

    # Trả PDF với CORS đầy đủ
    response = Response(
        r.content,
        mimetype="application/pdf"
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"

    return response

@app.route("/buy-label", methods=["GET"])
def buy_label():
    record_id = request.args.get("record_id")
    url = "https://open-sg.larksuite.com/anycross/trigger/callback/ZTQ0MjA4ZWMxOTFhODhlMzgzM2QxZmI2MzhlOTdiZDYw"
    params = {"record_id": record_id}
    try:
        r = requests.get(url, params=params)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)


