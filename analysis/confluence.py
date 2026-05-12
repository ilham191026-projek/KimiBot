"""
Confluence Engine — Aggregates all 6 analysis layers into a final score.
Signal requires minimum 5/6 layers to pass.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd

from config import MIN_CONFLUENCE_SCORE
from utils.logger import get_logger

# Import all layers
from analysis.layer1_h4_bias import analyze_h4
from analysis.layer2_h1_ob_fvg import analyze_h1_ob_fvg
from analysis.layer3_m30_msnr import analyze_m30_msnr
from analysis.layer4_m15_crt import analyze_m15_crt
from analysis.layer5_m5_mss import analyze_m5_mss
from analysis.layer6_m1_entry import analyze_m1_entry

logger = get_logger(__name__)


def run_full_analysis(
    pair: str,
    dataframes: Dict[str, pd.DataFrame]
) -> Dict:
    """
    Run all 6 analysis layers in sequence and compute confluence score.
    
    Args:
        pair: Instrument symbol (e.g., "EURUSD")
        dataframes: Dict mapping timeframe strings to OHLCV DataFrames
                    Expected keys: "H4", "H1", "M30", "M15", "M5", "M1"
    
    Returns:
        Dict with full analysis results:
        {
            "pair": str,
            "confluence_score": int,  # 0-6
            "confluence_passed": bool,  # score >= MIN_CONFLUENCE_SCORE
            "direction": str | None,  # "bullish" | "bearish" | None
            "layers": {
                "h4_bias": {...},
                "h1_ob_fvg": {...},
                "m30_msnr": {...},
                "m15_crt": {...},
                "m5_mss": {...},
                "m1_entry": {...},
            },
            "layer_results": List[Dict],  # sequential results
        }
    """
    logger.info("=" * 60)
    logger.info("Starting full 6-layer analysis for %s", pair)
    logger.info("=" * 60)
    
    results = {
        "pair": pair,
        "confluence_score": 0,
        "confluence_passed": False,
        "direction": None,
        "layers": {},
        "layer_results": [],
    }
    
    # ── Layer 1: H4 Market Structure ────────────────────────────────────────
    h4_result = analyze_h4(pair, dataframes.get("H4"))
    results["layers"]["h4_bias"] = h4_result
    results["layer_results"].append({
        "layer": 1,
        "name": "H4 Bias",
        "valid": h4_result.get("valid", False),
        "direction": h4_result.get("bias", "neutral"),
    })
    
    if not h4_result.get("valid", False):
        logger.info("Layer 1 FAILED — H4 bias is neutral or low confidence")
        return _finalize_results(results)
    
    direction = h4_result["bias"]
    results["direction"] = direction
    results["confluence_score"] += 1
    logger.info("Layer 1 PASSED — H4 bias: %s (confidence=%.2f)",
                direction, h4_result.get("confidence", 0))
    
    # ── Layer 2: H1 Order Block + FVG ───────────────────────────────────────
    h1_result = analyze_h1_ob_fvg(pair, dataframes.get("H1"), direction)
    results["layers"]["h1_ob_fvg"] = h1_result
    results["layer_results"].append({
        "layer": 2,
        "name": "H1 OB/FVG",
        "valid": h1_result.get("valid", False),
    })
    
    if h1_result.get("valid", False):
        results["confluence_score"] += 1
        logger.info("Layer 2 PASSED — H1 OB/FVG aligned")
    else:
        logger.info("Layer 2 FAILED — No valid OB/FVG")
    
    # ── Layer 3: M30 MSNR ──────────────────────────────────────────────────
    m30_result = analyze_m30_msnr(pair, dataframes.get("M30"))
    results["layers"]["m30_msnr"] = m30_result
    results["layer_results"].append({
        "layer": 3,
        "name": "M30 MSNR",
        "valid": m30_result.get("valid", False),
    })
    
    if m30_result.get("valid", False):
        results["confluence_score"] += 1
        msnr_type = m30_result.get("msnr", {}).get("type", "unknown")
        logger.info("Layer 3 PASSED — M30 MSNR: %s", msnr_type)
    else:
        logger.info("Layer 3 FAILED — No MSNR sweep detected")
    
    # ── Layer 4: M15 CRT (Most Critical) ──────────────────────────────────
    m15_result = analyze_m15_crt(pair, dataframes.get("M15"), direction)
    results["layers"]["m15_crt"] = m15_result
    results["layer_results"].append({
        "layer": 4,
        "name": "M15 CRT",
        "valid": m15_result.get("valid", False),
        "crt": m15_result.get("crt", {}),
    })
    
    if m15_result.get("valid", False):
        results["confluence_score"] += 1
        crt = m15_result.get("crt", {})
        logger.info("Layer 4 PASSED — M15 CRT: %s sweep at %.5f (age=%.0fmin)",
                    crt.get("direction", "?"), crt.get("sweep_level", 0), crt.get("age_min", 0))
    else:
        logger.info("Layer 4 FAILED — No valid CRT pattern")
    
    # ── Layer 5: M5 MSS + FVG ─────────────────────────────────────────────
    m5_result = analyze_m5_mss(pair, dataframes.get("M5"), direction)
    results["layers"]["m5_mss"] = m5_result
    results["layer_results"].append({
        "layer": 5,
        "name": "M5 MSS",
        "valid": m5_result.get("valid", False),
    })
    
    if m5_result.get("valid", False):
        results["confluence_score"] += 1
        logger.info("Layer 5 PASSED — M5 MSS confirmed")
    else:
        logger.info("Layer 5 FAILED — No MSS on M5")
    
    # ── Layer 6: M1 Entry ──────────────────────────────────────────────────
    m1_result = analyze_m1_entry(pair, dataframes.get("M1"), direction)
    results["layers"]["m1_entry"] = m1_result
    results["layer_results"].append({
        "layer": 6,
        "name": "M1 Entry",
        "valid": m1_result.get("valid", False),
    })
    
    if m1_result.get("valid", False):
        results["confluence_score"] += 1
        logger.info("Layer 6 PASSED — M1 entry confirmed")
    else:
        logger.info("Layer 6 FAILED — No M1 confirmation")
    
    return _finalize_results(results)


def _finalize_results(results: Dict) -> Dict:
    """Finalize and log confluence results."""
    score = results["confluence_score"]
    passed = score >= MIN_CONFLUENCE_SCORE
    results["confluence_passed"] = passed
    
    logger.info("-" * 40)
    logger.info("Confluence Score for %s: %d/6 | %s",
                results["pair"], score, "PASSED" if passed else "FAILED")
    logger.info("Direction: %s", results.get("direction", "N/A"))
    logger.info("=" * 60)
    
    return results


def get_passed_layers_summary(results: Dict) -> str:
    """Generate a text summary of passed/failed layers for display."""
    lines = []
    icons = {True: "✅", False: "❌"}
    
    for lr in results.get("layer_results", []):
        valid = lr.get("valid", False)
        layer_name = lr.get("name", "Unknown")
        lines.append(f"  {icons[valid]} {layer_name}")
    
    return "\n".join(lines)


def get_signal_direction(results: Dict) -> Optional[str]:
    """Extract the trade direction from confluence results."""
    if results.get("confluence_passed"):
        return results.get("direction")
    return None