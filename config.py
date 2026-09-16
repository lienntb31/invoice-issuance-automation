"""Central configuration, loaded from environment variables (see .env.example).

No secret is ever hardcoded here. SFTP passwords are retrieved from the OS keyring at
call time (see src/common/sftp_client.py), never read into an environment variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class WarehouseConfig:
    app_key: str = field(default_factory=lambda: _env("WAREHOUSE_APP_KEY", "demo.app.key"))
    app_secret: str = field(default_factory=lambda: _env("WAREHOUSE_APP_SECRET", "demo-secret"))
    api_base: str = field(
        default_factory=lambda: _env("WAREHOUSE_API_BASE", "https://warehouse-api.internal.example.com")
    )


@dataclass(frozen=True)
class SftpConfig:
    host: str = field(default_factory=lambda: _env("SFTP_HOST", "sftp.partner.example.com"))
    port: int = field(default_factory=lambda: int(_env("SFTP_PORT", "22")))
    username: str = field(default_factory=lambda: _env("SFTP_USERNAME", "demo_user"))
    keyring_service: str = field(
        default_factory=lambda: _env("SFTP_KEYRING_SERVICE", "invoicing-sftp-prod")
    )
    remote_outgoing_dir: str = field(default_factory=lambda: _env("SFTP_REMOTE_OUTGOING_DIR", "/outgoing"))
    remote_archive_dir: str = field(
        default_factory=lambda: _env("SFTP_REMOTE_ARCHIVE_DIR", "/outgoing/archive")
    )
    remote_incoming_dir: str = field(default_factory=lambda: _env("SFTP_REMOTE_INCOMING_DIR", "/incoming"))


@dataclass(frozen=True)
class SheetsConfig:
    service_account_path: str = field(
        default_factory=lambda: _env("GOOGLE_SERVICE_ACCOUNT_PATH", "./credentials/service-account.json")
    )
    daily_report_sheet_id: str = field(
        default_factory=lambda: _env("GSHEET_DAILY_REPORT_ID", "demo-daily-report-sheet-id")
    )
    tax_id_tracker_sheet_id: str = field(
        default_factory=lambda: _env("GSHEET_TAX_ID_TRACKER_ID", "demo-tax-id-tracker-sheet-id")
    )


@dataclass(frozen=True)
class PathsConfig:
    upload_dir: str = field(default_factory=lambda: _env("LOCAL_UPLOAD_DIR", "./data/uploads"))
    result_dir: str = field(default_factory=lambda: _env("LOCAL_RESULT_DIR", "./data/results"))
    output_dir: str = field(default_factory=lambda: _env("LOCAL_OUTPUT_DIR", "./output"))


@dataclass(frozen=True)
class RulesConfig:
    max_rows_per_file: int = field(default_factory=lambda: int(_env("MAX_ROWS_PER_FILE", "20000")))
    reconciliation_tolerance: float = field(
        default_factory=lambda: float(_env("RECONCILIATION_TOLERANCE", "1.0"))
    )


@dataclass(frozen=True)
class Config:
    warehouse: WarehouseConfig = field(default_factory=WarehouseConfig)
    sftp: SftpConfig = field(default_factory=SftpConfig)
    sheets: SheetsConfig = field(default_factory=SheetsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)


CONFIG = Config()
