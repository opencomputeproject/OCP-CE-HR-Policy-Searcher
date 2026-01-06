"""Google Sheets integration."""

import base64
import json
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models.policy import Policy


class SheetsClient:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, credentials_b64: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self._credentials_b64 = credentials_b64
        self._client: Optional[gspread.Client] = None
        self._spreadsheet = None

    def connect(self) -> None:
        creds_json = base64.b64decode(self._credentials_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        credentials = Credentials.from_service_account_info(creds_dict, scopes=self.SCOPES)
        self._client = gspread.authorize(credentials)
        self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)

    def get_staging_sheet(self, name: str = "Staging") -> gspread.Worksheet:
        try:
            return self._spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            sheet = self._spreadsheet.add_worksheet(name, rows=1000, cols=20)
            sheet.update("A1:N1", [Policy.sheet_headers()])
            return sheet

    def get_existing_urls(self, sheet_name: str = "Staging") -> set[str]:
        try:
            sheet = self._spreadsheet.worksheet(sheet_name)
            urls = sheet.col_values(1)
            return set(urls[1:])
        except gspread.WorksheetNotFound:
            return set()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def append_policies(self, policies: list[Policy], sheet_name: str = "Staging") -> int:
        if not policies:
            return 0

        sheet = self.get_staging_sheet(sheet_name)
        rows = [p.to_sheet_row() for p in policies]
        sheet.append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)
