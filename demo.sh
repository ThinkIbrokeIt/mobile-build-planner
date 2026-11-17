#!/bin/bash
# Demo script for Mobile Build Planner
# Runs a quick test with the echo brain (no API key required)

set -e

echo "=== Mobile Build Planner Demo ==="
echo "This will run the silent loop with a habit tracker seed."
echo "The agent will reason autonomously using the physics-aware echo brain."
echo ""

SEED="a habit tracker that gamifies daily tasks"
PROJECT="demo"

# Clean up any existing demo
rm -rf "projects/$PROJECT"
rm -rf "projects/${PROJECT}__incarnated"

echo "Planting seed: $SEED"
python3 agent.py "$PROJECT" --seed "$SEED" --brain echo --max-turns 25

echo ""
echo "=== Inspecting the reasoning ==="
echo "Thought trail:"
python3 substrate.py "$PROJECT" trail

echo ""
echo "Field state:"
python3 substrate.py "$PROJECT" field

echo ""
echo "=== Verification ==="
if [ -d "projects/${PROJECT}__incarnated" ]; then
    python3 mbp.py verify "${PROJECT}__incarnated"
    echo ""
    echo "Demo complete! Check projects/${PROJECT}__incarnated/ for the output."
else
    echo "No incarnation - the agent didn't reach coherence this run."
    echo "Try running again with more turns: --max-turns 30"
fi
