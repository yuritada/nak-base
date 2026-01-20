import os
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from ..config import get_settings

settings = get_settings()

SCOPES = ['https://www.googleapis.com/auth/drive']


def get_drive_service():
    """Get authenticated Google Drive service."""
    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials,
        scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


def get_or_create_folder(service, folder_name: str, parent_id: str = None) -> str:
    """Get existing folder or create new one."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    # Create folder
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]

    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')


def upload_file_to_drive(
    file_content: bytes,
    file_name: str,
    mime_type: str,
    student_name: str,
    paper_title: str
) -> str:
    """
    Upload file to Google Drive with folder structure:
    /{Root Folder}/{StudentName}/{PaperTitle}/{file}
    Returns the file_id.
    """
    service = get_drive_service()
    root_folder_id = settings.google_drive_folder_id

    # Create folder structure
    student_folder_id = get_or_create_folder(service, student_name, root_folder_id)
    paper_folder_id = get_or_create_folder(service, paper_title, student_folder_id)

    # Upload file
    file_metadata = {
        'name': file_name,
        'parents': [paper_folder_id]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_content),
        mimetype=mime_type,
        resumable=True
    )

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    return file.get('id')


def download_file_from_drive(file_id: str) -> bytes:
    """Download file from Google Drive."""
    service = get_drive_service()

    request = service.files().get_media(fileId=file_id)
    file_content = io.BytesIO()
    downloader = MediaIoBaseDownload(file_content, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return file_content.getvalue()


def get_file_metadata(file_id: str) -> dict:
    """Get file metadata from Google Drive."""
    service = get_drive_service()
    return service.files().get(fileId=file_id, fields='id, name, mimeType, size').execute()
