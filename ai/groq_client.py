"""
Groq API Client Wrapper.
Uses llama-3.3-70b-versatile for AI-powered trade signal narration.
"""

import os
import asyncio
from typing import Optional, Dict, Any

import groq
from groq import Groq

from config import GROQ_API_KEY
from utils.logger import get_logger

logger = get_logger(__name__)

# Default model
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqClient:
    """Wrapper for Groq API interactions."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Groq client.
        
        Args:
            api_key: Groq API key (falls back to GROQ_API_KEY env var)
        """
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key:
            logger.warning("No Groq API key configured")
        
        self.client = Groq(api_key=self.api_key) if self.api_key else None
    
    def is_configured(self) -> bool:
        """Check if the client has a valid API key."""
        return self.client is not None
    
    def chat_completion(
        self,
        messages: list,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: int = 10,
    ) -> Optional[str]:
        """
        Send a chat completion request to Groq.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum response tokens
            timeout: Request timeout in seconds
            
        Returns:
            Response text or None on failure
        """
        if not self.client:
            logger.warning("Groq client not configured, skipping")
            return None
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            
            content = response.choices[0].message.content
            logger.info("Groq response received (%d chars)", len(content) if content else 0)
            return content
        
        except Exception as e:
            logger.error("Groq API error: %s", e)
            return None
    
    async def chat_completion_async(
        self,
        messages: list,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.3,
        max_tokens: int = 300,
        timeout: int = 10,
    ) -> Optional[str]:
        """
        Async version of chat completion.
        
        Args:
            messages: List of message dicts
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum response tokens
            timeout: Request timeout in seconds
            
        Returns:
            Response text or None on failure
        """
        if not self.client:
            logger.warning("Groq client not configured, skipping")
            return None
        
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                ),
                timeout=timeout,
            )
            
            content = response.choices[0].message.content
            logger.info("Groq async response received (%d chars)", len(content) if content else 0)
            return content
        
        except asyncio.TimeoutError:
            logger.error("Groq API timeout after %ds", timeout)
            return None
        except Exception as e:
            logger.error("Groq API async error: %s", e)
            return None
    
    def strip_markdown(self, text: Optional[str]) -> str:
        """Remove markdown formatting from response."""
        if not text:
            return ""
        
        import re
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Remove bold/italic markers
        text = re.sub(r'\*\*?([^*]+)\*\*?', r'\1', text)
        # Remove headers
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        
        return text.strip()