"""项目专用的 SQLAlchemy 存储后端。

``CCAgentStorage`` 继承 agentscope 的 ``AsyncSQLAlchemyStorage``，为
SQL 后端补齐 channel 持久化能力——无需改 agentscope 内嵌副本即可让
渠道功能在 SQL 后端下可用。

设计要点：``ChannelRecord`` 的时间戳是 ISO 字符串而非 ``datetime``，不能
复用 ``AsyncSQLAlchemyStorage`` 的通用 ``_write_row`` / ``_from_record`` /
``_to_record``（它们假设 datetime）。因此 channel 读写绕过通用 mapper：
``payload`` 列存完整 record dump（读取的唯一真相来源），``user_id`` /
``channel_type`` / ``platform_bot_id`` 仅作索引与唯一性投影。``ChannelRow``
继承 agentscope 的 ``_JsonRecordMixin``，以便 ``_Base.metadata.create_all``
自动建表。
"""

from datetime import UTC, datetime

from agentscope.app.storage import ChannelRecord
from agentscope.app.storage._sql import AsyncSQLAlchemyStorage

# _JsonRecordMixin 是 SQL 后端声明式表的唯一扩展点——继承它才能让
# channels 表进入 _Base.metadata，从而被 create_tables=True 自动创建。
# 这是把 channel 适配隔离到应用层、同时复用框架建表机制的最小耦合。
from agentscope.app.storage._sql._tables import _JsonRecordMixin
from sqlalchemy import String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

# 对齐 agentscope _tables._ID_LEN（列长度统一为 255）。
_ID_LEN = 255


def _utcnow() -> datetime:
    """Naive UTC timestamp（对齐 agentscope._sql._storage._utcnow）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _to_naive_utc(dt: datetime) -> datetime:
    """把 dt 归一化为 naive UTC（对齐 agentscope._sql._storage._to_naive_utc）。"""
    return dt.astimezone(UTC).replace(tzinfo=None)


class ChannelRow(_JsonRecordMixin):
    """``ChannelRecord`` 的 SQL 表。

    与其它 ``_JsonRecordMixin`` 表不同，channel 读写绕过通用 mapper
    （``ChannelRecord`` 时间戳是 ISO str），故 ``payload`` 是读取的唯一
    来源，下面的提升列仅服务于查询过滤与 ``platform_bot_id`` 唯一性。
    """

    __tablename__ = "channels"

    user_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        nullable=False,
        index=True,
    )
    channel_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    # 由 ChannelService 从 credentials 提取，非 ChannelRecord 字段。
    # 全局唯一——两个渠道不能绑定同一个平台 bot。
    platform_bot_id: Mapped[str] = mapped_column(
        String(_ID_LEN),
        nullable=False,
    )

    # agentscope>=2.0.7 的 _tables 也定义了同名 channels 表（原生 channel
    # 持久化）。本模块先 import 上游 _tables（见上方 import），再以
    # extend_existing 重定义——让本表结构（payload 为读取真相源，兼容既有
    # SQLite 数据）胜出；上游原生 channel 方法已被下方 CCAgentStorage
    # 全量覆盖，不会执行。
    __table_args__ = (
        UniqueConstraint("platform_bot_id", name="uq_channels_platform_bot_id"),
        {"extend_existing": True},
    )

    _indexed_fields = ("user_id", "channel_type")


class CCAgentStorage(AsyncSQLAlchemyStorage):
    """``AsyncSQLAlchemyStorage`` + channel 持久化。

    覆盖 ``StorageBase`` 的 6 个 channel 方法（基类默认 raise
    NotImplementedError），让渠道管理 API 与生命周期 dispatcher 在 SQL
    后端下正常工作。复用父类的 ``_session()`` / ``_upsert_stmt()``。
    """

    async def upsert_channel(
        self,
        record: ChannelRecord,
        platform_bot_id: str,
    ) -> str:
        """Persist a channel record, refreshing its indexes.

        ``platform_bot_id`` 存在独立的 UNIQUE 列——DB 约束是
        ``ChannelService`` read-then-write 唯一性校验的并发兜底。
        ``updated_at`` 每次刷新（生命周期 dispatcher 用它做 reconcile
        版本号）。
        """
        record.updated_at = _utcnow().isoformat()
        values = {
            "id": record.id,
            "created_at": _to_naive_utc(
                datetime.fromisoformat(record.created_at),
            ),
            "updated_at": _to_naive_utc(
                datetime.fromisoformat(record.updated_at),
            ),
            "payload": record.model_dump(mode="json"),
            "user_id": record.user_id,
            "channel_type": record.channel_type,
            "platform_bot_id": platform_bot_id,
        }
        update_cols = (
            "updated_at",
            "payload",
            "user_id",
            "channel_type",
            "platform_bot_id",
        )
        async with self._session() as sess:
            await sess.execute(
                self._upsert_stmt(ChannelRow, values, ["id"], update_cols),
            )
            await sess.commit()
        return record.id

    async def get_channel(
        self,
        channel_id: str,
    ) -> ChannelRecord | None:
        """Fetch a channel record by its global id."""
        async with self._session() as sess:
            row = await sess.get(ChannelRow, channel_id)
        if row is None:
            return None
        return ChannelRecord.model_validate(row.payload)

    async def list_channels(
        self,
        user_id: str,
    ) -> list[ChannelRecord]:
        """Return every channel record owned by *user_id*."""
        async with self._session() as sess:
            rows = (
                (
                    await sess.execute(
                        select(ChannelRow).where(
                            ChannelRow.user_id == user_id,
                        ),
                    )
                )
                .scalars()
                .all()
            )
        return [ChannelRecord.model_validate(r.payload) for r in rows]

    async def list_all_channels(self) -> list[ChannelRecord]:
        """Return every channel record across all users."""
        async with self._session() as sess:
            rows = (await sess.execute(select(ChannelRow))).scalars().all()
        return [ChannelRecord.model_validate(r.payload) for r in rows]

    async def delete_channel(
        self,
        channel_id: str,
        platform_bot_id: str,
    ) -> bool:
        """Delete a channel record by id.

        *platform_bot_id* 仅为与 Redis 后端签名对齐而保留——这里的
        UNIQUE 列随行一起删除，参数未使用。
        """
        del platform_bot_id
        async with self._session() as sess:
            result = await sess.execute(
                delete(ChannelRow).where(ChannelRow.id == channel_id),
            )
            await sess.commit()
        return result.rowcount > 0

    async def get_channel_id_by_platform_bot_id(
        self,
        platform_bot_id: str,
    ) -> str | None:
        """Return the channel id bound to *platform_bot_id*, if any."""
        async with self._session() as sess:
            channel_id = (
                await sess.execute(
                    select(ChannelRow.id).where(
                        ChannelRow.platform_bot_id == platform_bot_id,
                    ),
                )
            ).scalar_one_or_none()
        return channel_id
