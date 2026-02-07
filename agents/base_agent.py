import yaml
import json
import logging
from pathlib import Path
from typing import Optional
from core.model_manager import ModelManager
from core.json_parser import parse_llm_json
from core.utils import log_step, log_error
from PIL import Image
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Cost rates per million tokens by provider/model family
COST_RATES = {
    "gemini": {
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-2.5-pro":   {"input": 1.25, "output": 10.00},
        "_default":          {"input": 0.15, "output": 0.60},
    },
    "ollama": {
        # Ollama is locally hosted, effectively free
        "_default": {"input": 0.0, "output": 0.0},
    },
}


class AgentRunner:
    def __init__(self, multi_mcp):
        self.multi_mcp = multi_mcp
        
        # Load agent configurations
        config_path = Path(__file__).parent.parent / "config/agent_config.yaml"
        with open(config_path, "r") as f:
            self.agent_configs = yaml.safe_load(f)["agents"]
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, provider: str, model_name: str) -> dict:
        """Calculate cost from real token counts and provider-specific rates."""
        provider_rates = COST_RATES.get(provider, COST_RATES["gemini"])
        rates = provider_rates.get(model_name, provider_rates["_default"])
        
        input_cost = (input_tokens / 1_000_000) * rates["input"]
        output_cost = (output_tokens / 1_000_000) * rates["output"]
        total_cost = input_cost + output_cost
        
        return {
            "cost": total_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens
        }

    async def run_agent(self, agent_type: str, input_data: dict, image_path: Optional[str] = None) -> dict:
        """Run a specific agent with input data and optional image"""
        
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")
            
        config = self.agent_configs[agent_type]
        
        try:
            # 1. Load prompt template
            prompt_template = Path(config["prompt_file"]).read_text(encoding="utf-8")
            
            # 2. Get tools from specified MCP servers (if any)
            tools_text = ""
            if config.get("mcp_servers"):
                tools = self.multi_mcp.get_tools_from_servers(config["mcp_servers"])
                if tools:
                    tool_descriptions = []
                    for tool in tools:
                        schema = tool.inputSchema
                        if "input" in schema.get("properties", {}):
                            inner_key = next(iter(schema.get("$defs", {})), None)
                            props = schema["$defs"][inner_key]["properties"]
                        else:
                            props = schema["properties"]

                        arg_types = []
                        for k, v in props.items():
                            t = v.get("type", "any")
                            arg_types.append(t)

                        signature_str = ", ".join(arg_types)
                        tool_descriptions.append(f"- `{tool.name}({signature_str})` # {tool.description}")
                    
                    tools_text = "\n\n### Available Tools\n\n" + "\n".join(tool_descriptions)

            
            # 3. Build full prompt
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # 3a. Inject user preferences (compact format)
            try:
                from remme.preferences import get_compact_policy
                # Map agent types to scopes for preference lookup
                scope_map = {
                    "PlannerAgent": "planning", "CoderAgent": "coding",
                    "DistillerAgent": "coding", "FormatterAgent": "formatting",
                    "RetrieverAgent": "research", "ThinkerAgent": "reasoning",
                }
                scope = scope_map.get(agent_type, "general")
                user_prefs_text = f"\n---\n## User Preferences\n{get_compact_policy(scope)}\n---\n"
            except Exception as e:
                print(f"⚠️ Could not load user preferences: {e}")
                user_prefs_text = ""
            
            full_prompt = f"CURRENT_DATE: {current_date}\n\n{prompt_template.strip()}{user_prefs_text}{tools_text}\n\n```json\n{json.dumps(input_data, indent=2)}\n```"

            # Save prompt to file for debugging
            debug_log_dir = Path(__file__).parent.parent / "memory" / "debug_logs"
            debug_log_dir.mkdir(parents=True, exist_ok=True)
            (debug_log_dir / "latest_prompt.txt").write_text(f"AGENT: {agent_type}\nCONFIG: {config['prompt_file']}\n\n{full_prompt}", encoding="utf-8")
            log_step(f"🤖 {agent_type} invoked", payload={"prompt_file": config['prompt_file'], "input_keys": list(input_data.keys())}, symbol="🟦")
            logger.debug(f"Tools text for {agent_type}: {tools_text[:200]}...")

            # 4. Create model manager with user's selected model from settings
            from config.settings_loader import get_fresh_settings
            fresh_settings = get_fresh_settings()
            agent_settings = fresh_settings.get("agent", {})
            
            # Check for per-agent overrides
            overrides = agent_settings.get("overrides", {})
            if agent_type in overrides:
                override = overrides[agent_type]
                model_provider = override.get("model_provider", "gemini")
                model_name = override.get("model", "gemini-2.5-flash")
                log_step(f"🎯 Override for {agent_type}: {model_provider}:{model_name}", symbol="✨")
            else:
                model_provider = agent_settings.get("model_provider", "gemini")
                model_name = agent_settings.get("default_model", "gemini-2.5-flash")
            
            log_step(f"📡 Using {model_provider}:{model_name}", symbol="🔌")
            model_manager = ModelManager(model_name, provider=model_provider)
            
            # 5. Generate response (with or without image)
            # ModelManager now returns dict: {text, input_tokens, output_tokens, total_tokens}
            if image_path and os.path.exists(image_path):
                log_step(f"🖼️ {agent_type} (with image)")
                image = Image.open(image_path)
                model_response = await model_manager.generate_content([full_prompt, image])
            else:
                model_response = await model_manager.generate_text(full_prompt)
            
            response_text = model_response["text"]
            real_input_tokens = model_response.get("input_tokens", 0)
            real_output_tokens = model_response.get("output_tokens", 0)
            
            # Save raw response for debugging
            timestamp = datetime.now().strftime("%H%M%S")
            (debug_log_dir / f"{timestamp}_{agent_type}_response.txt").write_text(response_text, encoding="utf-8")
            (debug_log_dir / f"{timestamp}_{agent_type}_prompt.txt").write_text(full_prompt, encoding="utf-8")

            # 6. Parse JSON response dynamically
            output = parse_llm_json(response_text)
            
            # Robustness: Some models (like gemma3) wrap JSON in a list
            if isinstance(output, list) and len(output) > 0 and isinstance(output[0], dict):
                output = output[0]
                
            log_step(f"🟩 {agent_type} finished", payload={"output_keys": list(output.keys()) if isinstance(output, dict) else "raw_string"}, symbol="🟩")

            # Calculate cost from REAL token counts (not approximations)
            cost_data = self.calculate_cost(real_input_tokens, real_output_tokens, model_provider, model_name)
            
            # Return clean envelope: output is pure LLM response, metadata is separate
            return {
                "success": True,
                "agent_type": agent_type,
                "output": output,
                "metadata": {
                    **cost_data,
                    "executed_model": f"{model_provider}:{model_name}",
                }
            }
            
        except Exception as e:
            logger.error(f"{agent_type} failed: {str(e)}", exc_info=True)
            log_error(f"❌ {agent_type}: {str(e)}")
            return {
                "success": False,
                "agent_type": agent_type,
                "error": str(e),
                "metadata": {
                    "cost": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
            }

    def get_available_agents(self) -> list:
        """Return list of available agent types"""
        return list(self.agent_configs.keys())
