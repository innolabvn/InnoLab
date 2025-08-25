#!/usr/bin/env python3
"""
Script để clear dữ liệu RAG và SonarQube sau mỗi lần chạy run_demo.py
Author: Assistant
Usage: python clear_data.py [--rag] [--sonar] [--all]
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from typing import Dict, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from modules.mongodb_service import get_mongo_manager
    MONGODB_AVAILABLE = True
except ImportError:
    print("⚠️  Warning: MongoDB service not available")
    MONGODB_AVAILABLE = False

class DataCleaner:
    """Class để clear dữ liệu RAG và SonarQube"""
    
    def __init__(self):
        self.mongo_manager = None
        if MONGODB_AVAILABLE:
            try:
                self.mongo_manager = get_mongo_manager()
                print("✅ Connected to MongoDB")
            except Exception as e:
                print(f"❌ Failed to connect to MongoDB: {e}")
                self.mongo_manager = None
    
    def clear_rag_data(self, confirm: bool = True) -> bool:
        """Clear tất cả dữ liệu RAG trong MongoDB"""
        if not self.mongo_manager:
            print("❌ MongoDB not available")
            return False
        
        if confirm:
            response = input("🗑️  Bạn có chắc chắn muốn xóa TẤT CẢ dữ liệu RAG? (y/N): ")
            if response.lower() != 'y':
                print("❌ Hủy bỏ xóa dữ liệu RAG")
                return False
        
        try:
            print("🧹 Đang clear dữ liệu RAG...")
            
            # Danh sách các collection RAG cần clear
            rag_collections = [
                "rag_documents",
                "bug_rag_documents", 
                "documents",
                "embeddings",
                "metadata",
                "rag_datasets",
                "execution_logs",
                "bug_fixes"
            ]
            
            cleared_count = 0
            for collection_name in rag_collections:
                try:
                    collection = self.mongo_manager.get_collection(collection_name)
                    result = collection.delete_many({})
                    if result.deleted_count > 0:
                        print(f"  ✅ Cleared {result.deleted_count} documents from {collection_name}")
                        cleared_count += result.deleted_count
                    else:
                        print(f"  ℹ️  Collection {collection_name} was already empty")
                except Exception as e:
                    print(f"  ⚠️  Warning: Could not clear {collection_name}: {e}")
            
            print(f"✅ RAG data cleared successfully! Total documents removed: {cleared_count}")
            return True
            
        except Exception as e:
            print(f"❌ Error clearing RAG data: {e}")
            return False
    
    def clear_sonar_project_data(self, project_key: str = None, confirm: bool = True) -> bool:
        """Clear dữ liệu SonarQube project"""
        if not project_key:
            project_key = os.getenv('PROJECT_KEY', 'my-service')
        
        if confirm:
            response = input(f"🗑️  Bạn có chắc chắn muốn xóa dữ liệu SonarQube project '{project_key}'? (y/N): ")
            if response.lower() != 'y':
                print("❌ Hủy bỏ xóa dữ liệu SonarQube")
                return False
        
        try:
            print(f"🧹 Đang clear dữ liệu SonarQube project: {project_key}...")
            
            # Lấy thông tin SonarQube từ environment
            sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
            sonar_token = os.getenv('SONAR_TOKEN')
            
            if not sonar_token:
                print("❌ SONAR_TOKEN not found in environment")
                return False
            
            # Xóa project trong SonarQube (nếu có quyền admin)
            import requests
            
            session = requests.Session()
            session.auth = (sonar_token, "")
            
            # Kiểm tra project có tồn tại không
            check_response = session.get(
                f"{sonar_host}/api/projects/search",
                params={"projects": project_key}
            )
            
            if check_response.status_code == 200:
                projects = check_response.json().get('components', [])
                if projects:
                    # Xóa project
                    delete_response = session.post(
                        f"{sonar_host}/api/projects/delete",
                        data={"project": project_key}
                    )
                    
                    if delete_response.status_code == 204:
                        print(f"✅ SonarQube project '{project_key}' deleted successfully")
                    else:
                        print(f"⚠️  Could not delete project: {delete_response.text}")
                        print("ℹ️  You may need admin privileges to delete projects")
                else:
                    print(f"ℹ️  Project '{project_key}' not found in SonarQube")
            else:
                print(f"❌ Error checking SonarQube: {check_response.text}")
                return False
            
            # Clear local SonarQube cache files
            sonar_dir = os.path.join(os.path.dirname(__file__), '..', 'SonarQ')
            cache_files = [
                f"issues_{project_key}.json",
                ".sonar",
                ".scannerwork"
            ]
            
            for cache_file in cache_files:
                cache_path = os.path.join(sonar_dir, cache_file)
                if os.path.exists(cache_path):
                    try:
                        if os.path.isfile(cache_path):
                            os.remove(cache_path)
                            print(f"  ✅ Removed cache file: {cache_file}")
                        elif os.path.isdir(cache_path):
                            import shutil
                            shutil.rmtree(cache_path)
                            print(f"  ✅ Removed cache directory: {cache_file}")
                    except Exception as e:
                        print(f"  ⚠️  Could not remove {cache_file}: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error clearing SonarQube data: {e}")
            return False
    
    def clear_generated_files(self, source_path: str = None, confirm: bool = True) -> bool:
        """Clear các file code được generate bởi demo"""
        if not source_path:
            source_path = os.getenv('SOURCE_CODE_PATH', 'd:\\ILA\\SonarQ\\source_bug')
        
        if confirm:
            response = input(f"🗑️  Bạn có chắc chắn muốn xóa các file generated trong '{source_path}'? (y/N): ")
            if response.lower() != 'y':
                print("❌ Hủy bỏ xóa generated files")
                return False
        
        try:
            print(f"🧹 Đang clear generated files trong: {source_path}...")
            
            if not os.path.exists(source_path):
                print(f"❌ Source path not found: {source_path}")
                return False
            
            # Tìm và xóa các file code_*.py và backup files
            import glob
            
            patterns = [
                os.path.join(source_path, "code_*.py"),
                os.path.join(source_path, "*.backup.*")
            ]
            
            removed_count = 0
            for pattern in patterns:
                files = glob.glob(pattern)
                for file_path in files:
                    try:
                        os.remove(file_path)
                        print(f"  ✅ Removed: {os.path.basename(file_path)}")
                        removed_count += 1
                    except Exception as e:
                        print(f"  ⚠️  Could not remove {file_path}: {e}")
            
            if removed_count > 0:
                print(f"✅ Generated files cleared successfully! Total files removed: {removed_count}")
            else:
                print("ℹ️  No generated files found to remove")
            
            return True
            
        except Exception as e:
            print(f"❌ Error clearing generated files: {e}")
            return False
    
    def clear_all_data(self, confirm: bool = True) -> bool:
        """Clear tất cả dữ liệu (RAG + SonarQube + Generated files)"""
        if confirm:
            print("⚠️  CẢNH BÁO: Bạn sắp xóa TẤT CẢ dữ liệu:")
            print("  - Tất cả dữ liệu RAG trong MongoDB")
            print("  - SonarQube project data")
            print("  - Generated code files")
            print("  - Cache files")
            response = input("\n🗑️  Bạn có CHẮC CHẮN muốn tiếp tục? (y/N): ")
            if response.lower() != 'y':
                print("❌ Hủy bỏ clear all data")
                return False
        
        print("\n🧹 Bắt đầu clear tất cả dữ liệu...")
        print("=" * 50)
        
        success = True
        
        # Clear RAG data
        print("\n1. Clearing RAG data...")
        if not self.clear_rag_data(confirm=False):
            success = False
        
        # Clear SonarQube data
        print("\n2. Clearing SonarQube data...")
        if not self.clear_sonar_project_data(confirm=False):
            success = False
        
        # Clear generated files
        print("\n3. Clearing generated files...")
        if not self.clear_generated_files(confirm=False):
            success = False
        
        print("\n" + "=" * 50)
        if success:
            print("✅ Tất cả dữ liệu đã được clear thành công!")
        else:
            print("⚠️  Một số dữ liệu có thể chưa được clear hoàn toàn")
        
        return success
    
    def show_data_status(self) -> Dict:
        """Hiển thị trạng thái dữ liệu hiện tại"""
        status = {
            "mongodb_connected": False,
            "rag_documents": 0,
            "execution_logs": 0,
            "sonar_project_exists": False,
            "generated_files": 0
        }
        
        print("📊 Trạng thái dữ liệu hiện tại:")
        print("=" * 40)
        
        # Check MongoDB
        if self.mongo_manager:
            status["mongodb_connected"] = True
            print("✅ MongoDB: Connected")
            
            # Count RAG documents
            try:
                rag_collection = self.mongo_manager.get_collection("rag_documents")
                status["rag_documents"] = rag_collection.count_documents({})
                print(f"  📄 RAG documents: {status['rag_documents']}")
                
                logs_collection = self.mongo_manager.get_collection("execution_logs")
                status["execution_logs"] = logs_collection.count_documents({})
                print(f"  📋 Execution logs: {status['execution_logs']}")
                
            except Exception as e:
                print(f"  ⚠️  Error counting documents: {e}")
        else:
            print("❌ MongoDB: Not connected")
        
        # Check SonarQube project
        project_key = os.getenv('PROJECT_KEY', 'my-service')
        try:
            import requests
            sonar_host = os.getenv('SONAR_HOST', 'http://localhost:9000')
            sonar_token = os.getenv('SONAR_TOKEN')
            
            if sonar_token:
                session = requests.Session()
                session.auth = (sonar_token, "")
                response = session.get(
                    f"{sonar_host}/api/projects/search",
                    params={"projects": project_key}
                )
                
                if response.status_code == 200:
                    projects = response.json().get('components', [])
                    status["sonar_project_exists"] = len(projects) > 0
                    print(f"📊 SonarQube project '{project_key}': {'Exists' if status['sonar_project_exists'] else 'Not found'}")
                else:
                    print(f"⚠️  SonarQube: Could not check project status")
            else:
                print("⚠️  SonarQube: No token configured")
        except Exception as e:
            print(f"⚠️  SonarQube: Error checking status - {e}")
        
        # Check generated files
        source_path = os.getenv('SOURCE_CODE_PATH', 'd:\\ILA\\SonarQ\\source_bug')
        if os.path.exists(source_path):
            import glob
            patterns = [
                os.path.join(source_path, "code_*.py"),
                os.path.join(source_path, "*.backup.*")
            ]
            
            for pattern in patterns:
                status["generated_files"] += len(glob.glob(pattern))
            
            print(f"📁 Generated files: {status['generated_files']}")
        else:
            print(f"⚠️  Source path not found: {source_path}")
        
        print("=" * 40)
        return status

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Clear dữ liệu RAG và SonarQube sau khi chạy demo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clear_data.py --status          # Xem trạng thái dữ liệu
  python clear_data.py --rag             # Clear chỉ dữ liệu RAG
  python clear_data.py --sonar           # Clear chỉ dữ liệu SonarQube
  python clear_data.py --files           # Clear chỉ generated files
  python clear_data.py --all             # Clear tất cả dữ liệu
  python clear_data.py --all --no-confirm # Clear tất cả không cần confirm
        """
    )
    
    parser.add_argument('--rag', action='store_true', help='Clear dữ liệu RAG trong MongoDB')
    parser.add_argument('--sonar', action='store_true', help='Clear dữ liệu SonarQube project')
    parser.add_argument('--files', action='store_true', help='Clear generated code files')
    parser.add_argument('--all', action='store_true', help='Clear tất cả dữ liệu')
    parser.add_argument('--status', action='store_true', help='Hiển thị trạng thái dữ liệu hiện tại')
    parser.add_argument('--no-confirm', action='store_true', help='Không cần confirm (nguy hiểm!)')
    
    args = parser.parse_args()
    
    # Initialize cleaner
    cleaner = DataCleaner()
    
    # Show status if requested
    if args.status:
        cleaner.show_data_status()
        return
    
    # If no specific action, show help
    if not any([args.rag, args.sonar, args.files, args.all]):
        parser.print_help()
        print("\n💡 Tip: Sử dụng --status để xem trạng thái dữ liệu hiện tại")
        return
    
    confirm = not args.no_confirm
    
    print("🧹 FixChain Data Cleaner")
    print("=" * 30)
    
    if args.all:
        cleaner.clear_all_data(confirm=confirm)
    else:
        if args.rag:
            cleaner.clear_rag_data(confirm=confirm)
        
        if args.sonar:
            cleaner.clear_sonar_project_data(confirm=confirm)
        
        if args.files:
            cleaner.clear_generated_files(confirm=confirm)
    
    print("\n✅ Data cleaning completed!")

if __name__ == "__main__":
    main()