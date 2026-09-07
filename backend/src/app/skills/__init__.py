"""Skills package — Python implementations of all Claude Code skills.

Each skill is a standalone module with a FastAPI route registered in router.py.
Skill executors follow the SkillExecutor ABC defined in base.py.
"""

from app.skills.router import router as skills_router

__all__ = ["skills_router"]
