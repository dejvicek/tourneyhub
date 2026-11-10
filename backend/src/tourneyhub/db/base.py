from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeEngine


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    # Any: the keys are Python types of every kind, the values any SQL type.
    type_annotation_map: ClassVar[dict[Any, TypeEngine[Any]]] = {
        datetime: DateTime(timezone=True)
    }


def str_enum[E: StrEnum](enum: type[E], *, name: str) -> Enum:
    """A varchar column without a length and a named CHECK of the enum's values."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=None,  # undocumented; a test pins the varchar without a length
        values_callable=lambda members: [member.value for member in members],
    )
