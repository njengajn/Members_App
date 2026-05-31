from channels.generic.websocket import AsyncWebsocketConsumer
import json

class AuditLogConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        await self.channel_layer.group_add("audit_logs", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("audit_logs", self.channel_name)

    async def send_alert(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"]
        }))