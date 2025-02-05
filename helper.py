import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from pdf2image import convert_from_bytes
from PIL import Image

# Define the scope and path to your credentials JSON file.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SERVICE_ACCOUNT_FILE = 'keys/wlsbot-8b58c062fc85.json'

SPREADSHEET_ID = '1as4XhkN-diOUwZWcOaFoNJ6SjE6mLep6qRSZUxGV0Y4'

VENMO_PAGE = 'Venmo'

def get_google_sheets_service():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('sheets', 'v4', credentials=creds)
    return service


def get_sheet_data(sheet_title: str):
    """
    Searches through all tabs in the spreadsheet for one that matches
    the provided sheet_title (e.g., a date string) and returns its data.
    """
    service = get_google_sheets_service()
    # Get spreadsheet metadata to list all sheet titles
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])

    target_sheet = None
    for sheet in sheets:
        properties = sheet.get('properties', {})
        title = properties.get('title', '')
        if title.lower() == sheet_title.lower():
            target_sheet = title
            break

    if not target_sheet:
        raise ValueError(f"Sheet titled '{sheet_title}' not found.")

    range_1 = f"'{target_sheet}'!N1:T27"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=range_1).execute()
    values = result.get('values', [])

    if not values:
        raise ValueError("No data found in the sheet.")

    df = pd.DataFrame(values[1:], columns=values[0])

    range_2 = f"'{target_sheet}'!T31"
    disc = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=range_2).execute()
    disc = disc.get('values', [])

    return df, disc


    # range_2 = f"'{VENMO_PAGE}'!A1:C200"
    # venmo_sheet = service.spreadsheets().values().get(
    #     spreadsheetId=SPREADSHEET_ID, range=range_2).execute()
    # values = venmo_sheet.get('values', [])
    #
    # if not values:
    #     raise ValueError("No data found in the sheet.")
    #
    # venmo = pd.DataFrame(values[1:], columns=values[0])
    #
    # return df, venmo


def parse_transactions(df: pd.DataFrame, venmo: pd.DataFrame):
    """
    Parses the DataFrame and returns a list of transaction dictionaries.
    For rows where the "Sender" cell is empty, the previously seen sender name is used.
    Parsing stops when a completely blank row is encountered.
    """
    transactions = []
    last_sender = None

    for index, row in df.iterrows():
        # If the row is completely blank (all cells empty or NaN), stop processing.
        if row.isnull().all() or (row.astype(str).str.strip() == "").all():
            break

        # Get the sender name, using the previously seen sender if empty.
        sender = row.get("Sender")
        if pd.isna(sender) or str(sender).strip() == "":
            sender = last_sender
        else:
            last_sender = sender

        if not pd.isna(sender):
            venmo_row = venmo[venmo.iloc[:, 0].str.strip().str.lower() == str(sender).strip().lower()]
            if not venmo_row.empty:
                discord_tag = venmo_row.iloc[0, 2]  # Assuming the Discord tag is in the 3rd column
                if not pd.isna(discord_tag) and str(discord_tag).strip() != "":
                    sender = f"@{discord_tag}"

        # Retrieve the receiver name.
        receiver = row.get("Receiver")
        if pd.isna(receiver) or str(receiver).strip() == "":
            # Skip rows without a valid receiver.
            continue

        transaction = {
            "sender_name": sender,
            "sender_contact": row.get("Sender Venmo", "N/A"),
            "amount": row.get("Amount", "N/A"),
            "receiver_name": receiver,
            "receiver_contact": row.get("Receiver Venmo", "N/A")
        }
        transactions.append(transaction)

    message_lines = []
    for t in transactions:
        line = (f"{t['sender_name']} owes {t['receiver_name']} "
                f"${t['amount']} (Payment Info: {t['receiver_contact']}).")
        message_lines.append(line)

    return "\n".join(message_lines)



def get_target_sheet_gid(sheet_title: str):
    """
    Using the Google Sheets API (like in get_sheet_data), retrieve the gid (sheetId)
    for the sheet with the given title.
    """
    service = get_google_sheets_service()
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = spreadsheet.get('sheets', [])

    for sheet in sheets:
        properties = sheet.get('properties', {})
        title = properties.get('title', '')
        if title.lower() == sheet_title.lower():
            return properties.get('sheetId')
    raise ValueError(f"Sheet titled '{sheet_title}' not found.")

def sheet_to_img(sheet_gid: str) -> bytes:
    """
    Exports a specific page (tab) of the Google Sheet as a PDF.
    The sheet_gid parameter specifies the GID (internal sheet id) for the target tab.
    Returns the PDF content as bytes.
    """

    # Use a Drive scope that allows read-only access.
    drive_scopes = ['https://www.googleapis.com/auth/drive.readonly']

    # Authenticate using the service account credentials.
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=drive_scopes)
    # Refresh the token (required for making authorized HTTP requests)
    creds.refresh(Request())

    # Build the export URL.
    # The URL for exporting a specific sheet as PDF uses the 'export' endpoint,
    # with parameters to specify the format and the target tab via its gid.
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export"
        f"?format=pdf&gid={sheet_gid}"
    )

    # Set up the HTTP headers with the Bearer token.
    headers = {
        'Authorization': f'Bearer {creds.token}'
    }

    # Make the request to export the PDF.
    response = requests.get(export_url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to export PDF: {response.status_code} {response.text}")

    images = convert_from_bytes(response.content, dpi=300)
    crop_box = (2125, 373, 3900, 1700)  # SET VALUES DO NOT MODIFY

    if not images:
        raise ValueError("No pages found in the PDF.")

    image = images[0]
    cropped_image = image.crop(crop_box)

    img_bytes_io = io.BytesIO()
    cropped_image.save(img_bytes_io, format='PNG')

    return img_bytes_io.getvalue()