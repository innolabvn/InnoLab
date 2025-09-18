#!/usr/bin/env python3
"""
Script để khởi động Serena MCP server và mở dashboard
"""

import subprocess
import time
import webbrowser
import sys
import os

def start_serena_server():
    """Khởi động Serena MCP server"""
    print("🚀 Đang khởi động Serena MCP server...")
    
    # Chuyển đến thư mục project
    project_dir = "/Users/fahn040-174/Projects/Sprint 15/InnoLab/FixChain"
    os.chdir(project_dir)
    
    try:
        # Khởi động Serena MCP server
        cmd = [
            "uvx",
            "--from",
            "git+https://github.com/oraios/serena",
            "serena",
            "start-mcp-server",
            "--project",
            project_dir
        ]
        
        print(f"📝 Chạy lệnh: {' '.join(cmd)}")
        
        # Khởi động server trong background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print("⏳ Đợi server khởi động...")
        time.sleep(5)  # Đợi server khởi động
        
        # Kiểm tra xem process có chạy không
        if process.poll() is None:
            print("✅ Serena MCP server đã khởi động thành công!")
            print("📊 Dashboard sẽ có sẵn tại: http://localhost:24282/dashboard/index.html")
            
            # Mở dashboard trong browser
            dashboard_url = "http://localhost:24282/dashboard/index.html"
            print(f"🌐 Đang mở dashboard: {dashboard_url}")
            webbrowser.open(dashboard_url)
            
            print("\n📋 Thông tin server:")
            print(f"   - PID: {process.pid}")
            print(f"   - Project: {project_dir}")
            print(f"   - Dashboard: {dashboard_url}")
            print("\n💡 Để dừng server, nhấn Ctrl+C")
            
            # Đợi user dừng server
            try:
                process.wait()
            except KeyboardInterrupt:
                print("\n🛑 Đang dừng Serena server...")
                process.terminate()
                process.wait()
                print("✅ Server đã dừng.")
                
        else:
            # Server không khởi động được
            stdout, stderr = process.communicate()
            print("❌ Không thể khởi động Serena server!")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return False
            
    except FileNotFoundError:
        print("❌ Lỗi: uvx không được tìm thấy!")
        print("💡 Hãy cài đặt uvx bằng lệnh:")
        print("   curl -LsSf https://astral.sh/uv/install.sh | sh")
        return False
    except Exception as e:
        print(f"❌ Lỗi không mong đợi: {e}")
        return False
        
    return True

def main():
    """Main function"""
    print("🎯 Serena MCP Server Launcher")
    print("=" * 40)
    
    if start_serena_server():
        print("\n🎉 Hoàn thành!")
    else:
        print("\n💥 Có lỗi xảy ra khi khởi động server.")
        sys.exit(1)

if __name__ == "__main__":
    main()