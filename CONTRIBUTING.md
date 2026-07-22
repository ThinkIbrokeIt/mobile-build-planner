# Contributing to Mobile Build Planner

Thank you for your interest in contributing to Mobile Build Planner. This project explores pre-linguistic reasoning in AI systems through a unique "silent layer" architecture.

## Philosophy

This project is not a conventional build tool. It's an exploration of:
- Pre-linguistic thought and reasoning
- Physics-based self-correction in AI systems
- Anti-hallucination through traceability
- The three-layer model: IDEA → WORD → FLESH

Contributions should respect this philosophical foundation.

## Areas for Contribution

### Code
- Improvements to the physics engine (emergent forces)
- Additional brain implementations (new reasoning models)
- Better substrate operations
- Enhanced forge translation layers

### Documentation
- Clearer explanations of the silent layer theory
- More usage examples
- Performance analysis
- Comparative studies with other approaches

### Examples
- New seed examples that showcase different reasoning patterns
- Domain-specific configurations
- Integration examples with other tools

## Development Setup

```bash
# Install dependencies
pip install pyyaml

# Run tests
python3 agent.py test-demo --seed "test" --brain echo --max-turns 5

# Verify output
python3 substrate.py test-demo trail
python3 mbp.py verify test-demo__incarnated
```

## Submission Guidelines

1. **Respect the silence**: Don't add schema constraints or hardcoded types to the substrate
2. **Keep it pure**: Physics should emerge from operations, not be imposed
3. **Trace everything**: Ensure all outputs trace back to thoughts
4. **Document the why**: Explain changes in terms of the philosophical goals

## Questions?

Open an issue with the "question" label. We're interested in discussions about the underlying theory as much as the implementation.
