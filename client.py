import grpc
import threading
import time
import queue
import chat_pb2
import chat_pb2_grpc


class ChatClient:
    def __init__(self, host="localhost", port=50051):
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
        self.user_id = None
        self.username = None
        self.running = True

    # -------------------------------
    # login 
    # -------------------------------
    def register(self, username,password):
        resp = self.stub.RegisterUser(chat_pb2.RegisterRequest(username=username, password=password))
        if resp.success:
            self.user_id = resp.user_id
            self.username = username
            print(f"✅ Đăng ký thành công! User ID: {self.user_id}")
        else:
            print("❌ Đăng ký thất bại:", resp.message)
        
        return resp.success
            
    def login (self, username,password):
        resp = self.stub.LoginUser(chat_pb2.LoginRequest(username=username, password=password))
        if resp.success:
            self.user_id = resp.user_id
            self.username = username
            print(f"✅ Đăng nhập thành công! User ID: {self.user_id}")
        else:
            print("❌ Đăng nhập thất bại:", resp.message)
            
        return resp.success
        
    def list_users(self):
        response = self.stub.ListUsers(chat_pb2.ListUsersRequest())
        print("\n📋 Danh sách người dùng:")
        for u in response.users:
            print(f"- {u.username}; UID: ({u.user_id}); STATUS: [{u.status}]")

    # -------------------------------
    # Tìm kiếm người dùng
    # -------------------------------
    def search_user(self, query):
        resp = self.stub.SearchUser(chat_pb2.SearchRequest(query=query, requester_id=self.user_id))
        if not resp.users:
            print("❌ Không tìm thấy người dùng nào.")
        else:
            print("🔍 Kết quả tìm kiếm:")
            for u in resp.users:
                print(f" - {u.username} ({u.user_id}) [{u.status}]")
                
    # -------------------------------
    # Gửi tin nhắn riêng
    # -------------------------------
    def send_private_message(self, receiver_id, content):
        resp = self.stub.SendPrivateMessage(
            chat_pb2.PrivateMessageRequest(sender_id=self.user_id, receiver_id=receiver_id, content=content)
        )
        if not resp.success:
            print("❌", resp.message)
            
    def get_private_history(self, receiver_id, limit=5):
        resp = self.stub.GetPrivateChatHistory(
            chat_pb2.GetPrivateChatRequest(sender_id =self.user_id,receiver_id = receiver_id , limit=limit)
        )
        if not resp.messages:
            print("❌ Không có tin nhắn nào trong cuộc trò chuyện.")
        else:
            print(f"🕑 Lịch sử tin nhắn trực tiếp với user (User ID: {receiver_id}):")
            for msg in resp.messages:
                print(f"> {msg}")

    # -------------------------------
    # Mở stream nhận tin nhắn realtime
    # -------------------------------
    def start_stream(self, keepalive_interval=1.0):
        
        def request_generator():
            yield chat_pb2.MessageStreamRequest(user_id=self.user_id, action="connect")
            while self.running:
                try:
                    time.sleep(1)
                    yield chat_pb2.MessageStreamRequest(user_id=self.user_id, action="connect")
                except queue.Empty:
                    continue
        def receive_messages():
            try:
                print(f"🔄 Đã kết nối stream...")
                # Nhận messages từ server
                for response in self.stub.MessageStream(request_generator()):
                    # Kiểm tra response có message không
                    if not hasattr(response, 'message') or not response.message.sender_id:
                        continue
                    msg = response.message

                    # Format timestamp
                    timestamp = time.strftime('%H:%M:%S', time.localtime(msg.timestamp))
                    
                    # Hiển thị message theo loại
                    if msg.message_type == "group":
                        
                        print(f"\n📢 [{timestamp}] [Group {msg.target_id}] {msg.sender_name}: {msg.content}")
                    else:
                        print(f"\n💬 [{timestamp}] [Private] {msg.sender_name}: {msg.content}")
                    
                    print("> ", end='', flush=True)
                    
            except grpc.RpcError as e:
                if self.running:
                    print(f"\n⚠️  Lỗi stream: {e}")
                    if e.code() == grpc.StatusCode.UNAVAILABLE:
                        print("Server không khả dụng. Vui lòng kiểm tra server đang chạy.")
            except Exception as e:
                print(f"\n❌ Lỗi không mong muốn: {e}")
            finally:
                if self.running:
                    print("\n❎ Stream đã ngắt kết nối")
        
        self.running = True
        self.stream_thread = threading.Thread(target=receive_messages, daemon=True)
        self.stream_thread.start()
        
        # Chờ một chút để stream kết nối
        time.sleep(0.5)

    def stop_stream(self):
        """Dừng client"""
        print ("stop")
        self.running = False
        time.sleep(0.2)
        if hasattr(self, 'stream_thread') and self.stream_thread:
            self.stream_thread.join(timeout=2)
        self.channel.close()
        print ( "Ngắt kết nối server")
        
    # -------------------------------
    # Tạo nhóm
    # -------------------------------
    def create_group(self, name, members):
        resp = self.stub.CreateGroup(
            chat_pb2.CreateGroupRequest(creator_id=self.user_id, group_name=name, member_ids=members)
        )
        if resp.success:
            print(f"✅ Đã tạo nhóm '{name}' (ID: {resp.group_id})")
        else:
            print("❌ Tạo nhóm thất bại:", resp.message)
    
    def get_groups( self):
        resp = self.stub.GetGroups(chat_pb2.GetGroupsRequest())
        if resp.groups == []:
            print("📭 Hiện không có nhóm nào trong hệ thống.")
            return
        for g in resp.groups:
            formatted = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(g.created_at))
            members_num = len(g.member_ids)
            print(f" - {g.group_name} (ID: {g.group_id}) (Created by: {g.creator_id}) (Members: {members_num}) (Created at: {formatted})")
            
    def get_user_groups(self):
        resp = self.stub.GetUserGroups(chat_pb2.GetUserGroupsRequest(user_id=self.user_id))
        if not resp.groups:
            print("📭 Bạn chưa tham gia nhóm nào.")
        else:
            print("📂 Danh sách nhóm bạn đã tham gia:")
            for g in resp.groups:
                members_num = len(g.member_ids)
                print(f" - {g.group_name} (ID: {g.group_id}) (Created by: {g.creator_id}) (Members: {members_num})")

    def get_group_members(self, group_id):
        resp = self.stub.GetGroupMembers(chat_pb2.GetGroupMembersRequest(group_id=group_id))
        if not resp.members:
            print("❌ Nhóm không có thành viên nào.")
        else:
            print(f"👥 Thành viên nhóm với gid: {group_id}:")
            for m in resp.members:
                print (f" - {m.username} (ID: {m.user_id}) [{m.status}]")

    def join_group(self, group_id):
        resp = self.stub.JoinGroup(chat_pb2.JoinGroupRequest(user_id=self.user_id, group_id=group_id))
        print(resp.message)
    def leave_group(self, group_id):
        resp = self.stub.LeaveGroup(chat_pb2.LeaveGroupRequest(user_id=self.user_id, group_id=group_id))
        print(resp.message)
        
    def get_group_history(self, group_id, limit=5):
        resp = self.stub.GetGroupChatHistory(
            chat_pb2.GetGroupChatRequest(group_id=group_id, limit=limit)
        )
        if not resp.messages:
            print("❌ Không có tin nhắn nào trong nhóm.")
        else:
            print(f"🕑 Lịch sử tin nhắn nhóm (Group ID: {group_id}):")
            for msg in resp.messages:
                print(f"> {msg}")

    # -------------------------------
    # Gửi tin nhắn nhóm
    # -------------------------------
    def send_group_message(self, group_id, content):
        resp = self.stub.SendGroupMessage(
            chat_pb2.GroupMessageRequest(sender_id=self.user_id, group_id=group_id, content=content)
        )
        if not resp.success:
            print("❌", resp.message)


def main():
    print("=" * 50)
    print("💬 CHAT CLIENT (gRPC)")
    print("=" * 50)

    client = ChatClient()
    # login hoặc register
    print ("[1] Đăng ký ")
    print ("[2] Đăng nhập ")
    print ("[3] Thoát")
    cont_flag = True
    while cont_flag:
        
        choice = input("Chọn (1/2/3): ")
        if choice == "1":
            username = input("Nhập username của bạn: ")
            password = input("Nhập mật khẩu của bạn: ")
            if client.register(username, password): cont_flag = False
        elif choice == "2":
            username = input("Nhập username của bạn: ")
            password = input("Nhập mật khẩu của bạn: ")
            if client.login(username,password): cont_flag = False
        elif choice == "3":
            print("👋 Đang thoát...")
            return
        else:
            print("❓ Hãy thử lại")
            
            
    print("\nLệnh có sẵn:")
    print(" =================== SEARCH ======================")
    print(" search <tên>              → Tìm user")
    print(" ul                        → Xem danh sách user")
    print(" groups                    → Xem tất cả nhóm")
    print(" sgroup                    → Xem nhóm của bạn")
    print(" gmem <group_id>           → Xem thành viên nhóm")
    print(" =================== MSG =========================")
    print(" msg <user_id> <nội dung>  → Gửi tin nhắn riêng")
    print(" gmsg <group_id> <nội dung>→ Gửi tin nhóm")
    print(" =================== GROUP =======================")
    print(" group <tên> <id1,id2,...> → Tạo nhóm")
    print(" join <group_id>           → Tham gia nhóm")
    print(" leave <group_id>          → Rời nhóm")
    print(" =================== HISTORY ==================== ")
    print(" uh <user_id> <lines_num>  → Xem lịch sử tin nhắn riêng")
    print(" gh <group_id> <lines_num> → Xem lịch sử tin nhắn nhóm")
    print(" exit                      → Thoát")  
    
    client.start_stream()



    try:
        while True:
            cmd = input("> ").strip()
            if not cmd:
                continue

            if cmd.startswith("search "):
                _, query = cmd.split(" ", 1)
                client.search_user(query)

            elif cmd.startswith("msg "):
                try:
                    _, uid, msg = cmd.split(" ", 2)
                    client.send_private_message(uid, msg)
                except ValueError:
                    print("❌ Sai cú pháp. Ví dụ: msg u2 Hello")

            elif cmd.startswith("group "):
                try:
                    _, name, ids = cmd.split(" ", 2)
                    members = [m.strip() for m in ids.split(",")]
                    client.create_group(name, members)
                except ValueError:
                    print("❌ Sai cú pháp. Ví dụ: group team u2,u3")

            elif cmd.startswith("join "):
                _, gid = cmd.split(" ", 1)
                client.join_group(gid)

            elif cmd == "groups":
                client.get_groups()
                
            elif cmd == "sgroups":
                client.get_user_groups()
            
            elif cmd.startswith("gmem "):
                _, gid = cmd.split(" ", 1)
                client.get_group_members(gid)

            elif cmd.startswith("gmsg "):
                try:
                    _, gid, msg = cmd.split(" ", 2)
                    client.send_group_message(gid, msg)
                except ValueError:
                    print("❌ Sai cú pháp. Ví dụ: gmsg g1 Hello nhóm!")

            elif cmd == "ul":
                client.list_users()
                
            elif cmd.startswith("leave "):
                try: 
                    _, gid = cmd.split(" ", 1)
                    client.leave_group(gid)
                   
                except ValueError:
                    print("❌ Sai cú pháp. Ví dụ: leave g1")
                    
            elif cmd.startswith("gh "):
                parts = [p.strip() for p in cmd.split(" ")]
                if len(parts) == 2:
                    _, gid = parts
                    client.get_group_history(gid)
                elif len(parts) == 3:
                    _, gid, lines_num = parts
                    lines_num = int(lines_num)
                    client.get_group_history(gid, limit=lines_num)

            elif cmd.startswith("uh "):
                parts = [p.strip() for p in cmd.split(" ")]
                if len(parts) == 2:
                    _, uid = parts
                    client.get_private_history(uid)
                elif len(parts) == 3:
                    _, uid, lines_num = parts
                    lines_num = int(lines_num)
                    client.get_private_history(uid, limit=lines_num)

            elif cmd == "exit":
                print("👋 Đang thoát...")
                break

            else:
                print("❓ Lệnh không hợp lệ.")
    except KeyboardInterrupt:
        pass
    finally:
        client.stop_stream()
        print("✅ Đã thoát client.")


if __name__ == "__main__":
    main()
