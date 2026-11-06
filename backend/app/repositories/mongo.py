"""Kho MongoDB: tất cả cú pháp truy vấn tập trung tại Repository."""
from datetime import datetime, timezone
from pymongo import AsyncMongoClient, ReturnDocument


class MongoRepository:
    """Lưu metadata phụ trợ; không lưu nội dung file của người dùng."""
    def __init__(self, settings):
        """Tạo client async trong cùng event loop → chọn database app."""
        self.client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        self.db = self.client[settings.mongodb_db_name]

    async def initialize(self):
        """Kiểm tra kết nối → tạo TTL cho phiên, state OAuth và khóa tạm."""
        await self.client.admin.command('ping')
        await self.db.refresh_sessions.create_index('expires_at', expireAfterSeconds=0)
        await self.db.oauth_states.create_index('expires_at', expireAfterSeconds=0)
        await self.db.upload_sessions.create_index('expires_at', expireAfterSeconds=0)

    async def get(self, collection, key):
        """Tra document bằng ID cố định, trả model thô cho Service."""
        return await self.db[collection].find_one({'_id': key})

    async def put(self, collection, key, values):
        """Upsert các trường đã được Service cho phép, giữ ID ổn định."""
        await self.db[collection].update_one({'_id': key}, {'$set': values}, upsert=True)

    async def remove(self, collection, key):
        """Xóa một document, dùng khi thu hồi session hoặc OAuth state."""
        await self.db[collection].delete_one({'_id': key})

    async def consume(self, collection, key):
        """Đọc rồi xóa nguyên tử → refresh token/OAuth state chỉ dùng một lần."""
        return await self.db[collection].find_one_and_delete({'_id': key, 'expires_at': {'$gt': datetime.now(timezone.utc)}})

    async def close(self):
        """Đóng pool MongoDB khi lifespan kết thúc."""
        await self.client.close()

    async def collection_names(self):
        """CLI backup hỏi danh sách collection mà không đưa query vào Service."""
        return await self.db.list_collection_names()

    async def records(self, collection):
        """Xuất từng BSON document qua async cursor, tránh gom DB vào RAM."""
        async for record in self.db[collection].find({}):
            yield record

    async def stage_record(self, collection, record):
        """CLI restore ghi staging trước, chưa tác động collection đang chạy."""
        await self.db[collection].insert_one(record)

    async def commit_stage(self, stage, collection):
        """Rename cùng DB là nguyên tử ở cấp collection; chỉ gọi sau validate backup."""
        await self.db[stage].rename(collection, dropTarget=True)

    async def create_collection(self, collection):
        """Giữ được collection rỗng khi khôi phục bản backup."""
        await self.db.create_collection(collection)

    async def drop_stage(self, collection):
        """Dọn collection staging nếu restore bị lỗi hoặc đã hoàn tất."""
        await self.db[collection].drop()

    async def revoke_sessions(self):
        """Restore hoàn tất → thu hồi phiên/state hiện tại; người dùng phải đăng nhập lại."""
        await self.db.refresh_sessions.delete_many({})
        await self.db.oauth_states.delete_many({})
        await self.db.upload_sessions.delete_many({})
