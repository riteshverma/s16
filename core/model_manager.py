import os
import time
import asyncio
import json
import yaml
import logging
from pathlib import Path
from google import genai
from google.genai.errors import ServerError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"

# Module-level aiohttp session for Ollama (reused across instances)
_ollama_session = None
_ollama_session_lock = asyncio.Lock()


async def _get_ollama_session():
    """Get or create a reusable aiohttp session for Ollama calls."""
    global _ollama_session
    async with _ollama_session_lock:
        if _ollama_session is None or _ollama_session.closed:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=300, connect=10)
            _ollama_session = aiohttp.ClientSession(timeout=timeout)
        return _ollama_session


async def close_ollama_session():
    """Close the shared aiohttp session (call on shutdown)."""
    global _ollama_session
    if _ollama_session and not _ollama_session.closed:
        await _ollama_session.close()
        _ollama_session = None


class ModelManager:
    def __init__(self, model_name: str = None, provider: str = None):
        """
        Initialize ModelManager with flexible model specification.
        
        Args:
            model_name: The model to use. Can be:
                - A key from models.json (e.g., "gemini", "phi4")
                - An actual model name (e.g., "gemini-2.5-flash", "llama3:8b")
            provider: Optional explicit provider ("gemini" or "ollama").
                      If provided, bypasses models.json lookup.
        """
        self.config = json.loads(MODELS_JSON.read_text())
        self.profile = yaml.safe_load(PROFILE_YAML.read_text())

        # Load settings for Ollama URL
        try:
            from config.settings_loader import settings
            self.ollama_base_url = settings.get("ollama", {}).get("base_url", "http://127.0.0.1:11434")
        except Exception as e:
            logger.warning(f"Could not load Ollama URL from settings: {e}")
            self.ollama_base_url = "http://127.0.0.1:11434"

        if provider:
            self.model_type = provider
            self.text_model_key = model_name or "gemini-2.5-flash"
            
            if provider == "gemini":
                self.model_info = {
                    "type": "gemini",
                    "model": self.text_model_key,
                    "api_key_env": "GEMINI_API_KEY"
                }
                api_key = os.getenv("GEMINI_API_KEY")
                self.client = genai.Client(api_key=api_key)
            elif provider == "ollama":
                self.model_info = {
                    "type": "ollama",
                    "model": self.text_model_key,
                    "url": {
                        "generate": f"{self.ollama_base_url}/api/generate",
                        "chat": f"{self.ollama_base_url}/api/chat"
                    }
                }
                self.client = None
            else:
                raise ValueError(f"Unknown provider: {provider}")
        else:
            if model_name:
                self.text_model_key = model_name
            else:
                self.text_model_key = self.profile["llm"]["text_generation"]
            
            if self.text_model_key not in self.config["models"]:
                available_models = list(self.config["models"].keys())
                raise ValueError(f"Model '{self.text_model_key}' not found in models.json. Available: {available_models}")
                
            self.model_info = self.config["models"][self.text_model_key]
            self.model_type = self.model_info["type"]

            if self.model_type == "gemini":
                api_key = os.getenv("GEMINI_API_KEY")
                self.client = genai.Client(api_key=api_key)

    async def generate_text(self, prompt: str) -> dict:
        """Generate text and return structured response with token metadata.
        
        Returns:
            dict with keys: text, input_tokens, output_tokens, total_tokens
        """
        if self.model_type == "gemini":
            return await self._gemini_generate(prompt)
        elif self.model_type == "ollama":
            return await self._ollama_generate(prompt)
        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    async def generate_content(self, contents: list) -> dict:
        """Generate content with support for text and images.
        
        Returns:
            dict with keys: text, input_tokens, output_tokens, total_tokens
        """
        if self.model_type == "gemini":
            await self._wait_for_rate_limit()
            return await self._gemini_generate_content(contents)
        elif self.model_type == "ollama":
            return await self._ollama_generate_content(contents)
        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    async def _ollama_generate_content(self, contents: list) -> dict:
        """Generate content with Ollama, supporting multimodal models like gemma3, llava, etc."""
        import base64
        import io
        from PIL import Image as PILImage
        
        text_parts = []
        images_base64 = []
        
        for content in contents:
            if isinstance(content, str):
                text_parts.append(content)
            elif hasattr(content, 'save'):  # PIL Image check
                try:
                    img = content
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    MAX_DIM = 1024
                    if img.width > MAX_DIM or img.height > MAX_DIM:
                        img.thumbnail((MAX_DIM, MAX_DIM), PILImage.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
                    images_base64.append(encoded)
                except Exception as e:
                    logger.warning(f"Failed to encode image for Ollama: {e}")
        
        prompt = "\n".join(text_parts)
        
        if images_base64:
            return await self._ollama_generate_with_images(prompt, images_base64)
        else:
            return await self._ollama_generate(prompt)

    async def _ollama_generate_with_images(self, prompt: str, images: list) -> dict:
        """Generate with Ollama using images (for multimodal models)."""
        try:
            session = await _get_ollama_session()
            async with session.post(
                self.model_info["url"]["generate"],
                json={
                    "model": self.model_info["model"],
                    "prompt": prompt,
                    "images": images,
                    "stream": False
                }
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return {
                    "text": result["response"].strip(),
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                }
        except Exception as e:
            raise RuntimeError(f"Ollama multimodal generation failed: {str(e)}")

    # --- Rate Limiting Helper ---
    _last_call = 0
    _lock = asyncio.Lock()

    async def _wait_for_rate_limit(self):
        """Enforce ~15 RPM limit for Gemini (4s interval)"""
        async with ModelManager._lock:
            now = time.time()
            elapsed = now - ModelManager._last_call
            if elapsed < 4.5:
                sleep_time = 4.5 - elapsed
                await asyncio.sleep(sleep_time)
            ModelManager._last_call = time.time()

    def _extract_gemini_usage(self, response) -> dict:
        """Extract real token counts from Gemini SDK response."""
        usage = getattr(response, 'usage_metadata', None)
        if usage:
            return {
                "input_tokens": getattr(usage, 'prompt_token_count', 0) or 0,
                "output_tokens": getattr(usage, 'candidates_token_count', 0) or 0,
                "total_tokens": getattr(usage, 'total_token_count', 0) or 0,
            }
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    async def _gemini_generate(self, prompt: str) -> dict:
        await self._wait_for_rate_limit()
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_info["model"],
                contents=prompt
            )
            token_usage = self._extract_gemini_usage(response)
            return {
                "text": response.text.strip(),
                **token_usage,
            }
        except ServerError as e:
            raise e
        except Exception as e:
            raise RuntimeError(f"Gemini generation failed: {str(e)}")

    async def _gemini_generate_content(self, contents: list) -> dict:
        """Generate content with support for text and images using Gemini SDK."""
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_info["model"],
                contents=contents
            )
            token_usage = self._extract_gemini_usage(response)
            return {
                "text": response.text.strip(),
                **token_usage,
            }
        except ServerError as e:
            raise e
        except Exception as e:
            raise RuntimeError(f"Gemini content generation failed: {str(e)}")

    async def _ollama_generate(self, prompt: str) -> dict:
        try:
            session = await _get_ollama_session()
            async with session.post(
                self.model_info["url"]["generate"],
                json={"model": self.model_info["model"], "prompt": prompt, "stream": False}
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return {
                    "text": result["response"].strip(),
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                }
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {str(e)}")
