from __future__ import annotations
from world_builder.llm import LLMClient
from world_engine.prompt_builder import PromptBuilder


class SceneAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def transition(
        self,
        current_location: str,
        destination: str,
        character: str,
        recent_events: list,
        world_rules: list,
    ) -> str:
        prompt = PromptBuilder.build_scene_transition_prompt(
            current_location, destination, character, recent_events, world_rules
        )
        return await self.llm.generate_text(prompt, temperature=0.8)
