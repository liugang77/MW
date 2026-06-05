from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "财智8 Web"
    api_prefix: str = "/api/v1"
    # 数据目录：backend/data/
    #   common.db        —— 通用设置（账本登记、分类、币种、汇率、存款利率、交易费率、产品资料与价格）
    #   ledger_{id}.db   —— 每个账本独立一个文件（账户、人员机构、流水、标签、预算、持仓、借贷、计划）
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    @property
    def common_db_path(self) -> Path:
        return self.data_dir / "common.db"

    def ledger_db_path(self, ledger_id: int) -> Path:
        return self.data_dir / f"ledger_{ledger_id}.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.common_db_path}"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)

