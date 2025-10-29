import time
import threading
import grpc
import queue
import os

from concurrent import futures
import chat_pb2
import chat_pb2_grpc

# from typing import TypedDict

# class myClass (TypedDict):
#     tmp: int 

# a : myClass = {"tmp"}

# ===============================
# DỮ LIỆU LƯU TẠM TRONG BỘ NHỚ
# ===============================
users = {}  # user_id -> {"username": ..., "password":....,  "status": ..., "stream": ...}
groups = {}  # group_id -> {"group_name": ..., "creator_id": ..., "member_ids": [...], "created_at": ...}
messages = []  # Danh sách tất cả tin nhắn gửi trong hệ thống (tuỳ chọn)
delimiter = "============== History ================"
lock = threading.Lock()

# logging
def log_message(message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    log_entry = f"[{timestamp}] {message}"
    print (log_entry)
    
    with open("server.log", "a", encoding="utf-8") as log_file:
        log_file.write(log_entry + "\n")

# ===============================
# TRIỂN KHAI SERVICE
# ===============================
def checkUserExist(username):
    for uid, u in users.items():
        if u["username"] == username:
            return True
    return False

def append_to_file(filename, content):
    with open(filename, "a", encoding="utf-8") as f:
        timestamp = time.strftime('%H:%M:%S', time.localtime(content.timestamp))
        f.write(f"[{timestamp}] {content.sender_name} : {content.content}\n")
        
def read_from_file(filename, num_lines = 5):
    with open(filename, "r", encoding="utf-8") as f:
        all_lines = [line.strip() for line in f.readlines()]
        delimiter_index = all_lines.index(delimiter)
        history_line = all_lines[delimiter_index + 1:]
        # Lấy num_lines dòng cuối cùng
        if len(history_line) >= num_lines:
            return history_line[-num_lines:]
        return history_line

    
class ChatService(chat_pb2_grpc.ChatServiceServicer):
    def RegisterUser(self, request, context):
        if checkUserExist(request.username):
            return chat_pb2.RegisterResponse(success=False, user_id="", message="Tên người dùng đã tồn tại, hãy đổi tên khác")
        with lock:
            user_id = f"u{len(users) + 1}"
            users[user_id] = {
                "username": request.username,
                "password": request.password,
                "status": "online",
                "stream":queue.Queue()
            }
        log_message(f"👤 User đăng ký: {request.username} (id={user_id})")
        return chat_pb2.RegisterResponse(success=True, user_id=user_id, message="Đăng ký thành công")
    
    def LoginUser(self, request, context):
        for uid, u in users.items():
            if u["username"] == request.username:
                if u["password"] == request.password:
                    u["status"] = "online"
                    log_message(f"🔐 User đăng nhập: {request.username} (id={uid})")
                    return chat_pb2.LoginResponse(success=True, user_id=uid, message="Đăng nhập thành công")
                else:
                    return chat_pb2.LoginResponse(success=False, user_id="", message="Mật khẩu không đúng")
        return chat_pb2.LoginResponse(success=False, user_id="", message="Người dùng không tồn tại")
    
    def ListUsers(self, request, context):
        """Trả về danh sách tất cả user"""
        user_list = [
            chat_pb2.User(
                user_id=uid,
                username=data["username"], 
                status=data["status"]
            )
            for uid, data in users.items()
        ]
        log_message(f"👥 Có {len(user_list)} người dùng trong hệ thống.")
        return chat_pb2.ListUsersResponse(users=user_list)

    def SearchUser(self, request, context):
        query = request.query.lower()
        matched_users = [
            chat_pb2.User(user_id=uid, username=u["username"], status=u["status"])
            for uid, u in users.items()
            if query in u["username"].lower() and uid != request.requester_id
        ]
        log_message(f"🔍 {request.requester_id} tìm: '{request.query}', thấy {len(matched_users)} kết quả")
        return chat_pb2.SearchResponse(users=matched_users)
    
    def SendPrivateMessage(self, request, context):
        if request.receiver_id not in users:
            return chat_pb2.MessageResponse(success=False, message="Người nhận không tồn tại")

        msg = chat_pb2.ChatMessage(
            message_id=f"msg_{len(messages) + 1}",
            sender_id=request.sender_id,
            sender_name=users[request.sender_id]["username"],
            content=request.content,
            timestamp=int(time.time()),
            message_type="private",
            target_id=request.receiver_id
        )
        messages.append(msg)
        file_name = f"history/{'_'.join(sorted([request.sender_id, request.receiver_id]))}.txt"
        if not os.path.exists(file_name):
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(f"{delimiter}\n")
        append_to_file(file_name, msg)
        
        log_message(f"💌 Tin nhắn riêng từ {request.sender_id} → {request.receiver_id}: {request.content}")

        # Gửi tin cho người nhận nếu đang online
        stream = users[request.receiver_id].get("stream")
        
        if stream:
            stream.put(msg)
        # if stream:
        #     items = list(stream.queue)  # ⚠️ dùng thuộc tính nội bộ .queue
        #     log_message(f"📦 Queue hiện có {len(items)} phần tử:")
        #     for i, item in enumerate(items, 1):
        #         log_message(f"  {i}. {item}")
        # else :
        #     log_message("🚫 Không có stream cho người nhận")
        # log_message (users[request.receiver_id])

        return chat_pb2.MessageResponse(success=True, message="Đã gửi tin nhắn riêng")
    
    def GetPrivateChatHistory(self, request, context):
        file_name = f"history/{'_'.join(sorted([request.sender_id, request.receiver_id]))}.txt"
        if not os.path.exists(file_name):
            return chat_pb2.GetPrivateChatResponse(messages=[])
        if request.sender_id not in users or request.receiver_id not in users:
            return chat_pb2.GetPrivateChatResponse(messages=[])

        history_msg = read_from_file(file_name, num_lines=request.limit)
        log_message (f"🕵️ Lịch sử chat riêng giữa {request.sender_id} và {request.receiver_id}, lấy {len(history_msg)} tin nhắn")
        return chat_pb2.GetPrivateChatResponse(messages=history_msg)

    # -------------------------------
    # GROUP FUNCTIONS
    # -------------------------------
    def CreateGroup(self, request, context):
        with lock:
            group_id = f"g{len(groups) + 1}"
            groups[group_id] = {
                "group_name": request.group_name,
                "creator_id": request.creator_id,
                "member_ids": list(set(request.member_ids) | {request.creator_id}),
                "created_at": int(time.time())
            }
        log_message(f"👥 Nhóm mới: {request.group_name} (id={group_id}), (creator_id: {request.creator_id})")
        # create txt file with gid name
        with open(f"history/{group_id}.txt", "w", encoding="utf-8") as f:
            f.write(f"Group ID: {group_id}\n")
            f.write(f"Group Name: {request.group_name}\n")
            f.write(f"Creator ID: {request.creator_id}\n")
            f.write(f"Member IDs: {', '.join(groups[group_id]['member_ids'])}\n")
            f.write(f"Created At: {time.ctime(groups[group_id]['created_at'])}\n")
            f.write(f"{delimiter}\n")
        
        return chat_pb2.CreateGroupResponse(success=True, group_id=group_id, message="Tạo nhóm thành công")
    
    
    def GetGroups ( self, request, context):
        group_list = [
            chat_pb2.Group(
                group_id=g_id,
                group_name=g["group_name"],
                creator_id=g["creator_id"],
                member_ids=g["member_ids"],
                created_at=g["created_at"]
            )
            for g_id, g in groups.items()
        ]
        log_message(f"👥 Có {len(group_list)} nhóm trong hệ thống.")
        return chat_pb2.GetGroupsResponse(groups=group_list)

    def JoinGroup(self, request, context):
        group = groups.get(request.group_id)
        if not group:
            return chat_pb2.JoinGroupResponse(success=False, message="Nhóm không tồn tại")

        with lock:
            if request.user_id not in group["member_ids"]:
                group["member_ids"].append(request.user_id)
        log_message(f"✅ {request.user_id} tham gia nhóm {request.group_id}")
        return chat_pb2.JoinGroupResponse(success=True, message="Tham gia nhóm thành công")
    
    def LeaveGroup(self, request, context):
        group = groups.get(request.group_id)
        if not group:
            return chat_pb2.LeaveGroupResponse(success=False, message="Nhóm không tồn tại")

        with lock:
            if request.user_id in group["member_ids"]:
                group["member_ids"].remove(request.user_id)
        log_message(f"❌ {request.user_id} rời nhóm {request.group_id}")
        return chat_pb2.LeaveGroupResponse(success=True, message="Rời nhóm thành công")

    def SendGroupMessage(self, request, context):
        if request.group_id not in groups:
            log_message (f"❌ Nhóm {request.group_id} không tồn tại")
            return chat_pb2.MessageResponse(success=False, message="Nhóm không tồn tại")
        
        if request.sender_id not in groups[request.group_id]["member_ids"]:
            log_message (f"❌ {request.sender_id} không phải thành viên nhóm {request.group_id}")
            return chat_pb2.MessageResponse(success=False, message="Bạn không phải thành viên nhóm")

        msg = chat_pb2.ChatMessage(
            message_id=f"msg_{len(messages) + 1}",
            sender_id=request.sender_id,
            sender_name=users[request.sender_id]["username"],
            content=request.content,
            timestamp=int(time.time()),
            message_type="group",
            target_id=request.group_id
        )
        messages.append(msg)
        append_to_file(f"history/{request.group_id}.txt", msg)
        
        log_message(f"💬 Tin nhắn nhóm [{request.group_id}] từ {request.sender_id}: {request.content}")

        # Gửi tin nhắn cho các thành viên online
        for uid in groups[request.group_id]["member_ids"]:
            if uid == request.sender_id:
                continue
            stream = users.get(uid, {}).get("stream")
            if stream:
                stream.put(msg)

        return chat_pb2.MessageResponse(success=True, message="Đã gửi tin nhắn nhóm")
    
    def GetGroupChatHistory(self, request, context):
        if request.group_id not in groups:
            log_message (f"❌ Nhóm {request.group_id} không tồn tại")
            return chat_pb2.GetGroupChatResponse(messages=[])

        history_msg = read_from_file(f"history/{request.group_id}.txt", num_lines=request.limit)
        log_message (f"🕵️ Lịch sử chat nhóm {request.group_id}, lấy {len(history_msg)} tin nhắn")
        return chat_pb2.GetGroupChatResponse(messages=history_msg)
        


    def GetUserGroups(self, request, context):
        user_groups = [
            chat_pb2.Group(
                group_id=g_id,
                group_name=g["group_name"],
                creator_id=g["creator_id"],
                member_ids=g["member_ids"],
                created_at=g["created_at"]
            )
            for g_id, g in groups.items()
            if request.user_id in g["member_ids"]
        ]
        log_message(f"📂 {request.user_id} có {len(user_groups)} nhóm")
        return chat_pb2.GetUserGroupsResponse(groups=user_groups)

    def GetGroupMembers(self, request, context):
        group = groups.get(request.group_id)
        if not group:
            return chat_pb2.GetGroupMembersResponse()
        members = [
            chat_pb2.User(user_id=uid, username=users[uid]["username"], status=users[uid]["status"])
            for uid in group["member_ids"] if uid in users
        ]
        log_message (f"👥 Nhóm {request.group_id} có {len(members)} thành viên")
        return chat_pb2.GetGroupMembersResponse(members=members)


                
    def MessageStream(self, request_iterator, context):
        """Streaming hai chiều: client gửi 'connect', server gửi tin nhắn"""
        try:
            for req in request_iterator:
                user_id = req.user_id
                # log_message (f"📨 Yêu cầu stream từ {user_id}: {req.action}")
                if req.action == "connect":
                    users[user_id]["status"] = "online"
                    while not users[user_id]["stream"].empty():
                        msg = users[user_id]["stream"].get()
                        yield chat_pb2.MessageStreamResponse(message=msg)
                else: 
                    users[user_id]["status"] = "offline"
                    log_message(f"❎ {user_id} stream đóng")

        except grpc.RpcError as e:
            log_message(f"⚠️ Stream lỗi: {e}")
        finally:
            if user_id and user_id in users:
                users[user_id]["status"] = "offline"
                log_message(f"❎ {user_id} stream đóng")


def clear_history_files():
    history_dir = "history"
    if os.path.exists(history_dir):
        for filename in os.listdir(history_dir):
            file_path = os.path.join(history_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    log_message(f"🗑️ Xoá file lịch sử: {file_path}")
            except Exception as e:
                log_message(f"❌ Lỗi khi xoá file {file_path}: {e}")
# ===============================
# HÀM KHỞI CHẠY SERVER
# ===============================
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    log_message("🚀 Chat server đang chạy trên cổng 50051...")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        log_message("🛑 Đang tắt server...")
        clear_history_files()
        server.stop(0)
