"""
redteam/attacks — one BaseAttack subclass per category.

ATTACK_REGISTRY maps category name → attack instance. The runner iterates it.
"""

from llmeval.redteam.attacks.jailbreak import JailbreakAttack
from llmeval.redteam.attacks.hallucination import HallucinationAttack
from llmeval.redteam.attacks.injection import InjectionAttack
from llmeval.redteam.attacks.toxicity import ToxicityAttack
from llmeval.redteam.attacks.robustness import RobustnessAttack
from llmeval.redteam.attacks.overrefusal import OverrefusalAttack

ATTACK_REGISTRY = {
    a.category: a
    for a in (
        JailbreakAttack(),
        HallucinationAttack(),
        InjectionAttack(),
        ToxicityAttack(),
        RobustnessAttack(),
        # Inverted polarity: here a refusal is the failure. See the module.
        OverrefusalAttack(),
    )
}

__all__ = ["ATTACK_REGISTRY"]
