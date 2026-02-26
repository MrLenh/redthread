from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
import os, re, io

SERVICE_ACCOUNT_FILE = "credentials.json"
URL_FILE = "urllist.txt"
DOWNLOAD_DIR = "downloaded_files"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def extract_folder_id(url):
    match = re.search(r"folders/([a-zA-Z0-9-_]+)", url)
    return match.group(1) if match else None

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

def download_file(file_id, file_name):
    request = drive_service.files().get_media(fileId=file_id)
    file_path = os.path.join(DOWNLOAD_DIR, file_name)

    with io.FileIO(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Downloading {file_name}: {int(status.progress()*100)}%")

def run():
    urls = read_url_list(URL_FILE)
    i=0
    name = ""
    for url in urls:
        match = re.search(r"name:\s*([A-Za-z0-9_-]+)", url)
        if match:
            name = match.group(1)
            print("Found name:", name)
        else:
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
                if(file['name'].includes('.DST')):
                    download_file(file["id"], name+"_"+str(i)+"_"+file["name"])

run()
