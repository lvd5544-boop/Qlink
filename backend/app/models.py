from pydantic import BaseModel, Field
from typing import List, Optional


class WorkExperience(BaseModel):
    company: str
    position: str
    duration_years: float
    description: Optional[str] = None


class ProjectExperience(BaseModel):
    name: str
    role: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Skill(BaseModel):
    name: str
    level: Optional[str] = "intermediate"  # beginner, intermediate, advanced, expert


class ResumeInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    expected_job_title: Optional[str] = None
    expected_salary: Optional[str] = None
    location_preference: Optional[str] = None
    summary: Optional[str] = None
    skills: List[Skill] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    projects: List[ProjectExperience] = Field(default_factory=list)
    education: Optional[str] = None
    school: Optional[str] = None
    degree: Optional[str] = None
    school_tier: Optional[str] = None  # 985 / 211 / 双一流 / 其他
    soft_skills: List[str] = Field(default_factory=list)
    languages: Optional[List[str]] = None
    hobbies: Optional[List[str]] = None


# 新增：面试官可提取的画像片段，用于部分更新
class ProfileFragment(BaseModel):
    """从对话中提取的可更新字段，全部可选"""

    expected_job_title: Optional[str] = None
    expected_salary: Optional[str] = None  # 保留字符串形式，如 "25k-35k"
    skills: Optional[List[str]] = None  # 简单技能列表
    work_summary: Optional[str] = None  # 工作经验概述
    education: Optional[str] = None
    hobbies: Optional[List[str]] = None
    location_preference: Optional[str] = None
    other_notes: Optional[str] = None


class SkillRequirement(BaseModel):
    name: str
    level: Optional[str] = "intermediate"  # beginner, intermediate, advanced, expert


class JobInfo(BaseModel):
    title: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    requirements: Optional[str] = None  # 纯文本或结构化
    required_skills: List[SkillRequirement] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    leadership_signals: List[str] = Field(default_factory=list)
    communication_signals: List[str] = Field(default_factory=list)
    education_requirement: Optional[str] = None
    school_tier_keywords: List[str] = Field(default_factory=list)
    salary_range: Optional[str] = None  # 如 "20k-30k"
    location: Optional[str] = None
    experience_years: Optional[int] = None
    education: Optional[str] = None
    other_notes: Optional[str] = None
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_info: Optional[str] = None
