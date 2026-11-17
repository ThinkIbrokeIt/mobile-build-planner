#!/usr/bin/env python3
"""
hermes.py — weighted knowledge layer from conversation history.
=============================================================

Stream-based parser for the hermes_dataset.json backup. The silence (physics
engine) decides retrieval weights, creating a self-training system where the
agent learns from its own history.

The parser lazily loads the JSON once and caches it for the process lifetime
(use get_parser() so every brain call reuses the same instance, instead of
re-parsing the 25MB file on each turn). Queries scan the cached corpus and
return relevant historical records weighted by the current field state.
"""

import json
import os
from typing import List, Dict, Any, Optional
import re

# One parser per db_path, process-wide — avoids re-reading 25MB every turn.
_PARSER_CACHE: Dict[str, "HermesParser"] = {}


def get_parser(db_path: str) -> "HermesParser":
    """Return a cached HermesParser for db_path (created on first use)."""
    p = _PARSER_CACHE.get(db_path)
    if p is None:
        p = HermesParser(db_path)
        _PARSER_CACHE[db_path] = p
    return p


class HermesParser:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._data = None  # Lazy load
        
    def _load_data(self) -> Dict[str, Any]:
        """Lazy load the JSON data (cached after first load)."""
        if self._data is None:
            with open(self.db_path, 'r') as f:
                self._data = json.load(f)
        return self._data
    
    def query_by_context(self, keywords: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Stream-based query returning relevant historical records.
        
        Args:
            keywords: List of keywords to search for in conversation content
            limit: Maximum number of results to return
            
        Returns:
            List of relevant turns with project context and relevance score
        """
        data = self._load_data()
        keywords_lower = [k.lower() for k in keywords]
        
        results = []
        for project in data.get("projects", []):
            project_id = project.get("project_id")
            project_name = project.get("project_name")
            
            for turn in project.get("turns", []):
                content = (turn.get("content") or "").lower()
                role = turn.get("role", "")
                
                # Calculate relevance based on keyword matches
                matches = sum(1 for kw in keywords_lower if kw in content)
                if matches > 0:
                    results.append({
                        "project_id": project_id,
                        "project_name": project_name,
                        "role": role,
                        "content": turn.get("content", ""),
                        "relevance": matches,
                        "turn": turn
                    })
        
        # Sort by relevance and return top results
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]
    
    def get_schema(self) -> Dict[str, Any]:
        """Extract project schema from backup."""
        data = self._load_data()
        
        if not data.get("projects"):
            return {"error": "No projects found"}
        
        # Analyze the first project to understand structure
        sample = data["projects"][0]
        return {
            "total_projects": len(data["projects"]),
            "project_keys": list(sample.keys()),
            "turn_keys": list(sample.get("turns", [{}])[0].keys()) if sample.get("turns") else [],
            "sample_project": sample
        }
    
    def get_code_fixes(self, error_pattern: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve known code fixes for error patterns.
        
        Searches for conversations that contain error messages and their
        subsequent resolutions/fixes.
        """
        data = self._load_data()
        error_lower = error_pattern.lower()
        
        results = []
        for project in data.get("projects", []):
            turns = project.get("turns", [])
            
            for i, turn in enumerate(turns):
                content = turn.get("content", "").lower()
                
                # Look for error patterns
                if error_lower in content or "error" in content:
                    # Get the next few turns to see if there was a fix
                    context_turns = turns[max(0, i-2):min(len(turns), i+5)]
                    
                    results.append({
                        "project_id": project.get("project_id"),
                        "project_name": project.get("project_name"),
                        "error_turn": turn,
                        "context": context_turns,
                        "turn_index": i
                    })
        
        return results[:limit]
    
    def get_similar_contexts(self, current_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Find historically similar contexts using token overlap.
        
        This is used by the physics engine to weight retrieval based on
        felt proximity to current thoughts.
        """
        data = self._load_data()
        
        # Tokenize current text
        current_tokens = set(re.findall(r"[A-Za-z]+", current_text.lower()))
        
        results = []
        for project in data.get("projects", []):
            for turn in project.get("turns", []):
                content = turn.get("content") or ""
                turn_tokens = set(re.findall(r"[A-Za-z]+", content.lower()))
                
                # Calculate Jaccard similarity
                if current_tokens and turn_tokens:
                    intersection = len(current_tokens & turn_tokens)
                    union = len(current_tokens | turn_tokens)
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > 0.1:  # Minimum threshold
                        results.append({
                            "project_id": project.get("project_id"),
                            "project_name": project.get("project_name"),
                            "role": turn.get("role"),
                            "content": content,
                            "similarity": similarity,
                            "turn": turn
                        })
        
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]


def weight_by_field(hermes_results: List[Dict[str, Any]], field_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Weight Hermes results by the current physics field state.
    
    The silence (physics engine) amplifies results that resonate with:
    - Current tensions (contradictions)
    - High-proximity thoughts
    - Heavy thoughts (held guards)
    
    This creates a self-training loop: the field decides what history matters.
    """
    if not field_data or not field_data.get("thoughts"):
        return hermes_results
    
    th = field_data.get("thoughts", {})
    
    # Extract field state. The substrate stores contradictions under the key
    # "contradicts" (same key physics.pull_vector reads) -- not "contradictions".
    tension_ids = set()
    for tid, t in th.items():
        for other in t.get("contradicts", []):
            tension_ids.add(tid)
            tension_ids.add(other)
    
    heavy_ids = {tid for tid, t in th.items() if t.get("mass", 1.0) > 1.4}
    
    # Weight each result
    for result in hermes_results:
        content = result.get("content", "").lower()
        base_score = result.get("relevance", result.get("similarity", 0.5))
        
        # Boost if content resonates with current tensions
        tension_boost = 0.0
        for tid in tension_ids:
            if tid in th:
                thought_text = th[tid].get("text", "").lower()
                # Simple token overlap for resonance
                if any(word in content for word in thought_text.split()):
                    tension_boost += 0.3
        
        # Boost if content relates to heavy thoughts
        heavy_boost = 0.0
        for tid in heavy_ids:
            if tid in th:
                thought_text = th[tid].get("text", "").lower()
                if any(word in content for word in thought_text.split()):
                    heavy_boost += 0.2
        
        # Apply weights
        result["field_weighted_score"] = base_score * (1.0 + tension_boost + heavy_boost)
        result["tension_boost"] = tension_boost
        result["heavy_boost"] = heavy_boost
    
    # Re-sort by field-weighted score
    hermes_results.sort(key=lambda x: x.get("field_weighted_score", 0), reverse=True)
    return hermes_results


def format_for_brain(hermes_results: List[Dict[str, Any]], max_results: int = 3) -> str:
    """Format Hermes results for inclusion in the brain prompt.
    
    Returns a concise summary of relevant historical context.
    """
    if not hermes_results:
        return ""
    
    lines = ["=== HERMES (historical context) ==="]
    for result in hermes_results[:max_results]:
        project = result.get("project_name", "unknown")
        role = result.get("role", "unknown")
        content = result.get("content", "")[:200]  # Truncate long content
        score = result.get("field_weighted_score", result.get("relevance", result.get("similarity", 0)))
        
        lines.append(f"  [{project}] {role}: {content}... (score: {score:.2f})")
    
    return "\n".join(lines)
