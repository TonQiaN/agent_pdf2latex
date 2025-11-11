"""Subtopic fetcher for preprocessing module"""

from typing import Dict, Any, List
from loguru import logger

from ....management.topic_operations import get_all_subtopics


async def get_subtopics_by_subject_grade(
    subject_id: int,
    grade_id: int
) -> List[Dict[str, Any]]:
    """
    根据 subject_id 和 grade_id 获取所有 subtopic 列表
    
    Args:
        subject_id: Subject ID
        grade_id: Grade ID
    
    Returns:
        List of subtopic dictionaries with topic_id, topic_name, subtopic_id and subtopic_name
    """
    logger.info(f"Fetching subtopics for subject_id={subject_id}, grade_id={grade_id}")
    
    subtopics = await get_all_subtopics(
        subject_id=subject_id,
        grade_id=grade_id
    )
    
    # 返回简化的列表，包含 topic_id, topic_name, subtopic_id 和 subtopic_name
    result = [
        {
            "topic_id": s.get("topicid") or s.get("topic_id"),
            "topic_name": s.get("topic_name") or s.get("topicname"),
            "subtopic_id": s.get("subtopicid") or s.get("subtopic_id"),
            "subtopic_name": s.get("subtopic_name") or s.get("subtopicname")
        }
        for s in subtopics
    ]
    
    logger.info(f"Retrieved {len(result)} subtopics")
    return result

