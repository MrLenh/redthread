# Lark Data Fetcher

A Python web application to fetch data from Lark Base, display it on a localhost web interface, and download attachments.

## Features

- **Fetch Processing Orders**: Get all records from Lark Base where Factory Status = "Processing"
- **View Orders**: See all orders grouped by Order ID with expandable record details
- **Save to JSON**: Export fetched data to JSON files
- **Batch Download Attachments**: Download all or selected attachments from records

## Requirements

- Python 3.10+
- Lark API credentials (App ID and App Secret)
- Access to a Lark Base with your data

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd redthread
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in your Lark credentials:
   ```
   LARK_APP_ID=your_app_id_here
   LARK_APP_SECRET=your_app_secret_here
   LARK_BASE_APP_TOKEN=your_base_app_token_here
   LARK_TABLE_ID=your_table_id_here
   ```

## Getting Lark Credentials

1. **App ID & App Secret**:
   - Go to [Lark Open Platform](https://open.larksuite.com/)
   - Create a new application
   - Copy the App ID and App Secret

2. **Base App Token**:
   - Open your Lark Base
   - The App Token is in the URL: `https://xxx.larksuite.com/base/{APP_TOKEN}?table={TABLE_ID}`

3. **Table ID**:
   - Also found in the URL as shown above

4. **Permissions Required**:
   - `bitable:record:read` - Read records from Base
   - `drive:drive:readonly` - Download attachments

## Usage

1. Start the application:
   ```bash
   python app.py
   ```

2. Open your browser and go to:
   ```
   http://127.0.0.1:5000
   ```

3. Click **"Fetch Data from Lark"** to load processing orders

4. Use the tabs to view:
   - **Orders**: Records grouped by Order ID
   - **All Records**: All individual records
   - **Attachments**: All attachments with download options

5. Click **"Save to JSON"** to export data to the `data/` folder

6. Click **"Download All Attachments"** to batch download files to `attachments/`

## Project Structure

```
redthread/
├── app.py              # Flask web application
├── config.py           # Configuration management
├── lark_client.py      # Lark API client
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
├── .gitignore          # Git ignore rules
├── templates/
│   └── index.html      # Web interface template
├── static/
│   ├── css/
│   │   └── style.css   # Styles
│   └── js/
│       └── app.js      # Frontend JavaScript
├── data/               # Saved JSON files
└── attachments/        # Downloaded attachments
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web interface |
| `/api/fetch` | POST | Fetch data from Lark Base |
| `/api/data` | GET | Get cached data |
| `/api/records` | GET | Get all records |
| `/api/orders` | GET | Get orders grouped data |
| `/api/attachments` | GET | Get attachment list |
| `/api/attachments/download` | POST | Batch download attachments |
| `/api/attachments/download/<token>` | GET | Download single attachment |
| `/api/save` | POST | Save data to JSON files |
| `/api/load` | POST | Load data from JSON files |
| `/api/files` | GET | List saved JSON files |

## Customization

### Field Names

Edit the following in `.env` to match your Lark Base schema:

```
FACTORY_STATUS_FIELD=Factory Status
ORDER_ID_FIELD=Order ID
```

### Flask Settings

```
FLASK_DEBUG=True
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
```

## License

MIT
