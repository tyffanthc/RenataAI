from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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
                TableColumn("system_name", "System", width=28),
                TableColumn("distance_ly", "Dist(LY)", fmt="ly", align="right", width=9),
                TableColumn("remaining_ly", "Rem(LY)", fmt="ly", align="right", width=9),
                TableColumn("neutron", "Neut", fmt="bool", align="center", width=4),
                TableColumn("jumps", "Jmp", fmt="int", align="right", width=4),
            ]
        ),
    ),
    "riches": TableSchema(
        schema_id="riches",
        title="Riches Route",
        columns=_cols(
            [
                TableColumn("done", "Done", fmt="bool", align="center", width=4),
                TableColumn("system_name", "System Name", width=26),
                TableColumn("body_name", "Name", width=24),
                TableColumn("subtype", "Subtype", width=22),
                TableColumn("terraformable", "Terra", fmt="bool", align="center", width=5),
                TableColumn("distance_ls", "Distance (LS)", fmt="ls", align="right", width=12),
                TableColumn("value_scan", "Scan Value", fmt="cr", align="right", width=12),
                TableColumn("value_map", "Mapping Value", fmt="cr", align="right", width=13),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
    "ammonia": TableSchema(
        schema_id="ammonia",
        title="Ammonia Route",
        columns=_cols(
            [
                TableColumn("done", "Done", fmt="bool", align="center", width=4),
                TableColumn("system_name", "System Name", width=26),
                TableColumn("body_name", "Name", width=24),
                TableColumn("subtype", "Subtype", width=22),
                TableColumn("terraformable", "Terra", fmt="bool", align="center", width=5),
                TableColumn("distance_ls", "Distance (LS)", fmt="ls", align="right", width=12),
                TableColumn("value_scan", "Scan Value", fmt="cr", align="right", width=12),
                TableColumn("value_map", "Mapping Value", fmt="cr", align="right", width=13),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
    "elw": TableSchema(
        schema_id="elw",
        title="ELW Route",
        columns=_cols(
            [
                TableColumn("done", "Done", fmt="bool", align="center", width=4),
                TableColumn("system_name", "System Name", width=26),
                TableColumn("body_name", "Name", width=24),
                TableColumn("subtype", "Subtype", width=22),
                TableColumn("terraformable", "Terra", fmt="bool", align="center", width=5),
                TableColumn("distance_ls", "Distance (LS)", fmt="ls", align="right", width=12),
                TableColumn("value_scan", "Scan Value", fmt="cr", align="right", width=12),
                TableColumn("value_map", "Mapping Value", fmt="cr", align="right", width=13),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
    "hmc": TableSchema(
        schema_id="hmc",
        title="HMC / Rocky Route",
        columns=_cols(
            [
                TableColumn("done", "Done", fmt="bool", align="center", width=4),
                TableColumn("system_name", "System Name", width=26),
                TableColumn("body_name", "Name", width=24),
                TableColumn("subtype", "Subtype", width=22),
                TableColumn("terraformable", "Terra", fmt="bool", align="center", width=5),
                TableColumn("distance_ls", "Distance (LS)", fmt="ls", align="right", width=12),
                TableColumn("value_scan", "Scan Value", fmt="cr", align="right", width=12),
                TableColumn("value_map", "Mapping Value", fmt="cr", align="right", width=13),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
    "exomastery": TableSchema(
        schema_id="exomastery",
        title="Exomastery Route",
        columns=_cols(
            [
                TableColumn("done", "Done", fmt="bool", align="center", width=4),
                TableColumn("system_name", "System Name", width=26),
                TableColumn("body_name", "Name", width=24),
                TableColumn("subtype", "Subtype", width=22),
                TableColumn("distance_ls", "Distance (LS)", fmt="ls", align="right", width=12),
                TableColumn("value_scan", "Scan Value", fmt="cr", align="right", width=12),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
    "trade": TableSchema(
        schema_id="trade",
        title="Trade Route",
        columns=_cols(
            [
                TableColumn("from_system", "From", width=20),
                TableColumn("to_system", "To", width=20),
                TableColumn("commodity", "Commodity", width=18),
                TableColumn("profit", "Profit", fmt="cr", align="right", width=12),
                TableColumn("profit_per_ton", "Profit/t", fmt="cr", align="right", width=10),
                TableColumn("jumps", "Jumps", fmt="int", align="right", width=5),
            ]
        ),
    ),
}


def get_schema(schema_id: str) -> TableSchema | None:
    return SCHEMAS.get(schema_id)


def list_schema_ids() -> list[str]:
    return list(SCHEMAS.keys())
