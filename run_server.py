import os
import sys
import subprocess

def check_proto_files():
    """Kiểm tra xem proto files đã được generate chưa"""
    return os.path.exists('chat_pb2.py') and os.path.exists('chat_pb2_grpc.py')

def build_proto():
    """Generate code từ proto file"""
    print("🔨 Đang generate code từ chat.proto...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'grpc_tools.protoc',
            '-I.', '--python_out=.', '--grpc_python_out=.', 'chat.proto'
        ], check=True, capture_output=True, text=True)
        print("✓ Đã generate proto files thành công!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi khi generate proto files: {e}")
        print(e.stderr)
        return False
    except FileNotFoundError:
        print("❌ grpcio-tools chưa được cài đặt!")
        print("Chạy: pip install -r requirements.txt")
        return False

def check_dependencies():
    """Kiểm tra dependencies"""
    try:
        import grpc
        import google.protobuf
        return True
    except ImportError as e:
        print(f"❌ Thiếu dependencies: {e}")
        print("Chạy: pip install -r requirements.txt")
        return False

def main():
    print("="*60)
    print("           CHAT SERVER - KHỞI ĐỘNG")
    print("="*60)
    
    # Kiểm tra dependencies
    print("\n📦 Đang kiểm tra dependencies...")
    if not check_dependencies():
        sys.exit(1)
    print("✓ Dependencies OK")
    
    # build proto files 
    if not build_proto():
        sys.exit(1)
    
    # Import và chạy server
    print("\n🚀 Đang khởi động server...")
    print("="*60)
    
    try:
        # Import server module
        import server
        
        # Chạy server
        server.serve()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Server đang dừng...")
        print("✓ Server đã dừng!")
        
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()