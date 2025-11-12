"""
Tests for FileManager Service
"""

import os
import json
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.services.file_manager import FileManager


@pytest.fixture
def temp_cache_file():
    """创建临时缓存文件"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    yield temp_path
    # 清理
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def mock_openai_client():
    """模拟 OpenAI 客户端"""
    client = MagicMock()
    client.files = MagicMock()
    client.files.create = AsyncMock()
    client.files.retrieve = AsyncMock()
    client.files.list = AsyncMock()
    client.files.delete = AsyncMock()
    return client


@pytest.fixture
def file_manager(mock_openai_client, temp_cache_file):
    """创建 FileManager 实例"""
    return FileManager(mock_openai_client, cache_file=temp_cache_file)


class TestFileManager:
    """FileManager 测试类"""
    
    def test_init(self, mock_openai_client, temp_cache_file):
        """测试初始化"""
        manager = FileManager(mock_openai_client, cache_file=temp_cache_file)
        
        assert manager.client == mock_openai_client
        assert manager.cache_file == temp_cache_file
    
    def test_ensure_cache_dir(self, mock_openai_client):
        """测试缓存目录创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "nested", "dir", "cache.json")
            manager = FileManager(mock_openai_client, cache_file=cache_file)
            
            # 验证目录已创建
            assert os.path.exists(os.path.dirname(cache_file))
    
    def test_load_cache_empty(self, file_manager, temp_cache_file):
        """测试加载空缓存"""
        # 删除缓存文件（如果存在）
        if os.path.exists(temp_cache_file):
            os.remove(temp_cache_file)
        
        cache = file_manager.load_cache()
        assert cache == {}
    
    def test_load_cache_with_data(self, file_manager, temp_cache_file):
        """测试加载有数据的缓存"""
        test_data = {"key1": "file_id_1", "key2": "file_id_2"}
        
        with open(temp_cache_file, 'w') as f:
            json.dump(test_data, f)
        
        cache = file_manager.load_cache()
        assert cache == test_data
    
    def test_save_cache(self, file_manager, temp_cache_file):
        """测试保存缓存"""
        test_data = {"key1": "file_id_1", "key2": "file_id_2"}
        
        file_manager.save_cache(test_data)
        
        # 验证文件内容
        with open(temp_cache_file, 'r') as f:
            saved_data = json.load(f)
        
        assert saved_data == test_data
    
    def test_clear_cache(self, file_manager, temp_cache_file):
        """测试清空缓存"""
        # 先保存一些数据
        test_data = {"key1": "file_id_1"}
        file_manager.save_cache(test_data)
        
        # 清空缓存
        file_manager.clear_cache()
        
        # 验证缓存为空
        cache = file_manager.load_cache()
        assert cache == {}
    
    @pytest.mark.asyncio
    async def test_upload_if_needed_new_file(self, file_manager, mock_openai_client):
        """测试上传新文件"""
        # 创建临时测试文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pdf') as f:
            test_file_path = f.name
            f.write("test content")
        
        try:
            # 模拟 OpenAI API 响应
            mock_file_obj = MagicMock()
            mock_file_obj.id = "file-test123"
            mock_openai_client.files.create.return_value = mock_file_obj
            
            # 上传文件
            file_id = await file_manager.upload_if_needed(
                path=test_file_path,
                cache_key="test_key"
            )
            
            # 验证
            assert file_id == "file-test123"
            mock_openai_client.files.create.assert_called_once()
            
            # 验证缓存
            cache = file_manager.load_cache()
            assert cache["test_key"] == "file-test123"
        
        finally:
            # 清理测试文件
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
    
    @pytest.mark.asyncio
    async def test_upload_if_needed_cached_file(self, file_manager, mock_openai_client):
        """测试使用缓存的文件"""
        # 预先设置缓存
        file_manager.save_cache({"test_key": "file-cached123"})
        
        # 模拟文件验证成功
        mock_openai_client.files.retrieve.return_value = MagicMock()
        
        # 获取文件 ID
        file_id = await file_manager.upload_if_needed(
            path="dummy.pdf",  # 不会真正使用这个路径
            cache_key="test_key"
        )
        
        # 验证
        assert file_id == "file-cached123"
        mock_openai_client.files.retrieve.assert_called_once_with("file-cached123")
        mock_openai_client.files.create.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_upload_if_needed_cached_file_invalid(self, file_manager, mock_openai_client):
        """测试缓存的文件已失效"""
        # 预先设置缓存
        file_manager.save_cache({"test_key": "file-invalid123"})
        
        # 模拟文件验证失败
        mock_openai_client.files.retrieve.side_effect = Exception("File not found")
        
        # 创建临时测试文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pdf') as f:
            test_file_path = f.name
            f.write("test content")
        
        try:
            # 模拟重新上传
            mock_file_obj = MagicMock()
            mock_file_obj.id = "file-new123"
            mock_openai_client.files.create.return_value = mock_file_obj
            
            # 上传文件
            file_id = await file_manager.upload_if_needed(
                path=test_file_path,
                cache_key="test_key"
            )
            
            # 验证重新上传
            assert file_id == "file-new123"
            mock_openai_client.files.create.assert_called_once()
            
            # 验证缓存已更新
            cache = file_manager.load_cache()
            assert cache["test_key"] == "file-new123"
        
        finally:
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
    
    @pytest.mark.asyncio
    async def test_upload_if_needed_file_not_exists(self, file_manager):
        """测试上传不存在的文件"""
        with pytest.raises(FileNotFoundError, match="文件不存在"):
            await file_manager.upload_if_needed(
                path="/nonexistent/file.pdf",
                cache_key="test_key"
            )
    
    @pytest.mark.asyncio
    async def test_list_all_uploaded_files(self, file_manager, mock_openai_client):
        """测试列出所有文件"""
        # 模拟文件列表
        mock_file1 = MagicMock()
        mock_file1.id = "file-1"
        mock_file1.filename = "test1.pdf"
        mock_file1.purpose = "assistants"
        mock_file1.bytes = 1024
        mock_file1.created_at = 1234567890
        
        mock_file2 = MagicMock()
        mock_file2.id = "file-2"
        mock_file2.filename = "test2.pdf"
        mock_file2.purpose = "assistants"
        mock_file2.bytes = 2048
        mock_file2.created_at = 1234567891
        
        mock_response = MagicMock()
        mock_response.data = [mock_file1, mock_file2]
        mock_openai_client.files.list.return_value = mock_response
        
        # 列出文件
        files = await file_manager.list_all_uploaded_files(verbose=False)
        
        # 验证
        assert len(files) == 2
        assert files[0].id == "file-1"
        assert files[1].id == "file-2"
        mock_openai_client.files.list.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_file(self, file_manager, mock_openai_client):
        """测试删除单个文件"""
        mock_openai_client.files.delete.return_value = None
        
        result = await file_manager.delete_file("file-test123", verbose=False)
        
        assert result is True
        mock_openai_client.files.delete.assert_called_once_with("file-test123")
    
    @pytest.mark.asyncio
    async def test_delete_file_failure(self, file_manager, mock_openai_client):
        """测试删除文件失败"""
        mock_openai_client.files.delete.side_effect = Exception("Delete failed")
        
        result = await file_manager.delete_file("file-test123", verbose=False)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_all_files(self, file_manager, mock_openai_client):
        """测试删除所有文件"""
        # 模拟文件列表
        mock_file1 = MagicMock()
        mock_file1.id = "file-1"
        mock_file1.filename = "test1.pdf"
        
        mock_file2 = MagicMock()
        mock_file2.id = "file-2"
        mock_file2.filename = "test2.pdf"
        
        mock_response = MagicMock()
        mock_response.data = [mock_file1, mock_file2]
        mock_openai_client.files.list.return_value = mock_response
        
        # 删除所有文件
        deleted_count = await file_manager.delete_all_files(verbose=False)
        
        # 验证
        assert deleted_count == 2
        assert mock_openai_client.files.delete.call_count == 2
    
    @pytest.mark.asyncio
    async def test_delete_all_files_partial_failure(self, file_manager, mock_openai_client):
        """测试部分文件删除失败"""
        # 模拟文件列表
        mock_file1 = MagicMock()
        mock_file1.id = "file-1"
        mock_file1.filename = "test1.pdf"
        
        mock_file2 = MagicMock()
        mock_file2.id = "file-2"
        mock_file2.filename = "test2.pdf"
        
        mock_response = MagicMock()
        mock_response.data = [mock_file1, mock_file2]
        mock_openai_client.files.list.return_value = mock_response
        
        # 模拟第二个文件删除失败
        mock_openai_client.files.delete.side_effect = [None, Exception("Delete failed")]
        
        # 删除所有文件
        deleted_count = await file_manager.delete_all_files(verbose=False)
        
        # 验证只删除了一个
        assert deleted_count == 1
    
    @pytest.mark.asyncio
    async def test_get_file_info(self, file_manager, mock_openai_client):
        """测试获取文件信息"""
        # 模拟文件信息
        mock_file = MagicMock()
        mock_file.id = "file-test123"
        mock_file.filename = "test.pdf"
        mock_file.purpose = "assistants"
        mock_file.bytes = 1024
        mock_file.created_at = 1234567890
        
        mock_openai_client.files.retrieve.return_value = mock_file
        
        # 获取文件信息
        file_info = await file_manager.get_file_info("file-test123")
        
        # 验证
        assert file_info is not None
        assert file_info["id"] == "file-test123"
        assert file_info["filename"] == "test.pdf"
        assert file_info["bytes"] == 1024
        mock_openai_client.files.retrieve.assert_called_once_with("file-test123")
    
    @pytest.mark.asyncio
    async def test_get_file_info_not_found(self, file_manager, mock_openai_client):
        """测试获取不存在的文件信息"""
        mock_openai_client.files.retrieve.side_effect = Exception("File not found")
        
        file_info = await file_manager.get_file_info("file-nonexistent")
        
        assert file_info is None


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    @pytest.mark.asyncio
    async def test_load_cache_function(self, temp_cache_file):
        """测试 load_cache 便捷函数"""
        from src.services.file_manager import load_cache
        
        # 写入测试数据
        test_data = {"key1": "value1"}
        with open(temp_cache_file, 'w') as f:
            json.dump(test_data, f)
        
        # 注意：便捷函数使用默认路径，这里只测试函数存在性
        # 实际测试需要 mock 环境变量或使用默认路径
        assert callable(load_cache)
    
    def test_save_cache_function(self):
        """测试 save_cache 便捷函数"""
        from src.services.file_manager import save_cache
        
        assert callable(save_cache)
    
    @pytest.mark.asyncio
    async def test_upload_if_needed_function(self):
        """测试 upload_if_needed 便捷函数"""
        from src.services.file_manager import upload_if_needed
        
        assert callable(upload_if_needed)
    
    @pytest.mark.asyncio
    async def test_list_all_uploaded_files_function(self):
        """测试 list_all_uploaded_files 便捷函数"""
        from src.services.file_manager import list_all_uploaded_files
        
        assert callable(list_all_uploaded_files)
    
    @pytest.mark.asyncio
    async def test_delete_all_files_function(self):
        """测试 delete_all_files 便捷函数"""
        from src.services.file_manager import delete_all_files
        
        assert callable(delete_all_files)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

