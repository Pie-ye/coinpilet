"""
Chronos Personas - 四大 AI 投資人角色

每位投資者具有獨特的：
- 投資哲學與風格
- System Prompt
- 資訊偏好（是否參考新聞、技術指標等）
"""

from .base import InvestorPersona, PersonaConfig
from .guardian import Guardian
from .degen import Degen
from .quant import Quant
from .strategist import Strategist

__all__ = [
    "InvestorPersona",
    "PersonaConfig",
    "Guardian",
    "Degen",
    "Quant",
    "Strategist",
]

# 便捷的角色工廠
PERSONAS = {
    "guardian": Guardian,
    "degen": Degen,
    "quant": Quant,
    "strategist": Strategist,
}


def create_persona(persona_id: str, **kwargs) -> InvestorPersona:
    """
    建立投資人角色
    
    Args:
        persona_id: 角色 ID (guardian, degen, quant, strategist)
        **kwargs: 傳遞給角色的參數
        
    Returns:
        InvestorPersona: 投資人角色實例
    """
    if persona_id not in PERSONAS:
        raise ValueError(f"未知的角色 ID: {persona_id}")
    
    return PERSONAS[persona_id](**kwargs)


def create_all_personas(**kwargs) -> dict[str, InvestorPersona]:
    """
    建立所有投資人角色
    
    Args:
        **kwargs: 傳遞給所有角色的共用參數
        
    Returns:
        dict[str, InvestorPersona]: 角色 ID 到實例的映射
    """
    return {
        persona_id: persona_class(**kwargs)
        for persona_id, persona_class in PERSONAS.items()
    }
