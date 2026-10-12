# inventory_app

小型的庫存管理範例專案（coding harness 的評測 fixture）。

- `inventory/models.py`：`Item` 資料類別
- `inventory/store.py`：`Inventory`（新增、移除、總價值、報表）
- `inventory/storage.py`：JSON 檔的讀寫
- `inventory/cli.py`：命令列介面（`python3 -m inventory.cli --file inv.json add apple 1.5 3`）

測試：`python3 -m pytest -q`
