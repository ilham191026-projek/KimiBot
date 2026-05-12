"""
Signal Narrator — Generates AI-powered trade rationales using Groq.
Builds structured prompts and calls llama-3.3-70b-versatile for human-readable
explanations of why a signal is valid.
"""

import asyncio
from typing import Dict, Optional, List

from ai.groq_client import GroqClient
from utils.logger import get_logger

logger = get_logger(__name__)


def _build_prompt(signal_data: Dict) -> str:
    """
    Build a structured prompt for the AI trade narrative.
    
    Args:
        signal_data: Complete signal data including all layers, SL/TP, etc.
        
    Returns:
        Formatted prompt string
    """
    pair = signal_data.get("pair", "Unknown")
    direction = signal_data.get("direction", "Unknown")
    session = signal_data.get("session", "Unknown")
    confluence_score = signal_data.get("confluence_score", 0)
    
    # SL/TP info
    sl_tp = signal_data.get("sl_tp", {})
    sl = sl_tp.get("sl", "N/A")
    tp1 = sl_tp.get("tp1", "N/A")
    tp2 = sl_tp.get("tp2", "N/A")
    rr1 = sl_tp.get("rr1", "N/A")
    rr2 = sl_tp.get("rr2", "N/A")
    sl_pip = sl_tp.get("sl_pip", "N/A")
    
    # Layer results
    layers = signal_data.get("layer_results", [])
    layer_summary = []
    for lr in layers:
        valid_icon = "PASS" if lr.get("valid", False) else "FAIL"
        layer_summary.append(f"- {lr.get('name', 'Unknown')}: {valid_icon}")
    
    # Risk info
    risk = signal_data.get("risk", {})
    lot_size = risk.get("lot_size", "N/A")
    dollar_risk = risk.get("dollar_risk", "N/A")
    
    # News context
    news = signal_data.get("news", "No high-impact events.")
    
    # CRT details
    crt = signal_data.get("layers", {}).get("m15_crt", {}).get("crt", {})
    crt_details = ""
    if crt and crt.get("found"):
        crt_details = (
            f"CRT Details: {crt.get('direction')} sweep at {crt.get('sweep_level', 'N/A')}, "
            f"depth: {crt.get('sweep_depth_pip', 'N/A'):.1f} pips, "
            f"age: {crt.get('age_min', 'N/A')} min, "
            f"in OB zone: {crt.get('in_ob_zone', False)}"
        )
    
    prompt = f"""You are a professional forex trader explaining a trade setup to a prop firm trader.

TRADE SIGNAL:
- Pair: {pair}
- Direction: {direction.upper()}
- Session: {session}
- Confluence Score: {confluence_score}/6

RISK PARAMETERS:
- Stop Loss: {sl} ({sl_pip} pips)
- Take Profit 1: {tp1} (RR: {rr1}:1)
- Take Profit 2: {tp2} (RR: {rr2}:1)
- Lot Size: {lot_size}
- Dollar Risk: ${dollar_risk}

LAYER ANALYSIS:
{chr(10).join(layer_summary)}

{crt_details}

MARKET CONTEXT:
{news}

TASK: Write a concise 5-8 sentence trade rationale explaining WHY this setup has edge.
Focus on:
1. The structural context (HTF bias)
2. The liquidity sweep narrative (CRT)
3. The confluence of signals across timeframes
4. Why the risk/reward is favorable

Write in a professional, factual tone. Be specific about price action mechanics.
Do not use markdown formatting. Do not add disclaimers.
"""
    
    return prompt


def strip_markdown(text: Optional[str]) -> str:
    """Remove markdown formatting from text."""
    if not text:
        return ""
    
    import re
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*?([^*]+)\*\*?', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    return text.strip()


async def generate_narrative(signal_data: Dict) -> str:
    """
    Generate AI trade narrative using Groq.
    
    Args:
        signal_data: Complete signal data from all layers
        
    Returns:
        Trade rationale string, or fallback message on error
    """
    client = GroqClient()
    
    if not client.is_configured():
        logger.warning("Groq not configured, returning fallback narrative")
        return "[AI narrative unavailable — Groq API key not configured]"
    
    try:
        prompt = _build_prompt(signal_data)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional forex trader and quantitative analyst. "
                    "Write concise, factual trade rationales. No disclaimers. No markdown."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        
        response = await client.chat_completion_async(
            messages=messages,
            temperature=0.3,
            max_tokens=300,
            timeout=10,
        )
        
        if response:
            cleaned = strip_markdown(response)
            logger.info("AI narrative generated: %d chars", len(cleaned))
            return cleaned
        else:
            logger.warning("Empty response from Groq API")
            return "[AI narrative unavailable]"
    
    except Exception as e:
        logger.error("Error generating narrative: %s", e)
        return "[AI narrative unavailable]"