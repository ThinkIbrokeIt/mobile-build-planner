# Hermes Integration Architecture

## Overview
Integrate 25MB JSON backup database as a weighted knowledge layer for the echo brain. The silence (physics engine) decides retrieval weights, creating a self-training system where the agent learns from its own history.

## Architecture

### Layer 0: JSON Database (Hermes Backup)
- **Source**: 25MB JSON database (`hermes_dataset.json`) in project root
- **Format**: JSON with 45 projects containing conversation turns
- **Content**: Conversation history, code fixes, schema, transaction logic
- **Access**: Lazy-loaded with caching (loads once per session, ~25MB)
- **Schema**:
  ```json
  {
    "projects": [
      {
        "project_id": "20260531_201202_348c71",
        "project_name": "Gateway Initialization Request",
        "turns": [
          {"role": "user", "content": "..."},
          {"role": "assistant", "content": "..."},
          {"role": "tool", "content": "..."}
        ]
      }
    ]
  }
  ```

### Layer 1: Hermes Parser
```python
class HermesParser:
    def __init__(self, db_path):
        self.db_path = db_path
        self._data = None  # Lazy load

    def query_by_context(self, keywords, limit=10):
        """Query by keyword matching, returns relevant historical records"""
        # Tokenizes keywords and searches across all project turns
        # Returns ranked results by relevance (keyword match count)

    def get_schema(self):
        """Extract project schema from backup"""
        # Returns structure info: total projects, keys, sample data

    def get_code_fixes(self, error_pattern, limit=5):
        """Retrieve known code fixes for error patterns"""
        # Searches for error patterns and returns surrounding context

    def get_similar_contexts(self, current_text, limit=10):
        """Find historically similar contexts using Jaccard similarity"""
        # Token overlap-based similarity search for felt proximity
```

**Implemented in**: `Echo_x.py`

### Layer 2: Weight Engine (Silence Decides)
The physics engine influences retrieval weights:
- **Tension proximity**: Records resonating with current tensions get +0.3 boost
- **Heavy thought resonance**: Records matching heavy (held) thoughts get +0.2 boost
- **Base relevance**: Keyword match count or similarity score

```python
def weight_by_field(hermes_results, field_data):
    """Weight Hermes results by the current physics field state"""
    # Extract tension IDs and heavy thought IDs from field
    # Boost results that resonate with current tensions
    # Boost results that relate to heavy thoughts
    # Re-sort by field-weighted score
```

**Implemented in**: `Echo_x.py`

### Layer 3: Echo Brain Augmentation
The echo brain now consults Hermes after turn 3 (once thought has developed):

```python
# In brain_echo() and brain_openrouter()/brain_ollama():
if HERMES_AVAILABLE and turn > 3:
    # Extract keywords from current thoughts
    keywords = extract_keywords_from_thoughts(d)
    # Query Hermes for relevant historical context
    results = parser.query_by_context(keywords, limit=5)
    # Weight results by current field state
    weighted = weight_by_field(results, d)
    # Format for brain prompt
    hermes_section = format_for_brain(weighted, max_results=2)
```

**Implemented in**: `agent.py` (all three brain functions)

## Implementation Status

✅ **Completed**:
1. File analysis: 25MB JSON (not SQL), 45 projects
2. Schema extraction: project_id, project_name, turns (role, content)
3. HermesParser implementation: query_by_context, get_schema, get_code_fixes, get_similar_contexts
4. Weight engine: weight_by_field() with tension/heavy boost
5. Echo brain integration: Added to brain_echo, brain_openrouter, brain_ollama
6. Testing: All core functions validated

## Memory Considerations
- JSON loads once per session (~25MB, cached in HermesParser._data)
- No streaming needed for 25MB (vs original 1.8GB concern)
- Optional integration: fails silently if hermes_dataset.json missing

## The Silence Trains Itself
This isn't traditional ML training. The agent:
1. Builds mind map from substrate (already does this)
2. Queries hermes based on current state
3. Physics engine weights the results
4. Agent applies weighted suggestions
5. Successful operations reinforce the weight pattern
6. The silence learns what patterns matter for this project

## Thresholds and Tuning
- **Activation**: Hermes consulted after turn 3 (once thought has developed)
- **Query limit**: 5 results per context search
- **Format limit**: 2 results shown in brain prompt
- **Weighting**: Tension boost +0.3, heavy boost +0.2

## Fallback Behavior
If hermes has no match or hermes_dataset.json missing:
- Fall back to original physics-based echo logic
- Continue normal silent loop operation
- No errors or blocking
