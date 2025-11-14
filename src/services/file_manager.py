"""
File Management Service
Handles file upload, caching, and management for OpenAI API
"""

import os
import json
from typing import Optional
from openai import OpenAI


class FileManager:
    """Manages file operations with OpenAI API and local caching"""
    
    def __init__(self, openai_client: OpenAI, cache_file: str = "../data/cache/file_cache_openai.json"):
        """
        Initialize FileManager
        
        Args:
            openai_client: OpenAI client instance (同步版本)
            cache_file: Path to cache file for storing file IDs
        """
        self.client = openai_client
        self.cache_file = cache_file
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists"""
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
    
    def load_cache(self) -> dict:
        """
        Read the cache in JSON format
        
        Returns:
            dict: Cache data mapping cache keys to file IDs
        """
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def save_cache(self, cache: dict) -> None:
        """
        Save the cache in JSON format
        
        Args:
            cache: Cache data to save
        """
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    
    def upload_if_needed(self, path: str, cache_key: str, purpose: str = "assistants") -> str:
        """
        Get the file ID if it has already been uploaded.
        If not, upload the file to OpenAI and return the file ID.
        
        Args:
            path: Path to the file to upload
            cache_key: Unique key for caching this file
            purpose: OpenAI file purpose (default: "assistants")
        
        Returns:
            str: OpenAI file ID
        
        Note: OpenAI uses file IDs, not URIs
        """
        # Load the cache
        cache = self.load_cache()
        
        # If the file ID is already cached, verify and return it
        if cache_key in cache:
            file_id = cache[cache_key]
            print(f"✅ 已缓存: {cache_key} → {file_id}")
            
            # Verify file still exists on OpenAI
            try:
                self.client.files.retrieve(file_id)
                return file_id
            except Exception as e:
                print(f"⚠️ 缓存的文件已失效，重新上传... (错误: {e})")
                cache.pop(cache_key, None)
        
        # Upload file to OpenAI
        print(f"⏫ 正在上传到 OpenAI: {path} ...")
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        
        with open(path, 'rb') as f:
            uploaded = self.client.files.create(
                file=f,
                purpose=purpose
            )
        
        file_id = uploaded.id
        cache[cache_key] = file_id
        self.save_cache(cache)
        print(f"✅ 上传完成: {cache_key} → {file_id}")
        
        return file_id
    
    def list_all_uploaded_files(self, verbose: bool = True) -> list:
        """
        列出所有已上传的文件
        
        Args:
            verbose: Whether to print detailed information
        
        Returns:
            list: List of file objects
        """
        files = self.client.files.list()
        
        if verbose:
            print("\n📁 OpenAI 已上传文件列表:")
            for f in files.data:
                print(f"""
                        ID:       {f.id}
                        Filename: {f.filename}
                        Purpose:  {f.purpose}
                        Size:     {f.bytes / 1024:.1f} KB
                        Created:  {f.created_at}
                """)
        
        return files.data
    
    def delete_file(self, file_id: str, verbose: bool = True) -> bool:
        """
        删除指定文件
        
        Args:
            file_id: File ID to delete
            verbose: Whether to print status
        
        Returns:
            bool: True if successful
        """
        try:
            self.client.files.delete(file_id)
            if verbose:
                print(f"🗑️ 已删除: {file_id}")
            return True
        except Exception as e:
            if verbose:
                print(f"❌ 删除失败: {file_id} (错误: {e})")
            return False
    
    def delete_all_files(self, verbose: bool = True) -> int:
        """
        删除所有已上传的文件
        
        Args:
            verbose: Whether to print status
        
        Returns:
            int: Number of files deleted
        """
        files = self.client.files.list()
        deleted_count = 0
        
        for f in files.data:
            try:
                self.client.files.delete(f.id)
                if verbose:
                    print(f"🗑️ 已删除: {f.id} ({f.filename})")
                deleted_count += 1
            except Exception as e:
                if verbose:
                    print(f"❌ 删除失败: {f.id} ({f.filename}) - {e}")
        
        if verbose:
            print(f"✅ 已删除 {deleted_count}/{len(files.data)} 个文件")
        
        return deleted_count
    
    def get_file_info(self, file_id: str) -> Optional[dict]:
        """
        获取文件信息
        
        Args:
            file_id: File ID
        
        Returns:
            dict: File information or None if not found
        """
        try:
            file_obj = self.client.files.retrieve(file_id)
            return {
                "id": file_obj.id,
                "filename": file_obj.filename,
                "purpose": file_obj.purpose,
                "bytes": file_obj.bytes,
                "created_at": file_obj.created_at,
            }
        except Exception as e:
            print(f"❌ 获取文件信息失败: {file_id} (错误: {e})")
            return None
    
    def clear_cache(self) -> None:
        """清空缓存文件"""
        self.save_cache({})
        print("✅ 缓存已清空")


# ============= 便捷函数（用于向后兼容 notebook） =============

_default_manager: Optional[FileManager] = None


def _get_default_manager() -> FileManager:
    """Get or create default FileManager instance"""
    global _default_manager
    if _default_manager is None:
        from openai import OpenAI
        import os
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        _default_manager = FileManager(client)
    return _default_manager


def load_cache() -> dict:
    """Read the cache in JSON format"""
    return _get_default_manager().load_cache()


def save_cache(cache: dict) -> None:
    """Save the cache in JSON format"""
    _get_default_manager().save_cache(cache)


def upload_if_needed(path: str, cache_key: str, purpose: str = "assistants") -> str:
    """
    Get the file ID if it has already been uploaded.
    If not, upload the file to OpenAI and return the file ID.
    """
    return _get_default_manager().upload_if_needed(path, cache_key, purpose)


def list_all_uploaded_files(verbose: bool = True) -> list:
    """列出所有已上传的文件"""
    return _get_default_manager().list_all_uploaded_files(verbose)


def delete_all_files(verbose: bool = True) -> int:
    """删除所有已上传的文件"""
    return _get_default_manager().delete_all_files(verbose)


def delete_file(file_id: str, verbose: bool = True) -> bool:
    """删除指定文件"""
    return _get_default_manager().delete_file(file_id, verbose)

