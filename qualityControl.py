from flask import Flask, jsonify, send_from_directory, request, render_template, Response
from flask_cors import CORS
import requests
import json
from textwrap import wrap

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
import time

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # file chứa thông tin xác thực
ROLE_USER = 'SHIPPER'  # Vai trò người dùng trong Lark Base [WORKER, SHIPPER, ADMIN]
status_flow = ["New", "Processing", "In-Production", "Done", "Shipped"]
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
    return send_from_directory(os.getcwd(), "home.html")

# Route lấy dữ liệu từ Lark Base
@app.route("/api/larkbase")
def fetch_lark_data():
    token = get_access_token(APP_ID, APP_SECRET)
    data = get_table_data(BASE_ID, TABLE_ID, token)
    upsert_local_records(data, 'processing.json', True)
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
    print("✅[get_orders] data:", data)
    return data

# Hàm lấy access token
def get_access_token(app_id, app_secret):
    url = "https://open.larksuite.com/open-apis/auth/v3/app_access_token/internal"
    payload = { "app_id": app_id, "app_secret": app_secret }
    res = requests.post(url, json=payload)
    return res.json().get("app_access_token")

# Hàm lấy dữ liệu bảng
update_table_status = ["Processing"] #"Shipped"
def get_table_data(base_id, table_id, token):
    has_more = True
    page_token = ''
    all_data = []
    page = 1
    # init client
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()
    while has_more:
        # send request
        request: SearchAppTableRecordRequest = SearchAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .user_id_type("user_id") \
            .page_token(page_token) \
            .page_size(200) \
            .request_body(SearchAppTableRecordRequestBody.builder()
                .filter(FilterInfo.builder()
                    .conjunction("and")
                    .conditions([
                        Condition.builder()
                        .field_name("Factory Status")
                        .operator("contains")
                        .value(update_table_status)
                        .build()
                        ])
                    .build())
                .build()) \
            .build()
        # Delay 1 giây trước khi query tiếp
        time.sleep(1)
        #print("✅[get_table_data] request:", request)
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
        orderData = extract_orders_from_json(response_data, False)
        #download_order_artworks(orderData)
        #delete_artwork(orderData)
        all_data.append(orderData)
       #order_list = get_order_list(orderData)
        #upsert_local_records(orderData, "order_data.json", True)
        print("✅[get_table_data] Page[length]:", page, len(orderData))
        if isinstance(response_data, str):
            data = json.loads(response_data)
        else:
            data = response_data
        has_more = data['has_more']
        if has_more:
            page_token = data['page_token']
        page += 1
    with open("order_data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
    return orderData

def delete_artwork(orders):
    for order in orders:
        record_id = order['record_id']
        file_path = Path(f"templates/static/tmp/{record_id}")
        if os.path.exists(f"templates/static/tmp/{record_id}"):
            print("✅ File already exists locally:", record_id)
        return record_id
def upsert_local_records(records, path="order_data.json", override = False):
    # load current cache (empty array if file missing/blank)
    print("✅[upsert_local_records] records:", records)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            local_data = json.loads(text) if text else []
    except FileNotFoundError:
        local_data = []
    if override:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=4)
        return None
    # keep quick lookup by record_id
    existing = {rec["record_id"]: rec for rec in local_data}
    updated = False
    for rec in records:
        rid = rec.get("record_id")
        if not rid:
            continue  # skip malformed
        if rid in existing:
            continue  # already cached
        existing[rid] = rec
        updated = True

    if updated:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list(existing.values()), f, ensure_ascii=False, indent=4)

def get_orders_records(record_id, order_id):
    print("✅[get_orders_records] order:", order_id, record_id)
    data = getOrderID(order_id, None)
    new_status = ""
    if ROLE_USER == "WORKER":
        new_status = "In-Production"
    elif ROLE_USER == "SHIPPER":
        new_status = "Done"
    updateData = getRecordStatus(data, record_id, new_status)
    print("✅[get_orders_records] updateData:", updateData)
    current_status = updateData[0]
    display_data = updateData[1]
    threading.Thread(target=update_record_status, args=(record_id, new_status,current_status)).start()
    #print("✅[get_orders_records] local_data:", local_data)
    #data = getOrderID(order_id, None)    
    return display_data
def getRecordStatus(data, record_id, new_status):
    for record in data:
        if record['record_id'] == record_id:
            current_status = record['status']
            if get_next_status(current_status, new_status) :
                record['status'] = new_status
                return [record, data]
            return [record, data]
    return ["", data]    

def getOrderID(order_id, record_id=None):
    # init client
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # send request
    orderData = []
    # send request
    if record_id:
        print("✅[getOrderID] record_id:", record_id)
        request = GetAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .record_id(record_id) \
            .user_id_type("user_id") \
            .build()
        
        response = client.bitable.v1.app_table_record.get(request)
        
        if not response.success():
             lark.logger.error(f"getOrderID failed for record {record_id}: {response.code} {response.msg}")
             return []
             
        # Normalize to list structure for extraction
        # response.data.record is the single AppTableRecord object
        if response.data and response.data.record:
            # Manually construct dict from the object attributes we need
            # Assuming attributes like fields, record_id exist directly on the object
            record_obj = response.data.record
            # Use vars() or attribute access if available, but safest to use lark.JSON.marshal for the whole response data
            # extract_orders_from_json expects a dict structure
            
            # Serialize the entire data object to JSON string then load it to dict
            data_dict = json.loads(lark.JSON.marshal(response.data, indent=4))
            
            # The structure from marshal(response.data) for 'get' has a 'record' key
            # We need to wrap it into 'items' list for existing extraction logic
            if 'record' in data_dict:
                raw_data = {"items": [data_dict['record']]}
                orderData = extract_orders_from_json(raw_data)
            else:
                 lark.logger.error(f"Unexpected response structure for record {record_id}: {data_dict.keys()}")
                 return []
        else:
             return []

    else:
        print("✅[getOrderID] order:", order_id)
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
            return []

        # print response data
        #lark.logger.info(lark.JSON.marshal(response.data, indent=4))
        orderData = extract_orders_from_json(lark.JSON.marshal(response.data, indent=4))
    
    return orderData

def get_order_list(orders):
    # Extract order IDs
    #order_ids = [item["order_id"] for item in orders]
    #print("✅[get_order_list] order:", orders)
    conditions = [
        {
            "field_name": "Order ID",
            "operator": "contains",
            "value": [oid["order_id"]]
        }
        for oid in orders
    ]
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
                .conjunction("or")
                .conditions(conditions)
                .build())
            .build()) \
        .build()
    
    #print("✅[get_order_list] request:", request)
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
BATCH_TABLE = "tblU7Py2lMELFueZ"

# Route xử lý đơn hàng
@app.route("/api/process-orders", methods=['POST'])
def process_orders():
    # load current cache (empty array if file missing/blank)
    try:
        with open("processing.json", "r", encoding="utf-8") as f:
            text = f.read().strip()
            processing_data = json.loads(text) if text else []
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "No processing data found."}), 404

    if not processing_data:
        return jsonify({"status": "error", "message": "Processing list is empty."}), 400

    # 1. Create Label (PDF)
    create_qr_labels(processing_data)

    # Prepare for batch creation
    batch_name = processing_data[0].get('batch_name', '') if processing_data else "Unknown_Batch"
    
    # Authenticate once for Lark operations
    user_token = get_access_token(APP_ID, APP_SECRET)
    if not user_token:
        return jsonify({'success': False, 'error': 'Missing USER_ACCESS_TOKEN'}), 500
    
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # Process each order
    total_qty = 0
    item_record_ids = []
    
    for order in processing_data:
        record_id = order['record_id']
        order_id = order['order_id']
        qty = order.get('qty', 0)
        try:
            total_qty += int(qty)
        except (ValueError, TypeError):
            pass # Or handle error appropriately
        
        item_record_ids.append(record_id)
        
        # 2. Update Label URL into "Qr Code" column on Lark
        api_url = f"http://localhost:5000/api/update-status/{record_id}?order_id={order_id}"
        update_lark_qrcode(client, user_token, record_id, api_url)

        # 4. Buy label
        #buy_label_for_order(record_id)

    # 3. Create batch record
    create_batch_record(client, user_token, batch_name, total_qty, item_record_ids)

    return jsonify({"status": "success", "message": "Orders processed: Labels created, Lark updated, Batch recorded, Labels bought."})

def update_lark_qrcode(client, user_token, record_id, qr_url):
    try:
        request_obj = UpdateAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(TABLE_ID) \
            .record_id(record_id) \
            .user_id_type("user_id") \
            .request_body(AppTableRecord.builder()
                .fields({
                    "Item Link": qr_url,
                    "Factory Status": "In-Production"}) # Assuming column name is "Qr Code"
                .build()) \
            .build()

        option = lark.RequestOption.builder().user_access_token(user_token).build()
        response = client.bitable.v1.app_table_record.update(request_obj, option)
        
        if not response.success():
             lark.logger.error(f"Failed to update QR Code for {record_id}: {response.msg}")
    except Exception as e:
        lark.logger.error(f"Exception updating QR Code for {record_id}: {e}")

def create_batch_record(client, user_token, batch_name, total_qty, item_record_ids):
    try:
        print(f"✅ Creating Batch: Name={batch_name}, Status=Active, Total={total_qty}, Items={item_record_ids}")
        request_obj = CreateAppTableRecordRequest.builder() \
            .app_token(BASE_ID) \
            .table_id(BATCH_TABLE) \
            .user_id_type("user_id") \
            .request_body(AppTableRecord.builder()
                .fields({
                    "Machine": batch_name,
                    "Batch Status": "Active",
                    "Total Item": total_qty,
                    "Items": item_record_ids
                }) 
                .build()) \
            .build()

        option = lark.RequestOption.builder().user_access_token(user_token).build()
        response = client.bitable.v1.app_table_record.create(request_obj, option)

        if not response.success():
             lark.logger.error(f"Failed to create Batch record {batch_name}: {response.msg}")
    except Exception as e:
        lark.logger.error(f"Exception creating Batch record {batch_name}: {e}")

def buy_label_for_order(record_id):
    url = "https://open-sg.larksuite.com/anycross/trigger/callback/ZTQ0MjA4ZWMxOTFhODhlMzgzM2QxZmI2MzhlOTdiZDYw"
    params = {"record_id": record_id}
    try:
        requests.get(url, params=params)
        print(f"✅ Triggered buy label for {record_id}")
    except Exception as e:
        print(f"❌ Failed to trigger buy label for {record_id}: {e}")


def create_qr_labels(orders):
    # Tạo file PDF
    #print("[create_qr_labels] orders: ", orders)   
    # Tạo cửa sổ ẩn
    #root = tk.Tk()
    #root.withdraw()
    # Hiện popup để nhập batch name
    #batchfilename = simpledialog.askstring("Batch Name", "Nhập batch name:")
    #print("✅[create_qr_labels] Create Batch name:", batchfilename)
    # Kích thước QR code: 20mm x 20mm
    # Kích thước trang PDF: 70mm x 25mm
    PAGE_WIDTH, PAGE_HEIGHT = 70 * mm, 22 * mm
    COLS = 2
    CELL_WIDTH = PAGE_WIDTH / COLS
    CELL_HEIGHT = PAGE_HEIGHT
    QR_WIDTH_MM = 15
    QR_HEIGHT_MM = 15
    QR_WIDTH_PT = QR_WIDTH_MM * mm
    QR_HEIGHT_PT = QR_HEIGHT_MM * mm
    QR_MARGIN = 0.5 *mm

    qrlabelname = f"qr_labels_70x22mm_{int(time.time())}.pdf"
    c = canvas.Canvas(qrlabelname, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    col = 0
    urls = []
    pgs_design_links = []
    batchfilename = "batch1"
    i=0
    for idx, order in enumerate(orders):
        #if ROLE_USER == "WORKER":
            #get_lark_file_preview_url(order["color_index_token"], order["record_id"])
        #else:
            #get_lark_file_preview_url(order["mockup_token"], order["record_id"])
        # Tạo QR code content với API endpoint
        api_url = f"http://localhost:5000/api/update-status/{order['record_id']}?order_id={order['order_id']}"
        #print("✅[create_qr_labels] api_url:", api_url)
        qr_content = api_url  # QR code sẽ chứa URL để update status
        #designlink = read_url_list(order['design_link'])
        if order['shop_name'].find("PGS") != -1:
            #pgs_design_links.append(order['design_link'])
            pgs_design_links.append(order)
        else:
            #urls.append(order['design_link'])
            urls.append(order)
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

        # Lưu ảnh tạm
        temp_img = f"temp_{idx}.png"
        qr_img.save(temp_img)


        # Chèn Order ID bên dưới
        c.setFont("Helvetica", 8)
        top_text = order['order_id']+' _ '+order['line_number']
        text_x = x + CELL_WIDTH / 2
        text_y = y + CELL_HEIGHT - 8
        #c.drawCentredString(x + CELL_WIDTH / 2, y + CELL_HEIGHT - 8 , top_text)
        c.drawCentredString(text_x, text_y, top_text)
        # Vẽ gạch ngang dưới text
        text_width = c.stringWidth(top_text, "Helvetica", 8)
        line_y = text_y - 5   # cách text 2pt
        c.line(x, line_y, text_x + text_width/2, line_y)

        # Tính vị trí ảnh QR trong ô
        img_x = x + QR_MARGIN#+ (CELL_WIDTH - QR_WIDTH_PT) / 2
        img_y = y + QR_MARGIN

        # Chèn ảnh QR
        c.drawImage(temp_img, img_x, img_y, width=QR_WIDTH_PT, height=QR_HEIGHT_PT)

        # Text bên phải QR: type + size
        c.setFont("Helvetica", 4)
        text_x = img_x + QR_WIDTH_PT + 5   # cách QR 5pt
        text_y = img_y + QR_HEIGHT_PT / 2  # căn giữa theo chiều cao QR
        # Dòng 1: type (style)
        c.drawString(text_x, img_y + QR_HEIGHT_PT - 5, f"Type: {order['style']}")
        c.drawString(text_x, img_y + QR_HEIGHT_PT - 11, f"Size: {order['size']}")
        c.drawString(text_x, img_y + QR_HEIGHT_PT - 17, f"color: {order['color']}")
        c.drawString(text_x, img_y + QR_HEIGHT_PT - 23, f"Batch: {batchfilename}")
        c.drawString(text_x, img_y + QR_HEIGHT_PT - 29, f"Total: {order.get('total_order_qty', 'N/A')}")
        line_y = img_y + QR_HEIGHT_PT - 35
        top_text = f"custom: {order['custom']}"
        lines = wrap(top_text, 25)  # 25 ký tự mỗi dòng
        line_height = 4
        for i, line in enumerate(lines):
            c.drawString(text_x, line_y - i*line_height, line)

        #c.drawString(text_x, img_y + QR_HEIGHT_PT - 28, f"custom: {order['custom']}")

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
    target_file = os.path.join(batchfilename, os.path.basename(batchfilename+qrlabelname))

    # Sao chép file
    shutil.copy(qrlabelname, target_file)
    
# Parse JSON data
def extract_orders_from_json(json_data, preview = False):
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data
    # Calculate total quantity per Order ID
    order_totals = {}
    items = data.get('items', [])
    for item in items:
        # Safe extraction for Order ID
        order_id_field = item['fields'].get('Order ID', [])
        if isinstance(order_id_field, list) and len(order_id_field) > 0:
            if isinstance(order_id_field[0], dict):
                 order_id = order_id_field[0].get('text', '')
            else:
                 order_id = str(order_id_field[0])
        else:
             order_id = str(order_id_field)

        try:
            qty = int(item['fields'].get('Quantity*', 1))
        except (ValueError, TypeError):
            qty = 1
        order_totals[order_id] = order_totals.get(order_id, 0) + qty

    # Group items by Order ID
    grouped_items = {}
    for item in items:
        # Safe extraction for Order ID (Repeat logic)
        order_id_field = item['fields'].get('Order ID', [])
        if isinstance(order_id_field, list) and len(order_id_field) > 0:
            if isinstance(order_id_field[0], dict):
                 order_id = order_id_field[0].get('text', '')
            else:
                 order_id = str(order_id_field[0])
        else:
             order_id = str(order_id_field)
             
        grouped_items.setdefault(order_id, []).append(item)

    orders = []
    def safe_get_text(field_val):
        if isinstance(field_val, list) and len(field_val) > 0:
            if isinstance(field_val[0], dict):
                 return field_val[0].get('text', '')
            else:
                 return str(field_val[0])
        elif isinstance(field_val, str):
             return field_val
        elif field_val is None:
             return ''
        else:
             return str(field_val)

    # Process each group
    for order_id, group_items in grouped_items.items():
        for idx, item in enumerate(group_items, start=1):
            record_id = item.get('record_id', '')       
            # order_id already extracted
            order = {
                "order_id": order_id,
                "record_id": record_id,
                "status": item['fields'].get('Factory Status'),
                "style": item['fields'].get('Style'),
                "size": item['fields'].get('Size'),
                "color": item['fields'].get('Color'),
                "qty": item['fields'].get('Quantity*'),
                "custom": safe_get_text(item['fields'].get('Personalization')),
                "label": safe_get_text(item['fields'].get('Label URL')),
                #"design_link": item['fields'].get('Link Design').get('link', ''),
                "batch_name": safe_get_text(item['fields'].get('BatchName')),
                "shop_name": safe_get_text(item['fields'].get('ShopName')),
                "mockup_token": '',
                "color_index_token": '',
                "in_production": item['fields'].get('In_Production'),
                "Done": item['fields'].get('Done'),
                "total_order_qty": order_totals.get(order_id, 0)
            }
            if item['fields'].get('Link Design') is not None:
               order["design_link"] = item['fields'].get('Link Design').get('link', '')
            if("Color Index" in item["fields"]): 
                order["color_index_token"] = item["fields"]["Color Index"][0]["file_token"]
            if("Mockup" in item["fields"]): 
                order["mockup_token"] = item["fields"]["Mockup"][0]["file_token"]   
            if(order["shop_name"].find("PGS") != -1): 
                order["design_link"] =  {
                    'artwork': item['fields'].get('Artwork', [{}]),
                    'order_id': order['order_id']
                }
                order["order_id"] = order["order_id"].replace("#", "")
                #order["shop_name"] = item["fields"]["ShopName"]
            try:
                qty_val = int(item['fields'].get('Quantity*', 1))
            except (ValueError, TypeError):
                qty_val = 1
                
            for i in range(qty_val):
                order_copy = order.copy()
                order_copy['qty'] = 1 # Split item has qty 1
                order_copy['line_number'] = f"{idx}-{i+1}"
                orders.append(order_copy)
    return orders

def download_order_artworks(orders):
    preview_url = ''
    for order in orders:
        print("✅[download_order_artworks] order:", order)
        file_token = order.get("mockup_token")
        if ROLE_USER == "WORKER":
            file_token = order.get("color_index_token")
        # If mockup_token is missing but we have record_id, try to fetch it again
        
        print(f"✅[download_order_artworks] file_token type: {type(file_token)}, value: {file_token}")
        if file_token:
            record_id = order.get("record_id")
            #print("✅[download_order_artworks] file_token:", file_token)
            preview_url = get_lark_file_preview_url(file_token, record_id)
        else:
            preview_url = get_drive_preview_url(order.get("design_link"), order.get("record_id"))
        #print("✅[download_order_artworks] preview_url:", preview_url)
    return preview_url
    # Lưu PDF


def get_next_status(current_status, new_status):
    try:
        current_index = status_flow.index(current_status)
        new_status = status_flow.index(new_status)
        if current_index <= new_status:
            return True
        else:   
            return False
    except ValueError:
        return False
# Route cập nhật status từ QR code scan
import threading
@app.route("/api/update-status/<record_id>", methods=['GET', 'POST'])
def update_status_from_qr(record_id):
    try:
        order_id = request.args.get('order_id', '')
        recordData = get_orders_records(record_id, order_id)
        print("✅[update_status_from_qr] recordData : ", recordData)
        if isinstance(recordData, dict):
            order_data = recordData
        else:
            order_data = next((item for item in recordData if item["record_id"] == record_id), None)
        #if os.path.exists(f"templates/static/tmp/{record_id}"):
            #preview_url = record_id
        #else:
            #preview_url = download_order_artworks([order_data], ROLE_USER) 
        label_pdf = recordData[0]['label']
        preview_url = get_lark_file_preview_url(order_data.get("mockup_token"), record_id)   
        if ROLE_USER == "WORKER" or preview_url == "":
            preview_url = get_lark_file_preview_url(order_data.get("color_index_token"), record_id)   
        print("✅[update_status_from_qr] preview_url : ", preview_url)
        if request.method == 'GET':
            print("✅[update_status_from_qr] get records.html : ", order_id, order_data, record_id, preview_url, ROLE_USER)
            return render_template("orders.html", order_id=order_id, records=recordData, active_record_id=record_id, design_link=preview_url, label_pdf=label_pdf, roles =ROLE_USER)
        # POST -> JSON success
        return jsonify({"status": "success", "message": f"Order data: {recordData}"})
        #return jsonify(recordData)
        #return render_template("orders.html", order_id=order_id, records=recordData, active_record_id=record_id, label_pdf=label_pdf, design_link=preview_url)

    except Exception as e:
        lark.logger.error(f"Exception updating record {record_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
def get_lark_file_preview_url(file_token, record_id):
    print("✅[get_lark_file_preview_url] file_token:", file_token)
    if os.path.exists(f"templates/static/tmp/{record_id+ROLE_USER}"):
        print("✅ File already exists locally:", record_id)
        return record_id+ROLE_USER
    #record_id = request.args.get("record_id")
    #time.sleep(0.1)
    if file_token == "":
        return "" 
    file_data = get_tmp_download_url_builder(file_token)
    #print("✅[get_lark_file_preview_url] file_data:", file_data)
    if not file_data['tmp_download_urls']:
        recordData = getOrderID(None, record_id)[0]
        
        file_token = recordData['mockup_token']
        if ROLE_USER == "WORKER":
            file_token = recordData["color_index_token"]
        file_data = get_tmp_download_url_builder(file_token)
    tmp_download_url = file_data['tmp_download_urls'][0]['tmp_download_url']
    folder = "templates/static/tmp"
    os.makedirs(folder, exist_ok=True)
    #file_name = file_token# + ".png"
    filepath = os.path.join(folder, record_id+ROLE_USER)
    dataResponse = requests.get(tmp_download_url)
    if dataResponse.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(dataResponse.content)
        print("✅[Debug] filepath:", filepath)
        return record_id+ROLE_USER
    else:
        print("❌ Lỗi tải ảnh:", dataResponse.status_code)
        return None

def get_tmp_download_url_builder(file_token) :
    time.sleep(0.5)
    #url = "https://open.larksuite.com/open-apis/drive/v1/medias/batch_get_tmp_download_url?file_tokens="+file_token
    user_token = get_access_token(APP_ID, APP_SECRET)
    if not user_token:
        return jsonify({'success': False, 'error': 'Missing USER_ACCESS_TOKEN env var'}), 500
    #khoi tao extra params
    extra = json.dumps({
        "bitablePerm": {
            "tableId": TABLE_ID,
            "rev": 5
        }
    })
    print("✅[get_tmp_download_url_builder] extra:", extra)
    # Khởi tạo client (enable_set_token để dùng user token)
    client = lark.Client.builder() \
        .enable_set_token(True) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()
    try:
        request: BatchGetTmpDownloadUrlMediaRequest = BatchGetTmpDownloadUrlMediaRequest.builder() \
        .file_tokens(file_token) \
        .extra(extra) \
        .build()
        time.sleep(0.5)
        option = lark.RequestOption.builder().user_access_token(user_token).build()
        response: BatchGetTmpDownloadUrlMediaResponse = client.drive.v1.media.batch_get_tmp_download_url(request, option)
        if not response.success():
            lark.logger.error(
                f"client.drive.v1.media.batch_get_tmp_download_url failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}")
            return None
        file_data = json.loads(lark.JSON.marshal(response.data, indent=4))
        return file_data
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
            update_record_status(record_id, "Shipped", record['status'])
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "success", "message": f"Order {order_id} status updated to Shipped."})

def get_record_data_json(record_id) :
    with open("order_data.json", "r", encoding="utf-8") as f:
        local_data = json.load(f)

    for record in local_data:
        if record["record_id"] == record_id:
            return record
def update_record_data_json(record_id, status):
    with open("order_data.json", "r", encoding="utf-8") as f:
        local_data = json.load(f)

    # Filter out invalid entries if any
    valid_data = []
    updated = False
    if isinstance(local_data, list):
         for record in local_data:
             if isinstance(record, dict):
                 if record.get("record_id") == record_id:
                     record['status'] = status
                     print("✅[update_record_data_json] status:", status)
                     updated = True
                 valid_data.append(record)
    
    if updated:
         with open("order_data.json", "w", encoding="utf-8") as f:
            json.dump(valid_data, f, ensure_ascii=False, indent=4)

def update_record_status(record_id, status, record):
    current_status = record['status']
    print("✅[update_record_status] record:", record)
    try:
        # Check if record_id exists in Lark by fetching it via getOrderID
        print("✅[update_record_status] change status from:", current_status, status)
        if get_next_status(current_status, status) :
            # user access token must be provided via env var for security
            user_token = get_access_token(APP_ID, APP_SECRET)
            #update_record_data_json(record_id, status)
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
                    .fields({
                        "Factory Status": status})
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
        import traceback
        lark.logger.error(f"Exception updating record {record_id}: {e}")
        lark.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
    return None

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
    for link in urls:
        i += 1
        url = link["design_link"]
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
                download_png(file["id"], link["record_id"])

def downloadpgsFiles(urls, filepath):
    #path = filepath
    for design_link in urls:
        #print(f"✅ [downloadpgsFiles] url:", url)
        order_id = design_link['order_id'].replace("#", "")
        orderpath = os.path.join(filepath, order_id)
        #print(f"✅ [downloadpgsFiles] orderpath:", orderpath)
        os.makedirs(orderpath, exist_ok=True)
        i=0
        url = design_link["design_link"]
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


def get_drive_preview_url(folder_url, record_id):
    if os.path.exists(f"templates/static/tmp/{record_id}"):
        print("✅ File already exists locally:", record_id)
        return record_id
    folder_id = extract_folder_id(folder_url)
    files = list_files_in_folder(folder_id)
    if not files:
        return None
    for file in files:
        if file['name'].lower().endswith('.png') or file['name'].lower().endswith('.jpg') or file['name'].lower().endswith('.jpeg'):
            download_png(file["id"], record_id)
            return record_id
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

def download_png(file_id, record_id):
    print("✅ [download_png] file_id:", file_id)
    if os.path.exists(f"templates/static/tmp/{record_id}"):
        print("✅ File already exists locally:", record_id)
        return filepath
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    folder = "templates/static/tmp"
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, record_id)
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
    get_table_data(None, None, None)


