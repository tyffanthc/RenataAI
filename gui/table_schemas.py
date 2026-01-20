from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from gui import strings as ui

@dataclass(frozen=True)
class TableColumn:
    key: str
    label: str
    value_path: str | None = None
    fmt: str = "text"
    width: int | None = None
    align: str = "left"
    default_visible: bool = True


@dataclass(frozen=True)
class TableSchema:
    schema_id: str
    title: str
    columns: tuple[TableColumn, ...]


def _cols(items: Iterable[TableColumn]) -> tuple[TableColumn, ...]:
    return tuple(items)


SCHEMAS: dict[str, TableSchema] = {
    "neutron": TableSchema(
        schema_id="neutron",
        title="Neutron Route",
        columns=_cols(
            [
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM, width=28),
                TableColumn("distance_ly", ui.TABLE_HDR_DISTANCE_LY, fmt="ly", align="right", width=11),
                TableColumn("remaining_ly", ui.TABLE_HDR_REMAINING_LY, fmt="ly", align="right", width=12),
                TableColumn("neutron", ui.TABLE_HDR_NEUTRON, fmt="bool", align="center", width=7),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "riches": TableSchema(
        schema_id="riches",
        title="Riches Route",
        columns=_cols(
            [
                TableColumn("done", ui.TABLE_HDR_DONE, fmt="bool", align="center", width=4),
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM_NAME, width=20),
                TableColumn("body_name", ui.TABLE_HDR_BODY_NAME, width=20),
                TableColumn("subtype", ui.TABLE_HDR_SUBTYPE, width=16),
                TableColumn("terraformable", ui.TABLE_HDR_TERRA, fmt="bool", align="center", width=6),
                TableColumn("distance_ls", ui.TABLE_HDR_DISTANCE_LS, fmt="ls", align="right", width=12),
                TableColumn("value_scan", ui.TABLE_HDR_SCAN_VALUE, fmt="cr", align="right", width=14),
                TableColumn("value_map", ui.TABLE_HDR_MAPPING_VALUE, fmt="cr", align="right", width=14),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "ammonia": TableSchema(
        schema_id="ammonia",
        title="Ammonia Route",
        columns=_cols(
            [
                TableColumn("done", ui.TABLE_HDR_DONE, fmt="bool", align="center", width=4),
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM_NAME, width=20),
                TableColumn("body_name", ui.TABLE_HDR_BODY_NAME, width=20),
                TableColumn("subtype", ui.TABLE_HDR_SUBTYPE, width=16),
                TableColumn("terraformable", ui.TABLE_HDR_TERRA, fmt="bool", align="center", width=6),
                TableColumn("distance_ls", ui.TABLE_HDR_DISTANCE_LS, fmt="ls", align="right", width=12),
                TableColumn("value_scan", ui.TABLE_HDR_SCAN_VALUE, fmt="cr", align="right", width=14),
                TableColumn("value_map", ui.TABLE_HDR_MAPPING_VALUE, fmt="cr", align="right", width=14),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "elw": TableSchema(
        schema_id="elw",
        title="ELW Route",
        columns=_cols(
            [
                TableColumn("done", ui.TABLE_HDR_DONE, fmt="bool", align="center", width=4),
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM_NAME, width=20),
                TableColumn("body_name", ui.TABLE_HDR_BODY_NAME, width=20),
                TableColumn("subtype", ui.TABLE_HDR_SUBTYPE, width=16),
                TableColumn("terraformable", ui.TABLE_HDR_TERRA, fmt="bool", align="center", width=6),
                TableColumn("distance_ls", ui.TABLE_HDR_DISTANCE_LS, fmt="ls", align="right", width=12),
                TableColumn("value_scan", ui.TABLE_HDR_SCAN_VALUE, fmt="cr", align="right", width=14),
                TableColumn("value_map", ui.TABLE_HDR_MAPPING_VALUE, fmt="cr", align="right", width=14),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "hmc": TableSchema(
        schema_id="hmc",
        title="HMC / Rocky Route",
        columns=_cols(
            [
                TableColumn("done", ui.TABLE_HDR_DONE, fmt="bool", align="center", width=4),
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM_NAME, width=20),
                TableColumn("body_name", ui.TABLE_HDR_BODY_NAME, width=20),
                TableColumn("subtype", ui.TABLE_HDR_SUBTYPE, width=16),
                TableColumn("terraformable", ui.TABLE_HDR_TERRA, fmt="bool", align="center", width=6),
                TableColumn("distance_ls", ui.TABLE_HDR_DISTANCE_LS, fmt="ls", align="right", width=12),
                TableColumn("value_scan", ui.TABLE_HDR_SCAN_VALUE, fmt="cr", align="right", width=14),
                TableColumn("value_map", ui.TABLE_HDR_MAPPING_VALUE, fmt="cr", align="right", width=14),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "exomastery": TableSchema(
        schema_id="exomastery",
        title="Exomastery Route",
        columns=_cols(
            [
                TableColumn("done", ui.TABLE_HDR_DONE, fmt="bool", align="center", width=4),
                TableColumn("system_name", ui.TABLE_HDR_SYSTEM_NAME, width=20),
                TableColumn("body_name", ui.TABLE_HDR_BODY_NAME, width=20),
                TableColumn("subtype", ui.TABLE_HDR_SUBTYPE, width=16),
                TableColumn("distance_ls", ui.TABLE_HDR_DISTANCE_LS, fmt="ls", align="right", width=12),
                TableColumn("value_scan", ui.TABLE_HDR_SCAN_VALUE, fmt="cr", align="right", width=14),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
    "trade": TableSchema(
        schema_id="trade",
        title="Trade Route",
        columns=_cols(
            [
                TableColumn("from_system", ui.TABLE_HDR_FROM, width=20),
                TableColumn("to_system", ui.TABLE_HDR_TO, width=20),
                TableColumn("commodity", ui.TABLE_HDR_COMMODITY, width=18),
                TableColumn("profit", ui.TABLE_HDR_PROFIT, fmt="cr", align="right", width=12),
                TableColumn("profit_per_ton", ui.TABLE_HDR_PROFIT_TON, fmt="cr", align="right", width=12),
                TableColumn("jumps", ui.TABLE_HDR_JUMPS, fmt="int", align="right", width=8),
            ]
        ),
    ),
}


def get_schema(schema_id: str) -> TableSchema | None:
    return SCHEMAS.get(schema_id)


def list_schema_ids() -> list[str]:
    return list(SCHEMAS.keys())
